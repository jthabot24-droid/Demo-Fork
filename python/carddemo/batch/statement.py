"""CBSTM03A / CBSTM03B — Statement Generation.

Generates account statements in plain-text and HTML formats by
iterating over the card cross-reference file, looking up customer
and account data, and collecting transactions for each card.

COBOL sources: ``app/cbl/CBSTM03A.CBL``, ``app/cbl/CBSTM03B.CBL``
JCL:           ``app/jcl/CREASTMT.JCL``

The original COBOL uses a dynamic CALL to CBSTM03B for file I/O
operations.  This Python port collapses both programs into a single
module that queries the database directly.
"""

from __future__ import annotations

import html
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import TextIO

from sqlalchemy import select
from sqlalchemy.orm import Session

from carddemo.models import Account, CardXref, Customer, Transaction

log = logging.getLogger(__name__)


@dataclass
class StatementResult:
    """Summary returned by :func:`run`."""

    accounts_processed: int = 0
    transactions_included: int = 0


def _format_amount(amount: Decimal) -> str:
    """Format amount like COBOL ``PIC Z(9).99-``."""
    sign = "-" if amount < 0 else " "
    abs_val = abs(amount)
    formatted = f"{abs_val:>12.2f}{sign}"
    return formatted


def _write_text_statement(
    out: TextIO,
    customer: Customer,
    account: Account,
    transactions: list[Transaction],
) -> Decimal:
    """Write a single account statement in plain-text format."""
    out.write("*" * 31 + "START OF STATEMENT" + "*" * 31 + "\n")

    name_parts = []
    for part in [customer.cust_first_name, customer.cust_middle_name, customer.cust_last_name]:
        stripped = str(part).strip()
        if stripped:
            name_parts.append(stripped)
    name = " ".join(name_parts)
    out.write(f"{name:<75}     \n")
    out.write(f"{str(customer.cust_addr_line_1).strip():<50}" + " " * 30 + "\n")
    out.write(f"{str(customer.cust_addr_line_2).strip():<50}" + " " * 30 + "\n")

    addr3_parts = []
    for part in [customer.cust_addr_line_3, customer.cust_addr_state_cd,
                 customer.cust_addr_country_cd, customer.cust_addr_zip]:
        stripped = str(part).strip()
        if stripped:
            addr3_parts.append(stripped)
    addr3 = " ".join(addr3_parts)
    out.write(f"{addr3:<80}\n")

    out.write("-" * 80 + "\n")
    out.write(" " * 33 + "Basic Details" + " " * 34 + "\n")
    out.write("-" * 80 + "\n")
    out.write(f"Account ID         :{str(account.acct_id):<20}" + " " * 40 + "\n")

    curr_bal = Decimal(str(account.acct_curr_bal))
    bal_sign = "-" if curr_bal < 0 else " "
    bal_str = f"{abs(curr_bal):>9.2f}{bal_sign}"
    out.write(f"Current Balance    :{bal_str:<20}" + " " * 47 + "\n")

    fico = str(customer.cust_fico_credit_score).strip()
    out.write(f"FICO Score         :{fico:<20}" + " " * 40 + "\n")
    out.write("-" * 80 + "\n")
    out.write(" " * 30 + "TRANSACTION SUMMARY " + " " * 30 + "\n")
    out.write("-" * 80 + "\n")
    out.write("Tran ID         Tran Details                                                "
              "  Tran Amount\n")
    out.write("-" * 80 + "\n")

    total = Decimal("0.00")
    for txn in transactions:
        amt = Decimal(str(txn.tran_amt))
        total += amt
        tran_id = str(txn.tran_id).strip()
        desc = str(txn.tran_desc).strip()[:49]
        amt_str = _format_amount(amt)
        out.write(f"{tran_id:<16} {desc:<49}${amt_str}\n")

    out.write("-" * 80 + "\n")
    total_str = _format_amount(total)
    out.write(f"Total EXP:" + " " * 56 + f"${total_str}\n")
    out.write("*" * 32 + "END OF STATEMENT" + "*" * 32 + "\n")
    return total


