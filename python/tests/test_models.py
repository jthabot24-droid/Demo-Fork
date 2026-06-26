"""Tests for Phase 1 copybook record models.

Verifies that ``from_record`` correctly parses each ASCII sample-data file and
that ``to_record`` round-trips back to the original fixed-width line.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from carddemo.models.account import AccountRecord
from carddemo.models.card_xref import CardXrefRecord
from carddemo.models.customer import CustomerRecord
from carddemo.models.daily_transaction import DailyTransactionRecord
from carddemo.models.transaction import TransactionRecord


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_lines(filepath: Path) -> list[str]:
    """Read all non-empty lines from a fixed-width file."""
    lines = []
    with open(filepath, "r", encoding="ascii", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n").rstrip("\r")
            if line:
                lines.append(line)
    return lines


# ---------------------------------------------------------------------------
# CVACT01Y — AccountRecord
# ---------------------------------------------------------------------------

class TestAccountRecord:
    def test_parse_first_record(self, ascii_data_dir: Path) -> None:
        lines = _read_lines(ascii_data_dir / "acctdata.txt")
        rec = AccountRecord.from_record(lines[0])
        assert rec.acct_id == 1
        assert rec.acct_active_status == "Y"
        assert rec.acct_curr_bal == Decimal("194.00")
        assert rec.acct_credit_limit == Decimal("2020.00")
        assert rec.acct_cash_credit_limit == Decimal("1020.00")
        assert rec.acct_open_date == "2014-11-20"
        assert rec.acct_expiration_date == "2025-05-20"
        assert rec.acct_reissue_date == "2025-05-20"
        assert rec.acct_curr_cyc_credit == Decimal("0.00")
        assert rec.acct_curr_cyc_debit == Decimal("0.00")

    def test_round_trip_all_records(self, ascii_data_dir: Path) -> None:
        lines = _read_lines(ascii_data_dir / "acctdata.txt")
        for i, line in enumerate(lines):
            rec = AccountRecord.from_record(line)
            serialized = rec.to_record()
            # The original line, padded to record length, should match
            padded = line.ljust(300)
            assert serialized == padded, (
                f"Round-trip mismatch on line {i}: "
                f"expected={padded!r}, got={serialized!r}"
            )

    def test_parse_all_records(self, ascii_data_dir: Path) -> None:
        lines = _read_lines(ascii_data_dir / "acctdata.txt")
        assert len(lines) == 50
        for line in lines:
            rec = AccountRecord.from_record(line)
            assert rec.acct_id > 0


# ---------------------------------------------------------------------------
# CVACT03Y — CardXrefRecord
# ---------------------------------------------------------------------------

class TestCardXrefRecord:
    def test_parse_first_record(self, ascii_data_dir: Path) -> None:
        lines = _read_lines(ascii_data_dir / "cardxref.txt")
        rec = CardXrefRecord.from_record(lines[0])
        assert len(rec.xref_card_num) > 0
        assert rec.xref_cust_id > 0
        assert rec.xref_acct_id > 0

    def test_round_trip_all_records(self, ascii_data_dir: Path) -> None:
        lines = _read_lines(ascii_data_dir / "cardxref.txt")
        for i, line in enumerate(lines):
            rec = CardXrefRecord.from_record(line)
            serialized = rec.to_record()
            padded = line.ljust(50)
            assert serialized == padded, (
                f"Round-trip mismatch on line {i}: "
                f"expected={padded!r}, got={serialized!r}"
            )

    def test_parse_all_records(self, ascii_data_dir: Path) -> None:
        lines = _read_lines(ascii_data_dir / "cardxref.txt")
        assert len(lines) == 50
        for line in lines:
            rec = CardXrefRecord.from_record(line)
            assert rec.xref_acct_id > 0


# ---------------------------------------------------------------------------
# CVCUS01Y — CustomerRecord
# ---------------------------------------------------------------------------

class TestCustomerRecord:
    def test_parse_first_record(self, ascii_data_dir: Path) -> None:
        lines = _read_lines(ascii_data_dir / "custdata.txt")
        rec = CustomerRecord.from_record(lines[0])
        assert rec.cust_id == 1
        assert rec.cust_first_name.strip() != ""
        assert rec.cust_last_name.strip() != ""

    def test_round_trip_all_records(self, ascii_data_dir: Path) -> None:
        lines = _read_lines(ascii_data_dir / "custdata.txt")
        for i, line in enumerate(lines):
            rec = CustomerRecord.from_record(line)
            serialized = rec.to_record()
            padded = line.ljust(500)
            assert serialized == padded, (
                f"Round-trip mismatch on line {i}: "
                f"expected={padded!r}, got={serialized!r}"
            )

    def test_parse_all_records(self, ascii_data_dir: Path) -> None:
        lines = _read_lines(ascii_data_dir / "custdata.txt")
        assert len(lines) == 50
        for line in lines:
            rec = CustomerRecord.from_record(line)
            assert rec.cust_id > 0


# ---------------------------------------------------------------------------
# CVTRA06Y — DailyTransactionRecord
# ---------------------------------------------------------------------------

class TestDailyTransactionRecord:
    def test_parse_first_record(self, ascii_data_dir: Path) -> None:
        lines = _read_lines(ascii_data_dir / "dailytran.txt")
        rec = DailyTransactionRecord.from_record(lines[0])
        assert rec.dalytran_id.strip() != ""
        assert rec.dalytran_type_cd.strip() != ""
        assert isinstance(rec.dalytran_amt, Decimal)

    def test_round_trip_all_records(self, ascii_data_dir: Path) -> None:
        lines = _read_lines(ascii_data_dir / "dailytran.txt")
        for i, line in enumerate(lines):
            rec = DailyTransactionRecord.from_record(line)
            serialized = rec.to_record()
            padded = line.ljust(350)
            assert serialized == padded, (
                f"Round-trip mismatch on line {i}: "
                f"expected={padded!r}, got={serialized!r}"
            )

    def test_parse_all_records(self, ascii_data_dir: Path) -> None:
        lines = _read_lines(ascii_data_dir / "dailytran.txt")
        assert len(lines) == 300
        for line in lines:
            rec = DailyTransactionRecord.from_record(line)
            assert isinstance(rec.dalytran_amt, Decimal)


# ---------------------------------------------------------------------------
# Codec round-trip for signed numerics
# ---------------------------------------------------------------------------

class TestSignedNumericCodec:
    def test_positive_zero(self) -> None:
        from carddemo.codec import decode_signed_numeric, encode_signed_numeric
        raw = "00000000000{"
        val = decode_signed_numeric(raw, 2)
        assert val == Decimal("0.00")
        assert encode_signed_numeric(val, 12, 2) == raw

    def test_positive_value(self) -> None:
        from carddemo.codec import decode_signed_numeric, encode_signed_numeric
        raw = "00000001940{"
        val = decode_signed_numeric(raw, 2)
        assert val == Decimal("194.00")
        assert encode_signed_numeric(val, 12, 2) == raw

    def test_negative_value(self) -> None:
        from carddemo.codec import decode_signed_numeric, encode_signed_numeric
        raw = "0000009190}"
        val = decode_signed_numeric(raw, 2)
        assert val == Decimal("-919.00")
        assert encode_signed_numeric(val, 11, 2) == raw

    def test_positive_nonzero_last_digit(self) -> None:
        from carddemo.codec import decode_signed_numeric, encode_signed_numeric
        raw = "0000005047G"
        val = decode_signed_numeric(raw, 2)
        assert val == Decimal("504.77")
        assert encode_signed_numeric(val, 11, 2) == raw

    def test_negative_nonzero_last_digit(self) -> None:
        from carddemo.codec import decode_signed_numeric, encode_signed_numeric
        raw = "0000005047P"
        val = decode_signed_numeric(raw, 2)
        assert val == Decimal("-504.77")
        assert encode_signed_numeric(val, 11, 2) == raw
