"""
Interest calculation batch job migrated from CardDemo COBOL program CBACT04C.cbl.

Source program
--------------
* **CBACT04C.cbl** -- Batch COBOL program (INTCALC job).
  Reads the transaction-category-balance file (TCATBALF) sequentially,
  groups records by account, looks up the disclosure-group interest rate,
  computes monthly interest, writes interest-transaction records to
  TRANSACT, and updates the account master balance.

Key copybooks (field layouts)
------------------------------
* CVTRA01Y -- TRAN-CAT-BAL-RECORD   (transaction category balance, 50 bytes)
* CVACT03Y -- CARD-XREF-RECORD      (card cross-reference, 50 bytes)
* CVTRA02Y -- DIS-GROUP-RECORD       (disclosure group, 50 bytes)
* CVACT01Y -- ACCOUNT-RECORD         (account master, 300 bytes)
* CVTRA05Y -- TRAN-RECORD            (transaction, 350 bytes)

Runtime parameter
-----------------
``PARM-DATE`` (``PIC X(10)``) -- passed via ``PROCEDURE DIVISION USING
EXTERNAL-PARMS``.  Used as a prefix for the generated transaction ID.

Assumptions
-----------
1. VSAM indexed lookups are modelled as pandas DataFrame filters keyed on
   the same fields as the COBOL record layouts.
2. ``decimal.Decimal`` is used for all monetary arithmetic to match COBOL
   packed-decimal precision (never ``float``).
3. COBOL ``COMPUTE`` without ``ROUNDED`` truncates toward zero; we use
   ``decimal.ROUND_DOWN``.
4. ``CEE3ABD`` (Language Environment abend) is mapped to a Python exception.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from typing import Callable, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Abend mapping
# ---------------------------------------------------------------------------


class CBACT04CAbend(Exception):
    """Maps to CEE3ABD (Language Environment abend service) on fatal errors."""

    def __init__(self, message: str, abend_code: int = 999):
        self.abend_code = abend_code
        super().__init__(f"ABEND {abend_code}: {message}")


# ---------------------------------------------------------------------------
# Decimal quantizer for PIC S9(09)V99 / PIC S9(10)V99
# ---------------------------------------------------------------------------

_V99 = Decimal("0.01")

# ---------------------------------------------------------------------------
# Data structures mirroring COBOL copybooks
# ---------------------------------------------------------------------------


@dataclass
class TranCatBalRecord:
    """CVTRA01Y -- Transaction category balance record (50 bytes)."""

    trancat_acct_id: int = 0  # PIC 9(11)
    trancat_type_cd: str = ""  # PIC X(02)
    trancat_cd: int = 0  # PIC 9(04)
    tran_cat_bal: Decimal = Decimal("0.00")  # PIC S9(09)V99


@dataclass
class CardXrefRecord:
    """CVACT03Y -- Card cross-reference record (50 bytes)."""

    xref_card_num: str = ""  # PIC X(16)
    xref_cust_id: int = 0  # PIC 9(09)
    xref_acct_id: int = 0  # PIC 9(11)


@dataclass
class DisGroupRecord:
    """CVTRA02Y -- Disclosure group record (50 bytes)."""

    dis_acct_group_id: str = ""  # PIC X(10)
    dis_tran_type_cd: str = ""  # PIC X(02)
    dis_tran_cat_cd: int = 0  # PIC 9(04)
    dis_int_rate: Decimal = Decimal("0.00")  # PIC S9(04)V99


@dataclass
class AccountRecord:
    """CVACT01Y -- Account record (300 bytes)."""

    acct_id: int = 0  # PIC 9(11)
    acct_active_status: str = ""  # PIC X(01)
    acct_curr_bal: Decimal = Decimal("0.00")  # PIC S9(10)V99
    acct_credit_limit: Decimal = Decimal("0.00")  # PIC S9(10)V99
    acct_cash_credit_limit: Decimal = Decimal("0.00")  # PIC S9(10)V99
    acct_open_date: str = ""  # PIC X(10)
    acct_expiration_date: str = ""  # PIC X(10)
    acct_reissue_date: str = ""  # PIC X(10)
    acct_curr_cyc_credit: Decimal = Decimal("0.00")  # PIC S9(10)V99
    acct_curr_cyc_debit: Decimal = Decimal("0.00")  # PIC S9(10)V99
    acct_addr_zip: str = ""  # PIC X(10)
    acct_group_id: str = ""  # PIC X(10)


@dataclass
class TransactionRecord:
    """CVTRA05Y -- Transaction record (350 bytes)."""

    tran_id: str = ""  # PIC X(16)
    tran_type_cd: str = ""  # PIC X(02)
    tran_cat_cd: int = 0  # PIC 9(04)
    tran_source: str = ""  # PIC X(10)
    tran_desc: str = ""  # PIC X(100)
    tran_amt: Decimal = Decimal("0.00")  # PIC S9(09)V99
    tran_merchant_id: int = 0  # PIC 9(09)
    tran_merchant_name: str = ""  # PIC X(50)
    tran_merchant_city: str = ""  # PIC X(50)
    tran_merchant_zip: str = ""  # PIC X(10)
    tran_card_num: str = ""  # PIC X(16)
    tran_orig_ts: str = ""  # PIC X(26)
    tran_proc_ts: str = ""  # PIC X(26)


# ---------------------------------------------------------------------------
# Timestamp helper
# ---------------------------------------------------------------------------


def get_db2_format_timestamp() -> str:
    """Port of Z-GET-DB2-FORMAT-TIMESTAMP.

    Produces: ``YYYY-MM-DD-HH.MM.SS.cc0000``
    where *cc* = centiseconds (``COB-MIL`` in the COBOL source, i.e. the
    first two digits of the six-digit microsecond field from
    ``FUNCTION CURRENT-DATE``).
    """
    now = datetime.now()
    centiseconds = now.microsecond // 10000
    return (
        f"{now.year:04d}-{now.month:02d}-{now.day:02d}-"
        f"{now.hour:02d}.{now.minute:02d}.{now.second:02d}."
        f"{centiseconds:02d}0000"
    )


# ---------------------------------------------------------------------------
# Interest computation  (1300-COMPUTE-INTEREST)
# ---------------------------------------------------------------------------


def compute_interest(
    tran_cat_bal: Decimal,
    dis_int_rate: Decimal,
) -> Decimal:
    """Port of 1300-COMPUTE-INTEREST.

    ``COMPUTE WS-MONTHLY-INT = (TRAN-CAT-BAL * DIS-INT-RATE) / 1200``

    COBOL ``COMPUTE`` without the ``ROUNDED`` keyword truncates the result
    to the scale of the receiving field (``PIC S9(09)V99`` -- 2 decimal
    places).  ``ROUND_DOWN`` (truncation toward zero) replicates this.
    """
    return (tran_cat_bal * dis_int_rate / Decimal("1200")).quantize(
        _V99, rounding=ROUND_DOWN
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _lookup_discgrp(
    discgrp_df: pd.DataFrame,
    acct_group_id: str,
    tran_type_cd: str,
    tran_cat_cd: int,
) -> Decimal:
    """Port of 1200-GET-INTEREST-RATE with DEFAULT fallback.

    When the primary key (group + type + cat) is not found (VSAM status
    ``23``), the program retries with ``'DEFAULT'`` as the group ID
    (``1200-A-GET-DEFAULT-INT-RATE``).

    Returns
    -------
    Decimal
        The ``DIS-INT-RATE`` value.

    Raises
    ------
    CBACT04CAbend
        If neither the primary nor the DEFAULT lookup succeeds.
    """
    match = discgrp_df.loc[
        (discgrp_df["dis_acct_group_id"] == acct_group_id)
        & (discgrp_df["dis_tran_type_cd"] == tran_type_cd)
        & (discgrp_df["dis_tran_cat_cd"] == tran_cat_cd)
    ]
    if not match.empty:
        return Decimal(str(match.iloc[0]["dis_int_rate"]))

    default_match = discgrp_df.loc[
        (discgrp_df["dis_acct_group_id"] == "DEFAULT")
        & (discgrp_df["dis_tran_type_cd"] == tran_type_cd)
        & (discgrp_df["dis_tran_cat_cd"] == tran_cat_cd)
    ]
    if not default_match.empty:
        return Decimal(str(default_match.iloc[0]["dis_int_rate"]))

    raise CBACT04CAbend("ERROR READING DEFAULT DISCLOSURE GROUP")


def _get_account(account_df: pd.DataFrame, acct_id: int) -> pd.Series:
    """Port of 1100-GET-ACCT-DATA."""
    match = account_df.loc[account_df["acct_id"] == acct_id]
    if match.empty:
        raise CBACT04CAbend(f"ACCOUNT NOT FOUND: {acct_id}")
    return match.iloc[0]


def _get_xref_card(xref_df: pd.DataFrame, acct_id: int) -> str:
    """Port of 1110-GET-XREF-DATA (read via alternate key FD-XREF-ACCT-ID)."""
    match = xref_df.loc[xref_df["xref_acct_id"] == acct_id]
    if match.empty:
        raise CBACT04CAbend(f"ACCOUNT NOT FOUND IN XREF: {acct_id}")
    return str(match.iloc[0]["xref_card_num"])


def _update_account(
    account_df: pd.DataFrame, acct_id: int, total_int: Decimal
) -> None:
    """Port of 1050-UPDATE-ACCOUNT.

    * ``ADD WS-TOTAL-INT TO ACCT-CURR-BAL``
    * ``MOVE 0 TO ACCT-CURR-CYC-CREDIT``
    * ``MOVE 0 TO ACCT-CURR-CYC-DEBIT``
    * ``REWRITE`` the account record (modifies *account_df* in place).
    """
    mask = account_df["acct_id"] == acct_id
    if not mask.any():
        raise CBACT04CAbend(f"ERROR RE-WRITING ACCOUNT FILE: {acct_id}")

    idx = account_df.index[mask][0]
    account_df.at[idx, "acct_curr_bal"] = (
        Decimal(str(account_df.at[idx, "acct_curr_bal"])) + total_int
    )
    account_df.at[idx, "acct_curr_cyc_credit"] = Decimal("0.00")
    account_df.at[idx, "acct_curr_cyc_debit"] = Decimal("0.00")


def _build_transaction_record(
    parm_date: str,
    tranid_suffix: int,
    monthly_int: Decimal,
    acct_id: int,
    xref_card_num: str,
    timestamp: str,
) -> TransactionRecord:
    """Port of 1300-B-WRITE-TX field mappings.

    * ``TRAN-ID`` = ``STRING PARM-DATE, WS-TRANID-SUFFIX DELIMITED BY SIZE``
    * ``TRAN-TYPE-CD`` = ``'01'``
    * ``TRAN-CAT-CD``  = ``5``  (COBOL ``MOVE '05' TO PIC 9(04)``)
    * ``TRAN-SOURCE``  = ``'System'``
    * ``TRAN-DESC``    = ``STRING 'Int. for a/c ', ACCT-ID DELIMITED BY SIZE``
    * ``TRAN-AMT``     = ``WS-MONTHLY-INT``
    * ``TRAN-MERCHANT-ID`` = ``0``
    * merchant name / city / zip = spaces (empty)
    * ``TRAN-CARD-NUM`` = ``XREF-CARD-NUM``
    * ``TRAN-ORIG-TS`` / ``TRAN-PROC-TS`` = DB2-format timestamp
    """
    tran_id = f"{parm_date}{tranid_suffix:06d}"
    tran_desc = f"Int. for a/c {acct_id:011d}"

    return TransactionRecord(
        tran_id=tran_id,
        tran_type_cd="01",
        tran_cat_cd=5,
        tran_source="System",
        tran_desc=tran_desc,
        tran_amt=monthly_int,
        tran_merchant_id=0,
        tran_merchant_name="",
        tran_merchant_city="",
        tran_merchant_zip="",
        tran_card_num=xref_card_num,
        tran_orig_ts=timestamp,
        tran_proc_ts=timestamp,
    )


# ---------------------------------------------------------------------------
# Main entry point  (PROCEDURE DIVISION)
# ---------------------------------------------------------------------------


def run_interest_calculation(
    tcatbal_df: pd.DataFrame,
    xref_df: pd.DataFrame,
    discgrp_df: pd.DataFrame,
    account_df: pd.DataFrame,
    parm_date: str,
    *,
    timestamp_fn: Optional[Callable[[], str]] = None,
) -> tuple[list[TransactionRecord], pd.DataFrame]:
    """Port of CBACT04C PROCEDURE DIVISION main loop.

    Parameters
    ----------
    tcatbal_df : pd.DataFrame
        Transaction category balance file (TCATBALF).  Must contain columns:
        ``trancat_acct_id``, ``trancat_type_cd``, ``trancat_cd``,
        ``tran_cat_bal``.  Rows are processed in sequential order (matching
        the COBOL VSAM KSDS sequential read).
    xref_df : pd.DataFrame
        Card cross-reference file (XREFFILE).  Must contain columns:
        ``xref_card_num``, ``xref_acct_id``.
    discgrp_df : pd.DataFrame
        Disclosure group file (DISCGRP).  Must contain columns:
        ``dis_acct_group_id``, ``dis_tran_type_cd``, ``dis_tran_cat_cd``,
        ``dis_int_rate``.
    account_df : pd.DataFrame
        Account master file (ACCTFILE).  Must contain columns matching
        ``AccountRecord`` fields.  **Modified in place** (COBOL ``OPEN I-O``
        with ``REWRITE``).
    parm_date : str
        Run-date parameter (``PIC X(10)``), e.g. ``'2026-06-15'``.
    timestamp_fn : callable, optional
        Override for ``get_db2_format_timestamp`` (useful in tests).

    Returns
    -------
    transactions : list[TransactionRecord]
        Generated interest transaction records (TRANSACT output file).
    account_df : pd.DataFrame
        Updated account master (balances adjusted, cycle fields zeroed).
    """
    if timestamp_fn is None:
        timestamp_fn = get_db2_format_timestamp

    # COBOL reads TCATBALF via VSAM KSDS sequential access, which returns
    # records in key order.  Enforce the same ordering defensively so that
    # account-boundary detection works even if the caller's DataFrame is
    # not pre-sorted.
    tcatbal_df = tcatbal_df.sort_values(
        by=["trancat_acct_id", "trancat_type_cd", "trancat_cd"]
    ).reset_index(drop=True)

    output_transactions: list[TransactionRecord] = []

    ws_last_acct_num: str = ""
    ws_total_int = Decimal("0.00")
    ws_first_time = True
    ws_record_count = 0
    ws_tranid_suffix = 0

    current_acct_id: int = 0
    current_acct_group_id: str = ""
    current_xref_card_num: str = ""

    for _, row in tcatbal_df.iterrows():
        ws_record_count += 1

        trancat_acct_id = int(row["trancat_acct_id"])
        trancat_type_cd = str(row["trancat_type_cd"])
        trancat_cd = int(row["trancat_cd"])
        tran_cat_bal = Decimal(str(row["tran_cat_bal"]))

        acct_id_str = str(trancat_acct_id)

        if acct_id_str != ws_last_acct_num:
            if not ws_first_time:
                _update_account(account_df, current_acct_id, ws_total_int)
            else:
                ws_first_time = False

            ws_total_int = Decimal("0.00")
            ws_last_acct_num = acct_id_str

            acct_row = _get_account(account_df, trancat_acct_id)
            current_acct_id = trancat_acct_id
            current_acct_group_id = str(acct_row["acct_group_id"])

            current_xref_card_num = _get_xref_card(xref_df, trancat_acct_id)

        dis_int_rate = _lookup_discgrp(
            discgrp_df, current_acct_group_id, trancat_type_cd, trancat_cd
        )

        if dis_int_rate != Decimal("0"):
            ws_monthly_int = compute_interest(tran_cat_bal, dis_int_rate)
            ws_total_int += ws_monthly_int

            ws_tranid_suffix += 1
            timestamp = timestamp_fn()
            tran = _build_transaction_record(
                parm_date,
                ws_tranid_suffix,
                ws_monthly_int,
                current_acct_id,
                current_xref_card_num,
                timestamp,
            )
            output_transactions.append(tran)

            # 1400-COMPUTE-FEES (stub -- "To be implemented" in COBOL)

    # Final account update for the last account group
    if ws_last_acct_num:
        _update_account(account_df, current_acct_id, ws_total_int)

    return output_transactions, account_df
