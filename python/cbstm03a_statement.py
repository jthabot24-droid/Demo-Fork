"""
Statement generation migrated from CBSTM03A.CBL / CBSTM03B.CBL.

CBSTM03A is the CREASTMT batch job in the CardDemo application.  It reads
transaction, cross-reference, customer, and account data and produces two
output files:

* **Plain-text statement** -- fixed 80-byte records (``STMTFILE``)
* **HTML statement**       -- fixed 100-byte records (``HTMLFILE``)

The COBOL program uses ``ALTER`` / ``GO TO`` and a two-dimensional
in-memory table (``WS-TRNX-TABLE``) to group transactions by card number
before writing.  This Python port replaces that with straight-line control
flow while preserving the exact output layout, including COBOL numeric
edit patterns, column positions, and padding.

Copybook field layouts
----------------------
* COSTM01  -- TRNX-RECORD  (350 bytes)
* CVACT03Y -- CARD-XREF-RECORD (50 bytes)
* CUSTREC  -- CUSTOMER-RECORD  (500 bytes)
* CVACT01Y -- ACCOUNT-RECORD   (300 bytes)
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from cbstm03b_io import (
    AccountRecord,
    CustomerRecord,
    FileStore,
    RC_EOF,
    RC_OK,
    TrnxRecord,
    XrefRecord,
)

logger = logging.getLogger(__name__)

STMT_RECORD_LEN = 80
HTML_RECORD_LEN = 100


# -----------------------------------------------------------------------
# COBOL numeric edit-picture formatters
# -----------------------------------------------------------------------

def format_pic_9_99_minus(value: Decimal, int_digits: int = 9) -> str:
    """Format ``PIC 9(n).99-`` -- no zero suppression, trailing sign.

    Width = int_digits + 1 (dot) + 2 (decimals) + 1 (sign) characters.
    """
    negative = value < 0
    abs_val = abs(value)
    quantized = abs_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    int_part = int(quantized)
    dec_part = int(round((quantized - int_part) * 100))
    formatted = (
        str(int_part).zfill(int_digits)[-int_digits:]
        + "."
        + str(dec_part).zfill(2)
    )
    formatted += "-" if negative else " "
    return formatted


def format_pic_z_99_minus(value: Decimal, int_digits: int = 9) -> str:
    """Format ``PIC Z(n).99-`` -- zero-suppressed integer, trailing sign.

    Width = int_digits + 1 (dot) + 2 (decimals) + 1 (sign) characters.
    """
    negative = value < 0
    abs_val = abs(value)
    quantized = abs_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    int_part = int(quantized)
    dec_part = int(round((quantized - int_part) * 100))
    if int_part == 0:
        int_str = " " * int_digits
    else:
        int_str = str(int_part).rjust(int_digits)[-int_digits:]
    formatted = int_str + "." + str(dec_part).zfill(2)
    formatted += "-" if negative else " "
    return formatted


# -----------------------------------------------------------------------
# COBOL STRING ... DELIMITED BY helpers
# -----------------------------------------------------------------------

def _delimited_by_char(source: str, delimiter: str) -> str:
    """Reproduce ``STRING src DELIMITED BY <delimiter>``."""
    idx = source.find(delimiter)
    if idx == -1:
        return source
    return source[:idx]


# -----------------------------------------------------------------------
# Fixed HTML literal values (88-level condition names on HTML-FIXED-LN)
# -----------------------------------------------------------------------

_HTML = {
    "L01": "<!DOCTYPE html>",
    "L02": '<html lang="en">',
    "L03": "<head>",
    "L04": '<meta charset="utf-8">',
    "L05": "<title>HTML Table Layout</title>",
    "L06": "</head>",
    "L07": '<body style="margin:0px;">',
    "L08": (
        '<table  align="center" frame="box" style="width:70%;'
        " font:12px Segoe UI,sans-serif;\">"
    ),
    "TRS": "<tr>",
    "TRE": "</tr>",
    "TDS": "<td>",
    "TDE": "</td>",
    "L10": (
        '<td colspan="3" style="padding:0px 5px;'
        'background-color:#1d1d96b3;">'
    ),
    "L15": (
        '<td colspan="3" style="padding:0px 5px;'
        'background-color:#FFAF33;">'
    ),
    "L16": '<p style="font-size:16px">Bank of XYZ</p>',
    "L17": "<p>410 Terry Ave N</p>",
    "L18": "<p>Seattle WA 99999</p>",
    "L22_35": (
        '<td colspan="3" style="padding:0px 5px;'
        'background-color:#f2f2f2;">'
    ),
    "L30_42": (
        '<td colspan="3" style="padding:0px 5px;'
        'background-color:#33FFD1; text-align:center;">'
    ),
    "L31": '<p style="font-size:16px">Basic Details</p>',
    "L43": '<p style="font-size:16px">Transaction Summary</p>',
    "L47": (
        '<td style="width:25%; padding:0px 5px; background-'
        'color:#33FF5E; text-align:left;">'
    ),
    "L48": '<p style="font-size:16px">Tran ID</p>',
    "L50": (
        '<td style="width:55%; padding:0px 5px; background-'
        'color:#33FF5E; text-align:left;">'
    ),
    "L51": '<p style="font-size:16px">Tran Details</p>',
    "L53": (
        '<td style="width:20%; padding:0px 5px; background-'
        'color:#33FF5E; text-align:right;">'
    ),
    "L54": '<p style="font-size:16px">Amount</p>',
    "L58": (
        '<td style="width:25%; padding:0px 5px; background-'
        'color:#f2f2f2; text-align:left;">'
    ),
    "L61": (
        '<td style="width:55%; padding:0px 5px; background-'
        'color:#f2f2f2; text-align:left;">'
    ),
    "L64": (
        '<td style="width:20%; padding:0px 5px; background-'
        'color:#f2f2f2; text-align:right;">'
    ),
    "L75": "<h3>End of Statement</h3>",
    "L78": "</table>",
    "L79": "</body>",
    "L80": "</html>",
}


def _html_fixed(key: str) -> str:
    """Return an HTML literal padded to 100 bytes (PIC X(100))."""
    return _HTML[key].ljust(HTML_RECORD_LEN)[:HTML_RECORD_LEN]


# -----------------------------------------------------------------------
# Plain-text STATEMENT-LINES builders
# -----------------------------------------------------------------------

def _st_line0() -> str:
    """``ST-LINE0`` -- START OF STATEMENT banner (80 bytes)."""
    return ("*" * 31) + "START OF STATEMENT" + ("*" * 31)


def _st_line5() -> str:
    """``ST-LINE5`` / ``ST-LINE10`` / ``ST-LINE12`` -- 80 dashes."""
    return "-" * STMT_RECORD_LEN


def _st_line6() -> str:
    """``ST-LINE6`` -- centred 'Basic Details' header."""
    return " " * 33 + "Basic Details" + " " + " " * 33


def _st_line7(acct_id: str) -> str:
    """``ST-LINE7`` -- Account ID line."""
    return "Account ID         :" + acct_id.ljust(20) + " " * 40


def _st_line8(curr_bal: Decimal) -> str:
    """``ST-LINE8`` -- Current Balance line."""
    bal_str = format_pic_9_99_minus(curr_bal, 9)
    return "Current Balance    :" + bal_str + " " * 7 + " " * 40


def _st_line9(fico: str) -> str:
    """``ST-LINE9`` -- FICO Score line."""
    return "FICO Score         :" + fico.ljust(20) + " " * 40


def _st_line11() -> str:
    """``ST-LINE11`` -- TRANSACTION SUMMARY header."""
    return " " * 30 + "TRANSACTION SUMMARY " + " " * 30


def _st_line13() -> str:
    """``ST-LINE13`` -- column headers for transactions."""
    return "Tran ID         " + "Tran Details    " + (" " * 35) + "  Tran Amount"


def _st_line14(tran_id: str, tran_desc: str, tran_amt: Decimal) -> str:
    """``ST-LINE14`` -- single transaction line."""
    return (
        tran_id.ljust(16)
        + " "
        + tran_desc.ljust(49)[:49]
        + "$"
        + format_pic_z_99_minus(tran_amt, 9)
    )


def _st_line14a(total_amt: Decimal) -> str:
    """``ST-LINE14A`` -- total expenditure line."""
    return "Total EXP:" + " " * 56 + "$" + format_pic_z_99_minus(total_amt, 9)


def _st_line15() -> str:
    """``ST-LINE15`` -- END OF STATEMENT banner (80 bytes)."""
    return ("*" * 32) + "END OF STATEMENT" + ("*" * 32)


def _st_line1(name: str) -> str:
    """``ST-LINE1`` -- customer name (75 chars) + 5 spaces."""
    return name.ljust(75)[:75] + " " * 5


def _st_line2(addr1: str) -> str:
    """``ST-LINE2`` -- address line 1."""
    return addr1.ljust(50)[:50] + " " * 30


def _st_line3(addr2: str) -> str:
    """``ST-LINE3`` -- address line 2."""
    return addr2.ljust(50)[:50] + " " * 30


def _st_line4(addr3: str) -> str:
    """``ST-LINE4`` -- address line 3 (full 80)."""
    return addr3.ljust(80)[:80]


# -----------------------------------------------------------------------
# COBOL STRING builder for names / addresses
# -----------------------------------------------------------------------

def _cobol_string_name(first: str, middle: str, last: str) -> str:
    """Reproduce the ``STRING CUST-FIRST-NAME DELIMITED BY ' ' ...`` logic.

    Each part is delimited by a single space; a literal space separates parts.
    Result goes into ST-NAME PIC X(75).
    """
    parts = []
    for part in [first, middle, last]:
        trimmed = _delimited_by_char(part, " ")
        parts.append(trimmed)
        parts.append(" ")
    result = "".join(parts)
    return result.ljust(75)[:75]


def _cobol_string_addr3(
    addr3: str, state: str, country: str, zipcode: str
) -> str:
    """Reproduce ``STRING CUST-ADDR-LINE-3 DELIMITED BY ' ' ...`` for ST-ADD3.

    Each field delimited by single space, separated by literal spaces.
    Result goes into ST-ADD3 PIC X(80).
    """
    parts = []
    for part in [addr3, state, country, zipcode]:
        trimmed = _delimited_by_char(part, " ")
        parts.append(trimmed)
        parts.append(" ")
    result = "".join(parts)
    return result.ljust(80)[:80]


# -----------------------------------------------------------------------
# HTML line builders
# -----------------------------------------------------------------------

def _html_l11(acct_id: str) -> str:
    """``HTML-L11`` -- account number heading."""
    line = (
        "<h3>Statement for Account Number: "
        + acct_id.ljust(20)[:20]
        + "</h3>"
    )
    return line.ljust(HTML_RECORD_LEN)[:HTML_RECORD_LEN]


def _html_name_line(name: str) -> str:
    """Name <p> tag built via STRING ... DELIMITED BY '  '."""
    trimmed = _delimited_by_char(name, "  ")
    line = '<p style="font-size:16px">' + trimmed + "  " + "</p>"
    return line.ljust(HTML_RECORD_LEN)[:HTML_RECORD_LEN]


def _html_addr_line(addr: str) -> str:
    """Address <p> tag built via STRING ... DELIMITED BY '  '."""
    trimmed = _delimited_by_char(addr, "  ")
    line = "<p>" + trimmed + "  " + "</p>"
    return line.ljust(HTML_RECORD_LEN)[:HTML_RECORD_LEN]


def _html_basic_line(label: str, value: str) -> str:
    """Basic-details line via STRING ... DELIMITED BY '*'."""
    line = "<p>" + label + value + "</p>"
    return line.ljust(HTML_RECORD_LEN)[:HTML_RECORD_LEN]


def _html_tran_cell(value: str) -> str:
    """Transaction cell via STRING ... DELIMITED BY '*'."""
    line = "<p>" + value + "</p>"
    return line.ljust(HTML_RECORD_LEN)[:HTML_RECORD_LEN]


# -----------------------------------------------------------------------
# Transaction table (WS-TRNX-TABLE) pre-load
# -----------------------------------------------------------------------

@dataclass
class _CardTransactions:
    card_num: str = ""
    transactions: List[TrnxRecord] = field(default_factory=list)


def _preload_transactions(store: FileStore) -> list[_CardTransactions]:
    """Read all transactions and group by card (reproduces 8500-READTRNX-READ).

    Returns a list of _CardTransactions, one per distinct card number,
    in the order first encountered.
    """
    rc = store.open("TRNXFILE")
    if rc not in (RC_OK, "04"):
        raise RuntimeError(f"ERROR OPENING TRNXFILE, RC={rc}")

    rc, first_rec = store.read_sequential("TRNXFILE")
    if rc not in (RC_OK, "04"):
        if rc == RC_EOF:
            return []
        raise RuntimeError(f"ERROR READING TRNXFILE, RC={rc}")

    cards: list[_CardTransactions] = []
    current = _CardTransactions(card_num=first_rec.trnx_card_num)

    def _store_record(rec: TrnxRecord) -> None:
        nonlocal current
        if rec.trnx_card_num != current.card_num:
            cards.append(current)
            current = _CardTransactions(card_num=rec.trnx_card_num)
        current.transactions.append(rec)

    _store_record(first_rec)

    while True:
        rc, rec = store.read_sequential("TRNXFILE")
        if rc == RC_EOF:
            break
        if rc not in (RC_OK, "04"):
            raise RuntimeError(f"ERROR READING TRNXFILE, RC={rc}")
        _store_record(rec)

    cards.append(current)
    return cards


# -----------------------------------------------------------------------
# Main statement generation
# -----------------------------------------------------------------------

class StatementGenerator:
    """Reproduces the CBSTM03A mainline logic."""

    def __init__(self, store: FileStore) -> None:
        self._store = store
        self._stmt_lines: list[str] = []
        self._html_lines: list[str] = []

    def _write_stmt(self, line: str) -> None:
        self._stmt_lines.append(line.ljust(STMT_RECORD_LEN)[:STMT_RECORD_LEN])

    def _write_html(self, line: str) -> None:
        self._html_lines.append(
            line.ljust(HTML_RECORD_LEN)[:HTML_RECORD_LEN]
        )

    def _write_html_fixed(self, key: str) -> None:
        self._write_html(_html_fixed(key))

    # -- 5100-WRITE-HTML-HEADER --
    def _write_html_header(self, acct_id: str) -> None:
        for key in [
            "L01", "L02", "L03", "L04", "L05", "L06", "L07", "L08",
            "TRS", "L10",
        ]:
            self._write_html_fixed(key)

        self._write_html(_html_l11(acct_id))
        self._write_html_fixed("TDE")
        self._write_html_fixed("TRE")
        self._write_html_fixed("TRS")
        self._write_html_fixed("L15")

        for key in ["L16", "L17", "L18"]:
            self._write_html_fixed(key)

        self._write_html_fixed("TDE")
        self._write_html_fixed("TRE")
        self._write_html_fixed("TRS")
        self._write_html_fixed("L22_35")

    # -- 5200-WRITE-HTML-NMADBS --
    def _write_html_name_addr_basics(
        self,
        st_name: str,
        st_add1: str,
        st_add2: str,
        st_add3: str,
        st_acct_id: str,
        st_curr_bal: str,
        st_fico: str,
    ) -> None:
        l23_name = st_name[:50]
        self._write_html(_html_name_line(l23_name))

        self._write_html(_html_addr_line(st_add1))
        self._write_html(_html_addr_line(st_add2))
        self._write_html(_html_addr_line(st_add3))

        self._write_html_fixed("TDE")
        self._write_html_fixed("TRE")
        self._write_html_fixed("TRS")
        self._write_html_fixed("L30_42")
        self._write_html_fixed("L31")
        self._write_html_fixed("TDE")
        self._write_html_fixed("TRE")
        self._write_html_fixed("TRS")
        self._write_html_fixed("L22_35")

        self._write_html(
            _html_basic_line("Account ID         : ", st_acct_id)
        )
        self._write_html(
            _html_basic_line("Current Balance    : ", st_curr_bal)
        )
        self._write_html(
            _html_basic_line("FICO Score         : ", st_fico)
        )

        self._write_html_fixed("TDE")
        self._write_html_fixed("TRE")
        self._write_html_fixed("TRS")
        self._write_html_fixed("L30_42")
        self._write_html_fixed("L43")
        self._write_html_fixed("TDE")
        self._write_html_fixed("TRE")

        self._write_html_fixed("TRS")
        self._write_html_fixed("L47")
        self._write_html_fixed("L48")
        self._write_html_fixed("TDE")
        self._write_html_fixed("L50")
        self._write_html_fixed("L51")
        self._write_html_fixed("TDE")
        self._write_html_fixed("L53")
        self._write_html_fixed("L54")
        self._write_html_fixed("TDE")
        self._write_html_fixed("TRE")

    # -- 6000-WRITE-TRANS --
    def _write_trans(
        self,
        tran_id: str,
        tran_desc: str,
        tran_amt: Decimal,
    ) -> None:
        st_tranid = tran_id.ljust(16)[:16]
        st_trandt = tran_desc.ljust(49)[:49]
        st_tranamt_str = format_pic_z_99_minus(tran_amt, 9)

        self._write_stmt(_st_line14(st_tranid, st_trandt, tran_amt))

        self._write_html_fixed("TRS")

        self._write_html_fixed("L58")
        self._write_html(_html_tran_cell(st_tranid))
        self._write_html_fixed("TDE")

        self._write_html_fixed("L61")
        self._write_html(_html_tran_cell(st_trandt))
        self._write_html_fixed("TDE")

        self._write_html_fixed("L64")
        self._write_html(_html_tran_cell(st_tranamt_str))
        self._write_html_fixed("TDE")

        self._write_html_fixed("TRE")

    # -- 5000-CREATE-STATEMENT --
    def _create_statement(
        self,
        customer: CustomerRecord,
        account: AccountRecord,
    ) -> tuple[str, str, str, str]:
        """Write the statement header; return (st_name, st_add1, st_add2, st_add3)."""
        st_name = _cobol_string_name(
            customer.cust_first_name,
            customer.cust_middle_name,
            customer.cust_last_name,
        )
        st_add1 = customer.cust_addr_line_1.ljust(50)[:50]
        st_add2 = customer.cust_addr_line_2.ljust(50)[:50]
        st_add3 = _cobol_string_addr3(
            customer.cust_addr_line_3,
            customer.cust_addr_state_cd,
            customer.cust_addr_country_cd,
            customer.cust_addr_zip,
        )

        st_acct_id = account.acct_id.ljust(20)[:20]
        st_curr_bal = format_pic_9_99_minus(account.acct_curr_bal, 9)
        st_fico = customer.cust_fico_credit_score.ljust(20)[:20]

        self._write_stmt(_st_line0())

        self._write_html_header(account.acct_id)

        self._write_html_name_addr_basics(
            st_name, st_add1, st_add2, st_add3,
            st_acct_id, st_curr_bal, st_fico,
        )

        self._write_stmt(_st_line1(st_name))
        self._write_stmt(_st_line2(st_add1))
        self._write_stmt(_st_line3(st_add2))
        self._write_stmt(_st_line4(st_add3))
        self._write_stmt(_st_line5())
        self._write_stmt(_st_line6())
        self._write_stmt(_st_line5())
        self._write_stmt(_st_line7(st_acct_id))
        self._write_stmt(_st_line8(account.acct_curr_bal))
        self._write_stmt(_st_line9(st_fico))
        self._write_stmt(_st_line5())
        self._write_stmt(_st_line11())
        self._write_stmt(_st_line5())
        self._write_stmt(_st_line13())
        self._write_stmt(_st_line5())

        return st_name, st_add1, st_add2, st_add3

    # -- 4000-TRNXFILE-GET --
    def _process_transactions(
        self,
        xref_card_num: str,
        card_table: list[_CardTransactions],
    ) -> None:
        """Find matching card transactions and write them."""
        ws_total_amt = Decimal("0.00")

        for card_entry in card_table:
            if card_entry.card_num > xref_card_num:
                break
            if card_entry.card_num == xref_card_num:
                for rec in card_entry.transactions:
                    self._write_trans(rec.trnx_id, rec.trnx_desc, rec.trnx_amt)
                    ws_total_amt += rec.trnx_amt

        ws_trn_amt = ws_total_amt
        st_total_tramt = format_pic_z_99_minus(ws_trn_amt, 9)

        self._write_stmt(_st_line5())
        self._write_stmt(_st_line14a(ws_trn_amt))
        self._write_stmt(_st_line15())

        self._write_html_fixed("TRS")
        self._write_html_fixed("L10")
        self._write_html_fixed("L75")
        self._write_html_fixed("TDE")
        self._write_html_fixed("TRE")
        self._write_html_fixed("L78")
        self._write_html_fixed("L79")
        self._write_html_fixed("L80")

    # -- 1000-MAINLINE --
    def run(self) -> tuple[list[str], list[str]]:
        """Execute the full statement generation job.

        Returns (stmt_lines, html_lines) where each element is a
        fixed-width record string.
        """
        card_table = _preload_transactions(self._store)

        rc = self._store.open("XREFFILE")
        if rc not in (RC_OK, "04"):
            raise RuntimeError(f"ERROR OPENING XREFFILE, RC={rc}")
        rc = self._store.open("CUSTFILE")
        if rc not in (RC_OK, "04"):
            raise RuntimeError(f"ERROR OPENING CUSTFILE, RC={rc}")
        rc = self._store.open("ACCTFILE")
        if rc not in (RC_OK, "04"):
            raise RuntimeError(f"ERROR OPENING ACCTFILE, RC={rc}")

        while True:
            rc, xref_rec = self._store.read_sequential("XREFFILE")
            if rc == RC_EOF:
                break
            if rc not in (RC_OK, "04"):
                raise RuntimeError(f"ERROR READING XREFFILE, RC={rc}")

            rc, cust_rec = self._store.read_by_key(
                "CUSTFILE",
                xref_rec.xref_cust_id,
                len(xref_rec.xref_cust_id.strip()),
            )
            if rc != RC_OK:
                raise RuntimeError(f"ERROR READING CUSTFILE, RC={rc}")

            rc, acct_rec = self._store.read_by_key(
                "ACCTFILE",
                xref_rec.xref_acct_id,
                len(xref_rec.xref_acct_id.strip()),
            )
            if rc != RC_OK:
                raise RuntimeError(f"ERROR READING ACCTFILE, RC={rc}")

            self._create_statement(cust_rec, acct_rec)
            self._process_transactions(xref_rec.xref_card_num, card_table)

        self._store.close("TRNXFILE")
        self._store.close("XREFFILE")
        self._store.close("CUSTFILE")
        self._store.close("ACCTFILE")

        return self._stmt_lines, self._html_lines


def generate_statements(
    trnx_file: str,
    xref_file: str,
    cust_file: str,
    acct_file: str,
    stmt_output: str,
    html_output: str,
) -> None:
    """Entry point: read four input CSV files and produce statement outputs.

    Parameters
    ----------
    trnx_file : str
        Path to transaction CSV (columns from COSTM01).
    xref_file : str
        Path to card cross-reference CSV (columns from CVACT03Y).
    cust_file : str
        Path to customer CSV (columns from CUSTREC).
    acct_file : str
        Path to account CSV (columns from CVACT01Y).
    stmt_output : str
        Path for the plain-text statement output.
    html_output : str
        Path for the HTML statement output.
    """
    store = FileStore(trnx_file, xref_file, cust_file, acct_file)
    gen = StatementGenerator(store)
    stmt_lines, html_lines = gen.run()

    with open(stmt_output, "w", newline="") as f:
        for line in stmt_lines:
            f.write(line + "\n")

    with open(html_output, "w", newline="") as f:
        for line in html_lines:
            f.write(line + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 7:
        print(
            "Usage: python cbstm03a_statement.py "
            "<trnx.csv> <xref.csv> <cust.csv> <acct.csv> "
            "<stmt.txt> <stmt.html>"
        )
        sys.exit(1)
    generate_statements(*sys.argv[1:7])
