"""Tests for CBACT04C INTCALC interest calculator migration.

Covers:
  - Numerically identical interest amounts (truncation vs rounding)
  - Zero-rate skip
  - DEFAULT-group fallback
  - Account update (balance + zero cycle)
  - Interest transaction record fields
  - Integration test with sample data files
"""

import os
from decimal import Decimal

import pytest

from migration.src.copybook_records import (
    TranCatBalRecord, DisGroupRecord, AccountRecord, CardXrefRecord,
    format_str, _trunc2,
)
from migration.src.cbact04c import (
    compute_monthly_interest, _lookup_interest_rate,
    run_intcalc_pure, run_intcalc,
)


FIXED_TS = "2022-07-18-00.00.00.000000"


def _discgrp(group_id, type_cd, cat_cd, rate):
    return DisGroupRecord(
        dis_acct_group_id=format_str(group_id, 10),
        dis_tran_type_cd=type_cd,
        dis_tran_cat_cd=cat_cd,
        dis_int_rate=Decimal(str(rate)),
    )


def _tcatbal(acct_id, type_cd, cat_cd, bal):
    return TranCatBalRecord(
        trancat_acct_id=acct_id,
        trancat_type_cd=type_cd,
        trancat_cd=cat_cd,
        tran_cat_bal=Decimal(str(bal)),
    )


def _account(acct_id, bal=Decimal("1000.00")):
    return AccountRecord(
        acct_id=acct_id,
        acct_active_status="Y",
        acct_curr_bal=bal,
        acct_credit_limit=Decimal("5000.00"),
        acct_cash_credit_limit=Decimal("2000.00"),
        acct_open_date="2020-01-01",
        acct_expiraion_date="2025-12-31",
        acct_reissue_date="2020-01-01",
        acct_curr_cyc_credit=Decimal("200.00"),
        acct_curr_cyc_debit=Decimal("100.00"),
        acct_addr_zip=format_str("12345", 10),
        acct_group_id=format_str("TESTGRP", 10),
    )


def _xref(acct_id, card_num="1234567890123456"):
    return CardXrefRecord(
        xref_card_num=format_str(card_num, 16),
        xref_cust_id="000000001",
        xref_acct_id=acct_id,
    )


# -----------------------------------------------------------------------
# Unit tests
# -----------------------------------------------------------------------

class TestComputeInterest:
    def test_basic_calculation(self):
        # 1000.00 * 15.00 / 1200 = 12.50 (exact)
        result = compute_monthly_interest(Decimal("1000.00"), Decimal("15.00"))
        assert result == Decimal("12.50")

    def test_truncation_not_rounding(self):
        # 1000.00 * 18.99 / 1200 = 15.825 -> truncate -> 15.82 (not 15.83)
        result = compute_monthly_interest(Decimal("1000.00"), Decimal("18.99"))
        assert result == Decimal("15.82")

    def test_truncation_edge_case(self):
        # 333.33 * 10.00 / 1200 = 2.77775 -> truncate -> 2.77
        result = compute_monthly_interest(Decimal("333.33"), Decimal("10.00"))
        assert result == Decimal("2.77")

    def test_negative_balance(self):
        # -500.00 * 15.00 / 1200 = -6.25
        result = compute_monthly_interest(Decimal("-500.00"), Decimal("15.00"))
        assert result == Decimal("-6.25")

    def test_zero_balance(self):
        result = compute_monthly_interest(Decimal("0.00"), Decimal("15.00"))
        assert result == Decimal("0.00")

    def test_large_balance_truncation(self):
        # 99999999.99 * 25.00 / 1200 = 2083333.33312... -> 2083333.33
        result = compute_monthly_interest(
            Decimal("99999999.99"), Decimal("25.00"))
        assert result == Decimal("2083333.33")


class TestLookupInterestRate:
    def test_exact_match(self):
        discgrp_map = {
            (format_str("TESTGRP", 10), "01", "0001"): _discgrp("TESTGRP", "01", "0001", "15.00"),
        }
        rate = _lookup_interest_rate(
            format_str("TESTGRP", 10), "01", "0001", discgrp_map)
        assert rate == Decimal("15.00")

    def test_default_fallback(self):
        discgrp_map = {
            (format_str("DEFAULT", 10), "01", "0001"): _discgrp("DEFAULT", "01", "0001", "12.00"),
        }
        rate = _lookup_interest_rate(
            format_str("MISSING", 10), "01", "0001", discgrp_map)
        assert rate == Decimal("12.00")

    def test_no_match_returns_zero(self):
        rate = _lookup_interest_rate(
            format_str("NOPE", 10), "99", "9999", {})
        assert rate == Decimal("0.00")


# -----------------------------------------------------------------------
# Integration tests (pure Python)
# -----------------------------------------------------------------------

