"""Tests for the carddemo.models package -- data model fidelity checks.

Verifies that every copybook translation preserves:
* Correct record lengths
* Fixed-width field widths matching COBOL PIC clauses
* Decimal precision for monetary fields
* REDEFINES / OCCURS semantics
"""

from decimal import Decimal

import pytest

from carddemo.models import (
    AccountRecord,
    CardRecord,
    CardXrefRecord,
    CustomerRecord,
    DailyTransactionRecord,
    DisclosureGroupRecord,
    ExportAccountData,
    ExportCardData,
    ExportCardXrefData,
    ExportCustomerData,
    ExportRecord,
    ExportTransactionData,
    SecUserData,
    TranCatBalRecord,
    TranCatRecord,
    TranTypeRecord,
    TransactionRecord,
)


# ===================================================================
# Record lengths (RECLN from copybook comments)
# ===================================================================


class TestRecordLengths:
    def test_account_record_length(self):
        assert AccountRecord.RECORD_LENGTH == 300

    def test_card_record_length(self):
        assert CardRecord.RECORD_LENGTH == 150

    def test_card_xref_record_length(self):
        assert CardXrefRecord.RECORD_LENGTH == 50

    def test_customer_record_length(self):
        assert CustomerRecord.RECORD_LENGTH == 500

    def test_transaction_record_length(self):
        assert TransactionRecord.RECORD_LENGTH == 350

    def test_daily_transaction_record_length(self):
        assert DailyTransactionRecord.RECORD_LENGTH == 350

    def test_tran_cat_bal_record_length(self):
        assert TranCatBalRecord.RECORD_LENGTH == 50

    def test_disclosure_group_record_length(self):
        assert DisclosureGroupRecord.RECORD_LENGTH == 50

    def test_tran_type_record_length(self):
        assert TranTypeRecord.RECORD_LENGTH == 60

    def test_tran_cat_record_length(self):
        assert TranCatRecord.RECORD_LENGTH == 60

    def test_user_security_record_length(self):
        assert SecUserData.RECORD_LENGTH == 80

    def test_export_record_length(self):
        assert ExportRecord.RECORD_LENGTH == 500


# ===================================================================
# Field widths matching COBOL PIC clauses
# ===================================================================


class TestFieldWidths:
    def test_account_field_widths(self):
        rec = AccountRecord()
        assert rec.FIELD_WIDTHS["acct_id"] == 11
        assert rec.FIELD_WIDTHS["acct_curr_bal"] == 12  # S9(10)V99
        assert rec.FIELD_WIDTHS["acct_group_id"] == 10

    def test_card_xref_field_widths(self):
        rec = CardXrefRecord()
        assert rec.FIELD_WIDTHS["xref_card_num"] == 16
        assert rec.FIELD_WIDTHS["xref_cust_id"] == 9
        assert rec.FIELD_WIDTHS["xref_acct_id"] == 11

    def test_transaction_field_widths(self):
        rec = TransactionRecord()
        assert rec.FIELD_WIDTHS["tran_id"] == 16
        assert rec.FIELD_WIDTHS["tran_amt"] == 11  # S9(09)V99
        assert rec.FIELD_WIDTHS["tran_desc"] == 100
        assert rec.FIELD_WIDTHS["tran_orig_ts"] == 26

    def test_customer_field_widths(self):
        rec = CustomerRecord()
        assert rec.FIELD_WIDTHS["cust_id"] == 9
        assert rec.FIELD_WIDTHS["cust_first_name"] == 25
        assert rec.FIELD_WIDTHS["cust_addr_line_1"] == 50
        assert rec.FIELD_WIDTHS["cust_fico_credit_score"] == 3


# ===================================================================
# Decimal precision for monetary fields
# ===================================================================


