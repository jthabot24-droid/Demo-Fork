"""Plain-Python migration of CBSTM03A.CBL — CREASTMT statement generator.

Original COBOL: app/cbl/CBSTM03A.CBL + subroutine app/cbl/CBSTM03B.CBL
Reads card cross-reference, customer, account, and transaction files,
groups transactions by card, and emits per-account plain-text (80-column)
and HTML (100-column) statements.

The COBOL ALTER/GO-TO control flow and TIOT control-block inspection are
replaced with structured Python.
"""

from decimal import Decimal, ROUND_DOWN
from typing import Optional

from migration.src.copybook_records import (
    TrnxRecord, CardXrefRecord, CustomerRecord, AccountRecord,
    parse_trnx, parse_card_xref, parse_customer, parse_account,
    load_file, format_str, _trunc2,
)


TWO_PLACES = Decimal("0.01")


# ---------------------------------------------------------------------------
# COBOL PIC editing helpers
# ---------------------------------------------------------------------------

def format_pic_9_dot_99_minus(value: Decimal, int_digits: int = 9) -> str:
    """Format like PIC 9(9).99- : fixed digits, fixed decimal, trailing sign.

    Always shows all leading-zero digits, fixed '.', 2 decimal digits,
    then '-' if negative or ' ' if positive.
    Total width = int_digits + 1 (dot) + 2 (dec) + 1 (sign) = int_digits + 4.
    """
    is_neg = value < 0
    abs_val = abs(_trunc2(value))
    int_part = int(abs_val)
    dec_part = int((abs_val - int_part) * 100)
    result = f"{int_part:0{int_digits}d}.{dec_part:02d}"
    result += "-" if is_neg else " "
    return result


def format_pic_z_dot_99_minus(value: Decimal, int_digits: int = 9) -> str:
    """Format like PIC Z(9).99- : zero-suppressed leading, fixed decimal,
    trailing sign.

    Leading zeros replaced with spaces. The digit immediately before the '.'
    is always shown (at minimum).
    Total width = int_digits + 1 (dot) + 2 (dec) + 1 (sign) = int_digits + 4.
    """
    is_neg = value < 0
    abs_val = abs(_trunc2(value))
    int_part = int(abs_val)
    dec_part = int((abs_val - int_part) * 100)
    int_str = f"{int_part:0{int_digits}d}"
    # Suppress leading zeros (but keep at least one digit)
    stripped = int_str.lstrip("0") or "0"
    padded = " " * (int_digits - len(stripped)) + stripped
    result = f"{padded}.{dec_part:02d}"
    result += "-" if is_neg else " "
    return result


# ---------------------------------------------------------------------------
# Statement lines (matches COBOL STATEMENT-LINES layout, 80 columns)
# ---------------------------------------------------------------------------

def _st_line0() -> str:
    """Start of statement header: stars + text + stars."""
    return "*" * 31 + "START OF STATEMENT" + "*" * 31


def _st_line15() -> str:
    """End of statement footer: stars + text + stars."""
    return "*" * 32 + "END OF STATEMENT" + "*" * 32


def _st_line_sep() -> str:
    """Separator: 80 dashes."""
    return "-" * 80


def _st_line_name(name: str) -> str:
    """ST-LINE1: name (75) + spaces (5)."""
    return format_str(name, 75) + " " * 5


def _st_line_add1(addr: str) -> str:
    """ST-LINE2: addr1 (50) + spaces (30)."""
    return format_str(addr, 50) + " " * 30


def _st_line_add2(addr: str) -> str:
    """ST-LINE3: addr2 (50) + spaces (30)."""
    return format_str(addr, 50) + " " * 30


def _st_line_add3(addr: str) -> str:
    """ST-LINE4: full line (80)."""
    return format_str(addr, 80)


def _st_line_basic_details() -> str:
    """ST-LINE6: centered 'Basic Details'."""
    return " " * 33 + "Basic Details" + " " + " " * 33


