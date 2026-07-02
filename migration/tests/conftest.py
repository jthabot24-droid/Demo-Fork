"""Shared pytest fixtures for migration tests."""

import os
import sys

import pytest

# Ensure migration package is importable from repo root
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture(scope="session")
def spark():
    """Session-scoped local SparkSession for tests."""
    from pyspark.sql import SparkSession
    session = (SparkSession.builder
               .master("local[1]")
               .appName("migration_tests")
               .config("spark.ui.enabled", "false")
               .config("spark.driver.host", "localhost")
               .getOrCreate())
    yield session
    session.stop()


@pytest.fixture
def data_dir():
    """Path to the app/data/ASCII directory."""
    return os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..", "app", "data", "ASCII"))
