"""Smoke tests for data models (Phase 0)."""

from __future__ import annotations

from decimal import Decimal

from models.account import AccountRecord
from models.card import CardRecord
from models.card_xref import CardXrefRecord
from models.customer import CustomerRecord
from models.daily_transaction import DailyTransactionRecord
from models.disclosure_group import DisclosureGroupRecord
from models.tran_cat_balance import TranCatBalanceRecord
from models.transaction import TransactionRecord
from models.user_security import UserSecurityRecord


class TestAccountRecord:
    def test_defaults(self):
        rec = AccountRecord()
        assert rec.acct_id == 0
        assert rec.acct_curr_bal == Decimal("0.00")
        assert rec.RECORD_LENGTH == 300

    def test_monetary_precision(self):
        rec = AccountRecord(acct_curr_bal=Decimal("12345.67"))
        assert rec.acct_curr_bal == Decimal("12345.67")


class TestCardRecord:
    def test_defaults(self):
        rec = CardRecord()
        assert rec.card_num == ""
        assert rec.RECORD_LENGTH == 150

    def test_populated(self):
        rec = CardRecord(card_num="4000000000000001", card_acct_id=1, card_cvv_cd=123)
        assert rec.card_num == "4000000000000001"


class TestCustomerRecord:
    def test_defaults(self):
        rec = CustomerRecord()
        assert rec.cust_id == 0
        assert rec.RECORD_LENGTH == 500


class TestCardXrefRecord:
    def test_defaults(self):
        rec = CardXrefRecord()
        assert rec.xref_card_num == ""
        assert rec.RECORD_LENGTH == 50


class TestTransactionRecord:
    def test_defaults(self):
        rec = TransactionRecord()
        assert rec.tran_amt == Decimal("0.00")
        assert rec.RECORD_LENGTH == 350


class TestDailyTransactionRecord:
    def test_defaults(self):
        rec = DailyTransactionRecord()
        assert rec.dalytran_amt == Decimal("0.00")
        assert rec.RECORD_LENGTH == 350


class TestUserSecurityRecord:
    def test_defaults(self):
        rec = UserSecurityRecord()
        assert rec.sec_usr_id == ""
        assert rec.RECORD_LENGTH == 80


class TestTranCatBalanceRecord:
    def test_composite_key(self):
        rec = TranCatBalanceRecord(
            trancat_acct_id=1, trancat_type_cd="01", trancat_cd=1
        )
        expected = f"{1:011d}{'01':2s}{1:04d}"
        assert rec.key == expected

    def test_defaults(self):
        rec = TranCatBalanceRecord()
        assert rec.RECORD_LENGTH == 50


class TestDisclosureGroupRecord:
    def test_composite_key(self):
        rec = DisclosureGroupRecord(
            dis_acct_group_id="A000000000",
            dis_tran_type_cd="01",
            dis_tran_cat_cd=1,
        )
        expected = f"{'A000000000':10s}{'01':2s}{1:04d}"
        assert rec.key == expected

    def test_defaults(self):
        rec = DisclosureGroupRecord()
        assert rec.RECORD_LENGTH == 50
