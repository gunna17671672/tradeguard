"""Database setup: engine/session factories and custom column types.

SQLite has no native DECIMAL or timezone-aware datetime storage, so money is
stored as TEXT (exact) and timestamps as naive UTC, converted at the boundary.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import String, create_engine
from sqlalchemy.engine import Dialect, Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.types import DateTime, TypeDecorator

# Anchor the default DB next to the backend package so every launch directory
# (uvicorn from backend/, the CLI from the repo root, ...) hits the same file.
_BACKEND_DIR = Path(__file__).resolve().parent.parent


def default_db_path() -> Path:
    """Fully resolved default SQLite path, independent of the launch directory.

    TRADEGUARD_DB wins when set (a relative value resolves against the cwd,
    since it was given explicitly); otherwise backend/tradeguard.db.
    """
    env = os.environ.get("TRADEGUARD_DB")
    if env:
        return Path(env).resolve()
    return _BACKEND_DIR / "tradeguard.db"


class Money(TypeDecorator[Decimal]):
    """Decimal stored as TEXT so SQLite never coerces money to float."""

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value: Decimal | None, dialect: Dialect) -> str | None:
        if value is None:
            return None
        if isinstance(value, float):
            raise TypeError("Money columns must be Decimal, never float")
        return str(Decimal(value))

    def process_result_value(self, value: str | None, dialect: Dialect) -> Decimal | None:
        return None if value is None else Decimal(value)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware UTC datetimes stored naive, returned aware."""

    impl = DateTime()
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("timestamps must be timezone-aware (UTC)")
        return value.astimezone(UTC).replace(tzinfo=None)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        return None if value is None else value.replace(tzinfo=UTC)


def make_engine(db_path: Path | str | None = None) -> Engine:
    return create_engine(f"sqlite:///{db_path if db_path is not None else default_db_path()}")


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    from app import models

    models.Base.metadata.create_all(engine)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
