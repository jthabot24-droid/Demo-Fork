"""
Unit tests for the interest calculation batch migration.

Covers the ``calculate_interest`` function from ``interest_calc.py``
(CBACT04C), exercising interest rate lookup, monthly interest
computation, account-change detection, and account balance updates.
"""

from decimal import Decimal

import pandas as pd
import pytest

from interest_calc import (
    DisGroupRecord,
    InterestResult,
    calculate_interest,
)
from post_transactions import TransactionRecord

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
                "acct_curr_bal": Decimal("1000.00"),
                "acct_credit_limit": Decimal("5000.00"),
                "acct_curr_cyc_credit": Decimal("500.00"),
                "acct_curr_cyc_debit": Decimal("-200.00"),
                "acct_expiration_date": "2027-12-31",
                "acct_group_id": "GROUP01",
            },
            {
                "acct_id": 80000000002,
                "acct_curr_bal": Decimal("2000.00"),
                "acct_credit_limit": Decimal("10000.00"),
                "acct_curr_cyc_credit": Decimal("300.00"),
                "acct_curr_cyc_debit": Decimal("-100.00"),
                "acct_expiration_date": "2028-06-30",
                "acct_group_id": "GROUP02",
            },
        ]
    )


@pytest.fixture()
def discgrp_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "dis_acct_group_id": "GROUP01",
                "dis_tran_type_cd": "01",
                "dis_tran_cat_cd": 5000,
                "dis_int_rate": Decimal("18.00"),
            },
            {
                "dis_acct_group_id": "GROUP02",
                "dis_tran_type_cd": "01",
                "dis_tran_cat_cd": 5000,
                "dis_int_rate": Decimal("24.00"),
            },
            {
                "dis_acct_group_id": "DEFAULT",
                "dis_tran_type_cd": "01",
                "dis_tran_cat_cd": 9000,
                "dis_int_rate": Decimal("12.00"),
            },
        ]
    )


@pytest.fixture()
def tcatbal_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "trancat_acct_id": 80000000001,
                "trancat_type_cd": "01",
                "trancat_cd": 5000,
                "tran_cat_bal": Decimal("600.00"),
            },
        ]
    )


PARM_DATE = "2026-06-15"


# ===================================================================
# INTEREST COMPUTATION -- 1300-COMPUTE-INTEREST
# ===================================================================


class TestInterestComputation:
    """Monthly interest = (balance * rate) / 1200."""

    def test_single_category_balance(
        self, xref_df, account_df, discgrp_df, tcatbal_df
    ):
        result = calculate_interest(
            tcatbal_df, xref_df, account_df, discgrp_df, PARM_DATE,
        )

        assert result.records_processed == 1
        assert len(result.interest_transactions) == 1

        tran = result.interest_transactions[0]
        # 600.00 * 18.00 / 1200 = 9.00
        assert tran.tran_amt == Decimal("9.00")

    def test_interest_precision(
        self, xref_df, account_df, discgrp_df,
    ):
        tcatbal = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 5000,
                    "tran_cat_bal": Decimal("333.33"),
                },
            ]
        )
        result = calculate_interest(
            tcatbal, xref_df, account_df, discgrp_df, PARM_DATE,
        )

        tran = result.interest_transactions[0]
        # 333.33 * 18.00 / 1200 = 4.99995
        expected = (Decimal("333.33") * Decimal("18.00")) / Decimal("1200")
        assert tran.tran_amt == expected


# ===================================================================
# INTEREST RATE LOOKUP -- 1200-GET-INTEREST-RATE
# ===================================================================


class TestInterestRateLookup:
    """Lookup by group, fallback to DEFAULT."""

    def test_default_group_fallback(
        self, xref_df, account_df, discgrp_df,
    ):
        tcatbal = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 9000,
                    "tran_cat_bal": Decimal("1200.00"),
                },
            ]
        )
        result = calculate_interest(
            tcatbal, xref_df, account_df, discgrp_df, PARM_DATE,
        )

        tran = result.interest_transactions[0]
        # 1200.00 * 12.00 / 1200 = 12.00
        assert tran.tran_amt == Decimal("12.00")

    def test_zero_rate_no_transaction(
        self, xref_df, account_df,
    ):
        discgrp = pd.DataFrame(
            [
                {
                    "dis_acct_group_id": "GROUP01",
                    "dis_tran_type_cd": "01",
                    "dis_tran_cat_cd": 5000,
                    "dis_int_rate": Decimal("0.00"),
                },
            ]
        )
        tcatbal = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 5000,
                    "tran_cat_bal": Decimal("500.00"),
                },
            ]
        )
        result = calculate_interest(
            tcatbal, xref_df, account_df, discgrp, PARM_DATE,
        )
        assert len(result.interest_transactions) == 0

    def test_no_matching_group_no_transaction(
        self, xref_df, account_df,
    ):
        discgrp = pd.DataFrame(
            columns=[
                "dis_acct_group_id",
                "dis_tran_type_cd",
                "dis_tran_cat_cd",
                "dis_int_rate",
            ]
        )
        tcatbal = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 5000,
                    "tran_cat_bal": Decimal("500.00"),
                },
            ]
        )
        result = calculate_interest(
            tcatbal, xref_df, account_df, discgrp, PARM_DATE,
        )
        assert len(result.interest_transactions) == 0


# ===================================================================
# ACCOUNT CHANGE DETECTION
# ===================================================================


