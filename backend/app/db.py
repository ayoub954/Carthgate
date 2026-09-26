"""Database engine/session — a single store containing real data only (no demonstration data)."""
from __future__ import annotations

from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import settings


class Base(DeclarativeBase):
    pass


def _engine(url: str):
    sqlite = url.startswith("sqlite")
    return create_engine(url, future=True, pool_pre_ping=True,
                         connect_args={"check_same_thread": False, "timeout": 30} if sqlite else {})


engine = _engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def session_for(mode: str | None = None) -> Session:
    """Kept for backward compatibility with older call sites: there is only one (real) store."""
    return SessionLocal()


def db_backend() -> str:
    return "sqlite" if engine.url.get_backend_name() == "sqlite" else engine.dialect.name


def _migrate(e) -> None:
    """Add columns introduced after the first release (idempotent)."""
    insp = inspect(e)
    for table in Base.metadata.sorted_tables:
        if not insp.has_table(table.name):
            continue
        existing = {c["name"] for c in insp.get_columns(table.name)}
        for col in table.columns:
            if col.name not in existing:
                ddl = col.type.compile(dialect=e.dialect)
                with e.begin() as c:
                    c.execute(text(f'ALTER TABLE {table.name} ADD COLUMN {col.name} {ddl}'))


def init_db() -> None:
    from . import models  # noqa: F401  (register tables)

    Base.metadata.create_all(engine)
    _migrate(engine)


@contextmanager
def session_scope(mode: str | None = None):
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()
