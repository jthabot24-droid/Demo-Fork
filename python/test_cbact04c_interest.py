"""
Unit tests for the CBACT04C interest-calculation migration.

Covers:
* ``compute_interest`` formula with COBOL truncation semantics
* Disclosure-group lookup with DEFAULT-rate fallback
* Transaction-record field mappings (1300-B-WRITE-TX)
* Full ``run_interest_calculation`` loop (account grouping, balance update)
* Error / abend paths
"""

from decimal import Decimal

import pandas as pd
import pytest

from cbact04c_interest import (
    CBACT04CAbend,
    TransactionRecord,
    compute_interest,
    run_interest_calculation,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FIXED_TS = "2026-06-15-10.30.00.000000"
PARM_DATE = "2026-06-15"


def _fixed_timestamp() -> str:
    return FIXED_TS


# ---------------------------------------------------------------------------
# Fixtures
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
                "acct_active_status": "Y",
                "acct_curr_bal": Decimal("1000.00"),
                "acct_credit_limit": Decimal("5000.00"),
                "acct_cash_credit_limit": Decimal("1000.00"),
                "acct_open_date": "2020-01-01",
                "acct_expiration_date": "2027-12-31",
                "acct_reissue_date": "",
                "acct_curr_cyc_credit": Decimal("500.00"),
                "acct_curr_cyc_debit": Decimal("200.00"),
                "acct_addr_zip": "98101",
                "acct_group_id": "PREMIUM",
            },
            {
                "acct_id": 80000000002,
                "acct_active_status": "Y",
                "acct_curr_bal": Decimal("2500.00"),
                "acct_credit_limit": Decimal("10000.00"),
                "acct_cash_credit_limit": Decimal("2000.00"),
                "acct_open_date": "2019-06-01",
                "acct_expiration_date": "2028-06-30",
                "acct_reissue_date": "",
                "acct_curr_cyc_credit": Decimal("300.00"),
                "acct_curr_cyc_debit": Decimal("100.00"),
                "acct_addr_zip": "10001",
                "acct_group_id": "STANDARD",
            },
        ]
    )


@pytest.fixture()
def discgrp_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "dis_acct_group_id": "PREMIUM",
                "dis_tran_type_cd": "01",
                "dis_tran_cat_cd": 1001,
                "dis_int_rate": Decimal("18.00"),
            },
            {
                "dis_acct_group_id": "PREMIUM",
                "dis_tran_type_cd": "01",
                "dis_tran_cat_cd": 1002,
                "dis_int_rate": Decimal("21.50"),
            },
            {
                "dis_acct_group_id": "STANDARD",
                "dis_tran_type_cd": "01",
                "dis_tran_cat_cd": 1001,
                "dis_int_rate": Decimal("24.00"),
            },
            {
                "dis_acct_group_id": "DEFAULT",
                "dis_tran_type_cd": "01",
                "dis_tran_cat_cd": 9999,
                "dis_int_rate": Decimal("19.99"),
            },
            {
                "dis_acct_group_id": "STANDARD",
                "dis_tran_type_cd": "02",
                "dis_tran_cat_cd": 2001,
                "dis_int_rate": Decimal("0.00"),
            },
        ]
    )


# ---------------------------------------------------------------------------
# 1300-COMPUTE-INTEREST formula
# ---------------------------------------------------------------------------


