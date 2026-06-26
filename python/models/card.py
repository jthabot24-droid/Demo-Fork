"""CVACT02Y -- CARD-RECORD (150 bytes)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CardRecord:
    """Python mirror of the COBOL CARD-RECORD copybook (CVACT02Y)."""

    card_num: str = ""              # PIC X(16)
    card_acct_id: int = 0           # PIC 9(11)
    card_cvv_cd: int = 0            # PIC 9(03)
    card_embossed_name: str = ""    # PIC X(50)
    card_expiration_date: str = ""  # PIC X(10)
    card_active_status: str = ""    # PIC X(01)

    RECORD_LENGTH: int = 150
