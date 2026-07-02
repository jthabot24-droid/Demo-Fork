"""Tests for CBSTM03A CREASTMT statement generator migration.

Covers:
  - Plain-text 80-column statement layout
  - COBOL PIC editing (9(9).99- and Z(9).99-)
  - Customer name / address construction
  - Transaction line formatting
  - Total line
  - Byte-for-byte regression against committed reference file
"""

import os
from decimal import Decimal

import pytest

from migration.src.copybook_records import (
    TrnxRecord, CardXrefRecord, CustomerRecord, AccountRecord, format_str,
)
from migration.src.cbstm03a import (
    format_pic_9_dot_99_minus, format_pic_z_dot_99_minus,
    generate_statement, run_creastmt_pure,
)


# -----------------------------------------------------------------------
# PIC editing helpers
# -----------------------------------------------------------------------

class TestPicEditing:
    def test_9_dot_99_minus_positive(self):
        result = format_pic_9_dot_99_minus(Decimal("1234.56"), 9)
        assert result == "000001234.56 "

    def test_9_dot_99_minus_negative(self):
        result = format_pic_9_dot_99_minus(Decimal("-1234.56"), 9)
        assert result == "000001234.56-"

    def test_9_dot_99_minus_zero(self):
        result = format_pic_9_dot_99_minus(Decimal("0.00"), 9)
        assert result == "000000000.00 "

    def test_z_dot_99_minus_positive(self):
        result = format_pic_z_dot_99_minus(Decimal("1234.56"), 9)
        assert result == "     1234.56 "

    def test_z_dot_99_minus_negative(self):
        result = format_pic_z_dot_99_minus(Decimal("-42.10"), 9)
        assert result == "       42.10-"

    def test_z_dot_99_minus_zero(self):
        result = format_pic_z_dot_99_minus(Decimal("0.00"), 9)
        assert result == "        0.00 "

    def test_z_dot_99_minus_large(self):
        result = format_pic_z_dot_99_minus(Decimal("999999999.99"), 9)
        assert result == "999999999.99 "

    def test_line_widths(self):
        # PIC 9(9).99- total width = 9 + 1 + 2 + 1 = 13
        assert len(format_pic_9_dot_99_minus(Decimal("0"), 9)) == 13
        # PIC Z(9).99- total width = 9 + 1 + 2 + 1 = 13
        assert len(format_pic_z_dot_99_minus(Decimal("0"), 9)) == 13


# -----------------------------------------------------------------------
# Statement generation
# -----------------------------------------------------------------------

def _make_xref():
    return CardXrefRecord(
        xref_card_num=format_str("4111111111111111", 16),
        xref_cust_id="000000001",
        xref_acct_id="00000000099",
    )


def _make_customer():
    return CustomerRecord(
        cust_id="000000001",
        cust_first_name=format_str("John", 25),
        cust_middle_name=format_str("Q", 25),
        cust_last_name=format_str("Public", 25),
        cust_addr_line_1=format_str("123 Main Street", 50),
        cust_addr_line_2=format_str("Apt. 456", 50),
        cust_addr_line_3=format_str("Springfield", 50),
        cust_addr_state_cd="IL",
        cust_addr_country_cd="USA",
        cust_addr_zip=format_str("62701", 10),
        cust_phone_num_1=format_str("(555)123-4567", 15),
        cust_phone_num_2=format_str("", 15),
        cust_ssn="123456789",
        cust_govt_issued_id=format_str("", 20),
        cust_dob_yyyymmdd="1980-01-15",
        cust_eft_account_id=format_str("", 10),
        cust_pri_card_holder_ind="Y",
        cust_fico_credit_score="750",
    )


def _make_account():
    return AccountRecord(
        acct_id="00000000099",
        acct_active_status="Y",
        acct_curr_bal=Decimal("1500.75"),
        acct_credit_limit=Decimal("5000.00"),
        acct_cash_credit_limit=Decimal("2000.00"),
        acct_open_date="2020-01-01",
        acct_expiraion_date="2025-12-31",
        acct_reissue_date="2020-01-01",
        acct_curr_cyc_credit=Decimal("0.00"),
        acct_curr_cyc_debit=Decimal("0.00"),
        acct_addr_zip=format_str("62701", 10),
        acct_group_id=format_str("A000000000", 10),
    )