class TestComputeInterest:
    """Verify (TRAN-CAT-BAL * DIS-INT-RATE) / 1200 with COBOL truncation."""

    def test_exact_division(self):
        # 1000.00 * 18.00 / 1200 = 15.00
        assert compute_interest(Decimal("1000.00"), Decimal("18.00")) == Decimal("15.00")

    def test_truncation_not_rounding(self):
        # 1000.00 * 19.99 / 1200 = 16.6583... → truncated to 16.65
        result = compute_interest(Decimal("1000.00"), Decimal("19.99"))
        assert result == Decimal("16.65")

    def test_truncation_negative(self):
        # -500.00 * 19.99 / 1200 = -8.3291... → truncated toward zero = -8.32
        result = compute_interest(Decimal("-500.00"), Decimal("19.99"))
        assert result == Decimal("-8.32")

    def test_negative_balance_exact(self):
        # -500.00 * 12.00 / 1200 = -5.00
        assert compute_interest(Decimal("-500.00"), Decimal("12.00")) == Decimal("-5.00")

    def test_zero_balance(self):
        assert compute_interest(Decimal("0.00"), Decimal("18.00")) == Decimal("0.00")

    def test_large_balance(self):
        # 999999999.99 * 24.00 / 1200 = 19999999.99 (exact: 19999999.9998)
        result = compute_interest(Decimal("999999999.99"), Decimal("24.00"))
        assert result == Decimal("19999999.99")

    def test_small_balance_truncates_to_zero(self):
        # 0.01 * 1.00 / 1200 = 0.00000833... → truncated to 0.00
        result = compute_interest(Decimal("0.01"), Decimal("1.00"))
        assert result == Decimal("0.00")

    def test_accumulation(self):
        # Two category balances for the same account:
        # cat1: 5000.00 * 18.00 / 1200 = 75.00
        # cat2: 3000.00 * 21.50 / 1200 = 53.75
        # total interest = 128.75
        int1 = compute_interest(Decimal("5000.00"), Decimal("18.00"))
        int2 = compute_interest(Decimal("3000.00"), Decimal("21.50"))
        assert int1 == Decimal("75.00")
        assert int2 == Decimal("53.75")
        assert int1 + int2 == Decimal("128.75")


# ---------------------------------------------------------------------------
# 1200-GET-INTEREST-RATE with DEFAULT fallback
# ---------------------------------------------------------------------------


class TestDisclosureGroupLookup:
    """Test disclosure-group rate lookup and DEFAULT fallback."""

    def test_direct_lookup(self, discgrp_df):
        from cbact04c_interest import _lookup_discgrp

        rate = _lookup_discgrp(discgrp_df, "PREMIUM", "01", 1001)
        assert rate == Decimal("18.00")

    def test_default_fallback(self, discgrp_df):
        from cbact04c_interest import _lookup_discgrp

        # "UNKNOWN" group, type "01", cat 9999 → not found → DEFAULT fallback
        rate = _lookup_discgrp(discgrp_df, "UNKNOWN", "01", 9999)
        assert rate == Decimal("19.99")

    def test_no_match_raises_abend(self, discgrp_df):
        from cbact04c_interest import _lookup_discgrp

        with pytest.raises(CBACT04CAbend, match="DEFAULT DISCLOSURE GROUP"):
            _lookup_discgrp(discgrp_df, "UNKNOWN", "99", 8888)

    def test_zero_rate_returned(self, discgrp_df):
        from cbact04c_interest import _lookup_discgrp

        rate = _lookup_discgrp(discgrp_df, "STANDARD", "02", 2001)
        assert rate == Decimal("0.00")


# ---------------------------------------------------------------------------
# 1300-B-WRITE-TX field mappings
# ---------------------------------------------------------------------------


class TestTransactionFieldMapping:
    """Verify the generated interest transaction record fields."""

    def test_tran_id_format(self):
        from cbact04c_interest import _build_transaction_record

        tran = _build_transaction_record(
            "2026-06-15", 1, Decimal("15.00"), 80000000001,
            "4111111111111111", FIXED_TS,
        )
        assert tran.tran_id == "2026-06-15000001"
        assert len(tran.tran_id) == 16

    def test_tran_id_suffix_increment(self):
        from cbact04c_interest import _build_transaction_record

        tran = _build_transaction_record(
            "2026-06-15", 42, Decimal("10.00"), 80000000001,
            "4111111111111111", FIXED_TS,
        )
        assert tran.tran_id == "2026-06-15000042"

    def test_fixed_fields(self):
        from cbact04c_interest import _build_transaction_record

        tran = _build_transaction_record(
            "2026-06-15", 1, Decimal("15.00"), 80000000001,
            "4111111111111111", FIXED_TS,
        )
        assert tran.tran_type_cd == "01"
        assert tran.tran_cat_cd == 5
        assert tran.tran_source == "System"
        assert tran.tran_merchant_id == 0
        assert tran.tran_merchant_name == ""
        assert tran.tran_merchant_city == ""
        assert tran.tran_merchant_zip == ""

    def test_tran_desc(self):
        from cbact04c_interest import _build_transaction_record

        tran = _build_transaction_record(
            "2026-06-15", 1, Decimal("15.00"), 80000000001,
            "4111111111111111", FIXED_TS,
        )
        assert tran.tran_desc == "Int. for a/c 80000000001"

    def test_tran_amt(self):
        from cbact04c_interest import _build_transaction_record

        tran = _build_transaction_record(
            "2026-06-15", 1, Decimal("53.75"), 80000000001,
            "4111111111111111", FIXED_TS,
        )
        assert tran.tran_amt == Decimal("53.75")

    def test_card_num(self):
        from cbact04c_interest import _build_transaction_record

        tran = _build_transaction_record(
            "2026-06-15", 1, Decimal("15.00"), 80000000001,
            "4111111111111111", FIXED_TS,
        )
        assert tran.tran_card_num == "4111111111111111"

    def test_timestamps(self):
        from cbact04c_interest import _build_transaction_record

        tran = _build_transaction_record(
            "2026-06-15", 1, Decimal("15.00"), 80000000001,
            "4111111111111111", FIXED_TS,
        )
        assert tran.tran_orig_ts == FIXED_TS
        assert tran.tran_proc_ts == FIXED_TS


