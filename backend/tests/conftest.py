"""Test fixtures.

Unit tests use an isolated in-memory database with SYNTHETIC fixtures (mocks are allowed only in tests;
they never reach the application database). Integration tests read the real local database.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app import models  # noqa: F401


@pytest.fixture()
def memdb():
    eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(eng)
    s = sessionmaker(bind=eng)()
    yield s
    s.close()


@pytest.fixture(scope="session")
def realdb():
    from app.db import SessionLocal
    from app.models import CustomsRecord
    s = SessionLocal()
    if s.query(CustomsRecord).count() == 0:
        pytest.skip("real data not ingested yet (run python -m app.pipeline)")
    yield s
    s.close()
