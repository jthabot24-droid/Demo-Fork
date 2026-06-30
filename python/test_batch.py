"""Tests for the carddemo.batch package.

Covers:
* CBACT04C interest calculation (run_interest_calculation)
* CBTRN02C transaction posting (run_post_daily_transactions)

Asserts byte-exact monetary results and identical error codes/ordering
versus the documented COBOL behavior.
"""

from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest

from carddemo.batch.interest_calc import (
    InterestCalcResult,
    run_interest_calculation,
    _db2_format_timestamp,
)
from carddemo.batch.post_transactions import (
    PostTransactionsResult,
    run_post_daily_transactions,
)
from carddemo.dataaccess import (
    InMemoryAccountRepository,
    InMemoryCardXrefRepository,
    InMemoryDisclosureGroupRepository,
    InMemoryTranCatBalRepository,
    InMemoryTransactionRepository,
)
from carddemo.models import (
    AccountRecord,
    DailyTransactionRecord,
    DisclosureGroupRecord,
    TranCatBalRecord,
    TransactionRecord,
)


# ===================================================================
# Fixtures
# ===================================================================


@pytest.fixture()
def account_repo():
    df = pd.DataFrame([
        {
            "acct_id": 80000000001,
            "acct_active_status": "Y",
            "acct_curr_bal": Decimal("1500.00"),
            "acct_credit_limit": Decimal("5000.00"),
            "acct_cash_credit_limit": Decimal("1000.00"),
            "acct_open_date": "2020-01-15",
            "acct_expiration_date": "2027-12-31",
            "acct_reissue_date": "",
            "acct_curr_cyc_credit": Decimal("500.00"),
            "acct_curr_cyc_debit": Decimal("100.00"),
            "acct_addr_zip": "98101",
            "acct_group_id": "GROUP01",
        },
        {
            "acct_id": 80000000002,
            "acct_active_status": "Y",
            "acct_curr_bal": Decimal("2000.00"),
            "acct_credit_limit": Decimal("10000.00"),
            "acct_cash_credit_limit": Decimal("2000.00"),
            "acct_open_date": "2019-06-01",
            "acct_expiration_date": "2028-06-30",
            "acct_reissue_date": "",
            "acct_curr_cyc_credit": Decimal("300.00"),
            "acct_curr_cyc_debit": Decimal("50.00"),
            "acct_addr_zip": "10001",
            "acct_group_id": "GROUP02",
        },
    ])
    return InMemoryAccountRepository(df)


@pytest.fixture()
def xref_repo():
    df = pd.DataFrame([
        {"xref_card_num": "4111111111111111", "xref_cust_id": 100000001, "xref_acct_id": 80000000001},
        {"xref_card_num": "4222222222222222", "xref_cust_id": 100000002, "xref_acct_id": 80000000002},
    ])
    return InMemoryCardXrefRepository(df)


@pytest.fixture()
def discgrp_repo():
    df = pd.DataFrame([
        {"dis_acct_group_id": "GROUP01", "dis_tran_type_cd": "01", "dis_tran_cat_cd": 5000, "dis_int_rate": Decimal("18.00")},
        {"dis_acct_group_id": "GROUP02", "dis_tran_type_cd": "01", "dis_tran_cat_cd": 5000, "dis_int_rate": Decimal("12.00")},
        {"dis_acct_group_id": "DEFAULT", "dis_tran_type_cd": "02", "dis_tran_cat_cd": 3000, "dis_int_rate": Decimal("24.00")},
    ])
    return InMemoryDisclosureGroupRepository(df)


@pytest.fixture()
def tcatbal_repo():
    df = pd.DataFrame([
        {"trancat_acct_id": 80000000001, "trancat_type_cd": "01", "trancat_cd": 5000, "tran_cat_bal": Decimal("5000.00")},
        {"trancat_acct_id": 80000000002, "trancat_type_cd": "01", "trancat_cd": 5000, "tran_cat_bal": Decimal("3000.00")},
    ])
    return InMemoryTranCatBalRepository(df)


