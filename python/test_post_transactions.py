"""
Unit tests for the batch daily-transaction posting migration.

Covers the ``post_daily_transactions`` function from
``post_transactions.py`` (CBTRN02C), exercising the main loop,
TCATBAL creation/update, account balance updates, and reject handling.
"""

from decimal import Decimal

import pandas as pd
import pytest

from post_transactions import (
    PostingResult,
    RejectRecord,
    TransactionRecord,
    post_daily_transactions,
)

# ---------------------------------------------------------------------------
# Fixtures -- small reference data sets
# ---------------------------------------------------------------------------


@pytest.fixture()
def xref_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "xref_card_num": "4111111111111111",
                "xref_cust_id": 100000001,
                "xref_acct_id": 80000000001,
            },
            {
                "xref_card_num": "4222222222222222",
                "xref_cust_id": 100000002,
                "xref_acct_id": 80000000002,
            },
        ]
    )


@pytest.fixture()
def account_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "acct_id": 80000000001,
                "acct_curr_bal": Decimal("500.00"),
                "acct_credit_limit": Decimal("5000.00"),
                "acct_curr_cyc_credit": Decimal("1000.00"),
                "acct_curr_cyc_debit": Decimal("200.00"),
                "acct_expiration_date": "2027-12-31",
            },
            {
                "acct_id": 80000000002,
                "acct_curr_bal": Decimal("50.00"),
                "acct_credit_limit": Decimal("100.00"),
                "acct_curr_cyc_credit": Decimal("90.00"),
                "acct_curr_cyc_debit": Decimal("0.00"),
                "acct_expiration_date": "2020-01-01",
            },
        ]
    )


@pytest.fixture()
def tcatbal_df() -> pd.DataFrame:
    return pd.DataFrame(
        columns=["trancat_acct_id", "trancat_type_cd", "trancat_cd", "tran_cat_bal"]
    ).astype(
        {
            "trancat_acct_id": "int64",
            "trancat_type_cd": "object",
            "trancat_cd": "int64",
            "tran_cat_bal": "object",
        }
    )


def _make_daily_df(rows: list[dict]) -> pd.DataFrame:
    """Build a daily-transactions DataFrame from a list of dicts."""
    defaults = {
        "dalytran_id": "0000000000000001",
        "dalytran_type_cd": "01",
        "dalytran_cat_cd": 5000,
        "dalytran_source": "BATCH",
        "dalytran_desc": "Daily purchase",
        "dalytran_amt": Decimal("100.00"),
        "dalytran_merchant_id": 123456789,
        "dalytran_merchant_name": "Acme Corp",
        "dalytran_merchant_city": "Seattle",
        "dalytran_merchant_zip": "98101",
        "dalytran_card_num": "4111111111111111",
        "dalytran_orig_ts": "2026-06-15-00.00.00.000000",
        "dalytran_proc_ts": "2026-06-15-00.00.00.000000",
    }
    merged = [{**defaults, **r} for r in rows]
    return pd.DataFrame(merged)


# ===================================================================
# HAPPY PATH -- 2000-POST-TRANSACTION
# ===================================================================


class TestPostHappyPath:
    """Valid transactions should be posted."""

    def test_single_valid_transaction(self, xref_df, account_df, tcatbal_df):
        daily = _make_daily_df([{}])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)

        assert result.transactions_processed == 1
        assert result.transactions_rejected == 0
        assert len(result.posted_transactions) == 1
        assert result.return_code == 0

    def test_posted_record_fields_match(self, xref_df, account_df, tcatbal_df):
        daily = _make_daily_df([{"dalytran_desc": "Widget", "dalytran_amt": Decimal("25.00")}])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)

        posted = result.posted_transactions[0]
        assert posted.tran_desc == "Widget"
        assert posted.tran_amt == Decimal("25.00")
        assert posted.tran_proc_ts != ""

    def test_multiple_valid_transactions(self, xref_df, account_df, tcatbal_df):
        daily = _make_daily_df([
            {"dalytran_id": "0000000000000001"},
            {"dalytran_id": "0000000000000002"},
            {"dalytran_id": "0000000000000003"},
        ])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)

        assert result.transactions_processed == 3
        assert len(result.posted_transactions) == 3


# ===================================================================
# REJECT HANDLING -- 2500-WRITE-REJECT-REC
# ===================================================================


class TestRejectHandling:
    """Invalid transactions should be written to rejects."""

    def test_unknown_card_rejected(self, xref_df, account_df, tcatbal_df):
        daily = _make_daily_df([{"dalytran_card_num": "0000000000000000"}])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)

        assert result.transactions_rejected == 1
        assert result.return_code == 4
        assert len(result.reject_records) == 1
        assert result.reject_records[0].fail_reason == 100

    def test_expired_card_rejected(self, xref_df, account_df, tcatbal_df):
        daily = _make_daily_df([{
            "dalytran_card_num": "4222222222222222",
            "dalytran_amt": Decimal("1.00"),
            "dalytran_orig_ts": "2026-06-15-00.00.00.000000",
        }])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)

        assert result.transactions_rejected == 1
        assert result.reject_records[0].fail_reason == 103

    def test_mixed_valid_and_rejected(self, xref_df, account_df, tcatbal_df):
        daily = _make_daily_df([
            {"dalytran_id": "0000000000000001"},
            {"dalytran_id": "0000000000000002", "dalytran_card_num": "0000000000000000"},
        ])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)

        assert result.transactions_processed == 2
        assert len(result.posted_transactions) == 1
        assert result.transactions_rejected == 1
        assert result.return_code == 4