class TestRunIntcalcPure:
    def test_single_account_single_category(self):
        acct_id = "00000000099"
        tcatbals = [_tcatbal(acct_id, "01", "0001", "1000.00")]
        discgrps = [_discgrp("TESTGRP", "01", "0001", "15.00")]
        accounts = [_account(acct_id, bal=Decimal("500.00"))]
        xrefs = [_xref(acct_id)]

        result = run_intcalc_pure(
            tcatbals, discgrps, accounts, xrefs,
            parm_date="2022071800", timestamp_override=FIXED_TS)

        assert result.record_count == 1
        assert len(result.interest_transactions) == 1

        tran = result.interest_transactions[0]
        assert tran.tran_amt == Decimal("12.50")
        assert tran.tran_type_cd == "01"
        assert tran.tran_cat_cd == "0005"
        assert "Int. for a/c" in tran.tran_desc
        assert tran.tran_source.strip() == "System"

        # Account updated: balance += interest, cycle zeroed
        updated_acct = result.updated_accounts[acct_id]
        assert updated_acct.acct_curr_bal == Decimal("512.50")
        assert updated_acct.acct_curr_cyc_credit == Decimal("0.00")
        assert updated_acct.acct_curr_cyc_debit == Decimal("0.00")

    def test_zero_rate_skip(self):
        acct_id = "00000000099"
        tcatbals = [_tcatbal(acct_id, "02", "0001", "5000.00")]
        discgrps = [_discgrp("TESTGRP", "02", "0001", "0.00")]
        accounts = [_account(acct_id)]
        xrefs = [_xref(acct_id)]

        result = run_intcalc_pure(
            tcatbals, discgrps, accounts, xrefs,
            parm_date="2022071800", timestamp_override=FIXED_TS)

        assert len(result.interest_transactions) == 0
        # Account still gets zeroed cycle even with no interest
        updated = result.updated_accounts[acct_id]
        assert updated.acct_curr_cyc_credit == Decimal("0.00")

    def test_multiple_categories_same_account(self):
        acct_id = "00000000099"
        tcatbals = [
            _tcatbal(acct_id, "01", "0001", "1000.00"),
            _tcatbal(acct_id, "01", "0002", "2000.00"),
        ]
        discgrps = [
            _discgrp("TESTGRP", "01", "0001", "12.00"),
            _discgrp("TESTGRP", "01", "0002", "18.00"),
        ]
        accounts = [_account(acct_id, bal=Decimal("100.00"))]
        xrefs = [_xref(acct_id)]

        result = run_intcalc_pure(
            tcatbals, discgrps, accounts, xrefs,
            parm_date="2022071800", timestamp_override=FIXED_TS)

        assert len(result.interest_transactions) == 2
        # 1000*12/1200=10.00, 2000*18/1200=30.00 -> total=40.00
        total = sum(t.tran_amt for t in result.interest_transactions)
        assert total == Decimal("40.00")
        assert result.updated_accounts[acct_id].acct_curr_bal == Decimal("140.00")

    def test_tran_id_format(self):
        acct_id = "00000000099"
        tcatbals = [_tcatbal(acct_id, "01", "0001", "100.00")]
        discgrps = [_discgrp("TESTGRP", "01", "0001", "12.00")]
        accounts = [_account(acct_id)]
        xrefs = [_xref(acct_id)]

        result = run_intcalc_pure(
            tcatbals, discgrps, accounts, xrefs,
            parm_date="2022071800", timestamp_override=FIXED_TS)

        tran = result.interest_transactions[0]
        assert tran.tran_id.startswith("2022071800")
        assert "000001" in tran.tran_id

    def test_default_group_fallback(self):
        acct_id = "00000000099"
        acct = _account(acct_id)
        acct.acct_group_id = format_str("NOEXIST", 10)
        tcatbals = [_tcatbal(acct_id, "01", "0001", "1000.00")]
        discgrps = [_discgrp("DEFAULT", "01", "0001", "6.00")]
        xrefs = [_xref(acct_id)]

        result = run_intcalc_pure(
            tcatbals, discgrps, [acct], xrefs,
            parm_date="2022071800", timestamp_override=FIXED_TS)

        assert len(result.interest_transactions) == 1
        assert result.interest_transactions[0].tran_amt == Decimal("5.00")


class TestRunIntcalcWithFiles:
    def test_with_sample_data(self, data_dir):
        """Run against actual app/data/ASCII files."""
        result = run_intcalc(
            tcatbal_path=os.path.join(data_dir, "tcatbal.txt"),
            discgrp_path=os.path.join(data_dir, "discgrp.txt"),
            account_path=os.path.join(data_dir, "acctdata.txt"),
            xref_path=os.path.join(data_dir, "cardxref.txt"),
            parm_date="2022071800",
            timestamp_override=FIXED_TS,
        )

        assert result.record_count == 50
        # All accounts should have had their cycles zeroed
        for acct in result.updated_accounts.values():
            assert acct.acct_curr_cyc_credit == Decimal("0.00")
            assert acct.acct_curr_cyc_debit == Decimal("0.00")
