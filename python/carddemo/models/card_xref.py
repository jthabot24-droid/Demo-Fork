"""CVACT03Y — CARD-XREF-RECORD (50 bytes).

COBOL layout::

    01 CARD-XREF-RECORD.
        05  XREF-CARD-NUM                     PIC X(16).
        05  XREF-CUST-ID                      PIC 9(09).
        05  XREF-ACCT-ID                      PIC 9(11).
        05  FILLER                            PIC X(14).
"""

from __future__ import annotations

from dataclasses import dataclass

from carddemo.codec import (
    decode_alphanumeric,
    decode_unsigned_numeric,
    encode_alphanumeric,
    encode_unsigned_numeric,
)

RECORD_LENGTH = 50


@dataclass
class CardXrefRecord:
    """CVACT03Y — CARD-XREF-RECORD (50 bytes)."""

    xref_card_num: str = ""   # PIC X(16)
    xref_cust_id: int = 0    # PIC 9(09)
    xref_acct_id: int = 0    # PIC 9(11)

    @classmethod
    def from_record(cls, line: str) -> CardXrefRecord:
        """Parse a fixed-width record line."""
        padded = line.ljust(RECORD_LENGTH)
        return cls(
            xref_card_num=decode_alphanumeric(padded[0:16]),
            xref_cust_id=decode_unsigned_numeric(padded[16:25]),
            xref_acct_id=decode_unsigned_numeric(padded[25:36]),
        )

    def to_record(self) -> str:
        """Serialize to a 50-character fixed-width line."""
        parts = [
            encode_alphanumeric(self.xref_card_num, 16),
            encode_unsigned_numeric(self.xref_cust_id, 9),
            encode_unsigned_numeric(self.xref_acct_id, 11),
        ]
        data = "".join(parts)
        return data.ljust(RECORD_LENGTH)