# ===================================================================
# TCATBAL UPDATES -- 2700-UPDATE-TCATBAL
# ===================================================================


class TestTcatbalUpdate:
    """Transaction category balance creation and updates."""

    def test_creates_new_tcatbal_record(self, xref_df, account_df, tcatbal_df):
        daily = _make_daily_df([{"dalytran_amt": Decimal("75.00")}])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)

        tcatbal = result.updated_tcatbal
        row = tcatbal.loc[
            (tcatbal["trancat_acct_id"] == 80000000001)
            & (tcatbal["trancat_type_cd"] == "01")
            & (tcatbal["trancat_cd"] == 5000)
        ]
        assert not row.empty
        assert Decimal(str(row.iloc[0]["tran_cat_bal"])) == Decimal("75.00")

    def test_updates_existing_tcatbal_record(self, xref_df, account_df):
        tcatbal = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 5000,
                    "tran_cat_bal": Decimal("200.00"),
                }
            ]
        )
        daily = _make_daily_df([{"dalytran_amt": Decimal("50.00")}])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal)

        updated = result.updated_tcatbal
        row = updated.loc[
            (updated["trancat_acct_id"] == 80000000001)
            & (updated["trancat_type_cd"] == "01")
            & (updated["trancat_cd"] == 5000)
        ]
        assert Decimal(str(row.iloc[0]["tran_cat_bal"])) == Decimal("250.00")

    def test_accumulates_multiple_same_category(self, xref_df, account_df, tcatbal_df):
        daily = _make_daily_df([
            {"dalytran_id": "0000000000000001", "dalytran_amt": Decimal("30.00")},
            {"dalytran_id": "0000000000000002", "dalytran_amt": Decimal("20.00")},
        ])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)

        tcatbal = result.updated_tcatbal
        row = tcatbal.loc[
            (tcatbal["trancat_acct_id"] == 80000000001)
            & (tcatbal["trancat_type_cd"] == "01")
            & (tcatbal["trancat_cd"] == 5000)
        ]
        assert Decimal(str(row.iloc[0]["tran_cat_bal"])) == Decimal("50.00")


# ===================================================================
# ACCOUNT UPDATES -- 2800-UPDATE-ACCOUNT-REC
# ===================================================================


class TestAccountUpdate:
    """Account balance and cycle credit/debit updates."""

    def test_positive_amount_updates_balance_and_credit(
        self, xref_df, account_df, tcatbal_df
    ):
        daily = _make_daily_df([{"dalytran_amt": Decimal("150.00")}])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)

        acct = result.updated_accounts
        row = acct.loc[acct["acct_id"] == 80000000001].iloc[0]
        assert Decimal(str(row["acct_curr_bal"])) == Decimal("650.00")
        assert Decimal(str(row["acct_curr_cyc_credit"])) == Decimal("1150.00")

    def test_negative_amount_updates_balance_and_debit(
        self, xref_df, account_df, tcatbal_df
    ):
        daily = _make_daily_df([{"dalytran_amt": Decimal("-75.00")}])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)

        acct = result.updated_accounts
        row = acct.loc[acct["acct_id"] == 80000000001].iloc[0]
        assert Decimal(str(row["acct_curr_bal"])) == Decimal("425.00")
        assert Decimal(str(row["acct_curr_cyc_debit"])) == Decimal("125.00")

    def test_multiple_transactions_accumulate(
        self, xref_df, account_df, tcatbal_df
    ):
        daily = _make_daily_df([
            {"dalytran_id": "0000000000000001", "dalytran_amt": Decimal("100.00")},
            {"dalytran_id": "0000000000000002", "dalytran_amt": Decimal("200.00")},
        ])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)

        acct = result.updated_accounts
        row = acct.loc[acct["acct_id"] == 80000000001].iloc[0]
        assert Decimal(str(row["acct_curr_bal"])) == Decimal("800.00")


# ===================================================================
# RETURN CODE
# ===================================================================


class TestReturnCode:
    """Return code handling."""

    def test_zero_when_all_valid(self, xref_df, account_df, tcatbal_df):
        daily = _make_daily_df([{}])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)
        assert result.return_code == 0

    def test_four_when_rejects_exist(self, xref_df, account_df, tcatbal_df):
        daily = _make_daily_df([{"dalytran_card_num": "0000000000000000"}])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)
        assert result.return_code == 4

    def test_empty_file(self, xref_df, account_df, tcatbal_df):
        daily = _make_daily_df([])
        result = post_daily_transactions(daily, xref_df, account_df, tcatbal_df)
        assert result.transactions_processed == 0
        assert result.return_code == 0
