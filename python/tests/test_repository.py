"""Tests for Phase 2 Repository data-access layer."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from carddemo.data.repository import (
    AccountRepository,
    CardXrefRepository,
    CustomerRepository,
    DailyTransactionRepository,
)
from carddemo.models.account import AccountRecord
from carddemo.models.card_xref import CardXrefRecord
from carddemo.models.customer import CustomerRecord


class TestAccountRepository:
    def test_load_and_count(self, ascii_data_dir: Path) -> None:
        repo = AccountRepository()
        df = repo.load(ascii_data_dir / "acctdata.txt")
        assert len(repo) == 50
        assert len(df) == 50
        assert "acct_id" in df.columns

    def test_get_by_key(self, ascii_data_dir: Path) -> None:
        repo = AccountRepository()
        repo.load(ascii_data_dir / "acctdata.txt")
        rec = repo.get(1)
        assert rec is not None
        assert isinstance(rec, AccountRecord)
        assert rec.acct_id == 1
        assert rec.acct_active_status == "Y"
        assert rec.acct_curr_bal == Decimal("194.00")

    def test_get_nonexistent(self, ascii_data_dir: Path) -> None:
        repo = AccountRepository()
        repo.load(ascii_data_dir / "acctdata.txt")
        assert repo.get(99999999999) is None

    def test_iterate(self, ascii_data_dir: Path) -> None:
        repo = AccountRepository()
        repo.load(ascii_data_dir / "acctdata.txt")
        records = list(repo.iterate())
        assert len(records) == 50
        assert records[0].acct_id == 1


class TestCardXrefRepository:
    def test_load_and_count(self, ascii_data_dir: Path) -> None:
        repo = CardXrefRepository()
        df = repo.load(ascii_data_dir / "cardxref.txt")
        assert len(repo) == 50
        assert "xref_card_num" in df.columns

    def test_get_by_primary_key(self, ascii_data_dir: Path) -> None:
        repo = CardXrefRepository()
        repo.load(ascii_data_dir / "cardxref.txt")
        # Get first record's card number for lookup
        first = list(repo.iterate())[0]
        found = repo.get(first.xref_card_num)
        assert found is not None
        assert found.xref_card_num == first.xref_card_num

    def test_get_by_alt_key(self, ascii_data_dir: Path) -> None:
        repo = CardXrefRepository()
        repo.load(ascii_data_dir / "cardxref.txt")
        first = list(repo.iterate())[0]
        found = repo.get_by_alt_key("xref_acct_id", first.xref_acct_id)
        assert found is not None
        assert found.xref_acct_id == first.xref_acct_id


class TestCustomerRepository:
    def test_load_and_count(self, ascii_data_dir: Path) -> None:
        repo = CustomerRepository()
        df = repo.load(ascii_data_dir / "custdata.txt")
        assert len(repo) == 50
        assert "cust_id" in df.columns

    def test_get_by_key(self, ascii_data_dir: Path) -> None:
        repo = CustomerRepository()
        repo.load(ascii_data_dir / "custdata.txt")
        rec = repo.get(1)
        assert rec is not None
        assert isinstance(rec, CustomerRecord)
        assert rec.cust_id == 1


class TestDailyTransactionRepository:
    def test_load_and_count(self, ascii_data_dir: Path) -> None:
        repo = DailyTransactionRepository()
        df = repo.load(ascii_data_dir / "dailytran.txt")
        assert len(repo) == 300
        assert "dalytran_id" in df.columns

    def test_iterate_sequential(self, ascii_data_dir: Path) -> None:
        repo = DailyTransactionRepository()
        repo.load(ascii_data_dir / "dailytran.txt")
        records = list(repo.iterate())
        assert len(records) == 300
        assert isinstance(records[0].dalytran_amt, Decimal)


class TestDataFrameAccess:
    """Verify the DataFrame returned by load() is usable for pandas-based
    lookups, matching the convention used by transaction_validation.py."""

    def test_xref_dataframe_for_validation(self, ascii_data_dir: Path) -> None:
        repo = CardXrefRepository()
        df = repo.load(ascii_data_dir / "cardxref.txt")
        # Should be usable for the validation code's DataFrame lookups
        assert "xref_card_num" in df.columns
        assert "xref_acct_id" in df.columns
        assert "xref_cust_id" in df.columns
        assert len(df) > 0

    def test_account_dataframe_for_validation(self, ascii_data_dir: Path) -> None:
        repo = AccountRepository()
        df = repo.load(ascii_data_dir / "acctdata.txt")
        assert "acct_id" in df.columns
        assert "acct_credit_limit" in df.columns
        assert "acct_curr_cyc_credit" in df.columns
        assert "acct_curr_cyc_debit" in df.columns
        assert "acct_expiration_date" in df.columns
