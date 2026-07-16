"""FastAPI application factory.

`uvicorn app.main:app --reload` serves the API. The default app resolves its
SQLite path from TRADEGUARD_DB (falling back to the canonical
backend/tradeguard.db — never the launch directory) and its rules.yaml from
TRADEGUARD_RULES (or by walking up from the cwd), and allows the dev frontend
origin via CORS. The resolved DB path is logged at startup and reported by
GET /api/health.

The module-level `app` is built lazily (PEP 562) so importing `create_app`
for tests never touches the default database file.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import imports, reports, rules, stats, trades, violations
from app.db import default_db_path, init_db, make_engine, make_session_factory
from app.rules import RuleConfigError
from app.rules.loader import bootstrap_rules_file, find_rules_file
from app.schemas import HealthRead

DEV_FRONTEND_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]

logger = logging.getLogger("tradeguard")


def _default_rules_path() -> Path | None:
    env = os.environ.get("TRADEGUARD_RULES")
    if env:
        return Path(env)
    # First run: no live rules.yaml yet — create it from the shipped template.
    return find_rules_file() or bootstrap_rules_file()


def create_app(
    db_path: Path | str | None = None,
    rules_path: Path | None = None,
    cors_origins: list[str] = DEV_FRONTEND_ORIGINS,
) -> FastAPI:
    resolved_db = Path(db_path).resolve() if db_path is not None else default_db_path()
    logger.info("SQLite database: %s", resolved_db)
    engine = make_engine(resolved_db)
    init_db(engine)

    app = FastAPI(title="TradeGuard", version="0.1.0")
    app.state.db_path = resolved_db
    app.state.session_factory = make_session_factory(engine)
    app.state.rules_path = rules_path if rules_path is not None else _default_rules_path()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> HealthRead:
        rules = app.state.rules_path
        return HealthRead(
            status="ok",
            db_path=str(resolved_db),
            rules_path=None if rules is None else str(rules),
        )

    @app.exception_handler(RuleConfigError)
    def rule_config_error(request: Request, exc: RuleConfigError) -> JSONResponse:
        # A broken user-edited rules.yaml is a client-fixable problem, not a 500.
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.include_router(imports.router)
    app.include_router(trades.router)
    app.include_router(violations.router)
    app.include_router(stats.router)
    app.include_router(rules.router)
    app.include_router(reports.router)
    return app


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        # uvicorn configures only its own loggers; give ours a handler so the
        # resolved-DB-path startup line reaches the console.
        logging.basicConfig(level=logging.INFO, format="%(levelname)s:     %(message)s")
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
