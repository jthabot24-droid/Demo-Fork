"""Shared pytest fixtures for CardDemo tests.

Uses the existing ASCII flat files under ``app/data/ASCII/`` as
golden-master regression fixtures.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from carddemo.models import Base, init_db

REPO_ROOT = Path(__file__).resolve().parents[2]
ASCII_DATA_DIR = REPO_ROOT / "app" / "data" / "ASCII"


@pytest.fixture()
def data_dir() -> Path:
    """Path to the ASCII data directory."""
    assert ASCII_DATA_DIR.exists(), f"Data dir missing: {ASCII_DATA_DIR}"
    return ASCII_DATA_DIR


@pytest.fixture()
def engine():
    """In-memory SQLite engine."""
    eng = create_engine("sqlite:///:memory:", echo=False)
    init_db(eng)
    return eng


@pytest.fixture()
def session(engine) -> Session:
    """Scoped SQLAlchemy session (rolled back after each test)."""
    sess = sessionmaker(bind=engine)()
    yield sess
    sess.rollback()
    sess.close()
