"""CBACT04C — Interest Calculation (INTCALC).

Iterates over the transaction-category-balance file (TCATBALF),
looks up the disclosure-group interest rate, and computes monthly
interest.  Writes interest-charge transaction records and updates
account balances.

COBOL source: ``app/cbl/CBACT04C.cbl``
JCL:          ``app/jcl/INTCALC.jcl``

Interest formula (lines 462-465):
    ``monthly_int = (TRAN-CAT-BAL * DIS-INT-RATE) / 1200``

The ``1400-COMPUTE-FEES`` paragraph is an explicit stub
("To be implemented") — kept as a no-op here.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from carddemo.models import (
    Account,
    CardXref,
    DiscGroup,
    TranCatBal,
    Transaction,
)

log = logging.getLogger(__name__)


@dataclass
class IntcalcResult:
    """Summary returned by :func:`run`."""

    records_processed: int = 0
    interest_transactions_written: int = 0


def _db2_timestamp() -> str:
    now = datetime.now()
    return now.strftime("%Y-%m-%d-%H.%M.%S.") + f"{now.microsecond // 10000:02d}0000"


def _get_interest_rate(
    session: Session,
    group_id: str,
    type_cd: str,
    cat_cd: str,
) -> Decimal:
    """Look up interest rate, falling back to 'DEFAULT' group."""
    dg = session.get(DiscGroup, (group_id, type_cd, cat_cd))
    if dg is None:
        dg = session.get(DiscGroup, ("DEFAULT", type_cd, cat_cd))
    if dg is None:
        return Decimal("0.00")
    return Decimal(str(dg.dis_int_rate))


def _compute_fees() -> None:
    """``1400-COMPUTE-FEES`` — explicit stub, not yet implemented."""
    pass


def run(
    session: Session,
    parm_date: str = "",
) -> IntcalcResult:
    """Execute the INTCALC batch job.

    Parameters
    ----------
    session:
        Active SQLAlchemy session with TCATBALF, DISCGRP, ACCOUNT,
        XREF, and TRANSACTION data loaded.
    parm_date:
        10-character date string (``YYYY-MM-DD``) used as prefix for
        generated interest transaction IDs.  Defaults to today.

    Returns
    -------
    IntcalcResult
    """
    if not parm_date:
        parm_date = datetime.now().strftime("%Y-%m-%d")

    result = IntcalcResult()
    log.info("START OF EXECUTION OF PROGRAM CBACT04C (Python)")

    stmt = select(TranCatBal).order_by(
        TranCatBal.trancat_acct_id,
        TranCatBal.trancat_type_cd,
        TranCatBal.trancat_cd,
    )
    tcb_rows = session.execute(stmt).scalars().all()

    last_acct_id: str | None = None
    total_int = Decimal("0.00")
    tranid_suffix = 0
    current_account: Account | None = None
    current_xref: CardXref | None = None

    for tcb in tcb_rows:
        result.records_processed += 1
        acct_id = str(tcb.trancat_acct_id).strip()

        if acct_id != last_acct_id:
            # Flush interest to the previous account (1050-UPDATE-ACCOUNT)
            if last_acct_id is not None and current_account is not None:
                current_account.acct_curr_bal = (
                    Decimal(str(current_account.acct_curr_bal)) + total_int
                )
                current_account.acct_curr_cyc_credit = Decimal("0.00")
                current_account.acct_curr_cyc_debit = Decimal("0.00")
                session.flush()

            total_int = Decimal("0.00")
            last_acct_id = acct_id

            current_account = session.get(Account, acct_id)
            if current_account is None:
                log.warning("Account not found: %s", acct_id)
                continue

            # Look up xref by acct_id (alternate index)
            xref_row = session.execute(
                select(CardXref).where(CardXref.xref_acct_id == acct_id)
            ).scalars().first()
            current_xref = xref_row

        if current_account is None:
            continue

        group_id = str(current_account.acct_group_id)
        type_cd = str(tcb.trancat_type_cd).strip()
        cat_cd = str(tcb.trancat_cd).strip()
        int_rate = _get_interest_rate(session, group_id, type_cd, cat_cd)

        if int_rate == 0:
            continue

        cat_bal = Decimal(str(tcb.tran_cat_bal))
        monthly_int = (cat_bal * int_rate / Decimal("1200")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        total_int += monthly_int

        # Write interest transaction (1300-B-WRITE-TX)
        tranid_suffix += 1
        tran_id = f"{parm_date}{tranid_suffix:06d}"
        card_num = ""
        if current_xref is not None:
            card_num = str(current_xref.xref_card_num).strip()

        ts = _db2_timestamp()
        tran_desc = f"Int. for a/c {acct_id}"
        posted = Transaction(
            tran_id=tran_id,
            tran_type_cd="01",
            tran_cat_cd="0005",
            tran_source="System",
            tran_desc=tran_desc,
            tran_amt=monthly_int,
            tran_merchant_id="000000000",
            tran_merchant_name="",
            tran_merchant_city="",
            tran_merchant_zip="",
            tran_card_num=card_num,
            tran_orig_ts=ts,
            tran_proc_ts=ts,
        )
        session.merge(posted)
        result.interest_transactions_written += 1

        _compute_fees()

    # Flush the last account
    if last_acct_id is not None and current_account is not None:
        current_account.acct_curr_bal = (
            Decimal(str(current_account.acct_curr_bal)) + total_int
        )
        current_account.acct_curr_cyc_credit = Decimal("0.00")
        current_account.acct_curr_cyc_debit = Decimal("0.00")

    session.commit()
    log.info(
        "Records processed: %d  Interest TXNs written: %d",
        result.records_processed,
        result.interest_transactions_written,
    )
    log.info("END OF EXECUTION OF PROGRAM CBACT04C (Python)")
    return result
