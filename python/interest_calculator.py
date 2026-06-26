"""
Python migration of COBOL program CBACT04C -- Interest Calculator.

Original source : app/cbl/CBACT04C.cbl
JCL job         : app/jcl/INTCALC.jcl  (step STEP15, PGM=CBACT04C)

This module reproduces the batch interest-calculation logic from the
CardDemo mainframe application.  It processes transaction-category-balance
records sequentially (sorted by account), looks up interest rates from the
disclosure-group master (with a DEFAULT fallback), computes monthly
interest, and emits fixed-layout transaction records.

Record layouts are derived from the following COBOL copybooks:

    CVTRA01Y  Transaction Category Balance   (RECLN = 50)
    CVACT03Y  Card Cross-Reference           (RECLN = 50)
    CVTRA02Y  Disclosure Group               (RECLN = 50)
    CVACT01Y  Account Record                 (RECLN = 300)
    CVTRA05Y  Transaction Record (output)    (RECLN = 350)

Assumptions and known deviations
---------------------------------
1. **COBOL bug -- last-account update**: the original COBOL has an
   unreachable ``ELSE`` branch inside ``PERFORM UNTIL END-OF-FILE = 'Y'``
   that was meant to call ``1050-UPDATE-ACCOUNT`` for the last account.
   Because the loop defaults to ``WITH TEST BEFORE``, the ``ELSE`` can
   never execute, so the last account's balance is never updated.  This
   port **corrects** that bug and updates every account.

2. **Timestamp granularity**: COBOL calls ``FUNCTION CURRENT-DATE``
   inside each ``1300-B-WRITE-TX`` invocation, giving each transaction a
   slightly different timestamp.  This port accepts an optional fixed
   ``timestamp`` for deterministic/reproducible output; when omitted it
   uses ``datetime.now()`` once for the entire batch (all records share
   the same timestamp).

3. **1400-COMPUTE-FEES**: the COBOL paragraph is a stub (``EXIT``).
   This port mirrors that -- no fee logic is implemented.

4. **Decimal precision**: all arithmetic uses ``decimal.Decimal`` with
   ``ROUND_DOWN`` (truncation toward zero) to match COBOL ``COMPUTE``
   without the ``ROUNDED`` phrase.

5. **Sign overpunch**: the fixed-width writer encodes signed-numeric
   DISPLAY fields with the standard EBCDIC trailing-sign overpunch so
   that the output is byte-compatible with the original COBOL SYSTRAN
   sequential dataset (LRECL = 350, RECFM = F).
"""

from datetime import datetime
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd

# ---------------------------------------------------------------------------
# Sign-overpunch tables (EBCDIC trailing-sign convention)
# ---------------------------------------------------------------------------
_POS_OVERPUNCH = dict(zip(range(10), "{ABCDEFGHI"))
_NEG_OVERPUNCH = dict(zip(range(10), "}JKLMNOPQR"))

# ---------------------------------------------------------------------------
# Transaction output column order (mirrors CVTRA05Y field sequence)
# ---------------------------------------------------------------------------
TRAN_OUTPUT_COLUMNS = [
    "tran_id",
    "tran_type_cd",
    "tran_cat_cd",
    "tran_source",
    "tran_desc",
    "tran_amt",
    "tran_merchant_id",
    "tran_merchant_name",
    "tran_merchant_city",
    "tran_merchant_zip",
    "tran_card_num",
    "tran_orig_ts",
    "tran_proc_ts",
]


# ===================================================================
# Formatting helpers
# ===================================================================

def _cobol_truncate(value: Decimal, decimal_places: int = 2) -> Decimal:
    """Truncate toward zero -- matches COBOL COMPUTE without ROUNDED."""
    return value.quantize(Decimal(10) ** -decimal_places, rounding=ROUND_DOWN)


def _make_db2_timestamp(dt: Optional[datetime] = None) -> str:
    """
    Build a DB2-style timestamp (26 chars).

    Format: ``YYYY-MM-DD-HH.MM.SS.NN0000``

    Mirrors ``Z-GET-DB2-FORMAT-TIMESTAMP`` in CBACT04C.
    """
    if dt is None:
        dt = datetime.now()
    centiseconds = dt.microsecond // 10000
    return dt.strftime("%Y-%m-%d-%H.%M.%S.") + f"{centiseconds:02d}0000"