@pytest.fixture()
def transaction_repo():
    return InMemoryTransactionRepository()


FIXED_TS = datetime(2026, 6, 30, 12, 0, 0)


# ===================================================================
# DB2 timestamp format
# ===================================================================


class TestDB2Timestamp:
    def test_format(self):
        ts = _db2_format_timestamp(datetime(2026, 6, 30, 14, 25, 30, 120000))
        assert ts == "2026-06-30-14.25.30.120000"

    def test_format_zero_microseconds(self):
        ts = _db2_format_timestamp(datetime(2026, 1, 1, 0, 0, 0, 0))
        assert ts == "2026-01-01-00.00.00.000000"

    def test_length_is_26(self):
        ts = _db2_format_timestamp(FIXED_TS)
        assert len(ts) == 26


# ===================================================================
# Interest Calculation (CBACT04C)
# ===================================================================


class TestInterestCalcBasic:
    """Basic interest calculation scenarios."""

    def test_single_account_single_category(
        self, account_repo, xref_repo, discgrp_repo, transaction_repo,
    ):
        """One account, one category balance → one interest transaction."""
        tcatbal = InMemoryTranCatBalRepository(pd.DataFrame([
            {"trancat_acct_id": 80000000001, "trancat_type_cd": "01", "trancat_cd": 5000, "tran_cat_bal": Decimal("5000.00")},
        ]))

        result = run_interest_calculation(
            tcatbal_repo=tcatbal,
            xref_repo=xref_repo,
            discgrp_repo=discgrp_repo,
            account_repo=account_repo,
            transaction_repo=transaction_repo,
            parm_date="2026-06-30",
            timestamp_provider=FIXED_TS,
        )

        assert result.records_processed == 1
        assert result.transactions_written == 1
        assert result.accounts_updated == 1

        # Verify interest: 5000.00 * 18.00 / 1200 = 75.00
        tran = transaction_repo.find_by_id("2026-06-30000001")
        assert tran is not None
        assert tran.tran_amt == Decimal("75.00")
        assert tran.tran_type_cd == "01"
        assert tran.tran_cat_cd == 5
        assert tran.tran_source == "System"
        assert tran.tran_desc == "Int. for a/c 80000000001"
        assert tran.tran_card_num == "4111111111111111"

    def test_account_balance_updated(
        self, account_repo, xref_repo, discgrp_repo, transaction_repo,
    ):
        """After interest calc, account balance should include interest."""
        tcatbal = InMemoryTranCatBalRepository(pd.DataFrame([
            {"trancat_acct_id": 80000000001, "trancat_type_cd": "01", "trancat_cd": 5000, "tran_cat_bal": Decimal("5000.00")},
        ]))

        run_interest_calculation(
            tcatbal_repo=tcatbal,
            xref_repo=xref_repo,
            discgrp_repo=discgrp_repo,
            account_repo=account_repo,
            transaction_repo=transaction_repo,
            parm_date="2026-06-30",
            timestamp_provider=FIXED_TS,
        )

        acct = account_repo.find_by_id(80000000001)
        # Original: 1500.00, interest: 75.00 → 1575.00
        assert acct.acct_curr_bal == Decimal("1575.00")
        # Cycle accumulators reset to 0
        assert acct.acct_curr_cyc_credit == Decimal("0")
        assert acct.acct_curr_cyc_debit == Decimal("0")