def _st_line_acct_id(acct_id: str) -> str:
    """ST-LINE7: Account ID line."""
    return "Account ID         :" + format_str(acct_id, 20) + " " * 40


def _st_line_curr_bal(bal: Decimal) -> str:
    """ST-LINE8: Current Balance line using PIC 9(9).99-."""
    formatted = format_pic_9_dot_99_minus(bal, 9)
    return "Current Balance    :" + formatted + " " * 7 + " " * 40


def _st_line_fico(score: str) -> str:
    """ST-LINE9: FICO Score line."""
    return "FICO Score         :" + format_str(score, 20) + " " * 40


def _st_line_tran_summary() -> str:
    """ST-LINE11: centered 'TRANSACTION SUMMARY'."""
    return " " * 30 + "TRANSACTION SUMMARY " + " " * 30


def _st_line_tran_header() -> str:
    """ST-LINE13: transaction column headers."""
    return "Tran ID         " + "Tran Details    " + " " * 35 + "  Tran Amount"


def _st_line_tran(tran_id: str, desc: str, amt: Decimal) -> str:
    """ST-LINE14: one transaction line."""
    formatted_amt = format_pic_z_dot_99_minus(amt, 9)
    return format_str(tran_id, 16) + " " + format_str(desc, 49) + "$" + formatted_amt


def _st_line_total(total: Decimal) -> str:
    """ST-LINE14A: total line."""
    formatted_total = format_pic_z_dot_99_minus(total, 9)
    return "Total EXP:" + " " * 56 + "$" + formatted_total


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def _generate_html_header(acct_id: str) -> list:
    lines = [
        "<!DOCTYPE html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>HTML Table Layout</title>",
        "</head>",
        '<body style="margin:0px;">',
        '<table  align="center" frame="box" style="width:70%; font:12px Segoe UI,sans-serif;">',
        "<tr>",
        '<td colspan="3" style="padding:0px 5px;background-color:#1d1d96b3;">',
    ]
    lines.append(f'<h3>Statement for Account Number: {format_str(acct_id, 20)}</h3>')
    lines.extend(["</td>", "</tr>", "<tr>",
                   '<td colspan="3" style="padding:0px 5px;background-color:#FFAF33;">',
                   '<p style="font-size:16px">Bank of XYZ</p>',
                   "<p>410 Terry Ave N</p>",
                   "<p>Seattle WA 99999</p>",
                   "</td>", "</tr>", "<tr>",
                   '<td colspan="3" style="padding:0px 5px;background-color:#f2f2f2;">'])
    return lines


def _generate_html_name_addr(name: str, add1: str, add2: str,
                              add3: str) -> list:
    lines = []
    n = name.rstrip()
    a1 = add1.rstrip()
    a2 = add2.rstrip()
    a3 = add3.rstrip()
    lines.append(f'<p style="font-size:16px">{n}  </p>')
    lines.append(f"<p>{a1}  </p>")
    lines.append(f"<p>{a2}  </p>")
    lines.append(f"<p>{a3}  </p>")
    lines.extend(["</td>", "</tr>"])
    return lines


def _generate_html_basic_details(acct_id: str, curr_bal: str,
                                  fico: str) -> list:
    lines = [
        "<tr>",
        '<td colspan="3" style="padding:0px 5px;background-color:#33FFD1; text-align:center;">',
        '<p style="font-size:16px">Basic Details</p>',
        "</td>", "</tr>", "<tr>",
        '<td colspan="3" style="padding:0px 5px;background-color:#f2f2f2;">',
        f"<p>Account ID         : {acct_id}</p>",
        f"<p>Current Balance    : {curr_bal}</p>",
        f"<p>FICO Score         : {fico}</p>",
        "</td>", "</tr>",
    ]
    return lines


