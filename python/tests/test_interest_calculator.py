"""
Tests for the Python migration of CBACT04C (Interest Calculator).

Covers:
    - Zero balance with non-zero rate
    - Positive balance with a specific disclosure-group interest rate
    - Multiple categories per account (accumulated total)
    - Rate lookup fallback to DEFAULT group
    - Rounding / truncation edge cases (COBOL COMPUTE without ROUNDED)
    - Zero interest rate (no transaction emitted)
    - Account balance update correctness
    - Fixed-width 350-byte output formatting
    - Transaction ID generation
"""

from datetime import datetime
from decimal import Decimal

import pandas as pd
import pytest

from python.interest_calculator import (
    TRAN_OUTPUT_COLUMNS,
    _cobol_truncate,
    _format_signed_display,
    _format_transaction_record,
    _make_db2_timestamp,
    compute_interest,
    write_transaction_file,
)

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

FIXED_TS = datetime(2022, 7, 18, 10, 30, 0, 0)
PARM_DATE = "2022071800"


def _make_tcatbal(**overrides) -> dict:
    defaults = {
        "trancat_acct_id": "00000000001",
        "trancat_type_cd": "01",
        "trancat_cd": 1,
        "tran_cat_bal": Decimal("1000.00"),
    }
    defaults.update(overrides)
    return defaults


def _make_xref(**overrides) -> dict:
    defaults = {
        "xref_card_num": "4111111111111111",
        "xref_cust_id": "000000001",
        "xref_acct_id": "00000000001",
    }
    defaults.update(overrides)
    return defaults


def _make_account(**overrides) -> dict:
    defaults = {
        "acct_id": "00000000001",
        "acct_active_status": "Y",
        "acct_curr_bal": Decimal("5000.00"),
        "acct_credit_limit": Decimal("10000.00"),
        "acct_cash_credit_limit": Decimal("2000.00"),
        "acct_open_date": "2020-01-01",
        "acct_expiraion_date": "2025-12-31",
        "acct_reissue_date": "2023-01-01",
        "acct_curr_cyc_credit": Decimal("200.00"),
        "acct_curr_cyc_debit": Decimal("150.00"),
        "acct_addr_zip": "10001",
        "acct_group_id": "PREMIUM",
    }
    defaults.update(overrides)
    return defaults


def _make_discgrp(**overrides) -> dict:
    defaults = {
        "dis_acct_group_id": "PREMIUM",
        "dis_tran_type_cd": "01",
        "dis_tran_cat_cd": 1,
        "dis_int_rate": Decimal("18.00"),
    }
    defaults.update(overrides)
    return defaults


def _build_dfs(
    tcatbal_rows=None,
    xref_rows=None,
    account_rows=None,
    discgrp_rows=None,
):
    tcatbal_df = pd.DataFrame(tcatbal_rows or [_make_tcatbal()])
    xref_df = pd.DataFrame(xref_rows or [_make_xref()])
    account_df = pd.DataFrame(account_rows or [_make_account()])
    discgrp_df = pd.DataFrame(discgrp_rows or [_make_discgrp()])
    return tcatbal_df, xref_df, account_df, discgrp_df


# ===================================================================
# Helper function tests
# ===================================================================


class TestCobolTruncate:
    def test_positive_truncation(self):
        assert _cobol_truncate(Decimal("15.416666")) == Decimal("15.41")

    def test_negative_truncation_toward_zero(self):
        assert _cobol_truncate(Decimal("-0.58333")) == Decimal("-0.58")

    def test_exact_value_unchanged(self):
        assert _cobol_truncate(Decimal("10.50")) == Decimal("10.50")

    def test_zero(self):
        assert _cobol_truncate(Decimal("0")) == Decimal("0.00")


class TestMakeDb2Timestamp:
    def test_format(self):
        ts = _make_db2_timestamp(datetime(2022, 7, 18, 14, 30, 45, 120000))
        assert ts == "2022-07-18-14.30.45.120000"
        assert len(ts) == 26

    def test_zero_microseconds(self):
        ts = _make_db2_timestamp(datetime(2022, 1, 1, 0, 0, 0, 0))
        assert ts == "2022-01-01-00.00.00.000000"


