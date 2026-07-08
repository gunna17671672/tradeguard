"""Load and validate rules.yaml into account settings plus rule instances.

Format:

    account:
      account_size: "25000"        # quote money so YAML keeps it exact
      timezone: America/New_York   # optional, this is the default
      r_value: "150"               # optional; needed for R-based params

    rules:
      max_trades_per_day:          # presence enables a rule
        n: 6                       # remaining keys are the rule's params
      stop_required:
        within_minutes: 5
        severity: warn             # reserved key: downgrade from `violation`
      revenge_trade:
        enabled: false             # reserved key: keep params, disable rule
        cooldown_minutes: 15
        size_multiplier: "1.5"

Every problem raises RuleConfigError with a message naming the offending key.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic import ValidationError

from app.models import Severity
from app.rules.engine import AccountSettings, Rule, RuleConfigError, get_rule_class

RESERVED_KEYS = frozenset({"enabled", "severity"})


@dataclass(frozen=True)
class RulesConfig:
    settings: AccountSettings
    rules: list[Rule]

    def enabled_rule_ids(self) -> list[str]:
        return [r.rule_id for r in self.rules]


def load_rules_config(path: Path | str) -> RulesConfig:
    path = Path(path)
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise RuleConfigError(f"rules file not found: {path}") from None
    except yaml.YAMLError as exc:
        raise RuleConfigError(f"{path.name}: not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise RuleConfigError(f"{path.name}: expected a mapping with 'account' and 'rules' keys")
    return parse_rules_config(raw, source=path.name)


def parse_rules_config(raw: dict[str, object], source: str = "rules.yaml") -> RulesConfig:
    unknown_sections = set(raw) - {"account", "rules"}
    if unknown_sections:
        raise RuleConfigError(f"{source}: unknown top-level key(s) {sorted(unknown_sections)}")
    if "account" not in raw:
        raise RuleConfigError(f"{source}: missing required 'account' section")

    account_raw = raw["account"]
    if not isinstance(account_raw, dict):
        raise RuleConfigError(f"{source}: 'account' must be a mapping")
    try:
        settings = AccountSettings(**account_raw)
    except ValidationError as exc:
        raise RuleConfigError(f"{source}: invalid account settings: {exc}") from exc

    rules_raw = raw.get("rules") or {}
    if not isinstance(rules_raw, dict):
        raise RuleConfigError(f"{source}: 'rules' must be a mapping of rule id -> params")

    rules: list[Rule] = []
    for rule_id, body in rules_raw.items():
        body = {} if body is None else body
        if not isinstance(body, dict):
            raise RuleConfigError(f"{source}: rule {rule_id!r} must map to params, not {body!r}")
        if not body.get("enabled", True):
            continue
        severity = _parse_severity(body.get("severity"), rule_id, source)
        params = {k: v for k, v in body.items() if k not in RESERVED_KEYS}
        rule = get_rule_class(rule_id).from_config(params, severity)
        rule.validate_against_settings(settings)
        rules.append(rule)
    return RulesConfig(settings=settings, rules=rules)


def _parse_severity(value: object, rule_id: str, source: str) -> Severity | None:
    if value is None:
        return None
    try:
        return Severity(str(value))
    except ValueError:
        valid = ", ".join(s.value for s in Severity)
        raise RuleConfigError(
            f"{source}: rule {rule_id!r}: invalid severity {value!r} (expected one of {valid})"
        ) from None


def find_rules_file(start: Path | None = None) -> Path | None:
    """Walk from `start` (default cwd) upward looking for rules.yaml."""
    origin = (start or Path.cwd()).resolve()
    for directory in (origin, *origin.parents):
        candidate = directory / "rules.yaml"
        if candidate.is_file():
            return candidate
    return None
