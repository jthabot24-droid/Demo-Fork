"""
Unit tests for the CardDemo transaction validation migration.

Covers both the **online** validation (COTRN02C) and the **batch** validation
(CBTRN02C) with small in-memory pandas DataFrames as fixtures.
"""

from decimal import Decimal

import pandas as pd
import pytest

from transaction_validation import (
    DailyTransactionRecord,
    TransactionInput,
    validate_batch_transaction,
    validate_online_transaction,
)

# ---------------------------------------------------------------------------
# Fixtures -- small reference data sets
# ---------------------------------------------------------------------------


@pytest.fixture()
def xref_by_card() -> pd.DataFrame:
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
def xref_by_acct(xref_by_card: pd.DataFrame) -> pd.DataFrame:
    return xref_by_card.copy()


@pytest.fixture()
def account_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "acct_id": 80000000001,
                "acct_credit_limit": Decimal("5000.00"),
                "acct_curr_cyc_credit": Decimal("1000.00"),
                "acct_curr_cyc_debit": Decimal("200.00"),
                "acct_expiration_date": "2027-12-31",
            },
            {
                "acct_id": 80000000002,
                "acct_credit_limit": Decimal("100.00"),
                "acct_curr_cyc_credit": Decimal("90.00"),
                "acct_curr_cyc_debit": Decimal("0.00"),
                "acct_expiration_date": "2020-01-01",
            },
        ]
    )


def _valid_txn(**overrides: str) -> TransactionInput:
    """Return a fully valid online TransactionInput; override any field."""
    defaults = dict(
        actid_in="",
        card_num_in="4111111111111111",
        ttype_cd="01",
        tcat_cd="5000",
        tran_source="ONLINE",
        tran_desc="Test purchase",
        tran_amt="+00000100.00",
        orig_date="2026-06-15",
        proc_date="2026-06-15",
        merchant_id="123456789",
        merchant_name="Acme Corp",
        merchant_city="Seattle",
        merchant_zip="98101",
    )
    defaults.update(overrides)
    return TransactionInput(**defaults)


# ===================================================================
# ONLINE VALIDATION (COTRN02C)
# ===================================================================