def _write_html_statement(
    out: TextIO,
    customer: Customer,
    account: Account,
    transactions: list[Transaction],
) -> None:
    """Write a single account statement in HTML format."""
    out.write("<!DOCTYPE html>\n")
    out.write('<html lang="en">\n')
    out.write("<head>\n")
    out.write('<meta charset="utf-8">\n')
    out.write("<title>HTML Table Layout</title>\n")
    out.write("</head>\n")
    out.write('<body style="margin:0px;">\n')
    out.write('<table  align="center" frame="box" '
              'style="width:70%; font:12px Segoe UI,sans-serif;">\n')

    out.write("<tr>\n")
    out.write('<td colspan="3" style="padding:0px 5px;background-color:#1d1d96b3;">\n')
    acct_id = str(account.acct_id).strip()
    out.write(f"<h3>Statement for Account Number: {html.escape(acct_id)}</h3>\n")
    out.write("</td>\n")
    out.write("</tr>\n")

    out.write("<tr>\n")
    out.write('<td colspan="3" style="padding:0px 5px;background-color:#FFAF33;">\n')
    out.write('<p style="font-size:16px">Bank of XYZ</p>\n')
    out.write("<p>410 Terry Ave N</p>\n")
    out.write("<p>Seattle WA 99999</p>\n")
    out.write("</td>\n")
    out.write("</tr>\n")

    out.write("<tr>\n")
    out.write('<td colspan="3" style="padding:0px 5px;background-color:#f2f2f2;">\n')

    name_parts = []
    for part in [customer.cust_first_name, customer.cust_middle_name, customer.cust_last_name]:
        stripped = str(part).strip()
        if stripped:
            name_parts.append(stripped)
    name = " ".join(name_parts)
    out.write(f'<p style="font-size:16px">{html.escape(name)}</p>\n')

    for addr in [customer.cust_addr_line_1, customer.cust_addr_line_2]:
        out.write(f"<p>{html.escape(str(addr).strip())}</p>\n")
    addr3_parts = []
    for part in [customer.cust_addr_line_3, customer.cust_addr_state_cd,
                 customer.cust_addr_country_cd, customer.cust_addr_zip]:
        stripped = str(part).strip()
        if stripped:
            addr3_parts.append(stripped)
    out.write(f"<p>{html.escape(' '.join(addr3_parts))}</p>\n")
    out.write("</td>\n")
    out.write("</tr>\n")

    # Basic details
    out.write("<tr>\n")
    out.write('<td colspan="3" style="padding:0px 5px;background-color:#33FFD1; '
              'text-align:center;">\n')
    out.write('<p style="font-size:16px">Basic Details</p>\n')
    out.write("</td>\n")
    out.write("</tr>\n")

    out.write("<tr>\n")
    out.write('<td colspan="3" style="padding:0px 5px;background-color:#f2f2f2;">\n')
    curr_bal = Decimal(str(account.acct_curr_bal))
    bal_sign = "-" if curr_bal < 0 else " "
    bal_str = f"{abs(curr_bal):>9.2f}{bal_sign}"
    out.write(f"<p>Account ID         : {html.escape(acct_id)}</p>\n")
    out.write(f"<p>Current Balance    : {bal_str}</p>\n")
    fico = str(customer.cust_fico_credit_score).strip()
    out.write(f"<p>FICO Score         : {html.escape(fico)}</p>\n")
    out.write("</td>\n")
    out.write("</tr>\n")

    # Transaction summary header
    out.write("<tr>\n")
    out.write('<td colspan="3" style="padding:0px 5px;background-color:#33FFD1; '
              'text-align:center;">\n')
    out.write('<p style="font-size:16px">Transaction Summary</p>\n')
    out.write("</td>\n")
    out.write("</tr>\n")

    out.write("<tr>\n")
    out.write('<td style="width:25%; padding:0px 5px; background-color:#33FF5E; '
              'text-align:left;">\n')
    out.write('<p style="font-size:16px">Tran ID</p>\n')
    out.write("</td>\n")
    out.write('<td style="width:55%; padding:0px 5px; background-color:#33FF5E; '
              'text-align:left;">\n')
    out.write('<p style="font-size:16px">Tran Details</p>\n')
    out.write("</td>\n")
    out.write('<td style="width:20%; padding:0px 5px; background-color:#33FF5E; '
              'text-align:right;">\n')
    out.write('<p style="font-size:16px">Amount</p>\n')
    out.write("</td>\n")
    out.write("</tr>\n")

    for txn in transactions:
        amt = Decimal(str(txn.tran_amt))
        amt_str = _format_amount(amt)
        out.write("<tr>\n")
        out.write('<td style="width:25%; padding:0px 5px; background-color:#f2f2f2; '
                  'text-align:left;">\n')
        out.write(f"<p>{html.escape(str(txn.tran_id).strip())}</p>\n")
        out.write("</td>\n")
        out.write('<td style="width:55%; padding:0px 5px; background-color:#f2f2f2; '
                  'text-align:left;">\n')
        out.write(f"<p>{html.escape(str(txn.tran_desc).strip())}</p>\n")
        out.write("</td>\n")
        out.write('<td style="width:20%; padding:0px 5px; background-color:#f2f2f2; '
                  'text-align:right;">\n')
        out.write(f"<p>{amt_str}</p>\n")
        out.write("</td>\n")
        out.write("</tr>\n")

    # Footer
    out.write("<tr>\n")
    out.write('<td colspan="3" style="padding:0px 5px;background-color:#1d1d96b3;">\n')
    out.write("<h3>End of Statement</h3>\n")
    out.write("</td>\n")
    out.write("</tr>\n")
    out.write("</table>\n")
    out.write("</body>\n")
    out.write("</html>\n")