# ---------------------------------------------------------------------------
# Full run_interest_calculation (integration)
# ---------------------------------------------------------------------------


class TestRunSingleAccount:
    """Single account with multiple category balances."""

    def test_two_categories(self, xref_df, account_df, discgrp_df):
        tcatbal_df = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 1001,
                    "tran_cat_bal": Decimal("5000.00"),
                },
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 1002,
                    "tran_cat_bal": Decimal("3000.00"),
                },
            ]
        )

        txns, updated_accts = run_interest_calculation(
            tcatbal_df, xref_df, discgrp_df, account_df, PARM_DATE,
            timestamp_fn=_fixed_timestamp,
        )

        # cat 1001: 5000.00 * 18.00 / 1200 = 75.00
        # cat 1002: 3000.00 * 21.50 / 1200 = 53.75
        assert len(txns) == 2
        assert txns[0].tran_amt == Decimal("75.00")
        assert txns[1].tran_amt == Decimal("53.75")

        # Total interest = 75.00 + 53.75 = 128.75
        # Account balance updated: 1000.00 + 128.75 = 1128.75
        acct = updated_accts.loc[updated_accts["acct_id"] == 80000000001].iloc[0]
        assert Decimal(str(acct["acct_curr_bal"])) == Decimal("1128.75")
        assert Decimal(str(acct["acct_curr_cyc_credit"])) == Decimal("0.00")
        assert Decimal(str(acct["acct_curr_cyc_debit"])) == Decimal("0.00")

    def test_tran_id_suffix_increments(self, xref_df, account_df, discgrp_df):
        tcatbal_df = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 1001,
                    "tran_cat_bal": Decimal("1000.00"),
                },
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 1002,
                    "tran_cat_bal": Decimal("2000.00"),
                },
            ]
        )

        txns, _ = run_interest_calculation(
            tcatbal_df, xref_df, discgrp_df, account_df, PARM_DATE,
            timestamp_fn=_fixed_timestamp,
        )

        assert txns[0].tran_id == "2026-06-15000001"
        assert txns[1].tran_id == "2026-06-15000002"


class TestRunMultipleAccounts:
    """Multiple accounts -- verify grouping and per-account balance update."""

    def test_two_accounts(self, xref_df, account_df, discgrp_df):
        tcatbal_df = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 1001,
                    "tran_cat_bal": Decimal("5000.00"),
                },
                {
                    "trancat_acct_id": 80000000002,
                    "trancat_type_cd": "01",
                    "trancat_cd": 1001,
                    "tran_cat_bal": Decimal("6000.00"),
                },
            ]
        )

        txns, updated_accts = run_interest_calculation(
            tcatbal_df, xref_df, discgrp_df, account_df, PARM_DATE,
            timestamp_fn=_fixed_timestamp,
        )

        assert len(txns) == 2

        # Acct 1: 5000.00 * 18.00 / 1200 = 75.00 → bal 1000 + 75 = 1075
        assert txns[0].tran_amt == Decimal("75.00")
        assert txns[0].tran_card_num == "4111111111111111"
        acct1 = updated_accts.loc[updated_accts["acct_id"] == 80000000001].iloc[0]
        assert Decimal(str(acct1["acct_curr_bal"])) == Decimal("1075.00")

        # Acct 2: 6000.00 * 24.00 / 1200 = 120.00 → bal 2500 + 120 = 2620
        assert txns[1].tran_amt == Decimal("120.00")
        assert txns[1].tran_card_num == "4222222222222222"
        acct2 = updated_accts.loc[updated_accts["acct_id"] == 80000000002].iloc[0]
        assert Decimal(str(acct2["acct_curr_bal"])) == Decimal("2620.00")

    def test_tranid_suffix_global_across_accounts(
        self, xref_df, account_df, discgrp_df
    ):
        tcatbal_df = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 1001,
                    "tran_cat_bal": Decimal("1000.00"),
                },
                {
                    "trancat_acct_id": 80000000002,
                    "trancat_type_cd": "01",
                    "trancat_cd": 1001,
                    "tran_cat_bal": Decimal("1000.00"),
                },
            ]
        )

        txns, _ = run_interest_calculation(
            tcatbal_df, xref_df, discgrp_df, account_df, PARM_DATE,
            timestamp_fn=_fixed_timestamp,
        )

        assert txns[0].tran_id == "2026-06-15000001"
        assert txns[1].tran_id == "2026-06-15000002"