def _generate_html_tran_header() -> list:
    return [
        "<tr>",
        '<td colspan="3" style="padding:0px 5px;background-color:#33FFD1; text-align:center;">',
        '<p style="font-size:16px">Transaction Summary</p>',
        "</td>", "</tr>",
        "<tr>",
        '<td style="width:25%; padding:0px 5px; background-color:#33FF5E; text-align:left;">',
        '<p style="font-size:16px">Tran ID</p>',
        "</td>",
        '<td style="width:55%; padding:0px 5px; background-color:#33FF5E; text-align:left;">',
        '<p style="font-size:16px">Tran Details</p>',
        "</td>",
        '<td style="width:20%; padding:0px 5px; background-color:#33FF5E; text-align:right;">',
        '<p style="font-size:16px">Amount</p>',
        "</td>",
        "</tr>",
    ]


def _generate_html_tran_line(tran_id: str, desc: str, amt_str: str) -> list:
    return [
        "<tr>",
        '<td style="width:25%; padding:0px 5px; background-color:#f2f2f2; text-align:left;">',
        f"<p>{tran_id}</p>",
        "</td>",
        '<td style="width:55%; padding:0px 5px; background-color:#f2f2f2; text-align:left;">',
        f"<p>{desc}</p>",
        "</td>",
        '<td style="width:20%; padding:0px 5px; background-color:#f2f2f2; text-align:right;">',
        f"<p>{amt_str}</p>",
        "</td>",
        "</tr>",
    ]


def _generate_html_footer() -> list:
    return [
        "<tr>",
        '<td colspan="3" style="padding:0px 5px;background-color:#1d1d96b3;">',
        "<h3>End of Statement</h3>",
        "</td>",
        "</tr>",
        "</table>",
        "</body>",
        "</html>",
    ]


# ---------------------------------------------------------------------------
# Core statement generation logic
# ---------------------------------------------------------------------------

def _build_customer_name(cust: CustomerRecord) -> str:
    """Build full name from customer record using COBOL STRING logic.

    STRING CUST-FIRST-NAME DELIMITED BY ' '
           ' ' CUST-MIDDLE-NAME DELIMITED BY ' '
           ' ' CUST-LAST-NAME DELIMITED BY ' '
    """
    first = cust.cust_first_name.split()[0] if cust.cust_first_name.strip() else ""
    middle = cust.cust_middle_name.split()[0] if cust.cust_middle_name.strip() else ""
    last = cust.cust_last_name.split()[0] if cust.cust_last_name.strip() else ""
    parts = [p for p in [first, middle, last] if p]
    return " ".join(parts)


def _build_address_line3(cust: CustomerRecord) -> str:
    """Build address line 3 using COBOL STRING logic."""
    line3 = cust.cust_addr_line_3.split()[0] if cust.cust_addr_line_3.strip() else ""
    state = cust.cust_addr_state_cd.split()[0] if cust.cust_addr_state_cd.strip() else ""
    country = cust.cust_addr_country_cd.split()[0] if cust.cust_addr_country_cd.strip() else ""
    zipcode = cust.cust_addr_zip.split()[0] if cust.cust_addr_zip.strip() else ""
    parts = [p for p in [line3, state, country, zipcode] if p]
    return " ".join(parts)


