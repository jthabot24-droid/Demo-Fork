"""CVTRA06Y -- DALYTRAN-RECORD (350 bytes)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class DailyTransactionRecord:
    """Python mirror of the COBOL DALYTRAN-RECORD copybook (CVTRA06Y)."""

    dalytran_id: str = ""                       # PIC X(16)
    dalytran_type_cd: str = ""                  # PIC X(02)
    dalytran_cat_cd: int = 0                    # PIC 9(04)
    dalytran_source: str = ""                   # PIC X(10)
    dalytran_desc: str = ""                     # PIC X(100)
    dalytran_amt: Decimal = Decimal("0.00")     # PIC S9(09)V99
    dalytran_merchant_id: int = 0               # PIC 9(09)
    dalytran_merchant_name: str = ""            # PIC X(50)
    dalytran_merchant_city: str = ""            # PIC X(50)
    dalytran_merchant_zip: str = ""             # PIC X(10)
    dalytran_card_num: str = ""                 # PIC X(16)
    dalytran_orig_ts: str = ""                  # PIC X(26)
    dalytran_proc_ts: str = ""                  # PIC X(26)

    RECORD_LENGTH: int = 350
