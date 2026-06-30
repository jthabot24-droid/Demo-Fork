"""Tests for the fixed-width parser/writer module."""

from decimal import Decimal

from carddemo.fixed_width import (
    ACCOUNT_SPEC,
    CARD_SPEC,
    CARD_XREF_SPEC,
    CUSTOMER_SPEC,
    DAILY_TRANSACTION_SPEC,
    DISC_GROUP_SPEC,
    TRAN_CAT_BAL_SPEC,
    TRAN_CAT_SPEC,
    TRAN_TYPE_SPEC,
    USER_SECURITY_SPEC,
    _decode_signed,
    _encode_signed,
    parse_record,
    write_record,
)


class TestSignedDecimal:
    def test_positive_zero(self):
        assert _decode_signed("{", 0, 1) == Decimal("0.0")

    def test_positive_value(self):
        assert _decode_signed("00000001940{", 10, 2) == Decimal("194.00")

    def test_negative_value(self):
        assert _decode_signed("0000009190}", 9, 2) == Decimal("-919.00")

    def test_positive_g(self):
        assert _decode_signed("0000005047G", 9, 2) == Decimal("504.77")

    def test_negative_j(self):
        assert _decode_signed("0000001000J", 9, 2) == Decimal("-100.01")

    def test_encode_positive(self):
        encoded = _encode_signed(Decimal("194.00"), 10, 2)
        assert encoded == "00000001940{"

    def test_encode_negative(self):
        encoded = _encode_signed(Decimal("-919.00"), 9, 2)
        assert encoded == "0000009190}"

    def test_roundtrip(self):
        for val in [Decimal("0.00"), Decimal("123.45"), Decimal("-67.89"),
                    Decimal("999999999.99"), Decimal("-1.01")]:
            encoded = _encode_signed(val, 9, 2)
            decoded = _decode_signed(encoded, 9, 2)
            assert decoded == val, f"Roundtrip failed for {val}: {encoded} → {decoded}"


class TestParseRecord:
    def test_account_record(self):
        line = (
            "00000000001Y00000001940{00000020200{00000010200{"
            "2014-11-202025-05-202025-05-20"
            "00000000000{00000000000{A000000000"
        )
        rec = parse_record(line, ACCOUNT_SPEC)
        assert rec["acct_id"] == "00000000001"
        assert rec["acct_active_status"] == "Y"
        assert rec["acct_curr_bal"] == Decimal("194.00")
        assert rec["acct_credit_limit"] == Decimal("2020.00")
        assert rec["acct_cash_credit_limit"] == Decimal("1020.00")
        assert rec["acct_open_date"] == "2014-11-20"
        assert rec["acct_expiration_date"] == "2025-05-20"
        assert rec["acct_reissue_date"] == "2025-05-20"
        assert rec["acct_curr_cyc_credit"] == Decimal("0.00")
        assert rec["acct_curr_cyc_debit"] == Decimal("0.00")

    def test_card_xref_record(self):
        line = "050002445376574000000005000000000050"
        rec = parse_record(line, CARD_XREF_SPEC)
        assert rec["xref_card_num"].strip() == "0500024453765740"
        assert rec["xref_cust_id"] == "000000050"
        assert rec["xref_acct_id"] == "00000000050"

    def test_disc_group_record(self):
        line = "A00000000001000100150{0000000000000000000000000000"
        rec = parse_record(line, DISC_GROUP_SPEC)
        assert rec["dis_acct_group_id"] == "A000000000"
        assert rec["dis_tran_type_cd"] == "01"
        assert rec["dis_tran_cat_cd"] == "0001"
        assert rec["dis_int_rate"] == Decimal("15.00")

    def test_tran_cat_bal_record(self):
        line = "000000000010100010000000000{0000000000000000000000"
        rec = parse_record(line, TRAN_CAT_BAL_SPEC)
        assert rec["trancat_acct_id"] == "00000000001"
        assert rec["trancat_type_cd"] == "01"
        assert rec["trancat_cd"] == "0001"
        assert rec["tran_cat_bal"] == Decimal("0.00")

    def test_tran_type_record(self):
        line = "01Purchase                                          00000000"
        rec = parse_record(line, TRAN_TYPE_SPEC)
        assert rec["tran_type"] == "01"
        assert rec["tran_type_desc"].strip() == "Purchase"

    def test_tran_cat_record(self):
        line = "010001Regular Sales Draft                               0000"
        rec = parse_record(line, TRAN_CAT_SPEC)
        assert rec["tran_type_cd"] == "01"
        assert rec["tran_cat_cd"] == "0001"
        assert rec["tran_cat_type_desc"].strip() == "Regular Sales Draft"


class TestWriteRecord:
    def test_roundtrip_account(self):
        line = (
            "00000000001Y00000001940{00000020200{00000010200{"
            "2014-11-202025-05-202025-05-20"
            "00000000000{00000000000{A000000000"
        )
        rec = parse_record(line, ACCOUNT_SPEC)
        output = write_record(rec, ACCOUNT_SPEC)
        reparsed = parse_record(output, ACCOUNT_SPEC)
        for key in rec:
            assert rec[key] == reparsed[key], f"Mismatch on {key}"

    def test_roundtrip_daily_tran(self):
        line = (
            "0000000000683580010001POS TERM  "
            "Purchase at Abshire-Lowe"
            + " " * 76
            + "0000005047G800000000"
            + "Abshire-Lowe" + " " * 38
            + "North Enoshaven" + " " * 35
            + "72112     "
            + "48594526128770652022-06-10 19:27:53.000000"
            + " " * 46
        )
        rec = parse_record(line, DAILY_TRANSACTION_SPEC)
        assert rec["dalytran_amt"] == Decimal("504.77")
        output = write_record(rec, DAILY_TRANSACTION_SPEC)
        reparsed = parse_record(output, DAILY_TRANSACTION_SPEC)
        assert reparsed["dalytran_amt"] == Decimal("504.77")
