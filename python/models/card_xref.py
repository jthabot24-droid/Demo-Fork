"""CVACT03Y -- CARD-XREF-RECORD (50 bytes)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CardXrefRecord:
    """Python mirror of the COBOL CARD-XREF-RECORD copybook (CVACT03Y)."""

    xref_card_num: str = ""  # PIC X(16)  -- primary key
    xref_cust_id: int = 0    # PIC 9(09)
    xref_acct_id: int = 0    # PIC 9(11)  -- alternate key

    RECORD_LENGTH: int = 50