class TestInterestCalcMultipleAccounts:
    """Multiple accounts / categories."""

    def test_two_accounts(
        self, account_repo, xref_repo, discgrp_repo, transaction_repo, tcatbal_repo,
    ):
        result = run_interest_calculation(
            tcatbal_repo=tcatbal_repo,
            xref_repo=xref_repo,
            discgrp_repo=discgrp_repo,
            account_repo=account_repo,
            transaction_repo=transaction_repo,
            parm_date="2026-06-30",
            timestamp_provider=FIXED_TS,
        )

        assert result.records_processed == 2
        assert result.transactions_written == 2
        assert result.accounts_updated == 2

        # Acct 1: 5000 * 18 / 1200 = 75
        t1 = transaction_repo.find_by_id("2026-06-30000001")
        assert t1.tran_amt == Decimal("75.00")

        # Acct 2: 3000 * 12 / 1200 = 30
        t2 = transaction_repo.find_by_id("2026-06-30000002")
        assert t2.tran_amt == Decimal("30.00")

    def test_multiple_categories_same_account(
        self, account_repo, xref_repo, discgrp_repo, transaction_repo,
    ):
        """Two category balances for the same account → two interest txns,
        total interest added to account balance."""
        tcatbal = InMemoryTranCatBalRepository(pd.DataFrame([
            {"trancat_acct_id": 80000000001, "trancat_type_cd": "01", "trancat_cd": 5000, "tran_cat_bal": Decimal("5000.00")},
            {"trancat_acct_id": 80000000001, "trancat_type_cd": "02", "trancat_cd": 3000, "tran_cat_bal": Decimal("2000.00")},
        ]))

        # Group01/02/3000 not defined; DEFAULT/02/3000 exists (rate=24.00)
        result = run_interest_calculation(
            tcatbal_repo=tcatbal,
            xref_repo=xref_repo,
            discgrp_repo=discgrp_repo,
            account_repo=account_repo,
            transaction_repo=transaction_repo,
            parm_date="2026-06-30",
            timestamp_provider=FIXED_TS,
        )

        assert result.records_processed == 2
        assert result.transactions_written == 2

        # Int1: 5000 * 18 / 1200 = 75.00
        # Int2: 2000 * 24 / 1200 = 40.00
        # Total: 115.00, added to 1500.00 → 1615.00
        acct = account_repo.find_by_id(80000000001)
        assert acct.acct_curr_bal == Decimal("1615.00")


class TestInterestCalcDefaultRate:
    """Fallback to DEFAULT disclosure group."""

    def test_default_group_fallback(
        self, account_repo, xref_repo, transaction_repo,
    ):
        """When account's group is not found, use DEFAULT."""
        tcatbal = InMemoryTranCatBalRepository(pd.DataFrame([
            {"trancat_acct_id": 80000000001, "trancat_type_cd": "02", "trancat_cd": 3000, "tran_cat_bal": Decimal("1200.00")},
        ]))
        discgrp = InMemoryDisclosureGroupRepository(pd.DataFrame([
            {"dis_acct_group_id": "DEFAULT", "dis_tran_type_cd": "02", "dis_tran_cat_cd": 3000, "dis_int_rate": Decimal("24.00")},
        ]))

        result = run_interest_calculation(
            tcatbal_repo=tcatbal,
            xref_repo=xref_repo,
            discgrp_repo=discgrp,
            account_repo=account_repo,
            transaction_repo=transaction_repo,
            parm_date="2026-06-30",
            timestamp_provider=FIXED_TS,
        )

        # 1200 * 24 / 1200 = 24.00
        t = transaction_repo.find_by_id("2026-06-30000001")
        assert t.tran_amt == Decimal("24.00")


class TestInterestCalcZeroRate:
    """When interest rate is 0, no transaction should be written."""

    def test_zero_rate_skips_transaction(
        self, account_repo, xref_repo, transaction_repo,
    ):
        tcatbal = InMemoryTranCatBalRepository(pd.DataFrame([
            {"trancat_acct_id": 80000000001, "trancat_type_cd": "01", "trancat_cd": 5000, "tran_cat_bal": Decimal("5000.00")},
        ]))
        discgrp = InMemoryDisclosureGroupRepository(pd.DataFrame([
            {"dis_acct_group_id": "GROUP01", "dis_tran_type_cd": "01", "dis_tran_cat_cd": 5000, "dis_int_rate": Decimal("0.00")},
        ]))

        result = run_interest_calculation(
            tcatbal_repo=tcatbal,
            xref_repo=xref_repo,
            discgrp_repo=discgrp,
            account_repo=account_repo,
            transaction_repo=transaction_repo,
            parm_date="2026-06-30",
            timestamp_provider=FIXED_TS,
        )

        assert result.records_processed == 1
        assert result.transactions_written == 0


