"""CVACT02Y -- CARD-RECORD (RECLN 150).

COBOL layout::

    01  CARD-RECORD.
        05  CARD-NUM                          PIC X(16).
        05  CARD-ACCT-ID                      PIC 9(11).
        05  CARD-CVV-CD                       PIC 9(03).
        05  CARD-EMBOSSED-NAME                PIC X(50).
        05  CARD-EXPIRAION-DATE               PIC X(10).
        05  CARD-ACTIVE-STATUS                PIC X(01).
        05  FILLER                            PIC X(59).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CardRecord:
    """Python equivalent of CVACT02Y CARD-RECORD (150 bytes)."""

    RECORD_LENGTH: int = 150

    card_num: str = ""              # PIC X(16)
    card_acct_id: int = 0           # PIC 9(11)
    card_cvv_cd: int = 0            # PIC 9(03)
    card_embossed_name: str = ""    # PIC X(50)
    card_expiration_date: str = ""  # PIC X(10)  -- COBOL typo EXPIRAION
    card_active_status: str = ""    # PIC X(01)
    # FILLER PIC X(59) -- not stored

    FIELD_WIDTHS: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.FIELD_WIDTHS = {
            "card_num": 16,
            "card_acct_id": 11,
            "card_cvv_cd": 3,
            "card_embossed_name": 50,
            "card_expiration_date": 10,
            "card_active_status": 1,
        }
