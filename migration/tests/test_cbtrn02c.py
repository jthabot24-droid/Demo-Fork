"""Tests for CBTRN02C POSTTRAN batch posting migration.

Covers:
  - Valid transaction posting (updates account, tcatbal, writes tran record)
  - Rejection reason 100 (card not in xref)
  - Rejection reason 101 (account not found)
  - Rejection reason 102 (over credit limit)
  - Rejection reason 103 (expired account)
  - Credit vs debit cycle-bucket routing
  - Category-balance create vs update
  - Return-code 4 when rejects > 0
"""

import os
import tempfile
from decimal import Decimal

import pytest

from migration.src.copybook_records import (
    DalytranRecord, AccountRecord, CardXrefRecord, TranCatBalRecord,
    serialize_dalytran, serialize_account, serialize_card_xref,
    serialize_tran_cat_bal, format_str, _trunc2,
)
from migration.src.cbtrn02c_pyspark import (
    validate_transaction, post_transaction, run_posttran_pure,
    run_posttran, make_db2_timestamp,
)

FIXED_TS = "2024-01-15-10.30.00.000000"


def _make_dalytran(card_num="1234567890123456", amt=Decimal("100.00"),
                   orig_ts="2023-06-15 12:00:00.000000",
                   type_cd="01", cat_cd="0001"):
    return DalytranRecord(
        dalytran_id="0000000000000001",
        dalytran_type_cd=type_cd,
        dalytran_cat_cd=cat_cd,
        dalytran_source="POS TERM  ",
        dalytran_desc=format_str("Test purchase", 100),
        dalytran_amt=amt,
        dalytran_merchant_id="000000001",
        dalytran_merchant_name=format_str("Test Merchant", 50),
        dalytran_merchant_city=format_str("Test City", 50),
        dalytran_merchant_zip=format_str("12345", 10),
        dalytran_card_num=format_str(card_num, 16),
        dalytran_orig_ts=format_str(orig_ts, 26),
        dalytran_proc_ts=format_str("", 26),
    )


def _make_xref(card_num="1234567890123456", acct_id="00000000099"):
    return CardXrefRecord(
        xref_card_num=format_str(card_num, 16),
        xref_cust_id="000000001",
        xref_acct_id=acct_id,
    )


def _make_account(acct_id="00000000099", bal=Decimal("500.00"),
                  limit=Decimal("2000.00"), exp_date="2025-12-31",
                  cyc_credit=Decimal("0.00"), cyc_debit=Decimal("0.00")):
    return AccountRecord(
        acct_id=acct_id,
        acct_active_status="Y",
        acct_curr_bal=bal,
        acct_credit_limit=limit,
        acct_cash_credit_limit=Decimal("1000.00"),
        acct_open_date="2020-01-01",
        acct_expiraion_date=exp_date,
        acct_reissue_date="2020-01-01",
        acct_curr_cyc_credit=cyc_credit,
        acct_curr_cyc_debit=cyc_debit,
        acct_addr_zip=format_str("12345", 10),
        acct_group_id=format_str("A000000000", 10),
    )


# -----------------------------------------------------------------------
# Validation tests
# -----------------------------------------------------------------------

class TestValidation:
    def test_valid_transaction(self):
        dt = _make_dalytran()
        xref_map = {dt.dalytran_card_num: _make_xref()}
        acct = _make_account()
        acct_map = {acct.acct_id: acct}
        reason, desc, _, _ = validate_transaction(dt, xref_map, acct_map)
        assert reason == 0

    def test_reject_100_card_not_found(self):
        dt = _make_dalytran(card_num="9999999999999999")
        reason, desc, _, _ = validate_transaction(dt, {}, {})
        assert reason == 100
        assert "CARD" in desc.upper()

    def test_reject_101_account_not_found(self):
        dt = _make_dalytran()
        xref = _make_xref(acct_id="00000099999")
        xref_map = {dt.dalytran_card_num: xref}
        reason, desc, _, _ = validate_transaction(dt, xref_map, {})
        assert reason == 101

    def test_reject_102_overlimit(self):
        dt = _make_dalytran(amt=Decimal("3000.00"))
        xref = _make_xref()
        acct = _make_account(limit=Decimal("2000.00"),
                             cyc_credit=Decimal("0.00"))
        xref_map = {dt.dalytran_card_num: xref}
        acct_map = {acct.acct_id: acct}
        reason, desc, _, _ = validate_transaction(dt, xref_map, acct_map)
        assert reason == 102

    def test_reject_103_expired(self):
        dt = _make_dalytran(orig_ts="2026-01-01 12:00:00.000000")
        xref = _make_xref()
        acct = _make_account(exp_date="2025-12-31")
        xref_map = {dt.dalytran_card_num: xref}
        acct_map = {acct.acct_id: acct}
        reason, desc, _, _ = validate_transaction(dt, xref_map, acct_map)
        assert reason == 103

    def test_103_overrides_102(self):
        """COBOL uses last-failure-wins: 103 check runs after 102."""
        dt = _make_dalytran(amt=Decimal("3000.00"),
                            orig_ts="2026-01-01 12:00:00.000000")
        xref = _make_xref()
        acct = _make_account(limit=Decimal("2000.00"), exp_date="2025-12-31")
        xref_map = {dt.dalytran_card_num: xref}
        acct_map = {acct.acct_id: acct}
        reason, _, _, _ = validate_transaction(dt, xref_map, acct_map)
        assert reason == 103