class TestFormatSignedDisplay:
    def test_positive(self):
        result = _format_signed_display(Decimal("1234.56"), 9, 2)
        assert result == "0000012345F"
        assert len(result) == 11

    def test_zero(self):
        result = _format_signed_display(Decimal("0.00"), 9, 2)
        assert result == "0000000000{"
        assert len(result) == 11

    def test_negative(self):
        result = _format_signed_display(Decimal("-500.25"), 9, 2)
        assert result == "0000005002N"
        assert len(result) == 11


# ===================================================================
# Interest computation tests
# ===================================================================


class TestZeroBalance:
    """COBOL: balance=0, rate!=0 -> transaction IS written with amt=0."""

    def test_zero_balance_produces_transaction(self):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            tcatbal_rows=[_make_tcatbal(tran_cat_bal=Decimal("0.00"))],
        )
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert len(tran_df) == 1
        assert tran_df.iloc[0]["tran_amt"] == Decimal("0.00")


class TestPositiveBalance:
    """Verify the core interest formula: (balance * rate) / 1200."""

    def test_standard_calculation(self):
        # balance=1000, rate=18 -> (1000*18)/1200 = 15.00
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            tcatbal_rows=[
                _make_tcatbal(tran_cat_bal=Decimal("1000.00")),
            ],
            discgrp_rows=[
                _make_discgrp(dis_int_rate=Decimal("18.00")),
            ],
        )
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert len(tran_df) == 1
        assert tran_df.iloc[0]["tran_amt"] == Decimal("15.00")

    def test_large_balance(self):
        # balance=500000, rate=24.50 -> (500000*24.50)/1200 = 10208.3333...
        # Truncated to 10208.33
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            tcatbal_rows=[
                _make_tcatbal(tran_cat_bal=Decimal("500000.00")),
            ],
            discgrp_rows=[
                _make_discgrp(dis_int_rate=Decimal("24.50")),
            ],
        )
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert tran_df.iloc[0]["tran_amt"] == Decimal("10208.33")


class TestMultipleCategoriesPerAccount:
    """Multiple TCATBAL rows for the same account accumulate interest."""

    def test_two_categories_same_account(self):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            tcatbal_rows=[
                _make_tcatbal(trancat_cd=1, tran_cat_bal=Decimal("1000.00")),
                _make_tcatbal(trancat_cd=2, tran_cat_bal=Decimal("2000.00")),
            ],
            discgrp_rows=[
                _make_discgrp(dis_tran_cat_cd=1, dis_int_rate=Decimal("12.00")),
                _make_discgrp(dis_tran_cat_cd=2, dis_int_rate=Decimal("18.00")),
            ],
        )
        updated_accts, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert len(tran_df) == 2
        # cat1: (1000*12)/1200 = 10.00
        assert tran_df.iloc[0]["tran_amt"] == Decimal("10.00")
        # cat2: (2000*18)/1200 = 30.00
        assert tran_df.iloc[1]["tran_amt"] == Decimal("30.00")
        # Account balance = 5000 + 10 + 30 = 5040
        acct = updated_accts.iloc[0]
        assert Decimal(str(acct["acct_curr_bal"])) == Decimal("5040.00")


class TestDefaultGroupFallback:
    """When the account's group has no match, fall back to DEFAULT."""

    def test_fallback_to_default(self):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            account_rows=[
                _make_account(acct_group_id="UNKNOWN_GRP"),
            ],
            discgrp_rows=[
                # No UNKNOWN_GRP entry -- only DEFAULT
                _make_discgrp(
                    dis_acct_group_id="DEFAULT",
                    dis_int_rate=Decimal("15.00"),
                ),
            ],
        )
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert len(tran_df) == 1
        # (1000*15)/1200 = 12.50
        assert tran_df.iloc[0]["tran_amt"] == Decimal("12.50")

    def test_specific_group_preferred_over_default(self):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            discgrp_rows=[
                _make_discgrp(
                    dis_acct_group_id="PREMIUM",
                    dis_int_rate=Decimal("18.00"),
                ),
                _make_discgrp(
                    dis_acct_group_id="DEFAULT",
                    dis_int_rate=Decimal("24.00"),
                ),
            ],
        )
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        # Should use PREMIUM (18), not DEFAULT (24)
        # (1000*18)/1200 = 15.00
        assert tran_df.iloc[0]["tran_amt"] == Decimal("15.00")

    def test_missing_both_groups_raises(self):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            account_rows=[_make_account(acct_group_id="MISSING")],
            discgrp_rows=[
                _make_discgrp(dis_acct_group_id="OTHER"),
            ],
        )
        with pytest.raises(ValueError, match="DEFAULT fallback also missing"):
            compute_interest(
                tcatbal_df, xref_df, account_df, discgrp_df,
                PARM_DATE, timestamp=FIXED_TS,
            )