def _format_signed_display(
    value: Decimal, int_digits: int, dec_digits: int
) -> str:
    """
    Format *value* as COBOL ``PIC S9(int_digits)V9(dec_digits) DISPLAY``
    with trailing sign overpunch.

    Total output length = *int_digits* + *dec_digits*.
    """
    total = int_digits + dec_digits
    negative = value < 0
    scaled = int(abs(value) * (10**dec_digits))
    raw = str(scaled).zfill(total)
    if len(raw) > total:
        raw = raw[-total:]                       # high-order truncation
    last_digit = int(raw[-1])
    table = _NEG_OVERPUNCH if negative else _POS_OVERPUNCH
    return raw[:-1] + table[last_digit]


def _format_unsigned_display(value: int, digits: int) -> str:
    """Format an unsigned integer as COBOL ``PIC 9(digits) DISPLAY``."""
    return str(abs(int(value))).zfill(digits)[-digits:]


def _pad_alpha(value: str, width: int) -> str:
    """Left-justify and space-pad/truncate to *width* (COBOL ``PIC X(n)``)."""
    return str(value).ljust(width)[:width]


# ===================================================================
# Disclosure-group lookup
# ===================================================================

def _lookup_interest_rate(
    discgrp_df: pd.DataFrame,
    acct_group_id: str,
    tran_type_cd: str,
    tran_cat_cd: int,
) -> Decimal:
    """
    Look up the annual interest rate from the disclosure-group master.

    Mirrors paragraphs ``1200-GET-INTEREST-RATE`` and
    ``1200-A-GET-DEFAULT-INT-RATE``.  Falls back to the ``DEFAULT``
    group when the account's specific group has no matching record.

    Returns ``Decimal('0')`` only when a matching record exists with a
    zero rate.

    Raises
    ------
    ValueError
        If neither the specific group nor the ``DEFAULT`` group contains
        a matching record (the COBOL program would ABEND).
    """
    type_cd_str = str(tran_type_cd).strip()
    cat_cd_int = int(tran_cat_cd)

    for group_id in (str(acct_group_id).strip(), "DEFAULT"):
        mask = (
            (discgrp_df["dis_acct_group_id"].astype(str).str.strip() == group_id)
            & (
                discgrp_df["dis_tran_type_cd"].astype(str).str.strip()
                == type_cd_str
            )
            & (discgrp_df["dis_tran_cat_cd"].astype(int) == cat_cd_int)
        )
        matches = discgrp_df.loc[mask]
        if not matches.empty:
            return Decimal(str(matches.iloc[0]["dis_int_rate"]))

    raise ValueError(
        f"Disclosure group not found for group={acct_group_id!r}, "
        f"type_cd={tran_type_cd!r}, cat_cd={tran_cat_cd} "
        "(DEFAULT fallback also missing -- COBOL would ABEND)"
    )


# ===================================================================
# Account balance update
# ===================================================================

def _apply_account_update(
    accounts: pd.DataFrame,
    acct_id: str,
    total_interest: Decimal,
) -> None:
    """
    Add accumulated interest to account balance and zero cycle fields.

    Mirrors ``1050-UPDATE-ACCOUNT``.

    Modifies *accounts* **in place**.
    """
    mask = accounts["acct_id"].astype(str).str.strip().str.zfill(11) == acct_id
    idx = accounts.index[mask]
    if idx.empty:
        return
    i = idx[0]
    curr_bal = Decimal(str(accounts.at[i, "acct_curr_bal"]))
    accounts.at[i, "acct_curr_bal"] = curr_bal + total_interest
    accounts.at[i, "acct_curr_cyc_credit"] = Decimal("0")
    accounts.at[i, "acct_curr_cyc_debit"] = Decimal("0")


# ===================================================================
# Core interest computation
# ===================================================================

