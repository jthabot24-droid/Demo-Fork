"""
Statement generation job migrated from CBSTM03A.CBL.

Produces account statements from transaction data in two formats:
plain text (fixed 80-byte records) and HTML (fixed 100-byte records).

Source program
--------------
* **CBSTM03A.CBL** -- batch COBOL program that reads TRNXFILE, XREFFILE,
  CUSTFILE, and ACCTFILE via subroutine CBSTM03B, groups transactions by
  card number, and writes per-account statements.

All monetary arithmetic uses ``decimal.Decimal`` (never ``float``) to
match COBOL packed-decimal precision.
"""

from __future__ import annotations

import logging
import sys
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import pandas as pd

from cbstm03b_io import (
    RC_EOF,
    RC_OK,
    AccountRecord,
    CustomerRecord,
    FileManager,
    TransactionRecord,
    XrefRecord,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants matching COBOL record widths
# ---------------------------------------------------------------------------
STMT_RECORD_LEN = 80   # FD-STMTFILE-REC  PIC X(80)
HTML_RECORD_LEN = 100   # FD-HTMLFILE-REC  PIC X(100)

# ---------------------------------------------------------------------------
# COBOL numeric-edit formatting helpers
# ---------------------------------------------------------------------------


def _format_pic_9_9_dot_99_minus(value: Decimal) -> str:
    """Format a Decimal as COBOL ``PIC 9(9).99-``.

    9 integer digits (leading zeros), literal dot, 2 decimal digits,
    trailing ``-`` for negative or `` `` (space) for non-negative.

    Total width: 13 characters.
    """
    abs_val = abs(value)
    int_part = int(abs_val)
    dec_part = int(round((abs_val - int_part) * 100))
    sign_char = "-" if value < 0 else " "
    return f"{int_part:09d}.{dec_part:02d}{sign_char}"


def _format_pic_z_9_dot_99_minus(value: Decimal) -> str:
    """Format a Decimal as COBOL ``PIC Z(9).99-``.

    9 integer positions with leading-zero suppression (replaced by
    spaces), literal dot, 2 decimal digits, trailing ``-`` for negative
    or `` `` (space) for non-negative.

    Total width: 13 characters.
    """
    abs_val = abs(value)
    int_part = int(abs_val)
    dec_part = int(round((abs_val - int_part) * 100))
    sign_char = "-" if value < 0 else " "
    if int_part == 0:
        int_str = " " * 9
    else:
        int_str = f"{int_part:9d}"
    return f"{int_str}.{dec_part:02d}{sign_char}"


# ---------------------------------------------------------------------------
# COBOL STRING DELIMITED BY helper
# ---------------------------------------------------------------------------


def _string_delimited_by(source: str, delimiter: str) -> str:
    """Reproduce COBOL ``STRING source DELIMITED BY delimiter``.

    Returns the portion of *source* before the first occurrence of
    *delimiter*.  If *delimiter* is not found, the entire source is
    returned.
    """
    idx = source.find(delimiter)
    if idx == -1:
        return source
    return source[:idx]


def _build_cobol_string(*parts: Tuple[str, Optional[str]]) -> str:
    """Reproduce a COBOL STRING statement with multiple sources.

    Each *part* is ``(source, delimiter)`` where *delimiter* is either a
    string (``DELIMITED BY <literal>``) or ``None`` (``DELIMITED BY
    SIZE`` — copy the entire source).
    """
    result: list[str] = []
    for source, delimiter in parts:
        if delimiter is None:
            result.append(source)
        else:
            result.append(_string_delimited_by(source, delimiter))
    return "".join(result)


# ---------------------------------------------------------------------------
# Record padding helpers (WRITE ... FROM)
# ---------------------------------------------------------------------------


def _pad_stmt(line: str) -> str:
    """Pad/truncate to STMT_RECORD_LEN (80 bytes)."""
    return line[:STMT_RECORD_LEN].ljust(STMT_RECORD_LEN)


def _pad_html(line: str) -> str:
    """Pad/truncate to HTML_RECORD_LEN (100 bytes)."""
    return line[:HTML_RECORD_LEN].ljust(HTML_RECORD_LEN)


# ---------------------------------------------------------------------------
# Grouped transaction table (WS-TRNX-TABLE)
# ---------------------------------------------------------------------------


def _preload_transactions(
    file_mgr: FileManager,
) -> Tuple[Dict[str, List[TransactionRecord]], List[str], int, int]:
    """Read all transactions and group by card number.

    Reproduces the 8100-TRNXFILE-OPEN / 8500-READTRNX-READ logic that
    builds ``WS-TRNX-TABLE``.

    Returns
    -------
    card_transactions : dict
        ``{card_num: [TransactionRecord, ...]}``
    card_order : list
        Ordered list of unique card numbers (preserving first-seen order).
    cr_cnt : int
        Number of distinct cards.
    tr_cnt : int
        Total number of transactions loaded.
    """
    card_transactions: Dict[str, List[TransactionRecord]] = {}
    card_order: List[str] = []
    cr_cnt = 0
    total_tr = 0

    while True:
        rc, rec = file_mgr.read_transaction()
        if rc == RC_EOF:
            break
        if rc != RC_OK:
            raise RuntimeError(f"ERROR READING TRNXFILE, RETURN CODE: {rc}")

        card = rec.trnx_card_num
        if card not in card_transactions:
            card_transactions[card] = []
            card_order.append(card)
            cr_cnt += 1
        card_transactions[card].append(rec)
        total_tr += 1

    return card_transactions, card_order, cr_cnt, total_tr


# ---------------------------------------------------------------------------
# Statement-line builders (STATEMENT-LINES after INITIALIZE)
# ---------------------------------------------------------------------------
# After INITIALIZE: alphanumeric elementary items → SPACES,
# numeric-edited items → zero representation, FILLER items → VALUE.


def _build_st_line0() -> str:
    """ST-LINE0: START OF STATEMENT banner."""
    return "*" * 31 + "START OF STATEMENT" + "*" * 31


def _build_st_line5() -> str:
    """ST-LINE5 / ST-LINE10 / ST-LINE12: dashes."""
    return "-" * 80


def _build_st_line6() -> str:
    """ST-LINE6: Basic Details header."""
    return " " * 33 + "Basic Details" + " " * 34


def _build_st_line7(acct_id: str) -> str:
    """ST-LINE7: Account ID."""
    st_acct_id = acct_id.ljust(20)
    return "Account ID         :" + st_acct_id + " " * 40


def _build_st_line8(curr_bal: Decimal) -> str:
    """ST-LINE8: Current Balance."""
    st_curr_bal = _format_pic_9_9_dot_99_minus(curr_bal)
    return "Current Balance    :" + st_curr_bal + " " * 7 + " " * 40


def _build_st_line9(fico_score: str) -> str:
    """ST-LINE9: FICO Score."""
    st_fico = fico_score.ljust(20)
    return "FICO Score         :" + st_fico + " " * 40


def _build_st_line11() -> str:
    """ST-LINE11: TRANSACTION SUMMARY header."""
    return " " * 30 + "TRANSACTION SUMMARY " + " " * 30


def _build_st_line13() -> str:
    """ST-LINE13: Transaction column headers."""
    return "Tran ID         " + "Tran Details    " + " " * 35 + "  Tran Amount"


def _build_st_line14(trnx_id: str, trnx_desc: str, trnx_amt: Decimal) -> str:
    """ST-LINE14: Transaction detail line."""
    st_tranid = trnx_id.ljust(16)
    st_trandt = trnx_desc[:49].ljust(49)
    st_tranamt = _format_pic_z_9_dot_99_minus(trnx_amt)
    return st_tranid + " " + st_trandt + "$" + st_tranamt


def _build_st_line14a(total_amt: Decimal) -> str:
    """ST-LINE14A: Total EXP line."""
    st_total = _format_pic_z_9_dot_99_minus(total_amt)
    return "Total EXP:" + " " * 56 + "$" + st_total


def _build_st_line15() -> str:
    """ST-LINE15: END OF STATEMENT banner."""
    return "*" * 32 + "END OF STATEMENT" + "*" * 32


def _build_st_name(cust: CustomerRecord) -> str:
    """Build the name line (ST-NAME, 75 chars) via COBOL STRING logic."""
    name_str = _build_cobol_string(
        (cust.cust_first_name, " "),
        (" ", None),
        (cust.cust_middle_name, " "),
        (" ", None),
        (cust.cust_last_name, " "),
        (" ", None),
    )
    return name_str[:75].ljust(75)


def _build_st_line1(cust: CustomerRecord) -> str:
    """ST-LINE1: Name + 5 spaces."""
    return _build_st_name(cust) + " " * 5


def _build_st_line2(cust: CustomerRecord) -> str:
    """ST-LINE2: Address line 1."""
    return cust.cust_addr_line_1[:50].ljust(50) + " " * 30


def _build_st_line3(cust: CustomerRecord) -> str:
    """ST-LINE3: Address line 2."""
    return cust.cust_addr_line_2[:50].ljust(50) + " " * 30


def _build_st_add3(cust: CustomerRecord) -> str:
    """Build ST-ADD3 (80 chars) via COBOL STRING logic."""
    add3_str = _build_cobol_string(
        (cust.cust_addr_line_3, " "),
        (" ", None),
        (cust.cust_addr_state_cd, " "),
        (" ", None),
        (cust.cust_addr_country_cd, " "),
        (" ", None),
        (cust.cust_addr_zip, " "),
        (" ", None),
    )
    return add3_str[:80].ljust(80)


# ---------------------------------------------------------------------------
# HTML line constants (88-level condition values from COBOL)
# ---------------------------------------------------------------------------

HTML_L01 = "<!DOCTYPE html>"
HTML_L02 = '<html lang="en">'
HTML_L03 = "<head>"
HTML_L04 = '<meta charset="utf-8">'
HTML_L05 = "<title>HTML Table Layout</title>"
HTML_L06 = "</head>"
HTML_L07 = '<body style="margin:0px;">'
HTML_L08 = (
    '<table  align="center" frame="box" style="width:70%;'
    " font:12px Segoe UI,sans-serif;\">"
)
HTML_LTRS = "<tr>"
HTML_LTRE = "</tr>"
HTML_LTDS = "<td>"
HTML_LTDE = "</td>"
HTML_L10 = (
    '<td colspan="3" style="padding:0px 5px;'
    'background-color:#1d1d96b3;">'
)
HTML_L15 = (
    '<td colspan="3" style="padding:0px 5px;'
    'background-color:#FFAF33;">'
)
HTML_L16 = '<p style="font-size:16px">Bank of XYZ</p>'
HTML_L17 = "<p>410 Terry Ave N</p>"
HTML_L18 = "<p>Seattle WA 99999</p>"
HTML_L22_35 = (
    '<td colspan="3" style="padding:0px 5px;'
    'background-color:#f2f2f2;">'
)
HTML_L30_42 = (
    '<td colspan="3" style="padding:0px 5px;'
    'background-color:#33FFD1; text-align:center;">'
)
HTML_L31 = '<p style="font-size:16px">Basic Details</p>'
HTML_L43 = '<p style="font-size:16px">Transaction Summary</p>'
HTML_L47 = (
    '<td style="width:25%; padding:0px 5px; background-'
    'color:#33FF5E; text-align:left;">'
)
HTML_L48 = '<p style="font-size:16px">Tran ID</p>'
HTML_L50 = (
    '<td style="width:55%; padding:0px 5px; background-'
    'color:#33FF5E; text-align:left;">'
)
HTML_L51 = '<p style="font-size:16px">Tran Details</p>'
HTML_L53 = (
    '<td style="width:20%; padding:0px 5px; background-'
    'color:#33FF5E; text-align:right;">'
)
HTML_L54 = '<p style="font-size:16px">Amount</p>'
HTML_L58 = (
    '<td style="width:25%; padding:0px 5px; background-'
    'color:#f2f2f2; text-align:left;">'
)
HTML_L61 = (
    '<td style="width:55%; padding:0px 5px; background-'
    'color:#f2f2f2; text-align:left;">'
)
HTML_L64 = (
    '<td style="width:20%; padding:0px 5px; background-'
    'color:#f2f2f2; text-align:right;">'
)
HTML_L75 = "<h3>End of Statement</h3>"
HTML_L78 = "</table>"
HTML_L79 = "</body>"
HTML_L80 = "</html>"


def _build_html_l11(acct_id: str) -> str:
    """HTML-L11: statement header with account number."""
    l11_acct = acct_id[:20].ljust(20)
    return "<h3>Statement for Account Number: " + l11_acct + "</h3>"


def _build_html_name_p(st_name_50: str) -> str:
    """Build the ``<p style=...>Name</p>`` line for HTML.

    Uses ``DELIMITED BY '  '`` (two spaces) to trim trailing spaces
    from the name.
    """
    trimmed = _string_delimited_by(st_name_50, "  ")
    return _build_cobol_string(
        ('<p style="font-size:16px">', "*"),
        (trimmed, "*"),
        ("  ", None),
        ("</p>", "*"),
    )


def _build_html_addr_ln(addr_field: str) -> str:
    """Build an address ``<p>...</p>`` HTML line.

    Uses ``DELIMITED BY '  '`` (two spaces) on the address value.
    """
    trimmed = _string_delimited_by(addr_field, "  ")
    return _build_cobol_string(
        ("<p>", "*"),
        (trimmed, "*"),
        ("  ", None),
        ("</p>", "*"),
    )


def _build_html_basic_ln(label: str, value: str) -> str:
    """Build a basic-detail ``<p>Label : Value</p>`` HTML line.

    Uses ``DELIMITED BY '*'`` on all parts (i.e., copies entire strings
    since ``*`` never appears in them).
    """
    return _build_cobol_string(
        (label, "*"),
        (value, "*"),
        ("</p>", "*"),
    )


def _build_html_tran_p(value: str) -> str:
    """Build ``<p>value</p>`` for a transaction cell."""
    return _build_cobol_string(
        ("<p>", "*"),
        (value, "*"),
        ("</p>", "*"),
    )


# ---------------------------------------------------------------------------
# Statement writer
# ---------------------------------------------------------------------------


class StatementWriter:
    """Writes plain-text and HTML statement files.

    Reproduces the WRITE statements from CBSTM03A exactly.
    """

    def __init__(self, stmt_path: str, html_path: str):
        self._stmt_path = stmt_path
        self._html_path = html_path
        self._stmt_lines: List[str] = []
        self._html_lines: List[str] = []

    def _write_stmt(self, line: str) -> None:
        self._stmt_lines.append(_pad_stmt(line))

    def _write_html(self, line: str) -> None:
        self._html_lines.append(_pad_html(line))

    def flush(self) -> None:
        with open(self._stmt_path, "w", newline="") as f:
            for line in self._stmt_lines:
                f.write(line + "\n")
        with open(self._html_path, "w", newline="") as f:
            for line in self._html_lines:
                f.write(line + "\n")

    # -- 5100-WRITE-HTML-HEADER --

    def write_html_header(self, acct_id: str) -> None:
        """5100-WRITE-HTML-HEADER."""
        self._write_html(HTML_L01)
        self._write_html(HTML_L02)
        self._write_html(HTML_L03)
        self._write_html(HTML_L04)
        self._write_html(HTML_L05)
        self._write_html(HTML_L06)
        self._write_html(HTML_L07)
        self._write_html(HTML_L08)
        self._write_html(HTML_LTRS)
        self._write_html(HTML_L10)

        self._write_html(_build_html_l11(acct_id))
        self._write_html(HTML_LTDE)
        self._write_html(HTML_LTRE)
        self._write_html(HTML_LTRS)
        self._write_html(HTML_L15)
        self._write_html(HTML_L16)
        self._write_html(HTML_L17)
        self._write_html(HTML_L18)
        self._write_html(HTML_LTDE)
        self._write_html(HTML_LTRE)
        self._write_html(HTML_LTRS)
        self._write_html(HTML_L22_35)

    # -- 5200-WRITE-HTML-NMADBS --

    def write_html_name_addr_basic(
        self,
        st_name: str,
        st_add1: str,
        st_add2: str,
        st_add3: str,
        acct_id: str,
        curr_bal_str: str,
        fico_score: str,
    ) -> None:
        """5200-WRITE-HTML-NMADBS."""
        st_name_50 = st_name[:50]
        self._write_html(_build_html_name_p(st_name_50))

        self._write_html(_build_html_addr_ln(st_add1))
        self._write_html(_build_html_addr_ln(st_add2))
        self._write_html(_build_html_addr_ln(st_add3))

        self._write_html(HTML_LTDE)
        self._write_html(HTML_LTRE)
        self._write_html(HTML_LTRS)
        self._write_html(HTML_L30_42)
        self._write_html(HTML_L31)
        self._write_html(HTML_LTDE)
        self._write_html(HTML_LTRE)
        self._write_html(HTML_LTRS)
        self._write_html(HTML_L22_35)

        acct_label = "<p>Account ID         : "
        self._write_html(
            _build_html_basic_ln(acct_label, acct_id[:20].ljust(20))
        )
        bal_label = "<p>Current Balance    : "
        self._write_html(_build_html_basic_ln(bal_label, curr_bal_str))
        fico_label = "<p>FICO Score         : "
        self._write_html(
            _build_html_basic_ln(fico_label, fico_score[:20].ljust(20))
        )

        self._write_html(HTML_LTDE)
        self._write_html(HTML_LTRE)
        self._write_html(HTML_LTRS)
        self._write_html(HTML_L30_42)
        self._write_html(HTML_L43)
        self._write_html(HTML_LTDE)
        self._write_html(HTML_LTRE)
        self._write_html(HTML_LTRS)
        self._write_html(HTML_L47)
        self._write_html(HTML_L48)
        self._write_html(HTML_LTDE)
        self._write_html(HTML_L50)
        self._write_html(HTML_L51)
        self._write_html(HTML_LTDE)
        self._write_html(HTML_L53)
        self._write_html(HTML_L54)
        self._write_html(HTML_LTDE)
        self._write_html(HTML_LTRE)

    # -- 5000-CREATE-STATEMENT --

    def write_statement_header(
        self,
        cust: CustomerRecord,
        acct: AccountRecord,
    ) -> None:
        """5000-CREATE-STATEMENT."""
        self._write_stmt(_build_st_line0())

        self.write_html_header(acct.acct_id)

        st_name = _build_st_name(cust)
        st_add1 = cust.cust_addr_line_1[:50].ljust(50)
        st_add2 = cust.cust_addr_line_2[:50].ljust(50)
        st_add3 = _build_st_add3(cust)

        curr_bal_str = _format_pic_9_9_dot_99_minus(acct.acct_curr_bal)
        fico_str = cust.cust_fico_credit_score[:20].ljust(20)

        self.write_html_name_addr_basic(
            st_name, st_add1, st_add2, st_add3,
            acct.acct_id, curr_bal_str, cust.cust_fico_credit_score,
        )

        self._write_stmt(st_name + " " * 5)
        self._write_stmt(st_add1 + " " * 30)
        self._write_stmt(st_add2 + " " * 30)
        self._write_stmt(st_add3)
        self._write_stmt(_build_st_line5())
        self._write_stmt(_build_st_line6())
        self._write_stmt(_build_st_line5())
        self._write_stmt(_build_st_line7(acct.acct_id))
        self._write_stmt(_build_st_line8(acct.acct_curr_bal))
        self._write_stmt(_build_st_line9(fico_str))
        self._write_stmt(_build_st_line5())
        self._write_stmt(_build_st_line11())
        self._write_stmt(_build_st_line5())
        self._write_stmt(_build_st_line13())
        self._write_stmt(_build_st_line5())

    # -- 6000-WRITE-TRANS --

    def write_transaction(
        self,
        trnx_id: str,
        trnx_desc: str,
        trnx_amt: Decimal,
    ) -> None:
        """6000-WRITE-TRANS."""
        st_tranamt_str = _format_pic_z_9_dot_99_minus(trnx_amt)

        self._write_stmt(
            _build_st_line14(trnx_id, trnx_desc, trnx_amt)
        )

        self._write_html(HTML_LTRS)
        self._write_html(HTML_L58)
        self._write_html(_build_html_tran_p(trnx_id[:16].ljust(16)))
        self._write_html(HTML_LTDE)
        self._write_html(HTML_L61)
        self._write_html(
            _build_html_tran_p(trnx_desc[:49].ljust(49))
        )
        self._write_html(HTML_LTDE)
        self._write_html(HTML_L64)
        self._write_html(_build_html_tran_p(st_tranamt_str))
        self._write_html(HTML_LTDE)
        self._write_html(HTML_LTRE)

    # -- Footer (end of 4000-TRNXFILE-GET) --

    def write_statement_footer(self, total_amt: Decimal) -> None:
        """Footer section from 4000-TRNXFILE-GET."""
        self._write_stmt(_build_st_line5())
        self._write_stmt(_build_st_line14a(total_amt))
        self._write_stmt(_build_st_line15())

        self._write_html(HTML_LTRS)
        self._write_html(HTML_L10)
        self._write_html(HTML_L75)
        self._write_html(HTML_LTDE)
        self._write_html(HTML_LTRE)
        self._write_html(HTML_L78)
        self._write_html(HTML_L79)
        self._write_html(HTML_L80)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------


def generate_statements(
    file_mgr: FileManager,
    stmt_path: str,
    html_path: str,
) -> None:
    """Run the full CREASTMT job.

    Parameters
    ----------
    file_mgr : FileManager
        Pre-configured I/O manager with all four data sources.
    stmt_path : str
        Output path for the plain-text statement file.
    html_path : str
        Output path for the HTML statement file.
    """
    writer = StatementWriter(stmt_path, html_path)

    file_mgr.open_all()

    card_transactions, card_order, cr_cnt, total_tr = _preload_transactions(
        file_mgr
    )
    logger.info("Loaded %d transactions for %d cards", total_tr, cr_cnt)

    end_of_file = False
    while not end_of_file:
        rc, xref = file_mgr.read_xref()
        if rc == RC_EOF:
            end_of_file = True
            break
        if rc != RC_OK:
            raise RuntimeError(f"ERROR READING XREFFILE, RETURN CODE: {rc}")

        rc, cust = file_mgr.read_customer(xref.xref_cust_id)
        if rc != RC_OK:
            raise RuntimeError(
                f"ERROR READING CUSTFILE for cust_id={xref.xref_cust_id}, "
                f"RETURN CODE: {rc}"
            )

        rc, acct = file_mgr.read_account(xref.xref_acct_id)
        if rc != RC_OK:
            raise RuntimeError(
                f"ERROR READING ACCTFILE for acct_id={xref.xref_acct_id}, "
                f"RETURN CODE: {rc}"
            )

        writer.write_statement_header(cust, acct)

        total_amt = Decimal("0.00")
        card_num = xref.xref_card_num
        if card_num in card_transactions:
            for trnx in card_transactions[card_num]:
                writer.write_transaction(
                    trnx.trnx_id, trnx.trnx_desc, trnx.trnx_amt
                )
                total_amt += trnx.trnx_amt

        writer.write_statement_footer(total_amt)

    file_mgr.close_all()
    writer.flush()
    logger.info("Statements written to %s and %s", stmt_path, html_path)


def generate_statements_from_csv(
    trnx_csv: str,
    xref_csv: str,
    cust_csv: str,
    acct_csv: str,
    stmt_path: str,
    html_path: str,
) -> None:
    """Convenience wrapper that reads input from CSV files.

    Parameters
    ----------
    trnx_csv, xref_csv, cust_csv, acct_csv : str
        Paths to CSV files for each input dataset.
    stmt_path : str
        Output path for the plain-text statement file.
    html_path : str
        Output path for the HTML statement file.
    """
    file_mgr = FileManager.from_csv_files(trnx_csv, xref_csv, cust_csv, acct_csv)
    generate_statements(file_mgr, stmt_path, html_path)


def main() -> None:
    """CLI entry point.

    Usage::

        python cbstm03a_statement.py TRNX.csv XREF.csv CUST.csv ACCT.csv \\
               statement.txt statement.html
    """
    if len(sys.argv) != 7:
        print(
            "Usage: python cbstm03a_statement.py "
            "TRNX.csv XREF.csv CUST.csv ACCT.csv "
            "statement.txt statement.html",
            file=sys.stderr,
        )
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)
    generate_statements_from_csv(*sys.argv[1:])


if __name__ == "__main__":
    main()
