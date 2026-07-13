"""Rules API: read and rewrite rules.yaml.

PUT validates the submitted config before anything is written, then rewrites
the file and re-audits every account so stored violations match the new rules.
The rewrite is a plain YAML dump: hand-written comments in rules.yaml do not
survive a save from the Settings page.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import RulesPathDep, SessionDep
from app.ingest import audit_account
from app.models import Trade
from app.rules import RuleConfigError, available_rules
from app.rules.loader import load_rules_config, parse_rules_config
from app.schemas import RulesFileRead, RulesFileWrite, RulesUpdateResponse

router = APIRouter(prefix="/api/rules", tags=["rules"])


def _require_path(rules_path: Path | None) -> Path:
    if rules_path is None:
        raise HTTPException(
            status_code=409,
            detail="No rules.yaml configured; create one at the repo root "
            "or point TRADEGUARD_RULES at it.",
        )
    return rules_path


def _raw_sections(path: Path) -> tuple[dict[str, object], dict[str, object]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RuleConfigError(f"{path.name}: expected a mapping with 'account' and 'rules' keys")
    account = raw.get("account")
    rules = raw.get("rules") or {}
    return account if isinstance(account, dict) else {}, rules if isinstance(rules, dict) else {}


@router.get("")
def read_rules(rules_path: RulesPathDep) -> RulesFileRead:
    path = _require_path(rules_path)
    if not path.is_file():
        raise RuleConfigError(f"rules file not found: {path}")
    config = load_rules_config(path)  # invalid file -> RuleConfigError -> HTTP 400
    account, rules = _raw_sections(path)
    return RulesFileRead(
        account=account,
        rules=rules,
        enabled_rule_ids=config.enabled_rule_ids(),
        available_rules=available_rules(),
    )


@router.put("")
def write_rules(
    session: SessionDep, rules_path: RulesPathDep, body: RulesFileWrite
) -> RulesUpdateResponse:
    path = _require_path(rules_path)
    raw = {"account": body.account, "rules": body.rules}
    try:
        config = parse_rules_config(raw, source="request body")
    except RuleConfigError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    path.write_text(yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")

    # Stored violations were produced by the old rules; re-audit everything.
    accounts = session.scalars(select(Trade.account_label).distinct()).all()
    violations_recorded = sum(audit_account(session, account, config) for account in accounts)

    return RulesUpdateResponse(
        account=body.account,
        rules=body.rules,
        enabled_rule_ids=config.enabled_rule_ids(),
        available_rules=available_rules(),
        violations_recorded=violations_recorded,
    )