def run(
    session: Session,
    stmt_path: str | Path = "statements.txt",
    html_path: str | Path = "statements.html",
) -> StatementResult:
    """Execute the statement-generation batch job.

    Parameters
    ----------
    session:
        Active SQLAlchemy session with XREF, CUSTOMER, ACCOUNT,
        and TRANSACTION data loaded.
    stmt_path:
        Output path for the plain-text statement file.
    html_path:
        Output path for the HTML statement file.

    Returns
    -------
    StatementResult
    """
    result = StatementResult()
    log.info("START OF EXECUTION OF PROGRAM CBSTM03A (Python)")

    xref_rows = session.execute(
        select(CardXref).order_by(CardXref.xref_card_num)
    ).scalars().all()

    seen_acct_ids: set[str] = set()

    with open(str(stmt_path), "w") as stmt_f, open(str(html_path), "w") as html_f:
        for xref in xref_rows:
            acct_id = str(xref.xref_acct_id).strip()
            if acct_id in seen_acct_ids:
                continue
            seen_acct_ids.add(acct_id)

            cust_id = str(xref.xref_cust_id).strip()
            customer = session.get(Customer, cust_id)
            account = session.get(Account, acct_id)
            if customer is None or account is None:
                log.warning("Missing customer/account for xref card %s", xref.xref_card_num)
                continue

            card_nums = [
                str(x.xref_card_num).strip()
                for x in session.execute(
                    select(CardXref).where(CardXref.xref_acct_id == acct_id)
                ).scalars().all()
            ]

            txns = session.execute(
                select(Transaction)
                .where(Transaction.tran_card_num.in_(card_nums))
                .order_by(Transaction.tran_card_num, Transaction.tran_id)
            ).scalars().all()

            _write_text_statement(stmt_f, customer, account, txns)
            _write_html_statement(html_f, customer, account, txns)

            result.accounts_processed += 1
            result.transactions_included += len(txns)

    log.info(
        "Accounts processed: %d  Transactions included: %d",
        result.accounts_processed,
        result.transactions_included,
    )
    log.info("END OF EXECUTION OF PROGRAM CBSTM03A (Python)")
    return result