def _make_trnx(trnx_id="0000000000000001", desc="Test purchase",
               amt=Decimal("42.50")):
    return TrnxRecord(
        trnx_card_num=format_str("4111111111111111", 16),
        trnx_id=format_str(trnx_id, 16),
        trnx_type_cd="01",
        trnx_cat_cd="0001",
        trnx_source=format_str("POS TERM", 10),
        trnx_desc=format_str(desc, 100),
        trnx_amt=amt,
        trnx_merchant_id="000000001",
        trnx_merchant_name=format_str("Test Merchant", 50),
        trnx_merchant_city=format_str("Test City", 50),
        trnx_merchant_zip=format_str("12345", 10),
        trnx_orig_ts=format_str("2023-01-15 10:00:00.000000", 26),
        trnx_proc_ts=format_str("2023-01-15 10:00:00.000000", 26),
    )


class TestStatementGeneration:
    def test_text_line_widths_are_80(self):
        xref = _make_xref()
        cust = _make_customer()
        acct = _make_account()
        trnx = _make_trnx()
        text_lines, _ = generate_statement(xref, cust, acct, [trnx])

        for i, line in enumerate(text_lines):
            assert len(line) == 80, f"Line {i} has length {len(line)}: {line!r}"

    def test_start_and_end_markers(self):
        xref = _make_xref()
        cust = _make_customer()
        acct = _make_account()
        text_lines, _ = generate_statement(xref, cust, acct, [])

        assert "START OF STATEMENT" in text_lines[0]
        assert "END OF STATEMENT" in text_lines[-1]

    def test_customer_name_in_output(self):
        xref = _make_xref()
        cust = _make_customer()
        acct = _make_account()
        text_lines, _ = generate_statement(xref, cust, acct, [])

        name_line = text_lines[1]
        assert "John" in name_line
        assert "Public" in name_line

    def test_transaction_line_formatting(self):
        xref = _make_xref()
        cust = _make_customer()
        acct = _make_account()
        trnx = _make_trnx(amt=Decimal("123.45"))
        text_lines, _ = generate_statement(xref, cust, acct, [trnx])

        # Find transaction line (after header)
        tran_line = text_lines[16]  # First tran after header lines
        assert "$" in tran_line
        assert "123.45" in tran_line
        assert len(tran_line) == 80

    def test_total_line(self):
        xref = _make_xref()
        cust = _make_customer()
        acct = _make_account()
        t1 = _make_trnx(trnx_id="0000000000000001", amt=Decimal("100.00"))
        t2 = _make_trnx(trnx_id="0000000000000002", amt=Decimal("-25.50"))
        text_lines, _ = generate_statement(xref, cust, acct, [t1, t2])

        total_line = text_lines[-2]  # Before END OF STATEMENT
        assert "Total EXP:" in total_line
        assert "74.50" in total_line

    def test_html_generated(self):
        xref = _make_xref()
        cust = _make_customer()
        acct = _make_account()
        _, html_lines = generate_statement(xref, cust, acct, [])

        html_text = "\n".join(html_lines)
        assert "<!DOCTYPE html>" in html_text
        assert "</html>" in html_text
        assert "Basic Details" in html_text


# -----------------------------------------------------------------------
# Regression test against reference file
# -----------------------------------------------------------------------

class TestRegressionReference:
    def test_byte_for_byte_match(self):
        """Compare generated statement against committed reference file."""
        ref_path = os.path.join(
            os.path.dirname(__file__), "reference", "statement_reference.txt")

        xref = _make_xref()
        cust = _make_customer()
        acct = _make_account()
        transactions = [
            _make_trnx("0000000000000001", "Purchase at Store A", Decimal("42.50")),
            _make_trnx("0000000000000002", "Online payment", Decimal("199.99")),
            _make_trnx("0000000000000003", "Return item", Decimal("-15.00")),
        ]

        text_lines, _ = generate_statement(xref, cust, acct, transactions)
        generated = "\n".join(text_lines) + "\n"

        assert os.path.exists(ref_path), (
            f"Reference file not found: {ref_path}")
        with open(ref_path, "r") as f:
            expected = f.read()

        assert generated == expected, (
            "Generated statement does not match reference.\n"
            f"Generated:\n{generated}\n\nExpected:\n{expected}")
