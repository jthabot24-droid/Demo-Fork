"""
Interest calculation batch program migrated from CardDemo COBOL.

Source program
--------------
* **CBACT04C.cbl** -- Batch "Interest Calculator" program.
  Reads the transaction category balance file (TCATBALF) sequentially,
  grouped by account.  For each category balance record the disclosure
  group interest rate is looked up and monthly interest is computed.
  Interest transactions are written to the TRANSACT output file, and
  each account's current balance is updated with the accumulated
  interest.

  Procedure Division paragraphs migrated:
  0000-TCATBALF-OPEN through file close (main loop),
  1000-TCATBALF-GET-NEXT, 1050-UPDATE-ACCOUNT,
  1100-GET-ACCT-DATA, 1110-GET-XREF-DATA,
  1200-GET-INTEREST-RATE / 1200-A-GET-DEFAULT-INT-RATE,
  1300-COMPUTE-INTEREST / 1300-B-WRITE-TX,
  1400-COMPUTE-FEES (stub), Z-GET-DB2-FORMAT-TIMESTAMP.

Key copybooks (field layouts)
------------------------------
* CVTRA01Y -- TRAN-CAT-BAL-RECORD  (transaction category balance, 50 bytes)
* CVTRA02Y -- DIS-GROUP-RECORD     (disclosure group, 50 bytes)
* CVACT01Y -- ACCOUNT-RECORD       (account master, 300 bytes)
* CVACT03Y -- CARD-XREF-RECORD     (card cross-reference, 50 bytes)
* CVTRA05Y -- TRAN-RECORD          (transaction master, 350 bytes)

Assumptions
-----------
1. VSAM file I/O is replaced by pandas DataFrame operations.
2. TCATBAL records are expected to be sorted (or sortable) by
   ``trancat_acct_id`` -- the program sorts the input DataFrame to
   ensure correct account-change detection.
3. ``decimal.Decimal`` is used for all monetary and rate fields to match
   COBOL packed-decimal precision.
4. The ``1400-COMPUTE-FEES`` paragraph is a stub in the COBOL source
   (``"To be implemented"``) and is represented as a no-op here.
5. The ``PARM-DATE`` JCL parameter is passed as a Python string argument
   (format ``YYYY-MM-DD``, 10 characters).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional

import pandas as pd

from post_transactions import TransactionRecord

# ---------------------------------------------------------------------------
# Data structures mirroring COBOL copybooks
# ---------------------------------------------------------------------------


@dataclass
class DisGroupRecord:
    """CVTRA02Y -- DIS-GROUP-RECORD (disclosure group, 50 bytes)."""

    dis_acct_group_id: str = ""                # PIC X(10)
    dis_tran_type_cd: str = ""                 # PIC X(02)
    dis_tran_cat_cd: int = 0                   # PIC 9(04)
    dis_int_rate: Decimal = Decimal("0.00")    # PIC S9(04)V99


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass
class InterestResult:
    """Outcome of the interest calculation run."""

    records_processed: int = 0
    interest_transactions: list[TransactionRecord] = field(default_factory=list)
    updated_accounts: Optional[pd.DataFrame] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_db2_format_timestamp() -> str:
    """Z-GET-DB2-FORMAT-TIMESTAMP paragraph."""
    now = datetime.now()
    return now.strftime("%Y-%m-%d-%H.%M.%S.%f")[:26]


def _lookup_interest_rate(
    acct_group_id: str,
    tran_type_cd: str,
    tran_cat_cd: int,
    discgrp_df: pd.DataFrame,
) -> Decimal:
    """1200-GET-INTEREST-RATE paragraph.

    Looks up the disclosure group by (group_id, type_cd, cat_cd).
    If not found, falls back to ``'DEFAULT'`` as the group ID
    (1200-A-GET-DEFAULT-INT-RATE).
    """
    mask = (
        (discgrp_df["dis_acct_group_id"] == acct_group_id)
        & (discgrp_df["dis_tran_type_cd"] == tran_type_cd)
        & (discgrp_df["dis_tran_cat_cd"] == tran_cat_cd)
    )
    match = discgrp_df.loc[mask]

    if match.empty:
        # 1200-A-GET-DEFAULT-INT-RATE
        default_mask = (
            (discgrp_df["dis_acct_group_id"] == "DEFAULT")
            & (discgrp_df["dis_tran_type_cd"] == tran_type_cd)
            & (discgrp_df["dis_tran_cat_cd"] == tran_cat_cd)
        )
        match = discgrp_df.loc[default_mask]

    if match.empty:
        return Decimal("0.00")

    return Decimal(str(match.iloc[0]["dis_int_rate"]))


def _update_account_interest(
    acct_id: int,
    total_int: Decimal,
    acct_df: pd.DataFrame,
) -> None:
    """1050-UPDATE-ACCOUNT paragraph.

    Adds accumulated interest to the account balance and resets the
    cycle credit/debit accumulators to zero.
    """
    mask = acct_df["acct_id"] == acct_id
    idx = acct_df.loc[mask].index
    if idx.empty:
        return

    i = idx[0]
    acct_df.at[i, "acct_curr_bal"] = (
        Decimal(str(acct_df.at[i, "acct_curr_bal"])) + total_int
    )
    acct_df.at[i, "acct_curr_cyc_credit"] = Decimal("0.00")
    acct_df.at[i, "acct_curr_cyc_debit"] = Decimal("0.00")


# ---------------------------------------------------------------------------
# Core interest-calculation logic
# ---------------------------------------------------------------------------


def calculate_interest(
    tcatbal_df: pd.DataFrame,
    xref_df: pd.DataFrame,
    account_df: pd.DataFrame,
    discgrp_df: pd.DataFrame,
    parm_date: str,
) -> InterestResult:
    """Reproduce the CBACT04C PROCEDURE DIVISION main loop.

    Parameters
    ----------
    tcatbal_df : pd.DataFrame
        Transaction category balance records.  Must contain
        ``trancat_acct_id``, ``trancat_type_cd``, ``trancat_cd``,
        ``tran_cat_bal``.
    xref_df : pd.DataFrame
        Card cross-reference records.  Must contain ``xref_acct_id``,
        ``xref_card_num``.
    account_df : pd.DataFrame
        Account master records.  Must contain ``acct_id``,
        ``acct_curr_bal``, ``acct_curr_cyc_credit``,
        ``acct_curr_cyc_debit``, ``acct_group_id``.
    discgrp_df : pd.DataFrame
        Disclosure group records.  Must contain ``dis_acct_group_id``,
        ``dis_tran_type_cd``, ``dis_tran_cat_cd``, ``dis_int_rate``.
    parm_date : str
        JCL PARM-DATE (``YYYY-MM-DD``), used for interest transaction
        IDs.

    Returns
    -------
    InterestResult
    """
    result = InterestResult()
    acct_working = account_df.copy()
    result.updated_accounts = acct_working

    last_acct_id: int = -1
    total_int = Decimal("0.00")
    first_time = True
    tranid_suffix = 0

    # Current account context
    acct_group_id = ""
    card_num = ""
    current_acct_id = 0

    # Sort by account to match COBOL sequential read of indexed VSAM file
    tcatbal_sorted = tcatbal_df.sort_values(
        "trancat_acct_id"
    ).reset_index(drop=True)

    for _, row in tcatbal_sorted.iterrows():
        result.records_processed += 1

        rec_acct_id = int(row["trancat_acct_id"])
        rec_type_cd = str(row["trancat_type_cd"])
        rec_cat_cd = int(row["trancat_cd"])
        rec_bal = Decimal(str(row["tran_cat_bal"]))

        # Account-change detection
        if rec_acct_id != last_acct_id:
            if not first_time:
                # 1050-UPDATE-ACCOUNT for previous account
                _update_account_interest(last_acct_id, total_int, acct_working)
            else:
                first_time = False

            total_int = Decimal("0.00")
            last_acct_id = rec_acct_id

            # 1100-GET-ACCT-DATA
            acct_mask = acct_working["acct_id"] == rec_acct_id
            acct_match = acct_working.loc[acct_mask]
            if not acct_match.empty:
                acct_group_id = str(
                    acct_match.iloc[0]["acct_group_id"]
                ).strip()
                current_acct_id = int(acct_match.iloc[0]["acct_id"])
            else:
                acct_group_id = ""
                current_acct_id = rec_acct_id

            # 1110-GET-XREF-DATA
            xref_mask = xref_df["xref_acct_id"] == rec_acct_id
            xref_match = xref_df.loc[xref_mask]
            if not xref_match.empty:
                card_num = str(xref_match.iloc[0]["xref_card_num"])
            else:
                card_num = ""

        # 1200-GET-INTEREST-RATE
        int_rate = _lookup_interest_rate(
            acct_group_id, rec_type_cd, rec_cat_cd, discgrp_df,
        )

        if int_rate != 0:
            # 1300-COMPUTE-INTEREST
            monthly_int = (rec_bal * int_rate) / Decimal("1200")
            total_int += monthly_int

            # 1300-B-WRITE-TX
            tranid_suffix += 1
            tran_id = f"{parm_date[:10]}{tranid_suffix:06d}"

            ts = _get_db2_format_timestamp()
            interest_tran = TransactionRecord(
                tran_id=tran_id,
                tran_type_cd="01",
                tran_cat_cd=5,
                tran_source="System",
                tran_desc=f"Int. for a/c {current_acct_id:011d}",
                tran_amt=monthly_int,
                tran_merchant_id=0,
                tran_merchant_name="",
                tran_merchant_city="",
                tran_merchant_zip="",
                tran_card_num=card_num,
                tran_orig_ts=ts,
                tran_proc_ts=ts,
            )
            result.interest_transactions.append(interest_tran)

            # 1400-COMPUTE-FEES (stub -- "To be implemented")

    # After loop: 1050-UPDATE-ACCOUNT for the last account
    if not first_time:
        _update_account_interest(last_acct_id, total_int, acct_working)

    return result
