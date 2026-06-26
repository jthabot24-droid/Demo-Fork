"""Transaction posting logic migrated from CBTRN02C.cbl.

Port of the COBOL paragraphs:
  * ``2000-POST-TRANSACTION`` -- copy daily-tran fields to a transaction record
  * ``2700-UPDATE-TCATBAL``   -- create or update category-balance record
  * ``2800-UPDATE-ACCOUNT-REC`` -- adjust account balances
  * ``2900-WRITE-TRANSACTION-FILE`` -- write the posted transaction

The validation step (``1500-VALIDATE-TRAN``) is in
:mod:`transaction_validation`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from data.store import VsamStore
from models.account import AccountRecord
from models.card_xref import CardXrefRecord
from models.daily_transaction import DailyTransactionRecord
from models.tran_cat_balance import TranCatBalanceRecord
from models.transaction import TransactionRecord
from transaction_validation import (
    ValidationResult,
    validate_batch_transaction,
)


@dataclass
class PostingResult:
    """Summary returned by :func:`post_daily_transactions`."""

    transactions_posted: int = 0
    transactions_rejected: int = 0
    rejected: list[tuple[DailyTransactionRecord, ValidationResult]] = None

    def __post_init__(self) -> None:
        if self.rejected is None:
            self.rejected = []


# ── Core posting helpers (CBTRN02C paragraphs) ─────────────────────


def _db2_timestamp() -> str:
    """Z-GET-DB2-FORMAT-TIMESTAMP replacement."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d-%H.%M.%S.") + f"{now.microsecond // 1000:03d}000"


def build_transaction_from_daily(
    daily: DailyTransactionRecord,
    tran_id: str,
) -> TransactionRecord:
    """2000-POST-TRANSACTION -- copy daily-tran fields to transaction record."""
    ts = _db2_timestamp()
    return TransactionRecord(
        tran_id=tran_id,
        tran_type_cd=daily.dalytran_type_cd,
        tran_cat_cd=daily.dalytran_cat_cd,
        tran_source=daily.dalytran_source,
        tran_desc=daily.dalytran_desc,
        tran_amt=daily.dalytran_amt,
        tran_merchant_id=daily.dalytran_merchant_id,
        tran_merchant_name=daily.dalytran_merchant_name,
        tran_merchant_city=daily.dalytran_merchant_city,
        tran_merchant_zip=daily.dalytran_merchant_zip,
        tran_card_num=daily.dalytran_card_num,
        tran_orig_ts=daily.dalytran_orig_ts,
        tran_proc_ts=ts,
    )


def update_tran_cat_balance(
    tcatbal_store: VsamStore[TranCatBalanceRecord],
    acct_id: int,
    type_cd: str,
    cat_cd: int,
    amount: Decimal,
) -> None:
    """2700-UPDATE-TCATBAL -- create or update the category-balance record.

    COBOL logic:
      * Read TCATBAL by composite key (acct_id + type_cd + cat_cd).
      * If not found (status '23') -> 2700-A-CREATE-TCATBAL-REC.
      * If found -> 2700-B-UPDATE-TCATBAL-REC (add amount).
    """
    composite_key = f"{acct_id:011d}{type_cd:2s}{cat_cd:04d}"
    existing = tcatbal_store.read(composite_key)

    if existing is None:
        # 2700-A: create new record
        new_rec = TranCatBalanceRecord(
            trancat_acct_id=acct_id,
            trancat_type_cd=type_cd,
            trancat_cd=cat_cd,
            tran_cat_bal=amount,
        )
        tcatbal_store.write(new_rec)
    else:
        # 2700-B: add amount to existing balance
        existing.tran_cat_bal += amount
        tcatbal_store.rewrite(existing)


def update_account(
    account_store: VsamStore[AccountRecord],
    acct_id: int,
    amount: Decimal,
) -> None:
    """2800-UPDATE-ACCOUNT-REC -- adjust account balances.

    COBOL logic:
      * ADD DALYTRAN-AMT TO ACCT-CURR-BAL
      * IF amount >= 0: ADD to ACCT-CURR-CYC-CREDIT
      * ELSE:           ADD to ACCT-CURR-CYC-DEBIT
    """
    acct_key = f"{acct_id:011d}"
    acct = account_store.read(acct_key)
    if acct is None:
        return

    acct.acct_curr_bal += amount
    if amount >= 0:
        acct.acct_curr_cyc_credit += amount
    else:
        acct.acct_curr_cyc_debit += amount

    account_store.rewrite(acct)


# ── Batch driver ────────────────────────────────────────────────────


def post_daily_transactions(
    daily_store: VsamStore[DailyTransactionRecord],
    xref_store: VsamStore[CardXrefRecord],
    account_store: VsamStore[AccountRecord],
    tcatbal_store: VsamStore[TranCatBalanceRecord],
    transaction_store: VsamStore[TransactionRecord],
    tran_id_start: int = 1,
) -> PostingResult:
    """Execute the daily-transaction posting batch job (CBTRN02C main loop).

    Reads daily transactions sequentially, validates each one, and for valid
    transactions: writes a transaction record, updates the category-balance
    file, and updates the account master.

    Parameters
    ----------
    daily_store : VsamStore[DailyTransactionRecord]
        Daily transaction input file (sequential read).
    xref_store : VsamStore[CardXrefRecord]
        Card cross-reference file (used for validation lookups).
    account_store : VsamStore[AccountRecord]
        Account master file (read and rewrite).
    tcatbal_store : VsamStore[TranCatBalanceRecord]
        Transaction-category-balance file (read/write/rewrite).
    transaction_store : VsamStore[TransactionRecord]
        Transaction master file (write posted transactions).
    tran_id_start : int
        Starting counter for auto-generated transaction IDs.

    Returns
    -------
    PostingResult
    """
    result = PostingResult()
    tran_counter = tran_id_start

    xref_df = xref_store.to_dataframe()
    account_df = account_store.to_dataframe()

    for daily in daily_store.read_sequential():
        # 1500-VALIDATE-TRAN
        vr = validate_batch_transaction(daily, xref_df, account_df)

        if not vr.is_valid:
            result.transactions_rejected += 1
            result.rejected.append((daily, vr))
            continue

        acct_id = vr.resolved_acct_id
        tran_id = f"TRN{tran_counter:013d}"
        tran_counter += 1

        # 2000-POST-TRANSACTION
        tran = build_transaction_from_daily(daily, tran_id)
        transaction_store.upsert(tran)
        result.transactions_posted += 1

        # 2700-UPDATE-TCATBAL
        update_tran_cat_balance(
            tcatbal_store,
            acct_id,
            daily.dalytran_type_cd,
            daily.dalytran_cat_cd,
            daily.dalytran_amt,
        )

        # 2800-UPDATE-ACCOUNT-REC
        update_account(account_store, acct_id, daily.dalytran_amt)

        # Refresh account_df so subsequent validations see updated balances
        account_df = account_store.to_dataframe()

    return result
