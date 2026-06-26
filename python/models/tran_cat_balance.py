"""CVTRA01Y -- TRAN-CAT-BAL-RECORD (50 bytes)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class TranCatBalanceRecord:
    """Python mirror of the COBOL TRAN-CAT-BAL-RECORD copybook (CVTRA01Y).

    The composite key is (trancat_acct_id, trancat_type_cd, trancat_cd).
    """

    trancat_acct_id: int = 0                        # PIC 9(11)
    trancat_type_cd: str = ""                       # PIC X(02)
    trancat_cd: int = 0                             # PIC 9(04)
    tran_cat_bal: Decimal = Decimal("0.00")         # PIC S9(09)V99

    RECORD_LENGTH: int = 50

    @property
    def key(self) -> str:
        """Return the composite key string used for VSAM keyed access."""
        return f"{self.trancat_acct_id:011d}{self.trancat_type_cd:2s}{self.trancat_cd:04d}"
