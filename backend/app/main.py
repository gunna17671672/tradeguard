"""FastAPI application factory.

`uvicorn app.main:app --reload` serves the API. The default app resolves its
SQLite path from TRADEGUARD_DB and its rules.yaml from TRADEGUARD_RULES (or by
walking up from the cwd), and allows the dev frontend origin via CORS.

The module-level `app` is built lazily (PEP 562) so importing `create_app`
for tests never touches the default database file.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import trades, violations
from app.db import DEFAULT_DB_PATH, init_db, make_engine, make_session_factory
from app.rules.loader import find_rules_file

DEV_FRONTEND_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]


def _default_rules_path() -> Path | None:
    env = os.environ.get("TRADEGUARD_RULES")
    return Path(env) if env else find_rules_file()


def create_app(
    db_path: Path | str = DEFAULT_DB_PATH,
    rules_path: Path | None = None,
    cors_origins: list[str] = DEV_FRONTEND_ORIGINS,
) -> FastAPI:
    engine = make_engine(db_path)
    init_db(engine)

    app = FastAPI(title="TradeGuard", version="0.1.0")
    app.state.session_factory = make_session_factory(engine)
    app.state.rules_path = rules_path if rules_path is not None else _default_rules_path()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(trades.router)
    app.include_router(violations.router)
    return app


def __getattr__(name: str) -> FastAPI:
    if name == "app":
        return create_app()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
