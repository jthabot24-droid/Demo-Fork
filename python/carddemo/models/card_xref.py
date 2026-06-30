"""CVACT03Y -- CARD-XREF-RECORD (RECLN 50).

COBOL layout::

    01 CARD-XREF-RECORD.
        05  XREF-CARD-NUM                     PIC X(16).
        05  XREF-CUST-ID                      PIC 9(09).
        05  XREF-ACCT-ID                      PIC 9(11).
        05  FILLER                            PIC X(14).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CardXrefRecord:
    """Python equivalent of CVACT03Y CARD-XREF-RECORD (50 bytes)."""

    RECORD_LENGTH: int = 50

    xref_card_num: str = ""   # PIC X(16) -- primary key, 16-byte zero-padded
    xref_cust_id: int = 0     # PIC 9(09)
    xref_acct_id: int = 0     # PIC 9(11) -- alternate key
    # FILLER PIC X(14) -- not stored

    FIELD_WIDTHS: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.FIELD_WIDTHS = {
            "xref_card_num": 16,
            "xref_cust_id": 9,
            "xref_acct_id": 11,
        }
