"""
Batch daily-transaction posting logic migrated from CardDemo COBOL.

Source program
--------------
* **CBTRN02C.cbl** -- Batch "Post Daily Transactions" program.
  Reads the sequential daily transaction file (DALYTRAN), validates each
  record against the card cross-reference (XREFFILE) and account master
  (ACCTFILE) before posting.  Valid transactions are written to TRANSACT,
  with TCATBAL and ACCOUNT files updated; invalid transactions are written
  to DALYREJS.

  Procedure Division paragraphs migrated:
  0000-DALYTRAN-OPEN through file close (main loop),
  1000-DALYTRAN-GET-NEXT, 1500-VALIDATE-TRAN (delegated to
  ``transaction_validation.validate_batch_transaction``),
  2000-POST-TRANSACTION, 2500-WRITE-REJECT-REC,
  2700-UPDATE-TCATBAL (A/B), 2800-UPDATE-ACCOUNT-REC,
  2900-WRITE-TRANSACTION-FILE, Z-GET-DB2-FORMAT-TIMESTAMP.

Key copybooks (field layouts)
------------------------------
* CVTRA06Y -- DALYTRAN-RECORD      (daily transaction, 350 bytes)
* CVTRA05Y -- TRAN-RECORD          (transaction master, 350 bytes)
* CVTRA01Y -- TRAN-CAT-BAL-RECORD  (transaction category balance, 50 bytes)
* CVACT03Y -- CARD-XREF-RECORD     (card cross-reference, 50 bytes)
* CVACT01Y -- ACCOUNT-RECORD       (account master, 300 bytes)

Assumptions
-----------
1. VSAM indexed file I/O is replaced by pandas DataFrame operations.
2. The COBOL ``Z-GET-DB2-FORMAT-TIMESTAMP`` utility is replaced by
   ``datetime.now()`` formatted as ``YYYY-MM-DD-HH.MM.SS.mm0000``.
3. ``decimal.Decimal`` is used for all monetary fields to match COBOL
   packed-decimal precision (``PIC S9(09)V99`` / ``PIC S9(10)V99``).
4. The batch ``validate_batch_transaction`` from ``transaction_validation``
   is reused for the 1500-VALIDATE-TRAN paragraph.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

import pandas as pd

from transaction_validation import (
    DailyTransactionRecord,
    ValidationError,
    validate_batch_transaction,
)

# ---------------------------------------------------------------------------
# Data structures mirroring COBOL copybooks
# ---------------------------------------------------------------------------


@dataclass
class TransactionRecord:
    """CVTRA05Y -- TRAN-RECORD (350 bytes).

    Output record written to the TRANSACT file.
    """

    tran_id: str = ""                          # PIC X(16)
    tran_type_cd: str = ""                     # PIC X(02)
    tran_cat_cd: int = 0                       # PIC 9(04)
    tran_source: str = ""                      # PIC X(10)
    tran_desc: str = ""                        # PIC X(100)
    tran_amt: Decimal = Decimal("0.00")        # PIC S9(09)V99
    tran_merchant_id: int = 0                  # PIC 9(09)
    tran_merchant_name: str = ""               # PIC X(50)
    tran_merchant_city: str = ""               # PIC X(50)
    tran_merchant_zip: str = ""                # PIC X(10)
    tran_card_num: str = ""                    # PIC X(16)
    tran_orig_ts: str = ""                     # PIC X(26)
    tran_proc_ts: str = ""                     # PIC X(26)


@dataclass
class TranCatBalRecord:
    """CVTRA01Y -- TRAN-CAT-BAL-RECORD (50 bytes)."""

    trancat_acct_id: int = 0                   # PIC 9(11)
    trancat_type_cd: str = ""                  # PIC X(02)
    trancat_cd: int = 0                        # PIC 9(04)
    tran_cat_bal: Decimal = Decimal("0.00")    # PIC S9(09)V99


@dataclass
class RejectRecord:
    """Rejected transaction with validation trailer.

    Maps to the REJECT-RECORD / WS-VALIDATION-TRAILER working-storage
    layout in CBTRN02C.
    """

    tran_data: DailyTransactionRecord
    fail_reason: int = 0                       # PIC 9(04)
    fail_reason_desc: str = ""                 # PIC X(76)


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class PostingResult:
    """Outcome of the batch posting run.

    ``updated_accounts`` and ``updated_tcatbal`` contain the DataFrames
    as modified by the posting loop (account balances updated, TCATBAL
    records created or updated).
    """

    transactions_processed: int = 0
    transactions_rejected: int = 0
    posted_transactions: list[TransactionRecord] = field(default_factory=list)
    reject_records: list[RejectRecord] = field(default_factory=list)
    return_code: int = 0
    updated_accounts: Optional[pd.DataFrame] = None
    updated_tcatbal: Optional[pd.DataFrame] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_db2_format_timestamp() -> str:
    """Z-GET-DB2-FORMAT-TIMESTAMP paragraph.

    Produces a DB2-style timestamp: ``YYYY-MM-DD-HH.MM.SS.mm0000``.
    """
    now = datetime.now()
    return now.strftime("%Y-%m-%d-%H.%M.%S.%f")[:26]


def _row_to_daily_tran(row: pd.Series) -> DailyTransactionRecord:
    """1000-DALYTRAN-GET-NEXT -- convert a DataFrame row."""
    return DailyTransactionRecord(
        dalytran_id=str(row.get("dalytran_id", "")),
        dalytran_type_cd=str(row.get("dalytran_type_cd", "")),
        dalytran_cat_cd=int(row.get("dalytran_cat_cd", 0)),
        dalytran_source=str(row.get("dalytran_source", "")),
        dalytran_desc=str(row.get("dalytran_desc", "")),
        dalytran_amt=Decimal(str(row.get("dalytran_amt", "0.00"))),
        dalytran_merchant_id=int(row.get("dalytran_merchant_id", 0)),
        dalytran_merchant_name=str(row.get("dalytran_merchant_name", "")),
        dalytran_merchant_city=str(row.get("dalytran_merchant_city", "")),
        dalytran_merchant_zip=str(row.get("dalytran_merchant_zip", "")),
        dalytran_card_num=str(row.get("dalytran_card_num", "")),
        dalytran_orig_ts=str(row.get("dalytran_orig_ts", "")),
        dalytran_proc_ts=str(row.get("dalytran_proc_ts", "")),
    )


# ---------------------------------------------------------------------------
# Core posting logic
# ---------------------------------------------------------------------------


def post_daily_transactions(
    daily_trans_df: pd.DataFrame,
    xref_df: pd.DataFrame,
    account_df: pd.DataFrame,
    tcatbal_df: pd.DataFrame,
) -> PostingResult:
    """Reproduce the CBTRN02C PROCEDURE DIVISION main loop.

    Parameters
    ----------
    daily_trans_df : pd.DataFrame
        Daily transaction records.  Columns match
        ``DailyTransactionRecord`` fields.
    xref_df : pd.DataFrame
        Card cross-reference records.  Must contain ``xref_card_num``,
        ``xref_acct_id``.
    account_df : pd.DataFrame
        Account master records.  Must contain ``acct_id``,
        ``acct_curr_bal``, ``acct_curr_cyc_credit``,
        ``acct_curr_cyc_debit``, ``acct_credit_limit``,
        ``acct_expiration_date``.
    tcatbal_df : pd.DataFrame
        Transaction category balance records.  Must contain
        ``trancat_acct_id``, ``trancat_type_cd``, ``trancat_cd``,
        ``tran_cat_bal``.

    Returns
    -------
    PostingResult
    """
    result = PostingResult()
    acct_working = account_df.copy()
    tcatbal_working = tcatbal_df.copy()
    new_tcatbal_rows: list[dict] = []

    for _, row in daily_trans_df.iterrows():
        tran = _row_to_daily_tran(row)
        result.transactions_processed += 1

        # 1500-VALIDATE-TRAN
        vr = validate_batch_transaction(tran, xref_df, acct_working)

        if vr.is_valid:
            # 2000-POST-TRANSACTION
            _post_transaction(
                tran, vr.resolved_acct_id, acct_working,
                tcatbal_working, new_tcatbal_rows, result,
            )
        else:
            # 2500-WRITE-REJECT-REC
            result.transactions_rejected += 1
            err = vr.errors[0] if vr.errors else ValidationError(0, "")
            result.reject_records.append(
                RejectRecord(
                    tran_data=tran,
                    fail_reason=err.code,
                    fail_reason_desc=err.message,
                )
            )

    # Merge any newly-created TCATBAL rows
    if new_tcatbal_rows:
        tcatbal_working = pd.concat(
            [tcatbal_working, pd.DataFrame(new_tcatbal_rows)],
            ignore_index=True,
        )

    if result.transactions_rejected > 0:
        result.return_code = 4

    result.updated_accounts = acct_working
    result.updated_tcatbal = tcatbal_working
    return result


def _post_transaction(
    tran: DailyTransactionRecord,
    acct_id: int,
    acct_working: pd.DataFrame,
    tcatbal_working: pd.DataFrame,
    new_tcatbal_rows: list[dict],
    result: PostingResult,
) -> None:
    """2000-POST-TRANSACTION paragraph.

    Copies daily transaction fields to a TRAN-RECORD, updates TCATBAL and
    ACCOUNT, then appends the posted transaction to the result.
    """
    posted = TransactionRecord(
        tran_id=tran.dalytran_id,
        tran_type_cd=tran.dalytran_type_cd,
        tran_cat_cd=tran.dalytran_cat_cd,
        tran_source=tran.dalytran_source,
        tran_desc=tran.dalytran_desc,
        tran_amt=tran.dalytran_amt,
        tran_merchant_id=tran.dalytran_merchant_id,
        tran_merchant_name=tran.dalytran_merchant_name,
        tran_merchant_city=tran.dalytran_merchant_city,
        tran_merchant_zip=tran.dalytran_merchant_zip,
        tran_card_num=tran.dalytran_card_num,
        tran_orig_ts=tran.dalytran_orig_ts,
        tran_proc_ts=_get_db2_format_timestamp(),
    )

    # 2700-UPDATE-TCATBAL
    _update_tcatbal(acct_id, tran, tcatbal_working, new_tcatbal_rows)

    # 2800-UPDATE-ACCOUNT-REC
    _update_account_rec(acct_id, tran, acct_working)

    # 2900-WRITE-TRANSACTION-FILE
    result.posted_transactions.append(posted)


def _update_tcatbal(
    acct_id: int,
    tran: DailyTransactionRecord,
    tcatbal_df: pd.DataFrame,
    new_rows: list[dict],
) -> None:
    """2700-UPDATE-TCATBAL paragraph.

    Looks up the TCATBAL record by composite key
    (acct_id, type_cd, cat_cd).  If found, adds the transaction amount
    to the existing balance (2700-B-UPDATE-TCATBAL-REC).  If not found,
    creates a new record with the transaction amount as the initial
    balance (2700-A-CREATE-TCATBAL-REC).
    """
    type_cd = tran.dalytran_type_cd
    cat_cd = tran.dalytran_cat_cd

    # Check existing DataFrame
    mask = (
        (tcatbal_df["trancat_acct_id"] == acct_id)
        & (tcatbal_df["trancat_type_cd"] == type_cd)
        & (tcatbal_df["trancat_cd"] == cat_cd)
    )
    matching = tcatbal_df.loc[mask]

    if not matching.empty:
        # 2700-B-UPDATE-TCATBAL-REC
        idx = matching.index[0]
        tcatbal_df.at[idx, "tran_cat_bal"] = (
            Decimal(str(tcatbal_df.at[idx, "tran_cat_bal"])) + tran.dalytran_amt
        )
        return

    # Check pending new rows (created earlier in the same run)
    for row in new_rows:
        if (
            row["trancat_acct_id"] == acct_id
            and row["trancat_type_cd"] == type_cd
            and row["trancat_cd"] == cat_cd
        ):
            row["tran_cat_bal"] = (
                Decimal(str(row["tran_cat_bal"])) + tran.dalytran_amt
            )
            return

    # 2700-A-CREATE-TCATBAL-REC
    new_rows.append(
        {
            "trancat_acct_id": acct_id,
            "trancat_type_cd": type_cd,
            "trancat_cd": cat_cd,
            "tran_cat_bal": tran.dalytran_amt,
        }
    )


def _update_account_rec(
    acct_id: int,
    tran: DailyTransactionRecord,
    account_df: pd.DataFrame,
) -> None:
    """2800-UPDATE-ACCOUNT-REC paragraph.

    Updates account balances to reflect posted transaction:

    * ``ACCT-CURR-BAL   += DALYTRAN-AMT``
    * If amount >= 0: ``ACCT-CURR-CYC-CREDIT += DALYTRAN-AMT``
    * If amount <  0: ``ACCT-CURR-CYC-DEBIT  += DALYTRAN-AMT``
    """
    mask = account_df["acct_id"] == acct_id
    idx = account_df.loc[mask].index
    if idx.empty:
        return

    i = idx[0]
    account_df.at[i, "acct_curr_bal"] = (
        Decimal(str(account_df.at[i, "acct_curr_bal"])) + tran.dalytran_amt
    )

    if tran.dalytran_amt >= 0:
        account_df.at[i, "acct_curr_cyc_credit"] = (
            Decimal(str(account_df.at[i, "acct_curr_cyc_credit"]))
            + tran.dalytran_amt
        )
    else:
        account_df.at[i, "acct_curr_cyc_debit"] = (
            Decimal(str(account_df.at[i, "acct_curr_cyc_debit"]))
            + tran.dalytran_amt
        )