class TestDefaultRateFallback:
    """DEFAULT disclosure-group rate used when account group not found."""

    def test_unknown_group_uses_default(self, xref_df, discgrp_df):
        account_df = pd.DataFrame(
            [
                {
                    "acct_id": 80000000001,
                    "acct_active_status": "Y",
                    "acct_curr_bal": Decimal("0.00"),
                    "acct_credit_limit": Decimal("5000.00"),
                    "acct_cash_credit_limit": Decimal("1000.00"),
                    "acct_open_date": "2020-01-01",
                    "acct_expiration_date": "2027-12-31",
                    "acct_reissue_date": "",
                    "acct_curr_cyc_credit": Decimal("0.00"),
                    "acct_curr_cyc_debit": Decimal("0.00"),
                    "acct_addr_zip": "98101",
                    "acct_group_id": "UNKNOWN_GROUP",
                },
            ]
        )

        tcatbal_df = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 9999,
                    "tran_cat_bal": Decimal("1000.00"),
                },
            ]
        )

        txns, updated_accts = run_interest_calculation(
            tcatbal_df, xref_df, discgrp_df, account_df, PARM_DATE,
            timestamp_fn=_fixed_timestamp,
        )

        # DEFAULT rate 19.99: 1000.00 * 19.99 / 1200 = 16.6583... → 16.65
        assert len(txns) == 1
        assert txns[0].tran_amt == Decimal("16.65")

        acct = updated_accts.loc[updated_accts["acct_id"] == 80000000001].iloc[0]
        assert Decimal(str(acct["acct_curr_bal"])) == Decimal("16.65")


class TestZeroRateSkipsTransaction:
    """When DIS-INT-RATE = 0, no interest transaction is generated."""

    def test_zero_rate(self, xref_df, account_df, discgrp_df):
        tcatbal_df = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000002,
                    "trancat_type_cd": "02",
                    "trancat_cd": 2001,
                    "tran_cat_bal": Decimal("5000.00"),
                },
            ]
        )

        txns, updated_accts = run_interest_calculation(
            tcatbal_df, xref_df, discgrp_df, account_df, PARM_DATE,
            timestamp_fn=_fixed_timestamp,
        )

        assert len(txns) == 0
        # Balance unchanged (total_int = 0)
        acct = updated_accts.loc[updated_accts["acct_id"] == 80000000002].iloc[0]
        assert Decimal(str(acct["acct_curr_bal"])) == Decimal("2500.00")


class TestEmptyInput:
    """No TCATBAL records -- no transactions, no account updates."""

    def test_empty_tcatbal(self, xref_df, account_df, discgrp_df):
        tcatbal_df = pd.DataFrame(
            columns=["trancat_acct_id", "trancat_type_cd", "trancat_cd", "tran_cat_bal"]
        )

        txns, updated_accts = run_interest_calculation(
            tcatbal_df, xref_df, discgrp_df, account_df, PARM_DATE,
            timestamp_fn=_fixed_timestamp,
        )

        assert txns == []
        acct1 = updated_accts.loc[updated_accts["acct_id"] == 80000000001].iloc[0]
        assert Decimal(str(acct1["acct_curr_bal"])) == Decimal("1000.00")


# ---------------------------------------------------------------------------
# Error / abend paths
# ---------------------------------------------------------------------------


