"""Tests for the fixed-width ASCII data parser (Phase 0)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from data.seed import _decode_signed_decimal, parse_fixed_width, ACCOUNT_FIELDS


class TestOverpunchDecoder:
    """Verify zoned-decimal overpunch decoding matches COBOL DISPLAY format."""

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("00000001940{", Decimal("194.00")),
            ("00000020200{", Decimal("2020.00")),
            ("00000010200{", Decimal("1020.00")),
            ("00000000000{", Decimal("0.00")),
            ("00000001940}", Decimal("-194.00")),
            ("0000001940J", Decimal("-194.01")),
            ("0000001940A", Decimal("194.01")),
            ("0000000100I", Decimal("10.09")),
            ("0000000100R", Decimal("-10.09")),
        ],
    )
    def test_decode(self, raw: str, expected: Decimal) -> None:
        assert _decode_signed_decimal(raw) == expected

    def test_empty_string(self) -> None:
        assert _decode_signed_decimal("") == Decimal("0.00")

    def test_spaces(self) -> None:
        assert _decode_signed_decimal("            ") == Decimal("0.00")


class TestParseFixedWidth:
    """Verify fixed-width record parsing."""

    def test_account_record(self) -> None:
        raw = (
            "00000000001"           # acct_id (11)
            "Y"                     # acct_active_status (1)
            "00000001940{"          # acct_curr_bal (12)
            "00000020200{"          # acct_credit_limit (12)
            "00000010200{"          # acct_cash_credit_limit (12)
            "2014-11-20"            # acct_open_date (10)
            "2025-05-20"            # acct_expiration_date (10)
            "2025-05-20"            # acct_reissue_date (10)
            "00000000000{"          # acct_curr_cyc_credit (12)
            "00000000000{"          # acct_curr_cyc_debit (12)
            "A000000000"            # acct_addr_zip (10)  [note: this is intentional test data]
            "A000000000"            # acct_group_id (10)
        )
        raw = raw.ljust(300)

        result = parse_fixed_width(raw, ACCOUNT_FIELDS)
        assert result["acct_id"] == 1
        assert result["acct_active_status"] == "Y"
        assert result["acct_curr_bal"] == Decimal("194.00")
        assert result["acct_credit_limit"] == Decimal("2020.00")
        assert result["acct_cash_credit_limit"] == Decimal("1020.00")
        assert result["acct_open_date"] == "2014-11-20"
        assert result["acct_expiration_date"] == "2025-05-20"
        assert result["acct_curr_cyc_credit"] == Decimal("0.00")
        assert result["acct_group_id"] == "A000000000"
