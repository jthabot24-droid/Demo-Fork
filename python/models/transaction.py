"""CVTRA05Y -- TRAN-RECORD (350 bytes)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class TransactionRecord:
    """Python mirror of the COBOL TRAN-RECORD copybook (CVTRA05Y)."""

    tran_id: str = ""                       # PIC X(16)
    tran_type_cd: str = ""                  # PIC X(02)
    tran_cat_cd: int = 0                    # PIC 9(04)
    tran_source: str = ""                   # PIC X(10)
    tran_desc: str = ""                     # PIC X(100)
    tran_amt: Decimal = Decimal("0.00")     # PIC S9(09)V99
    tran_merchant_id: int = 0               # PIC 9(09)
    tran_merchant_name: str = ""            # PIC X(50)
    tran_merchant_city: str = ""            # PIC X(50)
    tran_merchant_zip: str = ""             # PIC X(10)
    tran_card_num: str = ""                 # PIC X(16)
    tran_orig_ts: str = ""                  # PIC X(26)
    tran_proc_ts: str = ""                  # PIC X(26)

    RECORD_LENGTH: int = 350
