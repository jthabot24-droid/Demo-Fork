"""CVTRA02Y -- DIS-GROUP-RECORD (50 bytes)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class DisclosureGroupRecord:
    """Python mirror of the COBOL DIS-GROUP-RECORD copybook (CVTRA02Y).

    The composite key is (dis_acct_group_id, dis_tran_type_cd, dis_tran_cat_cd).
    """

    dis_acct_group_id: str = ""                 # PIC X(10)
    dis_tran_type_cd: str = ""                  # PIC X(02)
    dis_tran_cat_cd: int = 0                    # PIC 9(04)
    dis_int_rate: Decimal = Decimal("0.00")     # PIC S9(04)V99

    RECORD_LENGTH: int = 50

    @property
    def key(self) -> str:
        """Return the composite key string used for VSAM keyed access."""
        return f"{self.dis_acct_group_id:10s}{self.dis_tran_type_cd:2s}{self.dis_tran_cat_cd:04d}"
