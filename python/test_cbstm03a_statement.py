"""
Regression tests for the CBSTM03A statement-generation migration.

The tests exercise the full pipeline -- from CSV fixture files through
statement generation -- and compare the output **byte-for-byte** against
committed reference files.

Reference files
---------------
* ``reference/expected_statement.txt``  -- plain-text, 80-byte records
* ``reference/expected_statement.html`` -- HTML, 100-byte records

These were generated from a trusted initial run of the migrated Python
code on the fixture data in ``fixtures/``.  To regenerate them after a
*legitimate* change to the output format::

    cd python/
    python cbstm03a_statement.py \\
        fixtures/trnx.csv fixtures/xref.csv \\
        fixtures/cust.csv fixtures/acct.csv \\
        reference/expected_statement.txt \\
        reference/expected_statement.html

Then commit the updated reference files.

Fixture data
------------
* ``fixtures/trnx.csv``  -- 3 transactions across 2 cards
* ``fixtures/xref.csv``  -- 2 card-to-customer/account cross-references
* ``fixtures/cust.csv``  -- 2 customers
* ``fixtures/acct.csv``  -- 2 accounts
"""

from __future__ import annotations

import os
import tempfile
from decimal import Decimal
from pathlib import Path

import pandas as pd
import pytest

from cbstm03a_statement import (
    StatementWriter,
    _build_cobol_string,
    _build_st_line0,
    _build_st_line14,
    _build_st_line14a,
    _build_st_line15,
    _build_st_line5,
    _build_st_name,
    _format_pic_9_9_dot_99_minus,
    _format_pic_z_9_dot_99_minus,
    _string_delimited_by,
    generate_statements,
    generate_statements_from_csv,
)
from cbstm03b_io import (
    AccountRecord,
    CustomerRecord,
    FileManager,
    TransactionRecord,
    VsamKeyedFile,
    VsamSequentialFile,
    XrefRecord,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_HERE = Path(__file__).resolve().parent
_FIXTURES = _HERE / "fixtures"
_REFERENCE = _HERE / "reference"


# ---------------------------------------------------------------------------
# Unit tests: numeric formatting
# ---------------------------------------------------------------------------


class TestPic9_9Dot99Minus:
    """PIC 9(9).99- formatting (Current Balance)."""

    def test_positive_value(self):
        assert _format_pic_9_9_dot_99_minus(Decimal("1250.75")) == "000001250.75 "

    def test_negative_value(self):
        assert _format_pic_9_9_dot_99_minus(Decimal("-1250.75")) == "000001250.75-"

    def test_zero(self):
        assert _format_pic_9_9_dot_99_minus(Decimal("0")) == "000000000.00 "

    def test_large_value(self):
        assert _format_pic_9_9_dot_99_minus(Decimal("999999999.99")) == "999999999.99 "

    def test_width(self):
        assert len(_format_pic_9_9_dot_99_minus(Decimal("1.23"))) == 13


class TestPicZ9Dot99Minus:
    """PIC Z(9).99- formatting (Transaction Amount, Total)."""

    def test_positive_value(self):
        assert _format_pic_z_9_dot_99_minus(Decimal("25.50")) == "       25.50 "

    def test_negative_value(self):
        assert _format_pic_z_9_dot_99_minus(Decimal("-45.75")) == "       45.75-"

    def test_zero(self):
        assert _format_pic_z_9_dot_99_minus(Decimal("0")) == "         .00 "

    def test_large_value(self):
        assert _format_pic_z_9_dot_99_minus(Decimal("199.99")) == "      199.99 "

    def test_width(self):
        assert len(_format_pic_z_9_dot_99_minus(Decimal("1.00"))) == 13


# ---------------------------------------------------------------------------
# Unit tests: COBOL STRING DELIMITED BY
# ---------------------------------------------------------------------------


class TestStringDelimitedBy:

    def test_delimiter_found(self):
        assert _string_delimited_by("John Smith  ", "  ") == "John Smith"

    def test_delimiter_not_found(self):
        assert _string_delimited_by("NoDelim", "  ") == "NoDelim"

    def test_single_space(self):
        assert _string_delimited_by("Hello World", " ") == "Hello"

    def test_empty_source(self):
        assert _string_delimited_by("", " ") == ""


class TestBuildCobolString:

    def test_basic_concat(self):
        result = _build_cobol_string(
            ("<p>", "*"),
            ("Hello World  ", "  "),
            ("  ", None),
            ("</p>", "*"),
        )
        assert result == "<p>Hello World  </p>"

    def test_delimited_by_size(self):
        result = _build_cobol_string(
            ("ABC", None),
            ("DEF", None),
        )
        assert result == "ABCDEF"


# ---------------------------------------------------------------------------
# Unit tests: statement line builders
# ---------------------------------------------------------------------------


class TestStatementLines:

    def test_line0_width(self):
        assert len(_build_st_line0()) == 80

    def test_line0_content(self):
        line = _build_st_line0()
        assert line.startswith("*" * 31)
        assert "START OF STATEMENT" in line
        assert line.endswith("*" * 31)

    def test_line5_width(self):
        assert len(_build_st_line5()) == 80

    def test_line5_all_dashes(self):
        assert _build_st_line5() == "-" * 80

    def test_line14_width(self):
        line = _build_st_line14("ID123", "Desc", Decimal("10.00"))
        assert len(line) == 80

    def test_line14a_width(self):
        line = _build_st_line14a(Decimal("100.00"))
        assert len(line) == 80

    def test_line15_width(self):
        assert len(_build_st_line15()) == 80

    def test_line15_content(self):
        line = _build_st_line15()
        assert "END OF STATEMENT" in line


class TestBuildStName:

    def test_full_name(self):
        cust = CustomerRecord(
            cust_first_name="John",
            cust_middle_name="M",
            cust_last_name="Smith",
        )
        name = _build_st_name(cust)
        assert name.startswith("John M Smith ")
        assert len(name) == 75


# ---------------------------------------------------------------------------
# Unit tests: I/O layer (cbstm03b_io)
# ---------------------------------------------------------------------------


class TestVsamSequentialFile:

    def test_read_all(self):
        df = pd.DataFrame([
            {"xref_card_num": "1111", "xref_cust_id": "1", "xref_acct_id": "1"},
            {"xref_card_num": "2222", "xref_cust_id": "2", "xref_acct_id": "2"},
        ])
        from cbstm03b_io import _row_to_xref

        vsam = VsamSequentialFile(df, _row_to_xref)
        vsam.open()
        rc1, rec1 = vsam.read()
        rc2, rec2 = vsam.read()
        rc3, rec3 = vsam.read()
        vsam.close()

        assert rc1 == "00"
        assert rec1.xref_card_num == "1111"
        assert rc2 == "00"
        assert rec2.xref_card_num == "2222"
        assert rc3 == "10"
        assert rec3 is None


class TestVsamKeyedFile:

    def test_read_by_key(self):
        df = pd.DataFrame([
            {"cust_id": "100", "cust_first_name": "Alice"},
            {"cust_id": "200", "cust_first_name": "Bob"},
        ])
        from cbstm03b_io import _row_to_customer

        vsam = VsamKeyedFile(df, "cust_id", _row_to_customer)
        vsam.open()

        rc, rec = vsam.read_by_key("200")
        assert rc == "00"
        assert rec.cust_first_name == "Bob"

        rc, rec = vsam.read_by_key("999")
        assert rc == "99"
        assert rec is None

        vsam.close()


# ---------------------------------------------------------------------------
# Integration: full statement generation via CSV fixtures
# ---------------------------------------------------------------------------


class TestFullStatementGenerationCSV:
    """Run the full pipeline from CSV fixtures and compare byte-for-byte."""

    def test_plaintext_output_matches_reference(self, tmp_path):
        stmt_out = str(tmp_path / "statement.txt")
        html_out = str(tmp_path / "statement.html")

        generate_statements_from_csv(
            str(_FIXTURES / "trnx.csv"),
            str(_FIXTURES / "xref.csv"),
            str(_FIXTURES / "cust.csv"),
            str(_FIXTURES / "acct.csv"),
            stmt_out,
            html_out,
        )

        expected = (_REFERENCE / "expected_statement.txt").read_text()
        actual = Path(stmt_out).read_text()
        assert actual == expected, (
            "Plain-text statement output does not match reference file. "
            "If the change is intentional, regenerate the reference with:\n"
            "  python cbstm03a_statement.py fixtures/trnx.csv fixtures/xref.csv "
            "fixtures/cust.csv fixtures/acct.csv "
            "reference/expected_statement.txt reference/expected_statement.html"
        )

    def test_html_output_matches_reference(self, tmp_path):
        stmt_out = str(tmp_path / "statement.txt")
        html_out = str(tmp_path / "statement.html")

        generate_statements_from_csv(
            str(_FIXTURES / "trnx.csv"),
            str(_FIXTURES / "xref.csv"),
            str(_FIXTURES / "cust.csv"),
            str(_FIXTURES / "acct.csv"),
            stmt_out,
            html_out,
        )

        expected = (_REFERENCE / "expected_statement.html").read_text()
        actual = Path(html_out).read_text()
        assert actual == expected, (
            "HTML statement output does not match reference file. "
            "If the change is intentional, regenerate the reference with:\n"
            "  python cbstm03a_statement.py fixtures/trnx.csv fixtures/xref.csv "
            "fixtures/cust.csv fixtures/acct.csv "
            "reference/expected_statement.txt reference/expected_statement.html"
        )


# ---------------------------------------------------------------------------
# Integration: full statement generation via DataFrames
# ---------------------------------------------------------------------------


class TestFullStatementGenerationDataFrame:
    """Run the full pipeline from in-memory DataFrames."""

    @pytest.fixture()
    def file_mgr(self) -> FileManager:
        trnx_df = pd.DataFrame([
            {
                "trnx_card_num": "4111111111111111",
                "trnx_id": "0000000000000001",
                "trnx_type_cd": "01",
                "trnx_cat_cd": "5000",
                "trnx_source": "ONLINE",
                "trnx_desc": "Grocery Store Purchase",
                "trnx_amt": "25.50",
                "trnx_merchant_id": "100000001",
                "trnx_merchant_name": "FreshMart",
                "trnx_merchant_city": "Seattle",
                "trnx_merchant_zip": "98101",
                "trnx_orig_ts": "2026-06-10-10.30.00.000000",
                "trnx_proc_ts": "2026-06-10-10.30.00.000000",
            },
            {
                "trnx_card_num": "4111111111111111",
                "trnx_id": "0000000000000002",
                "trnx_type_cd": "01",
                "trnx_cat_cd": "5000",
                "trnx_source": "ONLINE",
                "trnx_desc": "Gas Station",
                "trnx_amt": "-45.75",
                "trnx_merchant_id": "100000002",
                "trnx_merchant_name": "QuickFuel",
                "trnx_merchant_city": "Portland",
                "trnx_merchant_zip": "97201",
                "trnx_orig_ts": "2026-06-11-14.15.00.000000",
                "trnx_proc_ts": "2026-06-11-14.15.00.000000",
            },
        ])
        xref_df = pd.DataFrame([
            {
                "xref_card_num": "4111111111111111",
                "xref_cust_id": "100000001",
                "xref_acct_id": "80000000001",
            },
        ])
        cust_df = pd.DataFrame([
            {
                "cust_id": "100000001",
                "cust_first_name": "John",
                "cust_middle_name": "M",
                "cust_last_name": "Smith",
                "cust_addr_line_1": "123 Main Street",
                "cust_addr_line_2": "Apt 4B",
                "cust_addr_line_3": "Seattle",
                "cust_addr_state_cd": "WA",
                "cust_addr_country_cd": "US",
                "cust_addr_zip": "98101",
                "cust_fico_credit_score": "750",
            },
        ])
        acct_df = pd.DataFrame([
            {
                "acct_id": "80000000001",
                "acct_active_status": "Y",
                "acct_curr_bal": "1250.75",
                "acct_credit_limit": "5000.00",
                "acct_cash_credit_limit": "1000.00",
                "acct_open_date": "2020-01-15",
                "acct_expiration_date": "2027-12-31",
                "acct_reissue_date": "2025-01-15",
                "acct_curr_cyc_credit": "1000.00",
                "acct_curr_cyc_debit": "200.00",
                "acct_addr_zip": "98101",
                "acct_group_id": "GRP001",
            },
        ])
        return FileManager(trnx_df, xref_df, cust_df, acct_df)

    def test_single_account_statement(self, file_mgr, tmp_path):
        stmt_out = str(tmp_path / "stmt.txt")
        html_out = str(tmp_path / "stmt.html")
        generate_statements(file_mgr, stmt_out, html_out)

        stmt = Path(stmt_out).read_text()
        lines = stmt.strip().split("\n")

        assert lines[0] == _build_st_line0()
        assert "John M Smith" in lines[1]
        assert "80000000001" in lines[8]
        assert "000001250.75" in lines[9]
        assert "END OF STATEMENT" in lines[-1]

        for line in lines:
            assert len(line) == 80, f"Bad width: {len(line)}"

    def test_total_is_sum_of_transactions(self, file_mgr, tmp_path):
        stmt_out = str(tmp_path / "stmt.txt")
        html_out = str(tmp_path / "stmt.html")
        generate_statements(file_mgr, stmt_out, html_out)

        stmt = Path(stmt_out).read_text()
        for line in stmt.split("\n"):
            if line.startswith("Total EXP:"):
                assert "20.25-" in line
                break
        else:
            pytest.fail("Total EXP: line not found")

    def test_html_record_width(self, file_mgr, tmp_path):
        stmt_out = str(tmp_path / "stmt.txt")
        html_out = str(tmp_path / "stmt.html")
        generate_statements(file_mgr, stmt_out, html_out)

        html = Path(html_out).read_text()
        for i, line in enumerate(html.rstrip("\n").split("\n"), 1):
            assert len(line) == 100, f"HTML line {i} bad width: {len(line)}"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:

    def test_no_transactions_for_card(self, tmp_path):
        """Card in XREF but no matching transactions produces a statement
        with zero total."""
        trnx_df = pd.DataFrame(
            columns=[
                "trnx_card_num", "trnx_id", "trnx_type_cd", "trnx_cat_cd",
                "trnx_source", "trnx_desc", "trnx_amt", "trnx_merchant_id",
                "trnx_merchant_name", "trnx_merchant_city", "trnx_merchant_zip",
                "trnx_orig_ts", "trnx_proc_ts",
            ]
        )
        xref_df = pd.DataFrame([{
            "xref_card_num": "4111111111111111",
            "xref_cust_id": "100000001",
            "xref_acct_id": "80000000001",
        }])
        cust_df = pd.DataFrame([{
            "cust_id": "100000001",
            "cust_first_name": "Alice",
            "cust_middle_name": "",
            "cust_last_name": "Wonder",
            "cust_addr_line_1": "1 Street",
            "cust_addr_line_2": "",
            "cust_addr_line_3": "Town",
            "cust_addr_state_cd": "CA",
            "cust_addr_country_cd": "US",
            "cust_addr_zip": "90210",
            "cust_fico_credit_score": "800",
        }])
        acct_df = pd.DataFrame([{
            "acct_id": "80000000001",
            "acct_curr_bal": "0.00",
        }])

        fm = FileManager(trnx_df, xref_df, cust_df, acct_df)
        stmt_out = str(tmp_path / "stmt.txt")
        html_out = str(tmp_path / "stmt.html")
        generate_statements(fm, stmt_out, html_out)

        stmt = Path(stmt_out).read_text()
        assert "START OF STATEMENT" in stmt
        assert "END OF STATEMENT" in stmt
        for line in stmt.split("\n"):
            if line.startswith("Total EXP:"):
                assert ".00 " in line
                break

    def test_negative_balance_formatting(self):
        assert _format_pic_9_9_dot_99_minus(Decimal("-9999.99")) == "000009999.99-"
        assert _format_pic_z_9_dot_99_minus(Decimal("-9999.99")) == "     9999.99-"

    def test_error_on_missing_customer(self, tmp_path):
        xref_df = pd.DataFrame([{
            "xref_card_num": "1111",
            "xref_cust_id": "999",
            "xref_acct_id": "111",
        }])
        cust_df = pd.DataFrame(columns=["cust_id"])
        acct_df = pd.DataFrame(columns=["acct_id"])
        trnx_df = pd.DataFrame(
            columns=[
                "trnx_card_num", "trnx_id", "trnx_type_cd", "trnx_cat_cd",
                "trnx_source", "trnx_desc", "trnx_amt", "trnx_merchant_id",
                "trnx_merchant_name", "trnx_merchant_city", "trnx_merchant_zip",
                "trnx_orig_ts", "trnx_proc_ts",
            ]
        )

        fm = FileManager(trnx_df, xref_df, cust_df, acct_df)
        with pytest.raises(RuntimeError, match="ERROR READING CUSTFILE"):
            generate_statements(
                fm, str(tmp_path / "s.txt"), str(tmp_path / "s.html")
            )