class TestAccountChangeDetection:
    """1050-UPDATE-ACCOUNT is called when account ID changes."""

    def test_two_accounts_updated_separately(
        self, xref_df, account_df, discgrp_df,
    ):
        tcatbal = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 5000,
                    "tran_cat_bal": Decimal("600.00"),
                },
                {
                    "trancat_acct_id": 80000000002,
                    "trancat_type_cd": "01",
                    "trancat_cd": 5000,
                    "tran_cat_bal": Decimal("1200.00"),
                },
            ]
        )
        result = calculate_interest(
            tcatbal, xref_df, account_df, discgrp_df, PARM_DATE,
        )

        assert result.records_processed == 2
        assert len(result.interest_transactions) == 2

        acct = result.updated_accounts

        # Account 1: 1000 + (600*18/1200=9.00) = 1009.00
        row1 = acct.loc[acct["acct_id"] == 80000000001].iloc[0]
        assert Decimal(str(row1["acct_curr_bal"])) == Decimal("1009.00")
        assert Decimal(str(row1["acct_curr_cyc_credit"])) == Decimal("0.00")
        assert Decimal(str(row1["acct_curr_cyc_debit"])) == Decimal("0.00")

        # Account 2: 2000 + (1200*24/1200=24.00) = 2024.00
        row2 = acct.loc[acct["acct_id"] == 80000000002].iloc[0]
        assert Decimal(str(row2["acct_curr_bal"])) == Decimal("2024.00")
        assert Decimal(str(row2["acct_curr_cyc_credit"])) == Decimal("0.00")
        assert Decimal(str(row2["acct_curr_cyc_debit"])) == Decimal("0.00")

    def test_multiple_categories_same_account(
        self, xref_df, account_df, discgrp_df,
    ):
        tcatbal = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 5000,
                    "tran_cat_bal": Decimal("600.00"),
                },
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 9000,
                    "tran_cat_bal": Decimal("1200.00"),
                },
            ]
        )
        result = calculate_interest(
            tcatbal, xref_df, account_df, discgrp_df, PARM_DATE,
        )

        assert len(result.interest_transactions) == 2
        # Total interest = 9.00 + 12.00 = 21.00
        # Account balance = 1000.00 + 21.00 = 1021.00
        acct = result.updated_accounts
        row = acct.loc[acct["acct_id"] == 80000000001].iloc[0]
        assert Decimal(str(row["acct_curr_bal"])) == Decimal("1021.00")


# ===================================================================
# ACCOUNT UPDATES -- 1050-UPDATE-ACCOUNT
# ===================================================================


class TestAccountUpdate:
    """Account balance and cycle reset."""

    def test_cycle_fields_reset_to_zero(
        self, xref_df, account_df, discgrp_df, tcatbal_df,
    ):
        result = calculate_interest(
            tcatbal_df, xref_df, account_df, discgrp_df, PARM_DATE,
        )

        acct = result.updated_accounts
        row = acct.loc[acct["acct_id"] == 80000000001].iloc[0]
        assert Decimal(str(row["acct_curr_cyc_credit"])) == Decimal("0.00")
        assert Decimal(str(row["acct_curr_cyc_debit"])) == Decimal("0.00")


# ===================================================================
# TRANSACTION RECORD OUTPUT -- 1300-B-WRITE-TX
# ===================================================================


class TestInterestTransactionRecord:
    """Interest transaction output fields."""

    def test_transaction_fields(
        self, xref_df, account_df, discgrp_df, tcatbal_df,
    ):
        result = calculate_interest(
            tcatbal_df, xref_df, account_df, discgrp_df, PARM_DATE,
        )

        tran = result.interest_transactions[0]
        assert tran.tran_type_cd == "01"
        assert tran.tran_cat_cd == 5
        assert tran.tran_source == "System"
        assert "80000000001" in tran.tran_desc
        assert tran.tran_card_num == "4111111111111111"
        assert tran.tran_orig_ts != ""
        assert tran.tran_proc_ts != ""

    def test_transaction_id_format(
        self, xref_df, account_df, discgrp_df, tcatbal_df,
    ):
        result = calculate_interest(
            tcatbal_df, xref_df, account_df, discgrp_df, PARM_DATE,
        )

        tran = result.interest_transactions[0]
        # ID = parm_date[:10] + 6-digit suffix
        assert tran.tran_id.startswith("2026-06-15")
        assert len(tran.tran_id) == 16


# ===================================================================
# EDGE CASES
# ===================================================================


class TestEdgeCases:
    """Empty inputs and boundary conditions."""

    def test_empty_tcatbal(self, xref_df, account_df, discgrp_df):
        tcatbal = pd.DataFrame(
            columns=[
                "trancat_acct_id",
                "trancat_type_cd",
                "trancat_cd",
                "tran_cat_bal",
            ]
        )
        result = calculate_interest(
            tcatbal, xref_df, account_df, discgrp_df, PARM_DATE,
        )
        assert result.records_processed == 0
        assert len(result.interest_transactions) == 0

    def test_negative_balance_produces_negative_interest(
        self, xref_df, account_df, discgrp_df,
    ):
        tcatbal = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 5000,
                    "tran_cat_bal": Decimal("-600.00"),
                },
            ]
        )
        result = calculate_interest(
            tcatbal, xref_df, account_df, discgrp_df, PARM_DATE,
        )

        tran = result.interest_transactions[0]
        # -600.00 * 18.00 / 1200 = -9.00
        assert tran.tran_amt == Decimal("-9.00")