def generate_statement(
    xref: CardXrefRecord,
    cust: CustomerRecord,
    acct: AccountRecord,
    transactions: list,
) -> tuple:
    """Generate plain-text and HTML statement lines for one account.

    Returns (text_lines, html_lines) where each is a list of strings.
    """
    text_lines = []
    html_lines = []

    # Customer name and address
    name = _build_customer_name(cust)
    addr1 = cust.cust_addr_line_1
    addr2 = cust.cust_addr_line_2
    addr3 = _build_address_line3(cust)

    acct_id = acct.acct_id
    curr_bal_str = format_pic_9_dot_99_minus(acct.acct_curr_bal, 9)
    fico = cust.cust_fico_credit_score

    # -- Plain text --
    text_lines.append(_st_line0())
    text_lines.append(_st_line_name(name))
    text_lines.append(_st_line_add1(addr1))
    text_lines.append(_st_line_add2(addr2))
    text_lines.append(_st_line_add3(addr3))
    text_lines.append(_st_line_sep())
    text_lines.append(_st_line_basic_details())
    text_lines.append(_st_line_sep())
    text_lines.append(_st_line_acct_id(acct_id))
    text_lines.append(_st_line_curr_bal(acct.acct_curr_bal))
    text_lines.append(_st_line_fico(fico))
    text_lines.append(_st_line_sep())  # ST-LINE10
    text_lines.append(_st_line_tran_summary())
    text_lines.append(_st_line_sep())  # ST-LINE12
    text_lines.append(_st_line_tran_header())
    text_lines.append(_st_line_sep())  # ST-LINE12 again

    # -- HTML --
    html_lines.extend(_generate_html_header(acct_id))
    html_lines.extend(_generate_html_name_addr(name, addr1, addr2, addr3))
    html_lines.extend(_generate_html_basic_details(
        format_str(acct_id, 20), curr_bal_str, format_str(fico, 20)))
    html_lines.extend(_generate_html_tran_header())

    # Transactions
    total_amt = Decimal("0.00")
    for trnx in transactions:
        tran_id = trnx.trnx_id
        desc = trnx.trnx_desc[:49]
        amt = trnx.trnx_amt
        total_amt = _trunc2(total_amt + amt)
        amt_str = format_pic_z_dot_99_minus(amt, 9)
        text_lines.append(_st_line_tran(tran_id, desc, amt))
        html_lines.extend(_generate_html_tran_line(
            tran_id, desc, amt_str))

    # Totals / footer
    text_lines.append(_st_line_sep())
    text_lines.append(_st_line_total(total_amt))
    text_lines.append(_st_line15())

    html_lines.extend(_generate_html_footer())

    return text_lines, html_lines


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_creastmt(
    trnx_path: str,
    xref_path: str,
    cust_path: str,
    acct_path: str,
    stmt_output_path: str,
    html_output_path: Optional[str] = None,
):
    """Execute the CREASTMT statement generation job."""
    trnx_records = load_file(trnx_path, parse_trnx)
    xref_records = load_file(xref_path, parse_card_xref)
    cust_records = load_file(cust_path, parse_customer)
    acct_records = load_file(acct_path, parse_account)

    return run_creastmt_pure(
        trnx_records, xref_records, cust_records, acct_records,
        stmt_output_path, html_output_path)


def run_creastmt_pure(
    trnx_records: list,
    xref_records: list,
    cust_records: list,
    acct_records: list,
    stmt_output_path: Optional[str] = None,
    html_output_path: Optional[str] = None,
) -> list:
    """Pure-Python CREASTMT logic.

    Returns list of (text_lines, html_lines) per account.
    """
    # Build maps
    cust_map = {rec.cust_id: rec for rec in cust_records}
    acct_map = {rec.acct_id: rec for rec in acct_records}

    # Build transaction table grouped by card number (COBOL 8500-READTRNX-READ)
    trnx_by_card = {}
    for trnx in trnx_records:
        card = trnx.trnx_card_num
        trnx_by_card.setdefault(card, []).append(trnx)

    all_statements = []
    all_text_lines = []
    all_html_lines = []

    # Process xref records sequentially (COBOL 1000-MAINLINE)
    for xref in xref_records:
        cust = cust_map.get(xref.xref_cust_id)
        acct = acct_map.get(xref.xref_acct_id)
        if cust is None or acct is None:
            continue

        # Gather transactions for this card
        card_transactions = trnx_by_card.get(xref.xref_card_num, [])

        text_lines, html_lines = generate_statement(
            xref, cust, acct, card_transactions)
        all_statements.append((text_lines, html_lines))
        all_text_lines.extend(text_lines)
        all_html_lines.extend(html_lines)

    # Write outputs
    if stmt_output_path:
        with open(stmt_output_path, "w") as f:
            for line in all_text_lines:
                f.write(line + "\n")

    if html_output_path:
        with open(html_output_path, "w") as f:
            for line in all_html_lines:
                f.write(line + "\n")

    return all_statements
