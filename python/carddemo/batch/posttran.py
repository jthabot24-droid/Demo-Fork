"""CBTRN02C — Post Daily Transactions (POSTTRAN).

Reads the sequential daily-transaction file, validates each record
against the card cross-reference and account master, and posts valid
transactions.  Rejected records are written to a rejects file.

COBOL source: ``app/cbl/CBTRN02C.cbl``
JCL:          ``app/jcl/POSTTRAN.jcl``

Validation rules (lines 370-422 of CBTRN02C.cbl):
  1500-A-LOOKUP-XREF  — card number must exist in XREF file
  1500-B-LOOKUP-ACCT  — account must exist; overlimit check
                         (credit_limit >= cyc_credit - cyc_debit + amt);
                         expiration-date check (acct exp >= tran orig date)

Post logic (lines 424-560):
  - Copy daily-tran fields to transaction record
  - Generate DB2-format processing timestamp
  - Update TCATBAL (create or add to category balance)
  - Update account: add amt to curr_bal; split into cyc_credit / cyc_debit
  - Write posted transaction
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Sequence

from sqlalchemy.orm import Session

from carddemo.models import (
    Account,
    CardXref,
    TranCatBal,
    Transaction,
)

log = logging.getLogger(__name__)


@dataclass
class RejectRecord:
    """A rejected daily transaction with the reason."""

    raw_data: dict
    fail_code: int
    fail_reason: str


@dataclass
class PosttranResult:
    """Summary returned by :func:`run`."""

    transactions_processed: int = 0
    transactions_posted: int = 0
    transactions_rejected: int = 0
    rejects: list[RejectRecord] = field(default_factory=list)


def _db2_timestamp() -> str:
    """Generate a DB2-format timestamp ``YYYY-MM-DD-HH.MM.SS.NN0000``."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d-%H.%M.%S.") + f"{now.microsecond // 10000:02d}0000"


def _validate_transaction(
    tran: dict,
    session: Session,
) -> tuple[int, str, CardXref | None, Account | None]:
    """Validate a daily transaction.

    Returns ``(fail_code, fail_reason, xref, account)``.
    ``fail_code == 0`` means the transaction is valid.
    """
    card_num = str(tran["dalytran_card_num"]).strip()
    xref = session.get(CardXref, card_num)
    if xref is None:
        return 100, "INVALID CARD NUMBER FOUND", None, None

    acct = session.get(Account, xref.xref_acct_id)
    if acct is None:
        return 101, "ACCOUNT RECORD NOT FOUND", xref, None

    tran_amt = Decimal(str(tran["dalytran_amt"]))
    cyc_credit = Decimal(str(acct.acct_curr_cyc_credit))
    cyc_debit = Decimal(str(acct.acct_curr_cyc_debit))
    credit_limit = Decimal(str(acct.acct_credit_limit))
    temp_bal = cyc_credit - cyc_debit + tran_amt
    if credit_limit < temp_bal:
        return 102, "OVERLIMIT TRANSACTION", xref, acct

    acct_exp = str(acct.acct_expiration_date).strip()
    orig_ts = str(tran["dalytran_orig_ts"]).strip()
    orig_date = orig_ts[:10]
    if acct_exp < orig_date:
        return 103, "TRANSACTION RECEIVED AFTER ACCT EXPIRATION", xref, acct

    return 0, "", xref, acct


def _post_transaction(
    tran: dict,
    xref: CardXref,
    acct: Account,
    session: Session,
) -> None:
    """Post a valid daily transaction."""
    proc_ts = _db2_timestamp()
    tran_amt = Decimal(str(tran["dalytran_amt"]))

    posted = Transaction(
        tran_id=str(tran["dalytran_id"]).strip(),
        tran_type_cd=str(tran["dalytran_type_cd"]).strip(),
        tran_cat_cd=str(tran["dalytran_cat_cd"]).strip(),
        tran_source=str(tran["dalytran_source"]).strip(),
        tran_desc=str(tran["dalytran_desc"]).strip(),
        tran_amt=tran_amt,
        tran_merchant_id=str(tran["dalytran_merchant_id"]).strip(),
        tran_merchant_name=str(tran["dalytran_merchant_name"]).strip(),
        tran_merchant_city=str(tran["dalytran_merchant_city"]).strip(),
        tran_merchant_zip=str(tran["dalytran_merchant_zip"]).strip(),
        tran_card_num=str(tran["dalytran_card_num"]).strip(),
        tran_orig_ts=str(tran["dalytran_orig_ts"]).strip(),
        tran_proc_ts=proc_ts,
    )
    session.merge(posted)

    # Update TCATBAL (2700-UPDATE-TCATBAL)
    acct_id = xref.xref_acct_id
    type_cd = str(tran["dalytran_type_cd"]).strip()
    cat_cd = str(tran["dalytran_cat_cd"]).strip()
    tcb = session.get(TranCatBal, (acct_id, type_cd, cat_cd))
    if tcb is None:
        tcb = TranCatBal(
            trancat_acct_id=acct_id,
            trancat_type_cd=type_cd,
            trancat_cd=cat_cd,
            tran_cat_bal=tran_amt,
        )
        session.add(tcb)
    else:
        tcb.tran_cat_bal = Decimal(str(tcb.tran_cat_bal)) + tran_amt

    # Update account (2800-UPDATE-ACCOUNT-REC)
    acct.acct_curr_bal = Decimal(str(acct.acct_curr_bal)) + tran_amt
    if tran_amt >= 0:
        acct.acct_curr_cyc_credit = Decimal(str(acct.acct_curr_cyc_credit)) + tran_amt
    else:
        acct.acct_curr_cyc_debit = Decimal(str(acct.acct_curr_cyc_debit)) + tran_amt

    session.flush()


def run(
    daily_transactions: Sequence[dict],
    session: Session,
) -> PosttranResult:
    """Execute the POSTTRAN batch job.

    Parameters
    ----------
    daily_transactions:
        Sequence of parsed daily-transaction dicts (from
        ``fixed_width.read_file`` with ``DAILY_TRANSACTION_SPEC``).
    session:
        An active SQLAlchemy session with account, xref, and tcatbal
        data already loaded.

    Returns
    -------
    PosttranResult
        Summary with counts and reject details.
    """
    result = PosttranResult()
    log.info("START OF EXECUTION OF PROGRAM CBTRN02C (Python)")

    for tran in daily_transactions:
        result.transactions_processed += 1
        fail_code, fail_reason, xref, acct = _validate_transaction(tran, session)

        if fail_code == 0 and xref is not None and acct is not None:
            _post_transaction(tran, xref, acct, session)
            result.transactions_posted += 1
        else:
            result.transactions_rejected += 1
            result.rejects.append(RejectRecord(
                raw_data=tran,
                fail_code=fail_code,
                fail_reason=fail_reason,
            ))

    session.commit()
    log.info(
        "TRANSACTIONS PROCESSED: %d  POSTED: %d  REJECTED: %d",
        result.transactions_processed,
        result.transactions_posted,
        result.transactions_rejected,
    )
    log.info("END OF EXECUTION OF PROGRAM CBTRN02C (Python)")
    return result
