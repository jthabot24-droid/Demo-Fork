"""CVTRA05Y -- TRAN-RECORD (RECLN 350) and CVTRA06Y -- DALYTRAN-RECORD (350).

COBOL layouts::

    01  TRAN-RECORD.                       (CVTRA05Y)
        05  TRAN-ID                  PIC X(16).
        05  TRAN-TYPE-CD             PIC X(02).
        05  TRAN-CAT-CD              PIC 9(04).
        05  TRAN-SOURCE              PIC X(10).
        05  TRAN-DESC                PIC X(100).
        05  TRAN-AMT                 PIC S9(09)V99.
        05  TRAN-MERCHANT-ID         PIC 9(09).
        05  TRAN-MERCHANT-NAME       PIC X(50).
        05  TRAN-MERCHANT-CITY       PIC X(50).
        05  TRAN-MERCHANT-ZIP        PIC X(10).
        05  TRAN-CARD-NUM            PIC X(16).
        05  TRAN-ORIG-TS             PIC X(26).
        05  TRAN-PROC-TS             PIC X(26).
        05  FILLER                   PIC X(20).

    01  DALYTRAN-RECORD.                   (CVTRA06Y -- identical layout)
        05  DALYTRAN-ID              PIC X(16).
        ...
        05  FILLER                   PIC X(20).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class TransactionRecord:
    """Python equivalent of CVTRA05Y TRAN-RECORD (350 bytes)."""

    RECORD_LENGTH: int = 350

    tran_id: str = ""                              # PIC X(16)
    tran_type_cd: str = ""                         # PIC X(02)
    tran_cat_cd: int = 0                           # PIC 9(04)
    tran_source: str = ""                          # PIC X(10)
    tran_desc: str = ""                            # PIC X(100)
    tran_amt: Decimal = Decimal("0.00")            # PIC S9(09)V99
    tran_merchant_id: int = 0                      # PIC 9(09)
    tran_merchant_name: str = ""                   # PIC X(50)
    tran_merchant_city: str = ""                   # PIC X(50)
    tran_merchant_zip: str = ""                    # PIC X(10)
    tran_card_num: str = ""                        # PIC X(16)
    tran_orig_ts: str = ""                         # PIC X(26)
    tran_proc_ts: str = ""                         # PIC X(26)
    # FILLER PIC X(20) -- not stored

    FIELD_WIDTHS: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.FIELD_WIDTHS = {
            "tran_id": 16,
            "tran_type_cd": 2,
            "tran_cat_cd": 4,
            "tran_source": 10,
            "tran_desc": 100,
            "tran_amt": 11,       # S9(09)V99 → 11 display digits
            "tran_merchant_id": 9,
            "tran_merchant_name": 50,
            "tran_merchant_city": 50,
            "tran_merchant_zip": 10,
            "tran_card_num": 16,
            "tran_orig_ts": 26,
            "tran_proc_ts": 26,
        }


@dataclass
class DailyTransactionRecord:
    """Python equivalent of CVTRA06Y DALYTRAN-RECORD (350 bytes).

    Identical layout to TRAN-RECORD but with DALYTRAN- prefix in COBOL.
    Used by the batch posting program (CBTRN02C).
    """

    RECORD_LENGTH: int = 350

    dalytran_id: str = ""                          # PIC X(16)
    dalytran_type_cd: str = ""                     # PIC X(02)
    dalytran_cat_cd: int = 0                       # PIC 9(04)
    dalytran_source: str = ""                      # PIC X(10)
    dalytran_desc: str = ""                        # PIC X(100)
    dalytran_amt: Decimal = Decimal("0.00")        # PIC S9(09)V99
    dalytran_merchant_id: int = 0                  # PIC 9(09)
    dalytran_merchant_name: str = ""               # PIC X(50)
    dalytran_merchant_city: str = ""               # PIC X(50)
    dalytran_merchant_zip: str = ""                # PIC X(10)
    dalytran_card_num: str = ""                    # PIC X(16)
    dalytran_orig_ts: str = ""                     # PIC X(26)
    dalytran_proc_ts: str = ""                     # PIC X(26)
    # FILLER PIC X(20) -- not stored

    FIELD_WIDTHS: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.FIELD_WIDTHS = {
            "dalytran_id": 16,
            "dalytran_type_cd": 2,
            "dalytran_cat_cd": 4,
            "dalytran_source": 10,
            "dalytran_desc": 100,
            "dalytran_amt": 11,
            "dalytran_merchant_id": 9,
            "dalytran_merchant_name": 50,
            "dalytran_merchant_city": 50,
            "dalytran_merchant_zip": 10,
            "dalytran_card_num": 16,
            "dalytran_orig_ts": 26,
            "dalytran_proc_ts": 26,
        }
