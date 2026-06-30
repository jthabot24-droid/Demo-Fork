"""CVTRA02Y -- DIS-GROUP-RECORD (RECLN 50).

COBOL layout::

    01  DIS-GROUP-RECORD.
        05  DIS-GROUP-KEY.
           10 DIS-ACCT-GROUP-ID        PIC X(10).
           10 DIS-TRAN-TYPE-CD         PIC X(02).
           10 DIS-TRAN-CAT-CD          PIC 9(04).
        05  DIS-INT-RATE               PIC S9(04)V99.
        05  FILLER                     PIC X(28).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class DisclosureGroupRecord:
    """CVTRA02Y -- Disclosure group / interest rate (50 bytes).

    Composite key: (DIS-ACCT-GROUP-ID, DIS-TRAN-TYPE-CD, DIS-TRAN-CAT-CD).
    ``dis_int_rate`` is an annual percentage rate (e.g. ``18.50`` means 18.5%).
    The interest calculator (CBACT04C) divides by 1200 to get a monthly rate.
    """

    RECORD_LENGTH: int = 50

    dis_acct_group_id: str = ""           # PIC X(10)
    dis_tran_type_cd: str = ""            # PIC X(02)
    dis_tran_cat_cd: int = 0              # PIC 9(04)
    dis_int_rate: Decimal = Decimal("0.00")  # PIC S9(04)V99
    # FILLER PIC X(28) -- not stored

    @property
    def key(self) -> str:
        return (
            f"{self.dis_acct_group_id:10s}"
            f"{self.dis_tran_type_cd:2s}"
            f"{self.dis_tran_cat_cd:04d}"
        )

    FIELD_WIDTHS: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.FIELD_WIDTHS = {
            "dis_acct_group_id": 10,
            "dis_tran_type_cd": 2,
            "dis_tran_cat_cd": 4,
            "dis_int_rate": 6,   # S9(04)V99 → 6 display digits
        }