def compute_interest(
    tcatbal_df: pd.DataFrame,
    xref_df: pd.DataFrame,
    account_df: pd.DataFrame,
    discgrp_df: pd.DataFrame,
    parm_date: str,
    timestamp: Optional[datetime] = None,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Batch interest calculation -- faithful port of CBACT04C.

    Parameters
    ----------
    tcatbal_df : DataFrame
        Transaction category balance records.
        Required columns: ``trancat_acct_id``, ``trancat_type_cd``,
        ``trancat_cd``, ``tran_cat_bal``.
    xref_df : DataFrame
        Card cross-reference records.
        Required columns: ``xref_card_num``, ``xref_acct_id``.
    account_df : DataFrame
        Account master records (a copy is made; the original is not
        mutated).  Required columns: ``acct_id``, ``acct_curr_bal``,
        ``acct_curr_cyc_credit``, ``acct_curr_cyc_debit``,
        ``acct_group_id``.
    discgrp_df : DataFrame
        Disclosure group records.
        Required columns: ``dis_acct_group_id``, ``dis_tran_type_cd``,
        ``dis_tran_cat_cd``, ``dis_int_rate``.
    parm_date : str
        10-character date parameter (e.g. ``'2022071800'``), used as the
        prefix of generated transaction IDs.  Passed to the COBOL
        program via ``EXEC PGM=CBACT04C,PARM='...'`` in the JCL.
    timestamp : datetime, optional
        Fixed timestamp for deterministic output.  When ``None``
        (default), ``datetime.now()`` is used once for the whole batch.

    Returns
    -------
    (updated_accounts, transactions) : (DataFrame, DataFrame)
        *updated_accounts* has the same schema as *account_df* with
        ``acct_curr_bal`` adjusted by the accumulated interest and
        cycle credit/debit zeroed for every processed account.

        *transactions* follows the CVTRA05Y column order (see
        ``TRAN_OUTPUT_COLUMNS``).
    """
    # Sort by composite key (mirrors sequential read of VSAM KSDS)
    tcatbal_sorted = tcatbal_df.sort_values(
        ["trancat_acct_id", "trancat_type_cd", "trancat_cd"]
    ).reset_index(drop=True)

    updated_accounts = account_df.copy()
    transactions: list[dict] = []

    # Working-storage variables (WS- prefix in COBOL)
    ws_last_acct_num = ""
    ws_total_int = Decimal("0")
    ws_tranid_suffix = 0

    current_acct_group_id: str = ""
    current_xref_card_num: str = ""

    db2_ts = _make_db2_timestamp(timestamp)

    for _, row in tcatbal_sorted.iterrows():
        acct_id = str(row["trancat_acct_id"]).strip().zfill(11)
        type_cd = str(row["trancat_type_cd"]).strip()
        cat_cd = int(row["trancat_cd"])
        balance = Decimal(str(row["tran_cat_bal"]))

        # ---- account break ----
        if acct_id != ws_last_acct_num:
            if ws_last_acct_num:
                _apply_account_update(
                    updated_accounts, ws_last_acct_num, ws_total_int
                )
            ws_total_int = Decimal("0")
            ws_last_acct_num = acct_id

            # 1100-GET-ACCT-DATA
            acct_mask = (
                updated_accounts["acct_id"]
                .astype(str)
                .str.strip()
                .str.zfill(11)
                == acct_id
            )
            acct_rows = updated_accounts.loc[acct_mask]
            if acct_rows.empty:
                raise ValueError(f"ACCOUNT NOT FOUND: {acct_id}")
            current_acct_group_id = str(acct_rows.iloc[0]["acct_group_id"])

            # 1110-GET-XREF-DATA (read by alternate key FD-XREF-ACCT-ID)
            xref_mask = (
                xref_df["xref_acct_id"]
                .astype(str)
                .str.strip()
                .str.zfill(11)
                == acct_id
            )
            xref_rows = xref_df.loc[xref_mask]
            if xref_rows.empty:
                raise ValueError(f"XREF ACCOUNT NOT FOUND: {acct_id}")
            current_xref_card_num = str(xref_rows.iloc[0]["xref_card_num"])

        # 1200-GET-INTEREST-RATE
        int_rate = _lookup_interest_rate(
            discgrp_df, current_acct_group_id, type_cd, cat_cd
        )

        if int_rate != Decimal("0"):
            # 1300-COMPUTE-INTEREST
            #   COMPUTE WS-MONTHLY-INT
            #     = ( TRAN-CAT-BAL * DIS-INT-RATE ) / 1200
            ws_monthly_int = _cobol_truncate(
                (balance * int_rate) / Decimal("1200")
            )
            ws_total_int += ws_monthly_int

            # 1300-B-WRITE-TX
            ws_tranid_suffix += 1
            tran_id = f"{parm_date}{ws_tranid_suffix:06d}"
            tran_desc = f"Int. for a/c {acct_id}"

            transactions.append(
                {
                    "tran_id": tran_id,
                    "tran_type_cd": "01",
                    "tran_cat_cd": 5,
                    "tran_source": "System",
                    "tran_desc": tran_desc,
                    "tran_amt": ws_monthly_int,
                    "tran_merchant_id": 0,
                    "tran_merchant_name": "",
                    "tran_merchant_city": "",
                    "tran_merchant_zip": "",
                    "tran_card_num": current_xref_card_num,
                    "tran_orig_ts": db2_ts,
                    "tran_proc_ts": db2_ts,
                }
            )

            # 1400-COMPUTE-FEES -- stub (not implemented in COBOL)

    # Update last account (corrects COBOL bug -- see module docstring)
    if ws_last_acct_num:
        _apply_account_update(
            updated_accounts, ws_last_acct_num, ws_total_int
        )

    tran_df = pd.DataFrame(transactions, columns=TRAN_OUTPUT_COLUMNS)
    return updated_accounts, tran_df


# ===================================================================
# Fixed-width 350-byte output writer
# ===================================================================

def _format_transaction_record(row: dict) -> str:
    """
    Serialize one transaction dict into a 350-character string matching
    the CVTRA05Y / SYSTRAN record layout.

    Field widths (total = 350):
        TRAN-ID            X(16)
        TRAN-TYPE-CD       X(02)
        TRAN-CAT-CD        9(04)
        TRAN-SOURCE        X(10)
        TRAN-DESC          X(100)
        TRAN-AMT           S9(09)V99   (11 bytes, sign overpunch)
        TRAN-MERCHANT-ID   9(09)
        TRAN-MERCHANT-NAME X(50)
        TRAN-MERCHANT-CITY X(50)
        TRAN-MERCHANT-ZIP  X(10)
        TRAN-CARD-NUM      X(16)
        TRAN-ORIG-TS       X(26)
        TRAN-PROC-TS       X(26)
        FILLER             X(20)
    """
    parts = [
        _pad_alpha(row["tran_id"], 16),
        _pad_alpha(row["tran_type_cd"], 2),
        _format_unsigned_display(row["tran_cat_cd"], 4),
        _pad_alpha(row["tran_source"], 10),
        _pad_alpha(row["tran_desc"], 100),
        _format_signed_display(Decimal(str(row["tran_amt"])), 9, 2),
        _format_unsigned_display(row["tran_merchant_id"], 9),
        _pad_alpha(row["tran_merchant_name"], 50),
        _pad_alpha(row["tran_merchant_city"], 50),
        _pad_alpha(row["tran_merchant_zip"], 10),
        _pad_alpha(row["tran_card_num"], 16),
        _pad_alpha(row["tran_orig_ts"], 26),
        _pad_alpha(row["tran_proc_ts"], 26),
        " " * 20,  # FILLER
    ]
    record = "".join(parts)
    assert len(record) == 350, f"Record length {len(record)} != 350"
    return record


def write_transaction_file(
    tran_df: pd.DataFrame,
    output_path: str | Path,
) -> None:
    """
    Write the transaction DataFrame as a fixed-width file.

    Each line is exactly 350 characters (matching ``LRECL=350, RECFM=F``
    from the JCL) followed by a newline.
    """
    output_path = Path(output_path)
    with output_path.open("w", encoding="utf-8") as fh:
        for _, row in tran_df.iterrows():
            fh.write(_format_transaction_record(row.to_dict()) + "\n")