# -----------------------------------------------------------------------
# Posting tests
# -----------------------------------------------------------------------

class TestPosting:
    def test_post_valid_credit(self):
        dt = _make_dalytran(amt=Decimal("100.00"))
        xref = _make_xref()
        acct = _make_account(bal=Decimal("500.00"))
        tcatbal_map = {}
        tran, acct_upd, tcatbal, created = post_transaction(
            dt, xref, acct, tcatbal_map, FIXED_TS)
        assert tran.tran_amt == Decimal("100.00")
        assert acct_upd.acct_curr_bal == Decimal("600.00")
        assert acct_upd.acct_curr_cyc_credit == Decimal("100.00")
        assert acct_upd.acct_curr_cyc_debit == Decimal("0.00")
        assert created is True
        assert tcatbal.tran_cat_bal == Decimal("100.00")

    def test_post_valid_debit(self):
        dt = _make_dalytran(amt=Decimal("-50.00"))
        xref = _make_xref()
        acct = _make_account(bal=Decimal("500.00"))
        tcatbal_map = {}
        tran, acct_upd, tcatbal, created = post_transaction(
            dt, xref, acct, tcatbal_map, FIXED_TS)
        assert acct_upd.acct_curr_bal == Decimal("450.00")
        assert acct_upd.acct_curr_cyc_credit == Decimal("0.00")
        assert acct_upd.acct_curr_cyc_debit == Decimal("-50.00")

    def test_tcatbal_update_existing(self):
        dt = _make_dalytran(amt=Decimal("200.00"), type_cd="01", cat_cd="0001")
        xref = _make_xref()
        acct = _make_account()
        existing = TranCatBalRecord(
            trancat_acct_id=xref.xref_acct_id,
            trancat_type_cd="01",
            trancat_cd="0001",
            tran_cat_bal=Decimal("300.00"),
        )
        tcatbal_map = {(xref.xref_acct_id, "01", "0001"): existing}
        _, _, tcatbal, created = post_transaction(
            dt, xref, acct, tcatbal_map, FIXED_TS)
        assert created is False
        assert tcatbal.tran_cat_bal == Decimal("500.00")

    def test_proc_timestamp_set(self):
        dt = _make_dalytran()
        xref = _make_xref()
        acct = _make_account()
        tran, _, _, _ = post_transaction(dt, xref, acct, {}, FIXED_TS)
        assert FIXED_TS in tran.tran_proc_ts


# -----------------------------------------------------------------------
# End-to-end pure-Python tests
# -----------------------------------------------------------------------

class TestRunPosttranPure:
    def test_mixed_valid_and_reject(self):
        # Valid transaction
        dt_valid = _make_dalytran(card_num="1234567890123456",
                                 amt=Decimal("50.00"))
        # Invalid (card not found)
        dt_invalid = _make_dalytran(card_num="0000000000000000",
                                   amt=Decimal("10.00"))
        xref = _make_xref(card_num="1234567890123456")
        acct = _make_account()
        tcatbal = TranCatBalRecord(
            trancat_acct_id=acct.acct_id,
            trancat_type_cd="01",
            trancat_cd="0001",
            tran_cat_bal=Decimal("0.00"),
        )

        result = run_posttran_pure(
            dalytran_lines=[serialize_dalytran(dt_valid),
                            serialize_dalytran(dt_invalid)],
            xref_lines=[serialize_card_xref(xref)],
            account_lines=[serialize_account(acct)],
            tcatbal_lines=[serialize_tran_cat_bal(tcatbal)],
            timestamp_override=FIXED_TS,
        )

        assert result.transaction_count == 2
        assert result.reject_count == 1
        assert result.return_code == 4
        assert len(result.posted_records) == 1
        assert len(result.reject_records) == 1

    def test_all_valid_return_code_0(self):
        dt = _make_dalytran()
        xref = _make_xref()
        acct = _make_account()

        result = run_posttran_pure(
            dalytran_lines=[serialize_dalytran(dt)],
            xref_lines=[serialize_card_xref(xref)],
            account_lines=[serialize_account(acct)],
            tcatbal_lines=[],
            timestamp_override=FIXED_TS,
        )

        assert result.return_code == 0
        assert result.reject_count == 0


# -----------------------------------------------------------------------
# Spark integration test
# -----------------------------------------------------------------------

class TestRunPosttranSpark:
    def test_with_spark(self, spark, tmp_path):
        dt = _make_dalytran()
        xref = _make_xref()
        acct = _make_account()

        dt_file = tmp_path / "dalytran.txt"
        xref_file = tmp_path / "cardxref.txt"
        acct_file = tmp_path / "acctdata.txt"
        tcat_file = tmp_path / "tcatbal.txt"
        posted_file = tmp_path / "posted.txt"
        rejects_file = tmp_path / "rejects.txt"

        dt_file.write_text(serialize_dalytran(dt) + "\n")
        xref_file.write_text(serialize_card_xref(xref) + "\n")
        acct_file.write_text(serialize_account(acct) + "\n")
        tcat_file.write_text("")

        result = run_posttran(
            dailytran_path=str(dt_file),
            xref_path=str(xref_file),
            account_path=str(acct_file),
            tcatbal_path=str(tcat_file),
            posted_output_path=str(posted_file),
            rejects_output_path=str(rejects_file),
            spark=spark,
            timestamp_override=FIXED_TS,
        )

        assert result.transaction_count == 1
        assert result.return_code == 0
        assert posted_file.exists()
        assert len(posted_file.read_text().strip().splitlines()) == 1
