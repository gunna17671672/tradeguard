"""FastAPI dependencies: per-request DB session and rules.yaml access."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import session_scope
from app.rules.loader import RulesConfig, load_rules_config


def get_session(request: Request) -> Iterator[Session]:
    """One DB session per request; commits on success, rolls back on error."""
    with session_scope(request.app.state.session_factory) as session:
        yield session


def get_rules_path(request: Request) -> Path | None:
    return request.app.state.rules_path


def get_rules_config(request: Request) -> RulesConfig | None:
    """Parsed rules.yaml, or None when no rules file is configured.

    Re-read per request: the file is user-edited (Settings page, text editor)
    and cheap to parse, so staleness beats caching here.
    """
    path: Path | None = request.app.state.rules_path
    if path is None or not path.is_file():
        return None
    return load_rules_config(path)


def require_rules_config(request: Request) -> RulesConfig:
    config = get_rules_config(request)
    if config is None:
        raise HTTPException(
            status_code=409,
            detail="No rules.yaml configured; create one at the repo root "
            "or point TRADEGUARD_RULES at it.",
        )
    return config


SessionDep = Annotated[Session, Depends(get_session)]
RulesPathDep = Annotated[Path | None, Depends(get_rules_path)]
RulesConfigDep = Annotated[RulesConfig | None, Depends(get_rules_config)]
RequiredRulesConfigDep = Annotated[RulesConfig, Depends(require_rules_config)]
