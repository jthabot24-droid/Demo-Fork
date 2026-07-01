"""
Unit tests for the PySpark POSTTRAN batch job (CBTRN02C migration).

Covers:
  - Valid transaction posting with account + category balance updates
  - Reject path 100 (invalid card number)
  - Reject path 101 (account not found)
  - Reject path 102 (overlimit transaction)
  - Reject path 103 (expired account)
  - Category-balance creation and accumulation
  - Return-code-4-on-any-reject behaviour
  - Negative-amount (payment/refund) account update logic
"""

from decimal import Decimal

import pytest
from pyspark.sql import SparkSession

from cbtrn02c_posting import (
    ACCTFILE_SCHEMA,
    DALYTRAN_SCHEMA,
    TCATBALF_SCHEMA,
    XREFFILE_SCHEMA,
    BatchResult,
    run_posttran,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXED_TIMESTAMP = "2026-07-01-10.00.00.000000"


@pytest.fixture(scope="session")
def spark():
    session = (
        SparkSession.builder.master("local[1]")
        .appName("test-posttran")
        .config("spark.sql.shuffle.partitions", "1")
        .config("spark.ui.enabled", "false")
        .config("spark.driver.bindAddress", "127.0.0.1")
        .getOrCreate()
    )
    yield session
    session.stop()


# ---------------------------------------------------------------------------
# DataFrame helpers
# ---------------------------------------------------------------------------

def _make_df(spark, records, schema):
    """Create a Spark DataFrame from a list of dicts matching *schema*."""
    if not records:
        return spark.createDataFrame([], schema=schema)
    field_names = [f.name for f in schema.fields]
    tuples = [tuple(r[name] for name in field_names) for r in records]
    return spark.createDataFrame(tuples, schema=schema)


# Standard reference data shared across tests

XREF_DATA = [
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

ACCT_DATA = [
    {
        "acct_id": 80000000001,
        "acct_active_status": "Y",
        "acct_curr_bal": Decimal("500.00"),
        "acct_credit_limit": Decimal("5000.00"),
        "acct_cash_credit_limit": Decimal("1000.00"),
        "acct_open_date": "2020-01-01",
        "acct_expiration_date": "2027-12-31",
        "acct_reissue_date": "2025-01-01",
        "acct_curr_cyc_credit": Decimal("1000.00"),
        "acct_curr_cyc_debit": Decimal("200.00"),
        "acct_addr_zip": "98101",
        "acct_group_id": "GROUP001",
    },
    {
        "acct_id": 80000000002,
        "acct_active_status": "Y",
        "acct_curr_bal": Decimal("50.00"),
        "acct_credit_limit": Decimal("100.00"),
        "acct_cash_credit_limit": Decimal("50.00"),
        "acct_open_date": "2019-01-01",
        "acct_expiration_date": "2020-01-01",
        "acct_reissue_date": "",
        "acct_curr_cyc_credit": Decimal("90.00"),
        "acct_curr_cyc_debit": Decimal("0.00"),
        "acct_addr_zip": "10001",
        "acct_group_id": "GROUP002",
    },
]


def _valid_tran(**overrides):
    """Return a dict for a valid daily transaction against acct 80000000001."""
    defaults = {
        "dalytran_id": "0000000000000001",
        "dalytran_type_cd": "01",
        "dalytran_cat_cd": 5000,
        "dalytran_source": "BATCH",
        "dalytran_desc": "Test purchase",
        "dalytran_amt": Decimal("100.00"),
        "dalytran_merchant_id": 123456789,
        "dalytran_merchant_name": "Acme Corp",
        "dalytran_merchant_city": "Seattle",
        "dalytran_merchant_zip": "98101",
        "dalytran_card_num": "4111111111111111",
        "dalytran_orig_ts": "2026-06-15-00.00.00.000000",
        "dalytran_proc_ts": "2026-06-15-00.00.00.000000",
    }
    defaults.update(overrides)
    return defaults


def _run(spark, transactions, xref=None, accounts=None, tcatbal=None):
    """Convenience wrapper around run_posttran with defaults."""
    dalytran_df = _make_df(spark, transactions, DALYTRAN_SCHEMA)
    xref_df = _make_df(spark, xref or XREF_DATA, XREFFILE_SCHEMA)
    acct_df = _make_df(spark, accounts or ACCT_DATA, ACCTFILE_SCHEMA)
    tcatbal_df = _make_df(spark, tcatbal or [], TCATBALF_SCHEMA)
    return run_posttran(
        spark,
        dalytran_df,
        xref_df,
        acct_df,
        tcatbal_df,
        timestamp_fn=lambda: FIXED_TIMESTAMP,
    )


# ===================================================================
# Happy-path: valid transaction posts and updates state
# ===================================================================


class TestValidTransactionPosts:
    def test_single_valid_transaction(self, spark):
        result, posted_df, rejects_df, _, _ = _run(spark, [_valid_tran()])

        assert result.transaction_count == 1
        assert result.reject_count == 0
        assert result.return_code == 0

        posted = posted_df.collect()
        assert len(posted) == 1
        assert posted[0].tran_id == "0000000000000001"
        assert posted[0].tran_amt == Decimal("100.00")
        assert posted[0].tran_proc_ts == FIXED_TIMESTAMP

        assert rejects_df.count() == 0

    def test_account_updated_after_positive_amount(self, spark):
        result, _, _, updated_acct_df, _ = _run(
            spark, [_valid_tran(dalytran_amt=Decimal("100.00"))]
        )

        acct = updated_acct_df.filter("acct_id = 80000000001").collect()[0]
        # Original: curr_bal=500, cyc_credit=1000, cyc_debit=200
        assert acct.acct_curr_bal == Decimal("600.00")
        assert acct.acct_curr_cyc_credit == Decimal("1100.00")
        assert acct.acct_curr_cyc_debit == Decimal("200.00")  # unchanged

    def test_negative_amount_updates_debit(self, spark):
        result, _, _, updated_acct_df, _ = _run(
            spark, [_valid_tran(dalytran_amt=Decimal("-50.00"))]
        )

        acct = updated_acct_df.filter("acct_id = 80000000001").collect()[0]
        # COBOL: ADD DALYTRAN-AMT TO ACCT-CURR-CYC-DEBIT  (amt is -50)
        assert acct.acct_curr_bal == Decimal("450.00")
        assert acct.acct_curr_cyc_credit == Decimal("1000.00")  # unchanged
        assert acct.acct_curr_cyc_debit == Decimal("150.00")  # 200 + (-50)

    def test_posted_record_field_mapping(self, spark):
        tran = _valid_tran(
            dalytran_id="ABCD1234EFGH5678",
            dalytran_type_cd="02",
            dalytran_cat_cd=3000,
            dalytran_source="ONLINE",
            dalytran_desc="Widget purchase",
            dalytran_merchant_id=999888777,
            dalytran_merchant_name="Widget Co",
            dalytran_merchant_city="Portland",
            dalytran_merchant_zip="97201",
            dalytran_orig_ts="2026-06-20-14.30.00.000000",
        )
        _, posted_df, _, _, _ = _run(spark, [tran])

        row = posted_df.collect()[0]
        assert row.tran_id == "ABCD1234EFGH5678"
        assert row.tran_type_cd == "02"
        assert row.tran_cat_cd == 3000
        assert row.tran_source == "ONLINE"
        assert row.tran_desc == "Widget purchase"
        assert row.tran_merchant_id == 999888777
        assert row.tran_merchant_name == "Widget Co"
        assert row.tran_merchant_city == "Portland"
        assert row.tran_merchant_zip == "97201"
        assert row.tran_card_num == "4111111111111111"
        assert row.tran_orig_ts == "2026-06-20-14.30.00.000000"
        assert row.tran_proc_ts == FIXED_TIMESTAMP


# ===================================================================
# Reject paths
# ===================================================================


class TestRejectInvalidCard:
    """Reject reason 100 -- card number not found in XREFFILE."""

    def test_reject_code_and_message(self, spark):
        result, posted_df, rejects_df, _, _ = _run(
            spark, [_valid_tran(dalytran_card_num="0000000000000000")]
        )

        assert result.transaction_count == 1
        assert result.reject_count == 1
        assert result.return_code == 4

        assert posted_df.count() == 0
        rejects = rejects_df.collect()
        assert len(rejects) == 1
        assert rejects[0].reject_reason_code == 100
        assert rejects[0].reject_reason_desc == "INVALID CARD NUMBER FOUND"


class TestRejectAccountNotFound:
    """Reject reason 101 -- account not in ACCTFILE."""

    def test_reject_code_and_message(self, spark):
        xref_with_missing_acct = [
            {
                "xref_card_num": "4333333333333333",
                "xref_cust_id": 100000003,
                "xref_acct_id": 99999999999,
            }
        ]
        result, _, rejects_df, _, _ = _run(
            spark,
            [_valid_tran(dalytran_card_num="4333333333333333")],
            xref=xref_with_missing_acct,
        )

        assert result.reject_count == 1
        rejects = rejects_df.collect()
        assert rejects[0].reject_reason_code == 101
        assert rejects[0].reject_reason_desc == "ACCOUNT RECORD NOT FOUND"


class TestRejectOverlimit:
    """Reject reason 102 -- overlimit transaction."""

    def test_reject_code_and_message(self, spark):
        # acct 80000000002: credit_limit=100, cyc_credit=90, cyc_debit=0
        # temp_bal = 90 - 0 + 50 = 140 > 100  -->  overlimit
        # orig_ts 2019-06-15 <= expiration 2020-01-01  -->  not expired
        result, _, rejects_df, _, _ = _run(
            spark,
            [
                _valid_tran(
                    dalytran_card_num="4222222222222222",
                    dalytran_amt=Decimal("50.00"),
                    dalytran_orig_ts="2019-06-15-00.00.00.000000",
                )
            ],
        )

        assert result.reject_count == 1
        rejects = rejects_df.collect()
        assert rejects[0].reject_reason_code == 102
        assert rejects[0].reject_reason_desc == "OVERLIMIT TRANSACTION"


class TestRejectExpired:
    """Reject reason 103 -- transaction after account expiration."""

    def test_expired_last_failure_wins(self, spark):
        # acct 80000000002: expiration_date=2020-01-01
        # orig_ts starts with 2026-06-15 > 2020-01-01  -->  expired
        # Also overlimit (90-0+1=91 < 100, so not overlimit actually)
        result, _, rejects_df, _, _ = _run(
            spark,
            [
                _valid_tran(
                    dalytran_card_num="4222222222222222",
                    dalytran_amt=Decimal("1.00"),
                    dalytran_orig_ts="2026-06-15-00.00.00.000000",
                )
            ],
        )

        assert result.reject_count == 1
        rejects = rejects_df.collect()
        assert rejects[0].reject_reason_code == 103
        assert (
            rejects[0].reject_reason_desc
            == "TRANSACTION RECEIVED AFTER ACCT EXPIRATION"
        )

    def test_overlimit_and_expired_returns_expiration(self, spark):
        # Both overlimit AND expired: last-failure-wins => 103
        # acct 80000000002: limit=100, cyc_credit=90, cyc_debit=0, exp=2020-01-01
        # amt=50 => temp_bal=140>100 => overlimit
        # orig 2026-06-15 > exp 2020-01-01 => expired
        result, _, rejects_df, _, _ = _run(
            spark,
            [
                _valid_tran(
                    dalytran_card_num="4222222222222222",
                    dalytran_amt=Decimal("50.00"),
                    dalytran_orig_ts="2026-06-15-00.00.00.000000",
                )
            ],
        )

        rejects = rejects_df.collect()
        assert len(rejects) == 1
        assert rejects[0].reject_reason_code == 103


# ===================================================================
# Category balance updates
# ===================================================================


class TestCategoryBalanceUpdate:
    def test_tcatbal_created_on_first_post(self, spark):
        _, _, _, _, updated_tcatbal_df = _run(spark, [_valid_tran()])

        tcatbal = updated_tcatbal_df.collect()
        assert len(tcatbal) == 1
        assert tcatbal[0].trancat_acct_id == 80000000001
        assert tcatbal[0].trancat_type_cd == "01"
        assert tcatbal[0].trancat_cd == 5000
        assert tcatbal[0].tran_cat_bal == Decimal("100.00")

    def test_tcatbal_accumulated_across_transactions(self, spark):
        _, _, _, _, updated_tcatbal_df = _run(
            spark,
            [
                _valid_tran(
                    dalytran_id="0000000000000001",
                    dalytran_amt=Decimal("100.00"),
                ),
                _valid_tran(
                    dalytran_id="0000000000000002",
                    dalytran_amt=Decimal("50.00"),
                ),
            ],
        )

        tcatbal = updated_tcatbal_df.collect()
        assert len(tcatbal) == 1
        assert tcatbal[0].tran_cat_bal == Decimal("150.00")

    def test_different_categories_create_separate_records(self, spark):
        _, _, _, _, updated_tcatbal_df = _run(
            spark,
            [
                _valid_tran(
                    dalytran_id="0000000000000001",
                    dalytran_type_cd="01",
                    dalytran_cat_cd=5000,
                    dalytran_amt=Decimal("100.00"),
                ),
                _valid_tran(
                    dalytran_id="0000000000000002",
                    dalytran_type_cd="02",
                    dalytran_cat_cd=6000,
                    dalytran_amt=Decimal("75.00"),
                ),
            ],
        )

        tcatbal = updated_tcatbal_df.collect()
        assert len(tcatbal) == 2
        bals = {(r.trancat_type_cd, r.trancat_cd): r.tran_cat_bal for r in tcatbal}
        assert bals[("01", 5000)] == Decimal("100.00")
        assert bals[("02", 6000)] == Decimal("75.00")

    def test_existing_tcatbal_is_updated(self, spark):
        existing_tcatbal = [
            {
                "trancat_acct_id": 80000000001,
                "trancat_type_cd": "01",
                "trancat_cd": 5000,
                "tran_cat_bal": Decimal("500.00"),
            }
        ]
        _, _, _, _, updated_tcatbal_df = _run(
            spark,
            [_valid_tran(dalytran_amt=Decimal("100.00"))],
            tcatbal=existing_tcatbal,
        )

        tcatbal = updated_tcatbal_df.collect()
        assert len(tcatbal) == 1
        assert tcatbal[0].tran_cat_bal == Decimal("600.00")


# ===================================================================
# Return code behaviour
# ===================================================================


class TestReturnCode:
    def test_return_code_0_when_all_valid(self, spark):
        result, _, _, _, _ = _run(spark, [_valid_tran()])
        assert result.return_code == 0

    def test_return_code_4_when_any_rejected(self, spark):
        result, posted_df, rejects_df, _, _ = _run(
            spark,
            [
                _valid_tran(dalytran_id="0000000000000001"),
                _valid_tran(
                    dalytran_id="0000000000000002",
                    dalytran_card_num="0000000000000000",
                ),
            ],
        )

        assert result.transaction_count == 2
        assert result.reject_count == 1
        assert result.return_code == 4
        assert posted_df.count() == 1
        assert rejects_df.count() == 1

    def test_return_code_4_when_all_rejected(self, spark):
        result, _, _, _, _ = _run(
            spark,
            [
                _valid_tran(
                    dalytran_id="0000000000000001",
                    dalytran_card_num="0000000000000000",
                ),
                _valid_tran(
                    dalytran_id="0000000000000002",
                    dalytran_card_num="9999999999999999",
                ),
            ],
        )

        assert result.transaction_count == 2
        assert result.reject_count == 2
        assert result.return_code == 4

    def test_empty_input_returns_code_0(self, spark):
        result, posted_df, rejects_df, _, _ = _run(spark, [])
        assert result.transaction_count == 0
        assert result.reject_count == 0
        assert result.return_code == 0
        assert posted_df.count() == 0
        assert rejects_df.count() == 0


# ===================================================================
# Sequential processing: account state propagates across transactions
# ===================================================================


class TestSequentialProcessing:
    def test_second_transaction_sees_updated_balance(self, spark):
        # acct 80000000001: limit=5000, cyc_credit=1000, cyc_debit=200
        # First tran: amt=4200 => temp_bal=1000-200+4200=5000 <= 5000 => OK
        # After posting: cyc_credit=5200
        # Second tran: amt=1.00 => temp_bal=5200-200+1=5001 > 5000 => overlimit
        result, posted_df, rejects_df, _, _ = _run(
            spark,
            [
                _valid_tran(
                    dalytran_id="0000000000000001",
                    dalytran_amt=Decimal("4200.00"),
                ),
                _valid_tran(
                    dalytran_id="0000000000000002",
                    dalytran_amt=Decimal("1.00"),
                ),
            ],
        )

        assert result.transaction_count == 2
        assert posted_df.count() == 1
        assert rejects_df.count() == 1

        rejects = rejects_df.collect()
        assert rejects[0].reject_reason_code == 102
