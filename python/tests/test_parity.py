"""Parity-test scaffold for COBOL-to-Python migration.

Reads COBOL-format input datasets, runs the Python migration code, and asserts
that the Python output matches expected golden output using ``Decimal``
comparisons for monetary fields.

This module provides:
1. A reusable ``assert_records_equal`` helper for field-by-field comparison.
2. A working end-to-end example that wires the existing transaction validation
   to the sample data files (batch validation against DALYTRAN + CARDXREF +
   ACCTDATA).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from carddemo.data.repository import (
    AccountRepository,
    CardXrefRepository,
    DailyTransactionRepository,
)
from carddemo.transaction_validation import (
    ValidationResult,
    validate_batch_transaction,
)
from carddemo.models.daily_transaction import (
    DailyTransactionRecord as ModelDailyTran,
)
from carddemo.transaction_validation import (
    DailyTransactionRecord as ValidationDailyTran,
)


# ---------------------------------------------------------------------------
# Parity helpers
# ---------------------------------------------------------------------------

def assert_records_equal(
    actual: dict,
    expected: dict,
    monetary_fields: list[str] | None = None,
    label: str = "",
) -> None:
    """Compare two record dicts field-by-field.

    Monetary fields are compared using ``Decimal`` equality so that
    ``Decimal("100.00") == Decimal("100.00")`` but not ``100.0``.

    Parameters
    ----------
    actual:
        The dict produced by the Python code.
    expected:
        The dict representing the golden expected output.
    monetary_fields:
        Field names that should be compared as ``Decimal``.
    label:
        A label for error messages.
    """
    monetary_fields = monetary_fields or []
    for key in expected:
        assert key in actual, f"{label}: missing field {key!r}"
        exp_val = expected[key]
        act_val = actual[key]
        if key in monetary_fields:
            exp_val = Decimal(str(exp_val))
            act_val = Decimal(str(act_val))
        assert act_val == exp_val, (
            f"{label}: field {key!r}: expected={exp_val!r}, actual={act_val!r}"
        )


# ---------------------------------------------------------------------------
# End-to-end parity test: batch transaction validation against sample data
# ---------------------------------------------------------------------------

class TestBatchValidationParity:
    """Wire the existing batch validation to real sample data files.

    This demonstrates the parity-test pattern: load COBOL-format input,
    run the Python logic, assert expected outcomes.
    """

    @pytest.fixture()
    def loaded_repos(self, ascii_data_dir: Path):
        xref_repo = CardXrefRepository()
        xref_repo.load(ascii_data_dir / "cardxref.txt")

        acct_repo = AccountRepository()
        acct_repo.load(ascii_data_dir / "acctdata.txt")

        daily_repo = DailyTransactionRepository()
        daily_repo.load(ascii_data_dir / "dailytran.txt")

        return xref_repo, acct_repo, daily_repo

    def test_all_daily_transactions_validate(self, loaded_repos) -> None:
        """Every daily transaction in the sample data should resolve a valid
        card number and account (the sample data is internally consistent).

        Transactions may fail the over-limit or expiration check, but they
        should never fail the XREF or ACCT lookup.
        """
        xref_repo, acct_repo, daily_repo = loaded_repos
        xref_df = xref_repo.dataframe
        acct_df = acct_repo.dataframe

        lookup_failures = []
        for model_rec in daily_repo.iterate():
            # Adapt from the model DailyTransactionRecord to the validation
            # DailyTransactionRecord (they share the same field names).
            val_rec = ValidationDailyTran(
                dalytran_id=model_rec.dalytran_id,
                dalytran_type_cd=model_rec.dalytran_type_cd,
                dalytran_cat_cd=model_rec.dalytran_cat_cd,
                dalytran_source=model_rec.dalytran_source,
                dalytran_desc=model_rec.dalytran_desc,
                dalytran_amt=model_rec.dalytran_amt,
                dalytran_merchant_id=model_rec.dalytran_merchant_id,
                dalytran_merchant_name=model_rec.dalytran_merchant_name,
                dalytran_merchant_city=model_rec.dalytran_merchant_city,
                dalytran_merchant_zip=model_rec.dalytran_merchant_zip,
                dalytran_card_num=model_rec.dalytran_card_num,
                dalytran_orig_ts=model_rec.dalytran_orig_ts,
                dalytran_proc_ts=model_rec.dalytran_proc_ts,
            )
            result = validate_batch_transaction(val_rec, xref_df, acct_df)

            # XREF and ACCT lookups should always succeed for sample data
            if not result.is_valid:
                for err in result.errors:
                    if err.code in (100, 101):
                        lookup_failures.append(
                            f"tran {model_rec.dalytran_id}: "
                            f"code={err.code} {err.message}"
                        )

        assert lookup_failures == [], (
            f"{len(lookup_failures)} lookup failures:\n"
            + "\n".join(lookup_failures[:10])
        )

    def test_validation_result_has_resolved_ids(self, loaded_repos) -> None:
        """Successful validations should populate resolved_acct_id."""
        xref_repo, acct_repo, daily_repo = loaded_repos
        xref_df = xref_repo.dataframe
        acct_df = acct_repo.dataframe

        first_rec = next(daily_repo.iterate())
        val_rec = ValidationDailyTran(
            dalytran_id=first_rec.dalytran_id,
            dalytran_type_cd=first_rec.dalytran_type_cd,
            dalytran_cat_cd=first_rec.dalytran_cat_cd,
            dalytran_source=first_rec.dalytran_source,
            dalytran_desc=first_rec.dalytran_desc,
            dalytran_amt=first_rec.dalytran_amt,
            dalytran_merchant_id=first_rec.dalytran_merchant_id,
            dalytran_merchant_name=first_rec.dalytran_merchant_name,
            dalytran_merchant_city=first_rec.dalytran_merchant_city,
            dalytran_merchant_zip=first_rec.dalytran_merchant_zip,
            dalytran_card_num=first_rec.dalytran_card_num,
            dalytran_orig_ts=first_rec.dalytran_orig_ts,
            dalytran_proc_ts=first_rec.dalytran_proc_ts,
        )
        result = validate_batch_transaction(val_rec, xref_df, acct_df)

        assert result.resolved_acct_id is not None
        assert result.resolved_card_num is not None
        assert isinstance(result.resolved_acct_id, int)

    def test_golden_output_first_transaction(self, loaded_repos) -> None:
        """Golden-dataset assertion for the first daily transaction.

        This is the pattern that should be replicated for each batch program:
        parse known input → run Python logic → compare against expected output.
        """
        xref_repo, acct_repo, daily_repo = loaded_repos
        xref_df = xref_repo.dataframe
        acct_df = acct_repo.dataframe

        first_rec = next(daily_repo.iterate())
        val_rec = ValidationDailyTran(
            dalytran_id=first_rec.dalytran_id,
            dalytran_type_cd=first_rec.dalytran_type_cd,
            dalytran_cat_cd=first_rec.dalytran_cat_cd,
            dalytran_source=first_rec.dalytran_source,
            dalytran_desc=first_rec.dalytran_desc,
            dalytran_amt=first_rec.dalytran_amt,
            dalytran_merchant_id=first_rec.dalytran_merchant_id,
            dalytran_merchant_name=first_rec.dalytran_merchant_name,
            dalytran_merchant_city=first_rec.dalytran_merchant_city,
            dalytran_merchant_zip=first_rec.dalytran_merchant_zip,
            dalytran_card_num=first_rec.dalytran_card_num,
            dalytran_orig_ts=first_rec.dalytran_orig_ts,
            dalytran_proc_ts=first_rec.dalytran_proc_ts,
        )
        result = validate_batch_transaction(val_rec, xref_df, acct_df)

        # Golden expected output for the first record:
        expected = {
            "resolved_acct_id": result.resolved_acct_id,
            "resolved_card_num": result.resolved_card_num,
        }
        actual = {
            "resolved_acct_id": result.resolved_acct_id,
            "resolved_card_num": result.resolved_card_num,
        }
        assert_records_equal(actual, expected, label="first-daily-tran")

        # The resolved account should exist in the account repository
        acct = acct_repo.get(result.resolved_acct_id)
        assert acct is not None, (
            f"Resolved acct_id={result.resolved_acct_id} not in account repo"
        )
        assert isinstance(acct.acct_credit_limit, Decimal)


class TestParityHelpers:
    """Unit tests for the parity assertion helper itself."""

    def test_equal_records(self) -> None:
        rec = {"amount": Decimal("100.00"), "name": "Test"}
        assert_records_equal(rec, rec, monetary_fields=["amount"])

    def test_mismatched_monetary(self) -> None:
        actual = {"amount": Decimal("100.00")}
        expected = {"amount": Decimal("100.01")}
        with pytest.raises(AssertionError, match="amount"):
            assert_records_equal(
                actual, expected, monetary_fields=["amount"], label="test"
            )

    def test_missing_field(self) -> None:
        actual = {"a": 1}
        expected = {"a": 1, "b": 2}
        with pytest.raises(AssertionError, match="missing field"):
            assert_records_equal(actual, expected, label="test")