class TestAbendPaths:
    """CEE3ABD abend mapped to CBACT04CAbend."""

    def test_missing_account_raises(self, xref_df, discgrp_df):
        account_df = pd.DataFrame(
            columns=[
                "acct_id", "acct_active_status", "acct_curr_bal",
                "acct_credit_limit", "acct_cash_credit_limit",
                "acct_open_date", "acct_expiration_date", "acct_reissue_date",
                "acct_curr_cyc_credit", "acct_curr_cyc_debit",
                "acct_addr_zip", "acct_group_id",
            ]
        )
        tcatbal_df = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 99999999999,
                    "trancat_type_cd": "01",
                    "trancat_cd": 1001,
                    "tran_cat_bal": Decimal("100.00"),
                },
            ]
        )

        with pytest.raises(CBACT04CAbend, match="ACCOUNT NOT FOUND"):
            run_interest_calculation(
                tcatbal_df, xref_df, discgrp_df, account_df, PARM_DATE,
                timestamp_fn=_fixed_timestamp,
            )

    def test_missing_xref_raises(self, account_df, discgrp_df):
        xref_df = pd.DataFrame(columns=["xref_card_num", "xref_acct_id"])
        tcatbal_df = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 1001,
                    "tran_cat_bal": Decimal("100.00"),
                },
            ]
        )

        with pytest.raises(CBACT04CAbend, match="XREF"):
            run_interest_calculation(
                tcatbal_df, xref_df, discgrp_df, account_df, PARM_DATE,
                timestamp_fn=_fixed_timestamp,
            )

    def test_missing_discgrp_and_default_raises(self, xref_df, account_df):
        discgrp_df = pd.DataFrame(
            columns=[
                "dis_acct_group_id", "dis_tran_type_cd",
                "dis_tran_cat_cd", "dis_int_rate",
            ]
        )
        tcatbal_df = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 1001,
                    "tran_cat_bal": Decimal("100.00"),
                },
            ]
        )

        with pytest.raises(CBACT04CAbend, match="DEFAULT DISCLOSURE GROUP"):
            run_interest_calculation(
                tcatbal_df, xref_df, discgrp_df, account_df, PARM_DATE,
                timestamp_fn=_fixed_timestamp,
            )


# ---------------------------------------------------------------------------
# DB2 timestamp format
# ---------------------------------------------------------------------------


class TestDB2Timestamp:
    """Verify Z-GET-DB2-FORMAT-TIMESTAMP format."""

    def test_format_pattern(self):
        from cbact04c_interest import get_db2_format_timestamp

        ts = get_db2_format_timestamp()
        # YYYY-MM-DD-HH.MM.SS.cc0000
        assert len(ts) == 26
        assert ts[4] == "-"
        assert ts[7] == "-"
        assert ts[10] == "-"
        assert ts[13] == "."
        assert ts[16] == "."
        assert ts[19] == "."
        assert ts[22:26] == "0000"


# ---------------------------------------------------------------------------
# Cycle-field zeroing
# ---------------------------------------------------------------------------


class TestCycleFieldsZeroed:
    """1050-UPDATE-ACCOUNT zeros ACCT-CURR-CYC-CREDIT and ACCT-CURR-CYC-DEBIT."""

    def test_cycle_fields_reset(self, xref_df, account_df, discgrp_df):
        tcatbal_df = pd.DataFrame(
            [
                {
                    "trancat_acct_id": 80000000001,
                    "trancat_type_cd": "01",
                    "trancat_cd": 1001,
                    "tran_cat_bal": Decimal("1000.00"),
                },
            ]
        )

        _, updated_accts = run_interest_calculation(
            tcatbal_df, xref_df, discgrp_df, account_df, PARM_DATE,
            timestamp_fn=_fixed_timestamp,
        )

        acct = updated_accts.loc[updated_accts["acct_id"] == 80000000001].iloc[0]
        assert Decimal(str(acct["acct_curr_cyc_credit"])) == Decimal("0.00")
        assert Decimal(str(acct["acct_curr_cyc_debit"])) == Decimal("0.00")
        # Acct 2 was NOT processed, so its cycle fields are NOT zeroed
        acct2 = updated_accts.loc[updated_accts["acct_id"] == 80000000002].iloc[0]
        assert Decimal(str(acct2["acct_curr_cyc_credit"])) == Decimal("300.00")
        assert Decimal(str(acct2["acct_curr_cyc_debit"])) == Decimal("100.00")