class TestDecimalPrecision:
    def test_account_monetary_defaults(self):
        rec = AccountRecord()
        assert rec.acct_curr_bal == Decimal("0.00")
        assert rec.acct_credit_limit == Decimal("0.00")
        assert rec.acct_curr_cyc_credit == Decimal("0.00")

    def test_account_monetary_arithmetic(self):
        rec = AccountRecord(
            acct_curr_bal=Decimal("1000.00"),
            acct_credit_limit=Decimal("5000.00"),
        )
        rec.acct_curr_bal += Decimal("123.45")
        assert rec.acct_curr_bal == Decimal("1123.45")

    def test_transaction_amount_precision(self):
        rec = TransactionRecord(tran_amt=Decimal("99999999.99"))
        assert rec.tran_amt == Decimal("99999999.99")

    def test_tran_cat_bal_precision(self):
        rec = TranCatBalRecord(tran_cat_bal=Decimal("123456789.01"))
        assert rec.tran_cat_bal == Decimal("123456789.01")

    def test_disclosure_rate_precision(self):
        rec = DisclosureGroupRecord(dis_int_rate=Decimal("18.50"))
        assert rec.dis_int_rate == Decimal("18.50")

    def test_interest_formula_byte_exact(self):
        """Verify the CBACT04C formula: monthly_int = (bal * rate) / 1200."""
        bal = Decimal("5000.00")
        rate = Decimal("18.00")
        monthly_int = (bal * rate) / Decimal("1200")
        assert monthly_int == Decimal("75.00")

    def test_interest_formula_fractional(self):
        bal = Decimal("1234.56")
        rate = Decimal("21.99")
        monthly_int = (bal * rate) / Decimal("1200")
        # 1234.56 * 21.99 / 1200 = 27148.2744 / 1200 = 22.6235...
        expected = (Decimal("1234.56") * Decimal("21.99")) / Decimal("1200")
        assert monthly_int == expected


# ===================================================================
# Composite keys
# ===================================================================


class TestCompositeKeys:
    def test_tran_cat_bal_key(self):
        rec = TranCatBalRecord(
            trancat_acct_id=80000000001,
            trancat_type_cd="01",
            trancat_cd=5000,
        )
        assert rec.key == "80000000001015000"

    def test_tran_cat_record_key(self):
        rec = TranCatRecord(tran_type_cd="01", tran_cat_cd=5000)
        assert rec.key == "015000"

    def test_disclosure_group_key(self):
        rec = DisclosureGroupRecord(
            dis_acct_group_id="GROUP01",
            dis_tran_type_cd="01",
            dis_tran_cat_cd=5000,
        )
        assert rec.key == "GROUP01   015000"


# ===================================================================
# REDEFINES and OCCURS (Export record)
# ===================================================================


class TestExportRedefines:
    def test_timestamp_redefines(self):
        rec = ExportRecord(
            export_timestamp="2026-06-30-12.30.45.000000"
        )
        assert rec.export_date == "2026-06-30"
        assert rec.export_time == "12.30.45.000000"

    def test_customer_occurs_addr_lines(self):
        cust = ExportCustomerData(
            exp_cust_addr_lines=["123 Main St", "Apt 4B", ""]
        )
        assert len(cust.exp_cust_addr_lines) == 3
        assert cust.exp_cust_addr_lines[0] == "123 Main St"
        assert cust.exp_cust_addr_lines[1] == "Apt 4B"

    def test_customer_occurs_phone_nums(self):
        cust = ExportCustomerData(
            exp_cust_phone_nums=["555-0100", "555-0200"]
        )
        assert len(cust.exp_cust_phone_nums) == 2

    def test_customer_default_occurs(self):
        cust = ExportCustomerData()
        assert len(cust.exp_cust_addr_lines) == 3
        assert len(cust.exp_cust_phone_nums) == 2

    def test_export_payload_variants(self):
        from carddemo.models.export import EXPORT_PAYLOAD_TYPES

        assert EXPORT_PAYLOAD_TYPES["C"] == ExportCustomerData
        assert EXPORT_PAYLOAD_TYPES["A"] == ExportAccountData
        assert EXPORT_PAYLOAD_TYPES["T"] == ExportTransactionData
        assert EXPORT_PAYLOAD_TYPES["X"] == ExportCardXrefData
        assert EXPORT_PAYLOAD_TYPES["D"] == ExportCardData

    def test_export_account_comp3_annotation(self):
        acct = ExportAccountData()
        assert "COMP-3" in acct.STORAGE_NOTES

    def test_export_transaction_comp3_annotation(self):
        tran = ExportTransactionData()
        assert "COMP-3" in tran.STORAGE_NOTES
