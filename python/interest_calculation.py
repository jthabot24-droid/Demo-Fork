"""Interest calculation logic migrated from CBACT04C.cbl.

Port of the COBOL paragraph ``1300-COMPUTE-INTEREST`` and its supporting
paragraphs (``1050-UPDATE-ACCOUNT``, ``1200-GET-INTEREST-RATE``).

Algorithm
---------
For every transaction-category-balance (TCATBAL) record, grouped by account:

1. Look up the account's disclosure-group ID via the account master.
2. Build the disclosure-group composite key (group_id + type_cd + cat_cd).
3. Look up the interest rate from the disclosure-group file.
4. Compute: ``monthly_interest = (tran_cat_bal * dis_int_rate) / 1200``
5. Accumulate total interest per account.
6. After processing all category-balance records for an account, update the
   account's current balance by adding the total interest and reset the cycle
   credit/debit accumulators.
7. Write an interest-charge transaction record for each non-zero interest.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from data.store import VsamStore
from models.account import AccountRecord
from models.card_xref import CardXrefRecord
from models.disclosure_group import DisclosureGroupRecord
from models.tran_cat_balance import TranCatBalanceRecord
from models.transaction import TransactionRecord


@dataclass
class InterestResult:
    """Summary returned by :func:`compute_interest`."""

    accounts_processed: int = 0
    transactions_written: int = 0
    total_interest: Decimal = Decimal("0.00")


def _make_interest_transaction(
    card_num: str,
    tran_type_cd: str,
    tran_cat_cd: int,
    amount: Decimal,
    tran_id: str,
) -> TransactionRecord:
    """Build a transaction record for the interest charge.

    Mirrors CBACT04C ``1300-B-WRITE-TX``.
    """
    now = datetime.now()
    ts = now.strftime("%Y-%m-%d-%H.%M.%S.") + f"{now.microsecond // 1000:03d}000"
    return TransactionRecord(
        tran_id=tran_id,
        tran_type_cd=tran_type_cd,
        tran_cat_cd=tran_cat_cd,
        tran_source="INTCALC",
        tran_desc="INTEREST CHARGE",
        tran_amt=amount,
        tran_merchant_id=0,
        tran_merchant_name="",
        tran_merchant_city="",
        tran_merchant_zip="",
        tran_card_num=card_num,
        tran_orig_ts=ts,
        tran_proc_ts=ts,
    )


def compute_interest(
    tcatbal_store: VsamStore[TranCatBalanceRecord],
    account_store: VsamStore[AccountRecord],
    xref_store: VsamStore[CardXrefRecord],
    discgrp_store: VsamStore[DisclosureGroupRecord],
    transaction_store: VsamStore[TransactionRecord],
    tran_id_generator: Optional[object] = None,
) -> InterestResult:
    """Execute the interest-calculation batch job (CBACT04C main loop).

    Parameters
    ----------
    tcatbal_store : VsamStore[TranCatBalanceRecord]
        Transaction-category-balance file (sequential read).
    account_store : VsamStore[AccountRecord]
        Account master file (random read/rewrite).
    xref_store : VsamStore[CardXrefRecord]
        Card cross-reference file (keyed by card_num; iterated to find
        a card for the account).
    discgrp_store : VsamStore[DisclosureGroupRecord]
        Disclosure-group file (keyed by composite key).
    transaction_store : VsamStore[TransactionRecord]
        Transaction file -- interest-charge records are written here.
    tran_id_generator : optional
        An iterator/callable that yields unique 16-char transaction IDs.
        If ``None``, IDs are auto-generated from a counter.

    Returns
    -------
    InterestResult
    """
    result = InterestResult()
    _id_counter = 0

    def _next_id() -> str:
        nonlocal _id_counter
        _id_counter += 1
        return f"INT{_id_counter:013d}"

    get_id = tran_id_generator or _next_id

    current_acct_id: Optional[int] = None
    total_int_for_acct = Decimal("0.00")

    all_tcatbal = list(tcatbal_store.read_sequential())

    for tcb in all_tcatbal:
        if tcb.trancat_acct_id != current_acct_id:
            # New account boundary -- flush the previous account
            if current_acct_id is not None:
                _update_account(
                    account_store, current_acct_id, total_int_for_acct
                )
                result.accounts_processed += 1

            current_acct_id = tcb.trancat_acct_id
            total_int_for_acct = Decimal("0.00")

        # Look up account to get group_id
        acct_key = f"{tcb.trancat_acct_id:011d}"
        acct = account_store.read(acct_key)
        if acct is None:
            continue

        # Look up disclosure-group interest rate (1200-GET-INTEREST-RATE)
        discgrp_key = (
            f"{acct.acct_group_id:10s}"
            f"{tcb.trancat_type_cd:2s}"
            f"{tcb.trancat_cd:04d}"
        )
        disc = discgrp_store.read(discgrp_key)
        if disc is None or disc.dis_int_rate == 0:
            continue

        # 1300-COMPUTE-INTEREST
        monthly_int = (tcb.tran_cat_bal * disc.dis_int_rate) / Decimal("1200")
        monthly_int = monthly_int.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        if monthly_int == 0:
            continue

        total_int_for_acct += monthly_int
        result.total_interest += monthly_int

        # Find a card number for this account (for the transaction record)
        card_num = _find_card_for_account(xref_store, tcb.trancat_acct_id)

        tran = _make_interest_transaction(
            card_num=card_num,
            tran_type_cd=tcb.trancat_type_cd,
            tran_cat_cd=tcb.trancat_cd,
            amount=monthly_int,
            tran_id=get_id() if callable(get_id) else next(get_id),
        )
        transaction_store.upsert(tran)
        result.transactions_written += 1

    # Flush last account
    if current_acct_id is not None:
        _update_account(account_store, current_acct_id, total_int_for_acct)
        result.accounts_processed += 1

    return result


def _update_account(
    account_store: VsamStore[AccountRecord],
    acct_id: int,
    total_interest: Decimal,
) -> None:
    """1050-UPDATE-ACCOUNT -- add accrued interest to account balance."""
    acct_key = f"{acct_id:011d}"
    acct = account_store.read(acct_key)
    if acct is None:
        return
    acct.acct_curr_bal += total_interest
    acct.acct_curr_cyc_credit = Decimal("0.00")
    acct.acct_curr_cyc_debit = Decimal("0.00")
    account_store.rewrite(acct)


def _find_card_for_account(
    xref_store: VsamStore[CardXrefRecord],
    acct_id: int,
) -> str:
    """Scan the cross-reference store for any card belonging to ``acct_id``."""
    for xref in xref_store.read_sequential():
        if xref.xref_acct_id == acct_id:
            return xref.xref_card_num
    return ""
