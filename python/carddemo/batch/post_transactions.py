"""CBTRN02C -- Post Daily Transactions (POSTTRAN batch job).

Faithfully replicates the COBOL control flow::

    PROCEDURE DIVISION.
        Open all files
        PERFORM UNTIL END-OF-FILE
            1000-DALYTRAN-GET-NEXT
            1500-VALIDATE-TRAN
            IF valid: 2000-POST-TRANSACTION
            ELSE:     2500-WRITE-REJECT-REC
        Close all files

The validation logic (``1500-VALIDATE-TRAN``) is delegated to
``carddemo.validation.transaction_validation.validate_batch_transaction``.

The posting logic (``2000-POST-TRANSACTION``) copies the daily
transaction to the transaction master, updates the transaction category
balance file, and updates the account record.

All monetary arithmetic uses ``decimal.Decimal``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

import pandas as pd

from carddemo.dataaccess.repository import (
    AccountRepository,
    CardXrefRepository,
    TranCatBalRepository,
    TransactionRepository,
)
from carddemo.models.account import AccountRecord
from carddemo.models.transaction import DailyTransactionRecord, TransactionRecord
from carddemo.models.transaction_category import TranCatBalRecord
from carddemo.validation.transaction_validation import validate_batch_transaction


# ---------------------------------------------------------------------------
# Result / reject types
# ---------------------------------------------------------------------------


@dataclass
class RejectedTransaction:
    """A daily transaction that failed validation."""

    record: DailyTransactionRecord
    fail_reason: int
    fail_reason_desc: str


@dataclass
class PostTransactionsResult:
    """Summary returned by ``run_post_daily_transactions``."""

    transactions_processed: int = 0
    transactions_posted: int = 0
    transactions_rejected: int = 0
    rejected: list[RejectedTransaction] = field(default_factory=list)
    return_code: int = 0


# ---------------------------------------------------------------------------
# Timestamp helper (same as interest_calc)
# ---------------------------------------------------------------------------

def _db2_format_timestamp(dt: Optional[datetime] = None) -> str:
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%Y-%m-%d-%H.%M.%S.") + f"{dt.microsecond // 10000:02d}0000"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_post_daily_transactions(
    daily_transactions: list[DailyTransactionRecord],
    xref_repo: CardXrefRepository,
    account_repo: AccountRepository,
    tcatbal_repo: TranCatBalRepository,
    transaction_repo: TransactionRepository,
    timestamp_provider: Optional[datetime] = None,
) -> PostTransactionsResult:
    """Execute the POSTTRAN batch job (CBTRN02C).

    Parameters
    ----------
    daily_transactions : list[DailyTransactionRecord]
        The sequential daily transaction file (DALYTRAN).
    xref_repo : CardXrefRepository
        Card cross-reference for validation lookups.
    account_repo : AccountRepository
        Account master for validation and balance updates.
    tcatbal_repo : TranCatBalRepository
        Transaction category balance file for balance tracking.
    transaction_repo : TransactionRepository
        Transaction master for writing posted transactions.
    timestamp_provider : datetime, optional
        Deterministic timestamp for testing.

    Returns
    -------
    PostTransactionsResult
    """
    result = PostTransactionsResult()

    # Build DataFrames from repositories for validation functions
    xref_df = xref_repo.df if hasattr(xref_repo, "df") else pd.DataFrame()
    acct_df = account_repo.df if hasattr(account_repo, "df") else pd.DataFrame()

    for tran in daily_transactions:
        result.transactions_processed += 1

        # 1500-VALIDATE-TRAN
        val_result = validate_batch_transaction(tran, xref_df, acct_df)

        if val_result.is_valid:
            # 2000-POST-TRANSACTION
            _post_transaction(
                tran,
                val_result.resolved_acct_id or 0,
                account_repo,
                tcatbal_repo,
                transaction_repo,
                xref_repo,
                timestamp_provider,
            )
            result.transactions_posted += 1
        else:
            # 2500-WRITE-REJECT-REC
            result.transactions_rejected += 1
            err = val_result.errors[0] if val_result.errors else None
            result.rejected.append(
                RejectedTransaction(
                    record=tran,
                    fail_reason=err.code if err else 0,
                    fail_reason_desc=err.message if err else "",
                )
            )

    if result.transactions_rejected > 0:
        result.return_code = 4  # COBOL: MOVE 4 TO RETURN-CODE

    return result


# ---------------------------------------------------------------------------
# Internal helpers matching COBOL paragraphs
# ---------------------------------------------------------------------------


def _post_transaction(
    tran: DailyTransactionRecord,
    acct_id: int,
    account_repo: AccountRepository,
    tcatbal_repo: TranCatBalRepository,
    transaction_repo: TransactionRepository,
    xref_repo: CardXrefRepository,
    timestamp_provider: Optional[datetime] = None,
) -> None:
    """2000-POST-TRANSACTION: copy daily tran → transaction master, update balances."""

    ts = _db2_format_timestamp(timestamp_provider)

    # Build TRAN-RECORD from DALYTRAN-RECORD
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
        tran_proc_ts=ts,
    )

    # 2700-UPDATE-TCATBAL
    _update_tcatbal(tran, acct_id, tcatbal_repo)

    # 2800-UPDATE-ACCOUNT-REC
    _update_account_for_posting(tran, acct_id, account_repo)

    # 2900-WRITE-TRANSACTION-FILE
    transaction_repo.add(posted)


def _update_tcatbal(
    tran: DailyTransactionRecord,
    acct_id: int,
    repo: TranCatBalRepository,
) -> None:
    """2700-UPDATE-TCATBAL: update or create transaction category balance record."""
    existing = repo.find_by_key(acct_id, tran.dalytran_type_cd, tran.dalytran_cat_cd)

    if existing is None:
        # 2700-A-CREATE-TCATBAL-REC
        new_rec = TranCatBalRecord(
            trancat_acct_id=acct_id,
            trancat_type_cd=tran.dalytran_type_cd,
            trancat_cd=tran.dalytran_cat_cd,
            tran_cat_bal=tran.dalytran_amt,
        )
        repo.add(new_rec)
    else:
        # 2700-B-UPDATE-TCATBAL-REC
        existing.tran_cat_bal += tran.dalytran_amt
        repo.update(existing)


def _update_account_for_posting(
    tran: DailyTransactionRecord,
    acct_id: int,
    repo: AccountRepository,
) -> None:
    """2800-UPDATE-ACCOUNT-REC: update account balance for a posted transaction."""
    account = repo.find_by_id(acct_id)
    if account is None:
        return

    account.acct_curr_bal += tran.dalytran_amt

    if tran.dalytran_amt >= Decimal("0"):
        account.acct_curr_cyc_credit += tran.dalytran_amt
    else:
        account.acct_curr_cyc_debit += tran.dalytran_amt

    repo.update(account)