class TestInterestCalcNoRecords:
    """Empty tcatbal file → no processing."""

    def test_empty_tcatbal(
        self, account_repo, xref_repo, discgrp_repo, transaction_repo,
    ):
        tcatbal = InMemoryTranCatBalRepository()
        result = run_interest_calculation(
            tcatbal_repo=tcatbal,
            xref_repo=xref_repo,
            discgrp_repo=discgrp_repo,
            account_repo=account_repo,
            transaction_repo=transaction_repo,
            parm_date="2026-06-30",
        )
        assert result.records_processed == 0
        assert result.accounts_updated == 0


class TestInterestCalcTransactionIdFormat:
    """Verify TRAN-ID = PARM-DATE (10) + suffix (6) = 16 chars."""

    def test_tran_id_format(
        self, account_repo, xref_repo, discgrp_repo, transaction_repo,
    ):
        tcatbal = InMemoryTranCatBalRepository(pd.DataFrame([
            {"trancat_acct_id": 80000000001, "trancat_type_cd": "01", "trancat_cd": 5000, "tran_cat_bal": Decimal("100.00")},
        ]))

        run_interest_calculation(
            tcatbal_repo=tcatbal,
            xref_repo=xref_repo,
            discgrp_repo=discgrp_repo,
            account_repo=account_repo,
            transaction_repo=transaction_repo,
            parm_date="2026-06-30",
            timestamp_provider=FIXED_TS,
        )

        tran = transaction_repo.find_by_id("2026-06-30000001")
        assert tran is not None
        assert len(tran.tran_id) == 16


class TestInterestCalcByteExact:
    """Byte-exact monetary results for precision-critical scenarios."""

    def test_fractional_interest(
        self, account_repo, xref_repo, transaction_repo,
    ):
        """1234.56 * 21.99 / 1200 → exact Decimal result."""
        tcatbal = InMemoryTranCatBalRepository(pd.DataFrame([
            {"trancat_acct_id": 80000000001, "trancat_type_cd": "01", "trancat_cd": 5000, "tran_cat_bal": Decimal("1234.56")},
        ]))
        discgrp = InMemoryDisclosureGroupRepository(pd.DataFrame([
            {"dis_acct_group_id": "GROUP01", "dis_tran_type_cd": "01", "dis_tran_cat_cd": 5000, "dis_int_rate": Decimal("21.99")},
        ]))

        run_interest_calculation(
            tcatbal_repo=tcatbal,
            xref_repo=xref_repo,
            discgrp_repo=discgrp,
            account_repo=account_repo,
            transaction_repo=transaction_repo,
            parm_date="2026-06-30",
            timestamp_provider=FIXED_TS,
        )

        expected = (Decimal("1234.56") * Decimal("21.99")) / Decimal("1200")
        tran = transaction_repo.find_by_id("2026-06-30000001")
        assert tran.tran_amt == expected


# ===================================================================
# Post Daily Transactions (CBTRN02C)
# ===================================================================


