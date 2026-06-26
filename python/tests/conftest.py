"""Shared fixtures for the CardDemo test suite."""

from __future__ import annotations

from pathlib import Path

import pytest

# Resolve the repo root relative to this file's location.
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ASCII_DATA_DIR = _REPO_ROOT / "app" / "data" / "ASCII"


@pytest.fixture()
def ascii_data_dir() -> Path:
    """Path to ``app/data/ASCII/``."""
    return ASCII_DATA_DIR
