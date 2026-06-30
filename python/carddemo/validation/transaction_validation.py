"""
Transaction validation logic migrated from CardDemo COBOL programs.

Source programs
---------------
* **COTRN02C.cbl** -- CICS online "Transaction Add" program.
  Validates user-entered fields before writing a new transaction to the
  TRANSACT VSAM file.  Validation paragraphs: VALIDATE-INPUT-KEY-FIELDS,
  VALIDATE-INPUT-DATA-FIELDS.

* **CBTRN02C.cbl** -- Batch "Post Daily Transactions" program.
  Reads daily transaction records, validates them against the card cross-
  reference (XREFFILE) and account master (ACCTFILE) before posting.
  Validation paragraph: 1500-VALIDATE-TRAN (calls 1500-A-LOOKUP-XREF,
  1500-B-LOOKUP-ACCT).

Key copybooks (field layouts)
------------------------------
* CVTRA05Y -- TRAN-RECORD          (transaction master, 350 bytes)
* CVTRA06Y -- DALYTRAN-RECORD      (daily transaction, 350 bytes)
* CVACT03Y -- CARD-XREF-RECORD     (card cross-reference, 50 bytes)
* CVACT01Y -- ACCOUNT-RECORD       (account master, 300 bytes)
* CVTRA01Y -- TRAN-CAT-BAL-RECORD  (transaction category balance, 50 bytes)
* CSMSG01Y -- common messages

Assumptions
-----------
1. The COBOL utility ``CSUTLDTC`` is replaced by Python ``datetime`` parsing.
   Only message-number ``2513`` (future-date warning) is suppressed in the
   original; we replicate that by accepting dates that are valid even if in the
   future.
2. VSAM lookups are replaced by pandas DataFrame operations keyed on the same
   fields as the COBOL record layouts.
3. ``decimal.Decimal`` is used for all monetary arithmetic to match COBOL
   packed-decimal (``PIC S9(09)V99`` / ``PIC S9(10)V99``) precision.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

import pandas as pd

from carddemo.models.common import (
    ValidationError,
    ValidationResult,
    is_blank,
    is_numeric,
    validate_amount_format,
    validate_date_format,
    validate_date_value,
)
from carddemo.models.transaction import DailyTransactionRecord

# ---------------------------------------------------------------------------
# Online-specific input data structure
# ---------------------------------------------------------------------------


@dataclass
class TransactionInput:
    """Fields entered by the online user (COTRN02C screen fields).

    Field names follow the BMS map names used in the COBOL program.
    """

    actid_in: str = ""          # Account ID  -- ACTIDINI
    card_num_in: str = ""       # Card Number -- CARDNINI
    ttype_cd: str = ""          # Type Code   -- TTYPCDI   PIC X(02)
    tcat_cd: str = ""           # Category CD -- TCATCDI   PIC X(04)
    tran_source: str = ""       # Source      -- TRNSRCI   PIC X(10)
    tran_desc: str = ""         # Description -- TDESCI    PIC X(100)
    tran_amt: str = ""          # Amount      -- TRNAMTI   PIC +99999999.99
    orig_date: str = ""         # Orig Date   -- TORIGDTI  YYYY-MM-DD
    proc_date: str = ""         # Proc Date   -- TPROCDTI  YYYY-MM-DD
    merchant_id: str = ""       # Merchant ID -- MIDI      PIC 9(09)
    merchant_name: str = ""     # Merchant Name -- MNAMEI PIC X(50)
    merchant_city: str = ""     # Merchant City -- MCITYI PIC X(50)
    merchant_zip: str = ""      # Merchant Zip  -- MZIPI  PIC X(10)


# ---------------------------------------------------------------------------
# Online validation  (COTRN02C)
# ---------------------------------------------------------------------------


def validate_online_transaction(
    txn: TransactionInput,
    xref_by_card: pd.DataFrame,
    xref_by_acct: pd.DataFrame,
) -> ValidationResult:
    """Reproduce the exact validation logic of COTRN02C.

    Parameters
    ----------
    txn : TransactionInput
        Screen input fields.
    xref_by_card : pd.DataFrame
        Card cross-reference data, must contain columns:
        ``xref_card_num`` (str), ``xref_cust_id`` (int), ``xref_acct_id`` (int).
        Indexed/keyed by ``xref_card_num``.
    xref_by_acct : pd.DataFrame
        Same data but indexed/keyed by ``xref_acct_id``.
        Must contain ``xref_card_num`` (str).

    Returns
    -------
    ValidationResult
    """
    result = ValidationResult()

    # ----- VALIDATE-INPUT-KEY-FIELDS -----
    _validate_key_fields(txn, xref_by_card, xref_by_acct, result)

    # In the COBOL, if the key-field validation set ERR-FLG-ON the data fields
    # are blanked and will therefore all fail the emptiness checks below.
    if result.errors:
        return result

    # ----- VALIDATE-INPUT-DATA-FIELDS -----
    _validate_data_fields(txn, result)

    return result


def _validate_key_fields(
    txn: TransactionInput,
    xref_by_card: pd.DataFrame,
    xref_by_acct: pd.DataFrame,
    result: ValidationResult,
) -> None:
    """VALIDATE-INPUT-KEY-FIELDS paragraph."""

    actid = txn.actid_in.strip() if txn.actid_in else ""
    cardnum = txn.card_num_in.strip() if txn.card_num_in else ""

    if not is_blank(actid):
        if not is_numeric(actid):
            result.is_valid = False
            result.errors.append(
                ValidationError(0, "Account ID must be Numeric...", "actid_in")
            )
            return

        acct_id_n = int(actid)
        matches = xref_by_acct.loc[xref_by_acct["xref_acct_id"] == acct_id_n]
        if matches.empty:
            result.is_valid = False
            result.errors.append(
                ValidationError(0, "Account ID NOT found...", "actid_in")
            )
            return

        resolved_card = str(matches.iloc[0]["xref_card_num"])
        result.resolved_acct_id = acct_id_n
        result.resolved_card_num = resolved_card
        txn.card_num_in = resolved_card

    elif not is_blank(cardnum):
        if not is_numeric(cardnum):
            result.is_valid = False
            result.errors.append(
                ValidationError(0, "Card Number must be Numeric...", "card_num_in")
            )
            return

        card_num_n = cardnum.zfill(16)
        matches = xref_by_card.loc[xref_by_card["xref_card_num"] == card_num_n]
        if matches.empty:
            result.is_valid = False
            result.errors.append(
                ValidationError(0, "Card Number NOT found...", "card_num_in")
            )
            return

        resolved_acct = int(matches.iloc[0]["xref_acct_id"])
        result.resolved_card_num = card_num_n
        result.resolved_acct_id = resolved_acct
        txn.actid_in = str(resolved_acct)

    else:
        result.is_valid = False
        result.errors.append(
            ValidationError(
                0,
                "Account or Card Number must be entered...",
                "actid_in",
            )
        )


def _validate_data_fields(
    txn: TransactionInput,
    result: ValidationResult,
) -> None:
    """VALIDATE-INPUT-DATA-FIELDS paragraph -- exact COBOL order."""

    # --- Emptiness checks (EVALUATE TRUE cascade) ---
    _required = [
        ("ttype_cd", txn.ttype_cd, "Type CD can NOT be empty..."),
        ("tcat_cd", txn.tcat_cd, "Category CD can NOT be empty..."),
        ("tran_source", txn.tran_source, "Source can NOT be empty..."),
        ("tran_desc", txn.tran_desc, "Description can NOT be empty..."),
        ("tran_amt", txn.tran_amt, "Amount can NOT be empty..."),
        ("orig_date", txn.orig_date, "Orig Date can NOT be empty..."),
        ("proc_date", txn.proc_date, "Proc Date can NOT be empty..."),
        ("merchant_id", txn.merchant_id, "Merchant ID can NOT be empty..."),
        ("merchant_name", txn.merchant_name, "Merchant Name can NOT be empty..."),
        ("merchant_city", txn.merchant_city, "Merchant City can NOT be empty..."),
        ("merchant_zip", txn.merchant_zip, "Merchant Zip can NOT be empty..."),
    ]

    for field_name, value, msg in _required:
        if is_blank(value):
            result.is_valid = False
            result.errors.append(ValidationError(0, msg, field_name))
            return  # COBOL PERFORM SEND-TRNADD-SCREEN exits on first error

    # --- Numeric checks (second EVALUATE TRUE) ---
    if not is_numeric(txn.ttype_cd):
        result.is_valid = False
        result.errors.append(
            ValidationError(0, "Type CD must be Numeric...", "ttype_cd")
        )
        return

    if not is_numeric(txn.tcat_cd):
        result.is_valid = False
        result.errors.append(
            ValidationError(0, "Category CD must be Numeric...", "tcat_cd")
        )
        return

    # --- Amount format ---
    if not validate_amount_format(txn.tran_amt):
        result.is_valid = False
        result.errors.append(
            ValidationError(
                0,
                "Amount should be in format -99999999.99",
                "tran_amt",
            )
        )
        return

    # --- Orig date format ---
    if not validate_date_format(txn.orig_date):
        result.is_valid = False
        result.errors.append(
            ValidationError(
                0,
                "Orig Date should be in format YYYY-MM-DD",
                "orig_date",
            )
        )
        return

    # --- Proc date format ---
    if not validate_date_format(txn.proc_date):
        result.is_valid = False
        result.errors.append(
            ValidationError(
                0,
                "Proc Date should be in format YYYY-MM-DD",
                "proc_date",
            )
        )
        return

    # --- Orig date calendar validity (CSUTLDTC replacement) ---
    if not validate_date_value(txn.orig_date):
        result.is_valid = False
        result.errors.append(
            ValidationError(
                0,
                "Orig Date - Not a valid date...",
                "orig_date",
            )
        )
        return

    # --- Proc date calendar validity ---
    if not validate_date_value(txn.proc_date):
        result.is_valid = False
        result.errors.append(
            ValidationError(
                0,
                "Proc Date - Not a valid date...",
                "proc_date",
            )
        )
        return

    # --- Merchant ID numeric ---
    if not is_numeric(txn.merchant_id):
        result.is_valid = False
        result.errors.append(
            ValidationError(0, "Merchant ID must be Numeric...", "merchant_id")
        )
        return


# ---------------------------------------------------------------------------
# Batch validation  (CBTRN02C)
# ---------------------------------------------------------------------------


def validate_batch_transaction(
    tran: DailyTransactionRecord,
    xref_df: pd.DataFrame,
    account_df: pd.DataFrame,
) -> ValidationResult:
    """Reproduce the exact validation logic of CBTRN02C (1500-VALIDATE-TRAN).

    Parameters
    ----------
    tran : DailyTransactionRecord
        A single daily transaction record.
    xref_df : pd.DataFrame
        Card cross-reference data.  Must contain columns matching
        ``CardXrefRecord`` fields: ``xref_card_num``, ``xref_acct_id``.
    account_df : pd.DataFrame
        Account master data.  Must contain columns matching
        ``AccountRecord`` fields: ``acct_id``, ``acct_credit_limit``,
        ``acct_curr_cyc_credit``, ``acct_curr_cyc_debit``,
        ``acct_expiration_date``.

    Returns
    -------
    ValidationResult
    """
    result = ValidationResult()

    # 1500-A-LOOKUP-XREF
    card_num = tran.dalytran_card_num.strip()
    xref_match = xref_df.loc[xref_df["xref_card_num"] == card_num]
    if xref_match.empty:
        result.is_valid = False
        result.errors.append(
            ValidationError(100, "INVALID CARD NUMBER FOUND", "dalytran_card_num")
        )
        return result

    # 1500-B-LOOKUP-ACCT
    acct_id = int(xref_match.iloc[0]["xref_acct_id"])
    result.resolved_acct_id = acct_id
    result.resolved_card_num = card_num

    acct_match = account_df.loc[account_df["acct_id"] == acct_id]
    if acct_match.empty:
        result.is_valid = False
        result.errors.append(
            ValidationError(101, "ACCOUNT RECORD NOT FOUND", "acct_id")
        )
        return result

    acct = acct_match.iloc[0]
    credit_limit = Decimal(str(acct["acct_credit_limit"]))
    curr_cyc_credit = Decimal(str(acct["acct_curr_cyc_credit"]))
    curr_cyc_debit = Decimal(str(acct["acct_curr_cyc_debit"]))
    expiration_date = str(acct["acct_expiration_date"]).strip()

    # Over-limit check
    temp_bal = curr_cyc_credit - curr_cyc_debit + tran.dalytran_amt

    if credit_limit < temp_bal:
        result.is_valid = False
        result.errors.append(
            ValidationError(102, "OVERLIMIT TRANSACTION", "dalytran_amt")
        )
        # NOTE: COBOL does NOT short-circuit here; continues to expiration
        # check and the last failure wins.

    # Expiration check
    orig_date_prefix = tran.dalytran_orig_ts[:10].strip()
    if expiration_date < orig_date_prefix:
        result.is_valid = False
        # Last-failure-wins: overwrite any previous error (COBOL behaviour)
        result.errors = [
            ValidationError(
                103,
                "TRANSACTION RECEIVED AFTER ACCT EXPIRATION",
                "dalytran_orig_ts",
            )
        ]

    return result
