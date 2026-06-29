"""Tests for CBSTM03A/CBSTM03B (statement generation)."""

import tempfile
from decimal import Decimal
from pathlib import Path

from carddemo.batch.statement import run as stmt_run
from carddemo.etl import (
    load_accounts,
    load_card_xref,
    load_customers,
)
from carddemo.models import Transaction


class TestStatement:
    def _load_base_data(self, session, data_dir):
        load_accounts(session, data_dir / "acctdata.txt")
        load_card_xref(session, data_dir / "cardxref.txt")
        load_customers(session, data_dir / "custdata.txt")
        session.commit()

    def _add_sample_transactions(self, session):
        txns = [
            Transaction(
                tran_id="TX00000000000001",
                tran_type_cd="01",
                tran_cat_cd="0001",
                tran_source="POS TERM",
                tran_desc="Purchase at Store A",
                tran_amt=Decimal("50.00"),
                tran_merchant_id="800000000",
                tran_merchant_name="Store A",
                tran_merchant_city="Seattle",
                tran_merchant_zip="98101",
                tran_card_num="0500024453765740",
                tran_orig_ts="2024-01-15 10:00:00.000000",
                tran_proc_ts="2024-01-15 10:00:01.000000",
            ),
            Transaction(
                tran_id="TX00000000000002",
                tran_type_cd="02",
                tran_cat_cd="0001",
                tran_source="ONLINE",
                tran_desc="Payment received",
                tran_amt=Decimal("-25.00"),
                tran_merchant_id="000000000",
                tran_merchant_name="",
                tran_merchant_city="",
                tran_merchant_zip="",
                tran_card_num="0500024453765740",
                tran_orig_ts="2024-01-16 14:00:00.000000",
                tran_proc_ts="2024-01-16 14:00:01.000000",
            ),
        ]
        for t in txns:
            session.add(t)
        session.commit()

    def test_generates_output_files(self, session, data_dir):
        self._load_base_data(session, data_dir)
        self._add_sample_transactions(session)
        with tempfile.TemporaryDirectory() as tmpdir:
            stmt_path = Path(tmpdir) / "statements.txt"
            html_path = Path(tmpdir) / "statements.html"
            result = stmt_run(session, stmt_path=stmt_path, html_path=html_path)
            assert stmt_path.exists()
            assert html_path.exists()
            assert result.accounts_processed > 0

    def test_text_contains_account_info(self, session, data_dir):
        self._load_base_data(session, data_dir)
        self._add_sample_transactions(session)
        with tempfile.TemporaryDirectory() as tmpdir:
            stmt_path = Path(tmpdir) / "statements.txt"
            html_path = Path(tmpdir) / "statements.html"
            stmt_run(session, stmt_path=stmt_path, html_path=html_path)
            content = stmt_path.read_text()
            assert "START OF STATEMENT" in content
            assert "END OF STATEMENT" in content
            assert "Account ID" in content

    def test_html_is_valid_structure(self, session, data_dir):
        self._load_base_data(session, data_dir)
        self._add_sample_transactions(session)
        with tempfile.TemporaryDirectory() as tmpdir:
            stmt_path = Path(tmpdir) / "statements.txt"
            html_path = Path(tmpdir) / "statements.html"
            stmt_run(session, stmt_path=stmt_path, html_path=html_path)
            content = html_path.read_text()
            assert "<!DOCTYPE html>" in content
            assert "</html>" in content
            assert "Transaction Summary" in content

    def test_no_transactions_still_generates(self, session, data_dir):
        self._load_base_data(session, data_dir)
        with tempfile.TemporaryDirectory() as tmpdir:
            stmt_path = Path(tmpdir) / "statements.txt"
            html_path = Path(tmpdir) / "statements.html"
            result = stmt_run(session, stmt_path=stmt_path, html_path=html_path)
            assert result.accounts_processed > 0
            assert result.transactions_included == 0
