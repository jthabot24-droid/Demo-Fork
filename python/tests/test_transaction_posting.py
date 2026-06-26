"""Parity tests for transaction posting (CBTRN02C).

Validates that the Python port correctly:
- Copies daily-transaction fields to a transaction record
- Creates or updates TCATBAL records
- Updates account balances (positive to credit, negative to debit)
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from data.store import InMemoryVsamStore
from models.account import AccountRecord
from models.card_xref import CardXrefRecord
from models.daily_transaction import DailyTransactionRecord
from models.tran_cat_balance import TranCatBalanceRecord
from models.transaction import TransactionRecord
from transaction_posting import (
    build_transaction_from_daily,
    post_daily_transactions,
    update_account,
    update_tran_cat_balance,
)


class TestBuildTransaction:
    """2000-POST-TRANSACTION: field copy from daily tran to transaction."""

    def test_fields_copied(self):
        daily = DailyTransactionRecord(
            dalytran_id="DLY0000000000001",
            dalytran_type_cd="01",
            dalytran_cat_cd=1,
            dalytran_source="ONLINE",
            dalytran_desc="TEST PURCHASE",
            dalytran_amt=Decimal("100.00"),
            dalytran_merchant_id=123456789,
            dalytran_merchant_name="ACME STORE",
            dalytran_merchant_city="NEW YORK",
            dalytran_merchant_zip="10001",
            dalytran_card_num="4000000000000001",
            dalytran_orig_ts="2024-01-15-10.30.00.000000",
        )
        tran = build_transaction_from_daily(daily, "TRN0000000000001")
        assert tran.tran_id == "TRN0000000000001"
        assert tran.tran_type_cd == "01"
        assert tran.tran_cat_cd == 1
        assert tran.tran_amt == Decimal("100.00")
        assert tran.tran_card_num == "4000000000000001"
        assert tran.tran_orig_ts == "2024-01-15-10.30.00.000000"
        assert tran.tran_proc_ts != ""  # auto-generated timestamp


class TestUpdateTranCatBalance:
    """2700-UPDATE-TCATBAL: create or update category balance."""

    def test_create_new_record(self):
        store: InMemoryVsamStore[TranCatBalanceRecord] = InMemoryVsamStore(
            TranCatBalanceRecord, lambda r: r.key
        )
        update_tran_cat_balance(store, acct_id=1, type_cd="01", cat_cd=1,
                                amount=Decimal("500.00"))
        rec = store.read(f"{1:011d}{'01':2s}{1:04d}")
        assert rec is not None
        assert rec.tran_cat_bal == Decimal("500.00")

    def test_update_existing_record(self):
        store: InMemoryVsamStore[TranCatBalanceRecord] = InMemoryVsamStore(
            TranCatBalanceRecord, lambda r: r.key
        )
        store.write(TranCatBalanceRecord(
            trancat_acct_id=1, trancat_type_cd="01", trancat_cd=1,
            tran_cat_bal=Decimal("1000.00"),
        ))
        update_tran_cat_balance(store, acct_id=1, type_cd="01", cat_cd=1,
                                amount=Decimal("250.00"))
        rec = store.read(f"{1:011d}{'01':2s}{1:04d}")
        assert rec.tran_cat_bal == Decimal("1250.00")

    def test_negative_amount(self):
        store: InMemoryVsamStore[TranCatBalanceRecord] = InMemoryVsamStore(
            TranCatBalanceRecord, lambda r: r.key
        )
        store.write(TranCatBalanceRecord(
            trancat_acct_id=1, trancat_type_cd="01", trancat_cd=1,
            tran_cat_bal=Decimal("1000.00"),
        ))
        update_tran_cat_balance(store, acct_id=1, type_cd="01", cat_cd=1,
                                amount=Decimal("-300.00"))
        rec = store.read(f"{1:011d}{'01':2s}{1:04d}")
        assert rec.tran_cat_bal == Decimal("700.00")


class TestUpdateAccount:
    """2800-UPDATE-ACCOUNT-REC: adjust balances."""

    def test_positive_amount_goes_to_credit(self, account_store):
        original = account_store.read(f"{1:011d}")
        orig_bal = original.acct_curr_bal
        orig_credit = original.acct_curr_cyc_credit

        update_account(account_store, acct_id=1, amount=Decimal("200.00"))

        updated = account_store.read(f"{1:011d}")
        assert updated.acct_curr_bal == orig_bal + Decimal("200.00")
        assert updated.acct_curr_cyc_credit == orig_credit + Decimal("200.00")

    def test_negative_amount_goes_to_debit(self, account_store):
        original = account_store.read(f"{1:011d}")
        orig_bal = original.acct_curr_bal
        orig_debit = original.acct_curr_cyc_debit

        update_account(account_store, acct_id=1, amount=Decimal("-50.00"))

        updated = account_store.read(f"{1:011d}")
        assert updated.acct_curr_bal == orig_bal + Decimal("-50.00")
        assert updated.acct_curr_cyc_debit == orig_debit + Decimal("-50.00")


class TestPostDailyTransactions:
    """End-to-end posting of daily transactions."""

    def test_valid_transaction_posted(
        self, daily_store, xref_store, account_store, tcatbal_store, transaction_store
    ):
        result = post_daily_transactions(
            daily_store, xref_store, account_store, tcatbal_store, transaction_store
        )
        assert result.transactions_posted == 1
        assert result.transactions_rejected == 0
        assert len(transaction_store) == 1

    def test_account_updated_after_post(
        self, daily_store, xref_store, account_store, tcatbal_store, transaction_store
    ):
        orig_bal = account_store.read(f"{1:011d}").acct_curr_bal
        post_daily_transactions(
            daily_store, xref_store, account_store, tcatbal_store, transaction_store
        )
        updated = account_store.read(f"{1:011d}")
        assert updated.acct_curr_bal == orig_bal + Decimal("100.00")

    def test_tcatbal_updated_after_post(
        self, daily_store, xref_store, account_store, tcatbal_store, transaction_store
    ):
        orig_key = f"{1:011d}{'01':2s}{1:04d}"
        orig_bal = tcatbal_store.read(orig_key).tran_cat_bal

        post_daily_transactions(
            daily_store, xref_store, account_store, tcatbal_store, transaction_store
        )

        updated = tcatbal_store.read(orig_key)
        assert updated.tran_cat_bal == orig_bal + Decimal("100.00")

    def test_invalid_card_rejected(
        self, xref_store, account_store, tcatbal_store, transaction_store
    ):
        bad_daily: InMemoryVsamStore[DailyTransactionRecord] = InMemoryVsamStore(
            DailyTransactionRecord, lambda r: r.dalytran_id
        )
        bad_daily.write(DailyTransactionRecord(
            dalytran_id="DLY_BAD_0000001",
            dalytran_type_cd="01",
            dalytran_cat_cd=1,
            dalytran_source="ONLINE",
            dalytran_desc="BAD CARD",
            dalytran_amt=Decimal("50.00"),
            dalytran_card_num="9999999999999999",
            dalytran_orig_ts="2024-01-15-10.30.00.000000",
        ))

        result = post_daily_transactions(
            bad_daily, xref_store, account_store, tcatbal_store, transaction_store
        )
        assert result.transactions_rejected == 1
        assert result.transactions_posted == 0
        assert len(result.rejected) == 1
        assert result.rejected[0][1].errors[0].code == 100

    def test_new_tcatbal_created_if_missing(
        self, xref_store, account_store, transaction_store
    ):
        """If no TCATBAL record exists for the type/cat, one is created."""
        empty_tcatbal: InMemoryVsamStore[TranCatBalanceRecord] = InMemoryVsamStore(
            TranCatBalanceRecord, lambda r: r.key
        )
        daily: InMemoryVsamStore[DailyTransactionRecord] = InMemoryVsamStore(
            DailyTransactionRecord, lambda r: r.dalytran_id
        )
        daily.write(DailyTransactionRecord(
            dalytran_id="DLY0000000000099",
            dalytran_type_cd="03",
            dalytran_cat_cd=5,
            dalytran_source="ONLINE",
            dalytran_desc="NEW CATEGORY",
            dalytran_amt=Decimal("75.00"),
            dalytran_card_num="4000000000000001",
            dalytran_orig_ts="2024-01-15-10.30.00.000000",
        ))

        post_daily_transactions(
            daily, xref_store, account_store, empty_tcatbal, transaction_store
        )

        key = f"{1:011d}{'03':2s}{5:04d}"
        rec = empty_tcatbal.read(key)
        assert rec is not None
        assert rec.tran_cat_bal == Decimal("75.00")
