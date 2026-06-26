"""CVACT01Y — ACCOUNT-RECORD (300 bytes).

COBOL layout::

    01  ACCOUNT-RECORD.
        05  ACCT-ID                           PIC 9(11).
        05  ACCT-ACTIVE-STATUS                PIC X(01).
        05  ACCT-CURR-BAL                     PIC S9(10)V99.
        05  ACCT-CREDIT-LIMIT                 PIC S9(10)V99.
        05  ACCT-CASH-CREDIT-LIMIT            PIC S9(10)V99.
        05  ACCT-OPEN-DATE                    PIC X(10).
        05  ACCT-EXPIRAION-DATE               PIC X(10).
        05  ACCT-REISSUE-DATE                 PIC X(10).
        05  ACCT-CURR-CYC-CREDIT              PIC S9(10)V99.
        05  ACCT-CURR-CYC-DEBIT               PIC S9(10)V99.
        05  ACCT-ADDR-ZIP                     PIC X(10).
        05  ACCT-GROUP-ID                     PIC X(10).
        05  FILLER                            PIC X(178).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from carddemo.codec import (
    decode_alphanumeric,
    decode_signed_numeric,
    decode_unsigned_numeric,
    encode_alphanumeric,
    encode_signed_numeric,
    encode_unsigned_numeric,
)

RECORD_LENGTH = 300

# Field offsets and widths (0-based)
_FIELDS = [
    # (name, offset, width)
    ("acct_id", 0, 11),
    ("acct_active_status", 11, 1),
    ("acct_curr_bal", 12, 12),
    ("acct_credit_limit", 24, 12),
    ("acct_cash_credit_limit", 36, 12),
    ("acct_open_date", 48, 10),
    ("acct_expiration_date", 58, 10),
    ("acct_reissue_date", 68, 10),
    ("acct_curr_cyc_credit", 78, 12),
    ("acct_curr_cyc_debit", 90, 12),
    ("acct_addr_zip", 102, 10),
    ("acct_group_id", 112, 10),
    # FILLER starts at 122, width 178
]


@dataclass
class AccountRecord:
    """CVACT01Y — ACCOUNT-RECORD (300 bytes)."""

    acct_id: int = 0                                        # PIC 9(11)
    acct_active_status: str = ""                            # PIC X(01)
    acct_curr_bal: Decimal = field(default_factory=lambda: Decimal("0.00"))
    acct_credit_limit: Decimal = field(default_factory=lambda: Decimal("0.00"))
    acct_cash_credit_limit: Decimal = field(default_factory=lambda: Decimal("0.00"))
    acct_open_date: str = ""                                # PIC X(10)
    acct_expiration_date: str = ""                          # PIC X(10)
    acct_reissue_date: str = ""                             # PIC X(10)
    acct_curr_cyc_credit: Decimal = field(default_factory=lambda: Decimal("0.00"))
    acct_curr_cyc_debit: Decimal = field(default_factory=lambda: Decimal("0.00"))
    acct_addr_zip: str = ""                                 # PIC X(10)
    acct_group_id: str = ""                                 # PIC X(10)

    @classmethod
    def from_record(cls, line: str) -> AccountRecord:
        """Parse a fixed-width record line into an ``AccountRecord``."""
        padded = line.ljust(RECORD_LENGTH)
        return cls(
            acct_id=decode_unsigned_numeric(padded[0:11]),
            acct_active_status=decode_alphanumeric(padded[11:12]),
            acct_curr_bal=decode_signed_numeric(padded[12:24], 2),
            acct_credit_limit=decode_signed_numeric(padded[24:36], 2),
            acct_cash_credit_limit=decode_signed_numeric(padded[36:48], 2),
            acct_open_date=decode_alphanumeric(padded[48:58]),
            acct_expiration_date=decode_alphanumeric(padded[58:68]),
            acct_reissue_date=decode_alphanumeric(padded[68:78]),
            acct_curr_cyc_credit=decode_signed_numeric(padded[78:90], 2),
            acct_curr_cyc_debit=decode_signed_numeric(padded[90:102], 2),
            acct_addr_zip=decode_alphanumeric(padded[102:112]),
            acct_group_id=decode_alphanumeric(padded[112:122]),
        )

    def to_record(self) -> str:
        """Serialize to a 300-character fixed-width line."""
        parts = [
            encode_unsigned_numeric(self.acct_id, 11),
            encode_alphanumeric(self.acct_active_status, 1),
            encode_signed_numeric(self.acct_curr_bal, 12, 2),
            encode_signed_numeric(self.acct_credit_limit, 12, 2),
            encode_signed_numeric(self.acct_cash_credit_limit, 12, 2),
            encode_alphanumeric(self.acct_open_date, 10),
            encode_alphanumeric(self.acct_expiration_date, 10),
            encode_alphanumeric(self.acct_reissue_date, 10),
            encode_signed_numeric(self.acct_curr_cyc_credit, 12, 2),
            encode_signed_numeric(self.acct_curr_cyc_debit, 12, 2),
            encode_alphanumeric(self.acct_addr_zip, 10),
            encode_alphanumeric(self.acct_group_id, 10),
        ]
        data = "".join(parts)
        return data.ljust(RECORD_LENGTH)