class TestPostTransactionsBasic:
    """Basic posting scenarios."""

    def test_valid_transaction_posted(
        self, account_repo, xref_repo, transaction_repo,
    ):
        tcatbal = InMemoryTranCatBalRepository()
        tran = DailyTransactionRecord(
            dalytran_id="0000000000000001",
            dalytran_type_cd="01",
            dalytran_cat_cd=5000,
            dalytran_source="BATCH",
            dalytran_desc="Daily purchase",
            dalytran_amt=Decimal("100.00"),
            dalytran_merchant_id=123456789,
            dalytran_merchant_name="Acme Corp",
            dalytran_merchant_city="Seattle",
            dalytran_merchant_zip="98101",
            dalytran_card_num="4111111111111111",
            dalytran_orig_ts="2026-06-15-00.00.00.000000",
            dalytran_proc_ts="2026-06-15-00.00.00.000000",
        )

        result = run_post_daily_transactions(
            daily_transactions=[tran],
            xref_repo=xref_repo,
            account_repo=account_repo,
            tcatbal_repo=tcatbal,
            transaction_repo=transaction_repo,
            timestamp_provider=FIXED_TS,
        )

        assert result.transactions_processed == 1
        assert result.transactions_posted == 1
        assert result.transactions_rejected == 0
        assert result.return_code == 0

        # Transaction written to master
        posted = transaction_repo.find_by_id("0000000000000001")
        assert posted is not None
        assert posted.tran_amt == Decimal("100.00")

    def test_invalid_card_rejected(self, account_repo, xref_repo, transaction_repo):
        tcatbal = InMemoryTranCatBalRepository()
        tran = DailyTransactionRecord(
            dalytran_id="0000000000000002",
            dalytran_card_num="0000000000000000",
            dalytran_amt=Decimal("50.00"),
            dalytran_orig_ts="2026-06-15-00.00.00.000000",
        )

        result = run_post_daily_transactions(
            daily_transactions=[tran],
            xref_repo=xref_repo,
            account_repo=account_repo,
            tcatbal_repo=tcatbal,
            transaction_repo=transaction_repo,
        )

        assert result.transactions_rejected == 1
        assert result.return_code == 4
        assert result.rejected[0].fail_reason == 100
        assert result.rejected[0].fail_reason_desc == "INVALID CARD NUMBER FOUND"


class TestPostTransactionsAccountUpdate:
    """2800-UPDATE-ACCOUNT-REC: balance updates on posting."""

    def test_positive_amount_adds_to_credit(
        self, account_repo, xref_repo, transaction_repo,
    ):
        tcatbal = InMemoryTranCatBalRepository()
        tran = DailyTransactionRecord(
            dalytran_id="0000000000000001",
            dalytran_type_cd="01",
            dalytran_cat_cd=5000,
            dalytran_source="BATCH",
            dalytran_desc="Credit",
            dalytran_amt=Decimal("200.00"),
            dalytran_card_num="4111111111111111",
            dalytran_orig_ts="2026-06-15-00.00.00.000000",
            dalytran_proc_ts="2026-06-15-00.00.00.000000",
        )

        run_post_daily_transactions(
            daily_transactions=[tran],
            xref_repo=xref_repo,
            account_repo=account_repo,
            tcatbal_repo=tcatbal,
            transaction_repo=transaction_repo,
            timestamp_provider=FIXED_TS,
        )

        acct = account_repo.find_by_id(80000000001)
        # curr_bal: 1500 + 200 = 1700
        assert acct.acct_curr_bal == Decimal("1700.00")
        # curr_cyc_credit: 500 + 200 = 700
        assert acct.acct_curr_cyc_credit == Decimal("700.00")

    def test_negative_amount_adds_to_debit(
        self, account_repo, xref_repo, transaction_repo,
    ):
        tcatbal = InMemoryTranCatBalRepository()
        tran = DailyTransactionRecord(
            dalytran_id="0000000000000001",
            dalytran_type_cd="01",
            dalytran_cat_cd=5000,
            dalytran_source="BATCH",
            dalytran_desc="Debit",
            dalytran_amt=Decimal("-50.00"),
            dalytran_card_num="4111111111111111",
            dalytran_orig_ts="2026-06-15-00.00.00.000000",
            dalytran_proc_ts="2026-06-15-00.00.00.000000",
        )

        run_post_daily_transactions(
            daily_transactions=[tran],
            xref_repo=xref_repo,
            account_repo=account_repo,
            tcatbal_repo=tcatbal,
            transaction_repo=transaction_repo,
            timestamp_provider=FIXED_TS,
        )

        acct = account_repo.find_by_id(80000000001)
        # curr_bal: 1500 + (-50) = 1450
        assert acct.acct_curr_bal == Decimal("1450.00")
        # curr_cyc_debit: 100 + (-50) = 50
        assert acct.acct_curr_cyc_debit == Decimal("50.00")


