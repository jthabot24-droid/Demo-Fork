"""Transaction category/type/balance copybooks.

CVTRA01Y -- TRAN-CAT-BAL-RECORD (RECLN 50)::

    01  TRAN-CAT-BAL-RECORD.
        05  TRAN-CAT-KEY.
           10 TRANCAT-ACCT-ID          PIC 9(11).
           10 TRANCAT-TYPE-CD          PIC X(02).
           10 TRANCAT-CD               PIC 9(04).
        05  TRAN-CAT-BAL               PIC S9(09)V99.
        05  FILLER                     PIC X(22).

CVTRA02Y -- DIS-GROUP-RECORD (RECLN 50)::

    (see disclosure_group.py)

CVTRA03Y -- TRAN-TYPE-RECORD (RECLN 60)::

    01  TRAN-TYPE-RECORD.
        05  TRAN-TYPE                  PIC X(02).
        05  TRAN-TYPE-DESC             PIC X(50).
        05  FILLER                     PIC X(08).

CVTRA04Y -- TRAN-CAT-RECORD (RECLN 60)::

    01  TRAN-CAT-RECORD.
        05  TRAN-CAT-KEY.
           10  TRAN-TYPE-CD            PIC X(02).
           10  TRAN-CAT-CD             PIC 9(04).
        05  TRAN-CAT-TYPE-DESC         PIC X(50).
        05  FILLER                     PIC X(04).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class TranCatBalRecord:
    """CVTRA01Y -- Transaction category balance (50 bytes).

    Composite key: (TRANCAT-ACCT-ID, TRANCAT-TYPE-CD, TRANCAT-CD).
    """

    RECORD_LENGTH: int = 50

    trancat_acct_id: int = 0              # PIC 9(11)
    trancat_type_cd: str = ""             # PIC X(02)
    trancat_cd: int = 0                   # PIC 9(04)
    tran_cat_bal: Decimal = Decimal("0.00")  # PIC S9(09)V99
    # FILLER PIC X(22) -- not stored

    @property
    def key(self) -> str:
        """Return the composite key as COBOL would store it."""
        return f"{self.trancat_acct_id:011d}{self.trancat_type_cd:2s}{self.trancat_cd:04d}"

    FIELD_WIDTHS: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.FIELD_WIDTHS = {
            "trancat_acct_id": 11,
            "trancat_type_cd": 2,
            "trancat_cd": 4,
            "tran_cat_bal": 11,   # S9(09)V99 → 11 display digits
        }


@dataclass
class TranTypeRecord:
    """CVTRA03Y -- Transaction type (60 bytes)."""

    RECORD_LENGTH: int = 60

    tran_type: str = ""             # PIC X(02) -- key
    tran_type_desc: str = ""        # PIC X(50)
    # FILLER PIC X(08) -- not stored

    FIELD_WIDTHS: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.FIELD_WIDTHS = {
            "tran_type": 2,
            "tran_type_desc": 50,
        }


@dataclass
class TranCatRecord:
    """CVTRA04Y -- Transaction category type (60 bytes).

    Composite key: (TRAN-TYPE-CD, TRAN-CAT-CD).
    """

    RECORD_LENGTH: int = 60

    tran_type_cd: str = ""           # PIC X(02)
    tran_cat_cd: int = 0             # PIC 9(04)
    tran_cat_type_desc: str = ""     # PIC X(50)
    # FILLER PIC X(04) -- not stored

    @property
    def key(self) -> str:
        return f"{self.tran_type_cd:2s}{self.tran_cat_cd:04d}"

    FIELD_WIDTHS: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.FIELD_WIDTHS = {
            "tran_type_cd": 2,
            "tran_cat_cd": 4,
            "tran_cat_type_desc": 50,
        }