class TestRoundingEdgeCases:
    """COBOL COMPUTE without ROUNDED truncates toward zero."""

    def test_truncation_not_rounding(self):
        # balance=100, rate=7 -> (100*7)/1200 = 0.58333...
        # Truncated = 0.58  (NOT 0.58 rounded)
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            tcatbal_rows=[
                _make_tcatbal(tran_cat_bal=Decimal("100.00")),
            ],
            discgrp_rows=[
                _make_discgrp(dis_int_rate=Decimal("7.00")),
            ],
        )
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert tran_df.iloc[0]["tran_amt"] == Decimal("0.58")

    def test_truncation_at_boundary(self):
        # balance=1, rate=1 -> (1*1)/1200 = 0.000833...
        # Truncated = 0.00
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            tcatbal_rows=[
                _make_tcatbal(tran_cat_bal=Decimal("1.00")),
            ],
            discgrp_rows=[
                _make_discgrp(dis_int_rate=Decimal("1.00")),
            ],
        )
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert tran_df.iloc[0]["tran_amt"] == Decimal("0.00")

    def test_negative_balance_truncation(self):
        # balance=-100, rate=7 -> (-100*7)/1200 = -0.58333...
        # Truncated toward zero = -0.58
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            tcatbal_rows=[
                _make_tcatbal(tran_cat_bal=Decimal("-100.00")),
            ],
            discgrp_rows=[
                _make_discgrp(dis_int_rate=Decimal("7.00")),
            ],
        )
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert tran_df.iloc[0]["tran_amt"] == Decimal("-0.58")

    def test_would_round_up_but_truncates(self):
        # balance=100, rate=19 -> (100*19)/1200 = 1.58333...
        # Would round to 1.58 either way, but let's test 5/6 boundary
        # balance=200, rate=5 -> (200*5)/1200 = 0.83333...
        # Truncated = 0.83  (a naive round would give 0.83 too)
        # Better: balance=100, rate=11 -> (100*11)/1200 = 0.91666...
        # Truncated = 0.91
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            tcatbal_rows=[
                _make_tcatbal(tran_cat_bal=Decimal("100.00")),
            ],
            discgrp_rows=[
                _make_discgrp(dis_int_rate=Decimal("11.00")),
            ],
        )
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert tran_df.iloc[0]["tran_amt"] == Decimal("0.91")


class TestZeroRate:
    """Rate = 0 -> no interest computed, no transaction written."""

    def test_zero_rate_skips_transaction(self):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            discgrp_rows=[
                _make_discgrp(dis_int_rate=Decimal("0.00")),
            ],
        )
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert len(tran_df) == 0


class TestAccountUpdate:
    """1050-UPDATE-ACCOUNT: adds total interest, zeros cycle fields."""

    def test_balance_updated(self):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs()
        updated, _ = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        acct = updated.iloc[0]
        # interest = (1000*18)/1200 = 15.00; new bal = 5000 + 15 = 5015
        assert Decimal(str(acct["acct_curr_bal"])) == Decimal("5015.00")
        assert Decimal(str(acct["acct_curr_cyc_credit"])) == Decimal("0")
        assert Decimal(str(acct["acct_curr_cyc_debit"])) == Decimal("0")

    def test_original_not_mutated(self):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs()
        original_bal = account_df.iloc[0]["acct_curr_bal"]
        compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert account_df.iloc[0]["acct_curr_bal"] == original_bal

    def test_multiple_accounts_all_updated(self):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            tcatbal_rows=[
                _make_tcatbal(
                    trancat_acct_id="00000000001",
                    tran_cat_bal=Decimal("1000.00"),
                ),
                _make_tcatbal(
                    trancat_acct_id="00000000002",
                    tran_cat_bal=Decimal("2000.00"),
                ),
            ],
            xref_rows=[
                _make_xref(xref_acct_id="00000000001"),
                _make_xref(
                    xref_acct_id="00000000002",
                    xref_card_num="5222222222222222",
                ),
            ],
            account_rows=[
                _make_account(
                    acct_id="00000000001",
                    acct_curr_bal=Decimal("5000.00"),
                ),
                _make_account(
                    acct_id="00000000002",
                    acct_curr_bal=Decimal("3000.00"),
                ),
            ],
        )
        updated, _ = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        # acct1: 5000 + 15 = 5015
        assert Decimal(str(updated.iloc[0]["acct_curr_bal"])) == Decimal(
            "5015.00"
        )
        # acct2: 3000 + (2000*18)/1200 = 3000 + 30 = 3030
        assert Decimal(str(updated.iloc[1]["acct_curr_bal"])) == Decimal(
            "3030.00"
        )