class TestPostTransactionsTcatbal:
    """2700-UPDATE-TCATBAL: category balance create/update."""

    def test_creates_new_tcatbal_record(
        self, account_repo, xref_repo, transaction_repo,
    ):
        tcatbal = InMemoryTranCatBalRepository()
        tran = DailyTransactionRecord(
            dalytran_id="0000000000000001",
            dalytran_type_cd="01",
            dalytran_cat_cd=5000,
            dalytran_source="BATCH",
            dalytran_desc="Purchase",
            dalytran_amt=Decimal("100.00"),
            dalytran_card_num="4111111111111111",
            dalytran_orig_ts="2026-06-15-00.00.00.000000",
            dalytran_proc_ts="2026-06-15-00.00.00.000000",
        )

        run_post_daily_transactions(
            daily_transactions=[tran],
            xref_repo=xref_repo,
            account_repo=account_repo,
            tcatbal_repo=tcatbal,
            transaction_repo=transaction_repo,
            timestamp_provider=FIXED_TS,
        )

        rec = tcatbal.find_by_key(80000000001, "01", 5000)
        assert rec is not None
        assert rec.tran_cat_bal == Decimal("100.00")

    def test_updates_existing_tcatbal_record(
        self, account_repo, xref_repo, transaction_repo,
    ):
        tcatbal = InMemoryTranCatBalRepository(pd.DataFrame([
            {"trancat_acct_id": 80000000001, "trancat_type_cd": "01", "trancat_cd": 5000, "tran_cat_bal": Decimal("500.00")},
        ]))
        tran = DailyTransactionRecord(
            dalytran_id="0000000000000001",
            dalytran_type_cd="01",
            dalytran_cat_cd=5000,
            dalytran_source="BATCH",
            dalytran_desc="Purchase",
            dalytran_amt=Decimal("100.00"),
            dalytran_card_num="4111111111111111",
            dalytran_orig_ts="2026-06-15-00.00.00.000000",
            dalytran_proc_ts="2026-06-15-00.00.00.000000",
        )

        run_post_daily_transactions(
            daily_transactions=[tran],
            xref_repo=xref_repo,
            account_repo=account_repo,
            tcatbal_repo=tcatbal,
            transaction_repo=transaction_repo,
            timestamp_provider=FIXED_TS,
        )

        rec = tcatbal.find_by_key(80000000001, "01", 5000)
        assert rec.tran_cat_bal == Decimal("600.00")


class TestPostTransactionsMixedBatch:
    """Multiple transactions with mix of valid and invalid."""

    def test_mixed_batch(self, account_repo, xref_repo, transaction_repo):
        tcatbal = InMemoryTranCatBalRepository()
        trans = [
            DailyTransactionRecord(
                dalytran_id="0000000000000001",
                dalytran_type_cd="01",
                dalytran_cat_cd=5000,
                dalytran_source="BATCH",
                dalytran_desc="Valid purchase",
                dalytran_amt=Decimal("100.00"),
                dalytran_card_num="4111111111111111",
                dalytran_orig_ts="2026-06-15-00.00.00.000000",
                dalytran_proc_ts="2026-06-15-00.00.00.000000",
            ),
            DailyTransactionRecord(
                dalytran_id="0000000000000002",
                dalytran_card_num="9999999999999999",
                dalytran_amt=Decimal("50.00"),
                dalytran_orig_ts="2026-06-15-00.00.00.000000",
            ),
            DailyTransactionRecord(
                dalytran_id="0000000000000003",
                dalytran_type_cd="02",
                dalytran_cat_cd=3000,
                dalytran_source="BATCH",
                dalytran_desc="Another valid",
                dalytran_amt=Decimal("75.50"),
                dalytran_card_num="4222222222222222",
                dalytran_orig_ts="2026-06-15-00.00.00.000000",
                dalytran_proc_ts="2026-06-15-00.00.00.000000",
            ),
        ]

        result = run_post_daily_transactions(
            daily_transactions=trans,
            xref_repo=xref_repo,
            account_repo=account_repo,
            tcatbal_repo=tcatbal,
            transaction_repo=transaction_repo,
            timestamp_provider=FIXED_TS,
        )

        assert result.transactions_processed == 3
        assert result.transactions_posted == 2
        assert result.transactions_rejected == 1
        assert result.return_code == 4