class TestOnlineKeyFieldValidation:
    """Tests for VALIDATE-INPUT-KEY-FIELDS."""

    def test_valid_card_number_resolves_acct(
        self, xref_by_card, xref_by_acct
    ):
        txn = _valid_txn()
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert result.is_valid
        assert result.resolved_acct_id == 80000000001
        assert result.resolved_card_num == "4111111111111111"

    def test_valid_account_id_resolves_card(
        self, xref_by_card, xref_by_acct
    ):
        txn = _valid_txn(actid_in="80000000001", card_num_in="")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert result.is_valid
        assert result.resolved_card_num == "4111111111111111"

    def test_neither_acct_nor_card_entered(
        self, xref_by_card, xref_by_acct
    ):
        txn = _valid_txn(actid_in="", card_num_in="")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert len(result.errors) == 1
        assert result.errors[0].message == "Account or Card Number must be entered..."

    def test_non_numeric_account_id(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(actid_in="ABCDE", card_num_in="")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert result.errors[0].message == "Account ID must be Numeric..."

    def test_non_numeric_card_number(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(actid_in="", card_num_in="41111ABCDE111111")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert result.errors[0].message == "Card Number must be Numeric..."

    def test_account_id_not_found(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(actid_in="99999999999", card_num_in="")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert result.errors[0].message == "Account ID NOT found..."

    def test_card_number_not_found(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(actid_in="", card_num_in="9999999999999999")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert result.errors[0].message == "Card Number NOT found..."


class TestOnlineDataFieldValidation:
    """Tests for VALIDATE-INPUT-DATA-FIELDS."""

    # ---- Required-field emptiness checks ----

    @pytest.mark.parametrize(
        "field_name, expected_msg",
        [
            ("ttype_cd", "Type CD can NOT be empty..."),
            ("tcat_cd", "Category CD can NOT be empty..."),
            ("tran_source", "Source can NOT be empty..."),
            ("tran_desc", "Description can NOT be empty..."),
            ("tran_amt", "Amount can NOT be empty..."),
            ("orig_date", "Orig Date can NOT be empty..."),
            ("proc_date", "Proc Date can NOT be empty..."),
            ("merchant_id", "Merchant ID can NOT be empty..."),
            ("merchant_name", "Merchant Name can NOT be empty..."),
            ("merchant_city", "Merchant City can NOT be empty..."),
            ("merchant_zip", "Merchant Zip can NOT be empty..."),
        ],
    )
    def test_empty_field(
        self, field_name, expected_msg, xref_by_card, xref_by_acct
    ):
        txn = _valid_txn(**{field_name: ""})
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert result.errors[0].message == expected_msg

    # ---- Numeric checks ----

    def test_type_cd_not_numeric(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(ttype_cd="AB")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert result.errors[0].message == "Type CD must be Numeric..."

    def test_category_cd_not_numeric(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(tcat_cd="XY12")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert result.errors[0].message == "Category CD must be Numeric..."

    # ---- Amount format ----

    def test_amount_bad_format_no_sign(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(tran_amt="000000100.00")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert result.errors[0].message == "Amount should be in format -99999999.99"

    def test_amount_bad_format_no_decimal(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(tran_amt="+0000010000")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert result.errors[0].message == "Amount should be in format -99999999.99"

    def test_amount_bad_format_letters(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(tran_amt="+0000ABCD.00")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert result.errors[0].message == "Amount should be in format -99999999.99"

    # ---- Date format ----

    def test_orig_date_bad_format(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(orig_date="06/15/2026")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert (
            result.errors[0].message
            == "Orig Date should be in format YYYY-MM-DD"
        )

    def test_proc_date_bad_format(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(proc_date="2026/06/15")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert (
            result.errors[0].message
            == "Proc Date should be in format YYYY-MM-DD"
        )

    # ---- Date value validity (CSUTLDTC replacement) ----

    def test_orig_date_invalid_calendar(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(orig_date="2026-02-30")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert result.errors[0].message == "Orig Date - Not a valid date..."

    def test_proc_date_invalid_calendar(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(proc_date="2026-13-01")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert result.errors[0].message == "Proc Date - Not a valid date..."

    def test_future_dates_are_valid(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(orig_date="2099-12-31", proc_date="2099-12-31")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert result.is_valid

    # ---- Merchant ID numeric ----

    def test_merchant_id_not_numeric(self, xref_by_card, xref_by_acct):
        txn = _valid_txn(merchant_id="ABC123XYZ")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert not result.is_valid
        assert result.errors[0].message == "Merchant ID must be Numeric..."


class TestOnlineHappyPath:
    """Fully valid transactions should pass."""

    def test_valid_transaction_via_card(self, xref_by_card, xref_by_acct):
        txn = _valid_txn()
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert result.is_valid
        assert result.errors == []

    def test_valid_transaction_negative_amount(
        self, xref_by_card, xref_by_acct
    ):
        txn = _valid_txn(tran_amt="-00000050.00")
        result = validate_online_transaction(txn, xref_by_card, xref_by_acct)
        assert result.is_valid


# ===================================================================
# BATCH VALIDATION (CBTRN02C)
# ===================================================================


def _valid_daily_tran(**overrides) -> DailyTransactionRecord:
    """Return a valid DailyTransactionRecord; override any field."""
    defaults = dict(
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
    defaults.update(overrides)
    return DailyTransactionRecord(**defaults)


class TestBatchXrefLookup:
    """1500-A-LOOKUP-XREF."""

    def test_invalid_card_number(self, xref_by_card, account_df):
        tran = _valid_daily_tran(dalytran_card_num="0000000000000000")
        result = validate_batch_transaction(tran, xref_by_card, account_df)
        assert not result.is_valid
        assert result.errors[0].code == 100
        assert result.errors[0].message == "INVALID CARD NUMBER FOUND"

    def test_valid_card_resolves(self, xref_by_card, account_df):
        tran = _valid_daily_tran()
        result = validate_batch_transaction(tran, xref_by_card, account_df)
        assert result.is_valid
        assert result.resolved_acct_id == 80000000001


class TestBatchAccountLookup:
    """1500-B-LOOKUP-ACCT."""

    def test_account_not_found(self, xref_by_card, account_df):
        xref = pd.DataFrame(
            [
                {
                    "xref_card_num": "4333333333333333",
                    "xref_cust_id": 100000003,
                    "xref_acct_id": 99999999999,
                }
            ]
        )
        tran = _valid_daily_tran(dalytran_card_num="4333333333333333")
        result = validate_batch_transaction(tran, xref, account_df)
        assert not result.is_valid
        assert result.errors[0].code == 101
        assert result.errors[0].message == "ACCOUNT RECORD NOT FOUND"


class TestBatchOverlimit:
    """Over-limit check in 1500-B-LOOKUP-ACCT."""

    def test_overlimit_transaction(self, xref_by_card, account_df):
        # acct 80000000002 has credit_limit=100, cyc_credit=90, cyc_debit=0
        # temp_bal = 90 - 0 + 50 = 140 > 100 => overlimit
        tran = _valid_daily_tran(
            dalytran_card_num="4222222222222222",
            dalytran_amt=Decimal("50.00"),
            dalytran_orig_ts="2019-06-15-00.00.00.000000",
        )
        result = validate_batch_transaction(tran, xref_by_card, account_df)
        assert not result.is_valid
        # Expiration date 2020-01-01 >= orig 2019-06-15 → expiration passes
        # so only overlimit remains
        assert result.errors[0].code == 102
        assert result.errors[0].message == "OVERLIMIT TRANSACTION"

    def test_within_limit(self, xref_by_card, account_df):
        tran = _valid_daily_tran(dalytran_amt=Decimal("100.00"))
        result = validate_batch_transaction(tran, xref_by_card, account_df)
        assert result.is_valid


class TestBatchExpiration:
    """Expiration check in 1500-B-LOOKUP-ACCT."""

    def test_transaction_after_expiration(self, xref_by_card, account_df):
        # acct 80000000002 expires 2020-01-01
        # orig_ts starts with 2026-06-15 which is > 2020-01-01
        tran = _valid_daily_tran(
            dalytran_card_num="4222222222222222",
            dalytran_amt=Decimal("1.00"),
            dalytran_orig_ts="2026-06-15-00.00.00.000000",
        )
        result = validate_batch_transaction(tran, xref_by_card, account_df)
        assert not result.is_valid
        # Last-failure-wins: expiration overwrites overlimit
        assert result.errors[0].code == 103
        assert (
            result.errors[0].message
            == "TRANSACTION RECEIVED AFTER ACCT EXPIRATION"
        )

    def test_transaction_before_expiration(self, xref_by_card, account_df):
        tran = _valid_daily_tran(
            dalytran_orig_ts="2027-01-01-00.00.00.000000",
        )
        result = validate_batch_transaction(tran, xref_by_card, account_df)
        assert result.is_valid


class TestBatchLastFailureWins:
    """COBOL 1500-B-LOOKUP-ACCT does not short-circuit: both overlimit and
    expiration can fire, and the last one to fire wins.
    """

    def test_overlimit_and_expired_returns_expiration(
        self, xref_by_card, account_df
    ):
        # acct 80000000002: credit_limit=100, cyc_credit=90, cyc_debit=0
        # dalytran_amt=50 → temp_bal=140 > 100 → overlimit
        # expiration_date=2020-01-01 < orig 2026-06-15 → expired
        # last-failure-wins → code 103
        tran = _valid_daily_tran(
            dalytran_card_num="4222222222222222",
            dalytran_amt=Decimal("50.00"),
            dalytran_orig_ts="2026-06-15-00.00.00.000000",
        )
        result = validate_batch_transaction(tran, xref_by_card, account_df)
        assert not result.is_valid
        assert len(result.errors) == 1
        assert result.errors[0].code == 103


class TestBatchHappyPath:
    """Fully valid daily transactions should pass."""

    def test_valid_daily_transaction(self, xref_by_card, account_df):
        tran = _valid_daily_tran()
        result = validate_batch_transaction(tran, xref_by_card, account_df)
        assert result.is_valid
        assert result.errors == []
        assert result.resolved_acct_id == 80000000001

    def test_negative_amount_passes(self, xref_by_card, account_df):
        tran = _valid_daily_tran(dalytran_amt=Decimal("-50.00"))
        result = validate_batch_transaction(tran, xref_by_card, account_df)
        assert result.is_valid


class TestBatchBoundaryAmounts:
    """Edge cases for the over-limit check."""

    def test_exactly_at_limit(self, xref_by_card, account_df):
        # acct 80000000001: limit=5000, cyc_credit=1000, cyc_debit=200
        # temp_bal = 1000 - 200 + 4200 = 5000 == limit → passes
        tran = _valid_daily_tran(dalytran_amt=Decimal("4200.00"))
        result = validate_batch_transaction(tran, xref_by_card, account_df)
        assert result.is_valid

    def test_one_cent_over_limit(self, xref_by_card, account_df):
        # temp_bal = 1000 - 200 + 4200.01 = 5000.01 > 5000 → overlimit
        tran = _valid_daily_tran(dalytran_amt=Decimal("4200.01"))
        result = validate_batch_transaction(tran, xref_by_card, account_df)
        assert not result.is_valid
        assert result.errors[0].code == 102