class TestTransactionIdGeneration:
    """TRAN-ID = PARM-DATE (10) + suffix (06) = 16 chars."""

    def test_id_format(self):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs()
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        tran_id = tran_df.iloc[0]["tran_id"]
        assert tran_id == "2022071800000001"
        assert len(tran_id) == 16

    def test_sequential_ids(self):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs(
            tcatbal_rows=[
                _make_tcatbal(trancat_cd=1, tran_cat_bal=Decimal("100.00")),
                _make_tcatbal(trancat_cd=2, tran_cat_bal=Decimal("200.00")),
            ],
            discgrp_rows=[
                _make_discgrp(dis_tran_cat_cd=1),
                _make_discgrp(dis_tran_cat_cd=2),
            ],
        )
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert tran_df.iloc[0]["tran_id"] == "2022071800000001"
        assert tran_df.iloc[1]["tran_id"] == "2022071800000002"


class TestTransactionRecordFields:
    """Verify all output fields match the COBOL logic."""

    def test_fixed_fields(self):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs()
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        row = tran_df.iloc[0]
        assert row["tran_type_cd"] == "01"
        assert row["tran_cat_cd"] == 5
        assert row["tran_source"] == "System"
        assert row["tran_desc"] == "Int. for a/c 00000000001"
        assert row["tran_merchant_id"] == 0
        assert row["tran_merchant_name"] == ""
        assert row["tran_merchant_city"] == ""
        assert row["tran_merchant_zip"] == ""
        assert row["tran_card_num"] == "4111111111111111"
        assert row["tran_orig_ts"] == row["tran_proc_ts"]

    def test_output_columns_order(self):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs()
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert list(tran_df.columns) == TRAN_OUTPUT_COLUMNS


class TestFixedWidthOutput:
    """Verify the 350-byte record writer."""

    def test_record_length(self):
        row = {
            "tran_id": "2022071800000001",
            "tran_type_cd": "01",
            "tran_cat_cd": 5,
            "tran_source": "System",
            "tran_desc": "Int. for a/c 00000000001",
            "tran_amt": Decimal("15.00"),
            "tran_merchant_id": 0,
            "tran_merchant_name": "",
            "tran_merchant_city": "",
            "tran_merchant_zip": "",
            "tran_card_num": "4111111111111111",
            "tran_orig_ts": "2022-07-18-10.30.00.000000",
            "tran_proc_ts": "2022-07-18-10.30.00.000000",
        }
        record = _format_transaction_record(row)
        assert len(record) == 350

    def test_write_and_read_back(self, tmp_path):
        tcatbal_df, xref_df, account_df, discgrp_df = _build_dfs()
        _, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        out_file = tmp_path / "SYSTRAN.dat"
        write_transaction_file(tran_df, out_file)
        lines = out_file.read_text().splitlines()
        assert len(lines) == 1
        assert len(lines[0]) == 350


class TestEmptyInput:
    """No TCATBAL records -> no transactions, no account changes."""

    def test_empty_tcatbal(self):
        _, _, account_df, discgrp_df = _build_dfs()
        tcatbal_df = pd.DataFrame(
            columns=["trancat_acct_id", "trancat_type_cd",
                      "trancat_cd", "tran_cat_bal"]
        )
        xref_df = pd.DataFrame(
            columns=["xref_card_num", "xref_cust_id", "xref_acct_id"]
        )
        updated, tran_df = compute_interest(
            tcatbal_df, xref_df, account_df, discgrp_df,
            PARM_DATE, timestamp=FIXED_TS,
        )
        assert len(tran_df) == 0
        assert Decimal(str(updated.iloc[0]["acct_curr_bal"])) == Decimal(
            "5000.00"
        )
