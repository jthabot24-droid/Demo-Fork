"""CBACT04C -- Interest Calculator (INTCALC batch job).

Faithfully replicates the COBOL paragraph ordering and control flow:

    PROCEDURE DIVISION USING EXTERNAL-PARMS.
        Open TCATBALF, XREF, DISCGRP, ACCTFILE, TRANSACT
        PERFORM UNTIL END-OF-FILE
            1000-TCATBALF-GET-NEXT
            IF new account:
                1050-UPDATE-ACCOUNT (previous account)
                reset totals
                1100-GET-ACCT-DATA
                1110-GET-XREF-DATA
            1200-GET-INTEREST-RATE
            IF rate != 0:
                1300-COMPUTE-INTEREST
                1400-COMPUTE-FEES (stub)
        Close all files

Key formula (1300-COMPUTE-INTEREST)::

    COMPUTE WS-MONTHLY-INT = (TRAN-CAT-BAL * DIS-INT-RATE) / 1200

This divides the annual percentage rate by 12 (months) and by 100
(percent→decimal), producing a monthly interest amount.  All arithmetic
uses ``decimal.Decimal``.

1400-COMPUTE-FEES is a stub in the original COBOL ("To be implemented").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

from carddemo.dataaccess.repository import (
    AccountRepository,
    CardXrefRepository,
    DisclosureGroupRepository,
    TranCatBalRepository,
    TransactionRepository,
)
from carddemo.models.account import AccountRecord
from carddemo.models.transaction import TransactionRecord
from carddemo.models.transaction_category import TranCatBalRecord


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class InterestCalcResult:
    """Summary returned by ``run_interest_calculation``."""

    records_processed: int = 0
    transactions_written: int = 0
    accounts_updated: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Timestamp helper (Z-GET-DB2-FORMAT-TIMESTAMP)
# ---------------------------------------------------------------------------

def _db2_format_timestamp(dt: Optional[datetime] = None) -> str:
    """Produce a DB2-style 26-char timestamp.

    Format: ``YYYY-MM-DD-HH.MM.SS.mm0000``

    Mirrors the COBOL paragraph ``Z-GET-DB2-FORMAT-TIMESTAMP``.
    """
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%Y-%m-%d-%H.%M.%S.") + f"{dt.microsecond // 10000:02d}0000"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def run_interest_calculation(
    tcatbal_repo: TranCatBalRepository,
    xref_repo: CardXrefRepository,
    discgrp_repo: DisclosureGroupRepository,
    account_repo: AccountRepository,
    transaction_repo: TransactionRepository,
    parm_date: str,
    timestamp_provider: Optional[datetime] = None,
) -> InterestCalcResult:
    """Execute the INTCALC batch job (CBACT04C).

    Parameters
    ----------
    tcatbal_repo : TranCatBalRepository
        Sequential read of transaction category balances.
    xref_repo : CardXrefRepository
        Random keyed access to card cross-reference (AIX by acct_id).
    discgrp_repo : DisclosureGroupRepository
        Random keyed access to disclosure group / interest rates.
    account_repo : AccountRepository
        Random keyed access (read + rewrite) to account master.
    transaction_repo : TransactionRepository
        Sequential write of interest-charge transaction records.
    parm_date : str
        The run date passed via JCL PARM (``PIC X(10)``), used as the
        first 10 characters of each generated transaction ID.
    timestamp_provider : datetime, optional
        If given, used instead of ``datetime.now()`` for deterministic
        testing of timestamps.

    Returns
    -------
    InterestCalcResult
    """
    result = InterestCalcResult()

    last_acct_num: Optional[int] = None
    total_int = Decimal("0.00")
    first_time = True
    tranid_suffix = 0

    current_account: Optional[AccountRecord] = None
    current_card_num: Optional[str] = None

    for tcatbal in tcatbal_repo.iter_all():
        result.records_processed += 1

        # -- Account break logic --
        if tcatbal.trancat_acct_id != last_acct_num:
            # 1050-UPDATE-ACCOUNT for previous account
            if not first_time and current_account is not None:
                _update_account(current_account, total_int, account_repo)
                result.accounts_updated += 1
            else:
                first_time = False

            total_int = Decimal("0.00")
            last_acct_num = tcatbal.trancat_acct_id

            # 1100-GET-ACCT-DATA
            current_account = account_repo.find_by_id(tcatbal.trancat_acct_id)
            if current_account is None:
                result.errors.append(
                    f"ACCOUNT NOT FOUND: {tcatbal.trancat_acct_id}"
                )
                continue

            # 1110-GET-XREF-DATA
            xref = xref_repo.find_by_acct_id(tcatbal.trancat_acct_id)
            if xref is None:
                result.errors.append(
                    f"XREF NOT FOUND FOR ACCOUNT: {tcatbal.trancat_acct_id}"
                )
                current_card_num = ""
            else:
                current_card_num = xref.xref_card_num

        if current_account is None:
            continue

        # 1200-GET-INTEREST-RATE
        int_rate = _get_interest_rate(
            discgrp_repo,
            current_account.acct_group_id,
            tcatbal.trancat_type_cd,
            tcatbal.trancat_cd,
        )

        if int_rate != Decimal("0.00"):
            # 1300-COMPUTE-INTEREST
            monthly_int = (tcatbal.tran_cat_bal * int_rate) / Decimal("1200")
            total_int += monthly_int

            # 1300-B-WRITE-TX
            tranid_suffix += 1
            tran = _build_interest_transaction(
                parm_date=parm_date,
                tranid_suffix=tranid_suffix,
                monthly_int=monthly_int,
                acct_id=current_account.acct_id,
                card_num=current_card_num or "",
                timestamp_provider=timestamp_provider,
            )
            transaction_repo.add(tran)
            result.transactions_written += 1

            # 1400-COMPUTE-FEES (stub -- "To be implemented" in COBOL)

    # After EOF: update the last account
    if current_account is not None and not first_time:
        _update_account(current_account, total_int, account_repo)
        result.accounts_updated += 1

    return result


# ---------------------------------------------------------------------------
# Internal helpers matching COBOL paragraphs
# ---------------------------------------------------------------------------


def _update_account(
    account: AccountRecord,
    total_int: Decimal,
    repo: AccountRepository,
) -> None:
    """1050-UPDATE-ACCOUNT: add interest to balance, zero cycle accumulators."""
    account.acct_curr_bal += total_int
    account.acct_curr_cyc_credit = Decimal("0")
    account.acct_curr_cyc_debit = Decimal("0")
    repo.update(account)


def _get_interest_rate(
    repo: DisclosureGroupRepository,
    acct_group_id: str,
    tran_type_cd: str,
    tran_cat_cd: int,
) -> Decimal:
    """1200-GET-INTEREST-RATE + 1200-A-GET-DEFAULT-INT-RATE.

    First tries the account's group; if not found (VSAM status '23'),
    falls back to the 'DEFAULT' group.
    """
    rec = repo.find_by_key(acct_group_id, tran_type_cd, tran_cat_cd)
    if rec is not None:
        return rec.dis_int_rate

    # Fallback: try DEFAULT group
    rec = repo.find_by_key("DEFAULT", tran_type_cd, tran_cat_cd)
    if rec is not None:
        return rec.dis_int_rate

    return Decimal("0.00")


def _build_interest_transaction(
    parm_date: str,
    tranid_suffix: int,
    monthly_int: Decimal,
    acct_id: int,
    card_num: str,
    timestamp_provider: Optional[datetime] = None,
) -> TransactionRecord:
    """1300-B-WRITE-TX: build a TRAN-RECORD for the interest charge.

    COBOL builds the transaction ID via::

        STRING PARM-DATE, WS-TRANID-SUFFIX
          DELIMITED BY SIZE INTO TRAN-ID

    ``PARM-DATE`` is 10 chars, ``WS-TRANID-SUFFIX`` is ``PIC 9(06)``,
    giving a 16-char ``TRAN-ID``.
    """
    ts = _db2_format_timestamp(timestamp_provider)

    # TRAN-DESC: 'Int. for a/c ' + ACCT-ID (11 digits)
    # In COBOL: STRING 'Int. for a/c ', ACCT-ID DELIMITED BY SIZE INTO TRAN-DESC
    tran_desc = f"Int. for a/c {acct_id:011d}"

    return TransactionRecord(
        tran_id=f"{parm_date}{tranid_suffix:06d}",
        tran_type_cd="01",
        tran_cat_cd=5,        # COBOL: MOVE '05' TO TRAN-CAT-CD (PIC 9(04) stores 5)
        tran_source="System",
        tran_desc=tran_desc,
        tran_amt=monthly_int,
        tran_merchant_id=0,
        tran_merchant_name="",
        tran_merchant_city="",
        tran_merchant_zip="",
        tran_card_num=card_num,
        tran_orig_ts=ts,
        tran_proc_ts=ts,
    )
