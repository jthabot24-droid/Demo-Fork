"""Tests for the CLI workflow runner."""

import tempfile
from pathlib import Path

from carddemo.runner import run_batch


class TestRunner:
    def test_full_pipeline(self, data_dir):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{tmpdir}/test.db"
            run_batch(
                data_dir=data_dir,
                db_url=db_url,
                steps=("load", "posttran", "intcalc", "statement"),
                parm_date="2024-06-15",
                output_dir=tmpdir,
            )
            assert Path(tmpdir, "statements.txt").exists()
            assert Path(tmpdir, "statements.html").exists()

    def test_load_only(self, data_dir):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{tmpdir}/test.db"
            run_batch(
                data_dir=data_dir,
                db_url=db_url,
                steps=("load",),
            )

    def test_posttran_only_after_load(self, data_dir):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_url = f"sqlite:///{tmpdir}/test.db"
            run_batch(
                data_dir=data_dir,
                db_url=db_url,
                steps=("load", "posttran"),
            )
