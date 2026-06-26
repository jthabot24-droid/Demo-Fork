"""CVTRA06Y — DALYTRAN-RECORD (350 bytes).

COBOL layout::

    01  DALYTRAN-RECORD.
        05  DALYTRAN-ID                       PIC X(16).
        05  DALYTRAN-TYPE-CD                  PIC X(02).
        05  DALYTRAN-CAT-CD                   PIC 9(04).
        05  DALYTRAN-SOURCE                   PIC X(10).
        05  DALYTRAN-DESC                     PIC X(100).
        05  DALYTRAN-AMT                      PIC S9(09)V99.
        05  DALYTRAN-MERCHANT-ID              PIC 9(09).
        05  DALYTRAN-MERCHANT-NAME            PIC X(50).
        05  DALYTRAN-MERCHANT-CITY            PIC X(50).
        05  DALYTRAN-MERCHANT-ZIP             PIC X(10).
        05  DALYTRAN-CARD-NUM                 PIC X(16).
        05  DALYTRAN-ORIG-TS                  PIC X(26).
        05  DALYTRAN-PROC-TS                  PIC X(26).
        05  FILLER                            PIC X(20).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from carddemo.codec import (
    decode_alphanumeric,
    decode_signed_numeric,
    decode_unsigned_numeric,
    encode_alphanumeric,
    encode_signed_numeric,
    encode_unsigned_numeric,
)

RECORD_LENGTH = 350


@dataclass
class DailyTransactionRecord:
    """CVTRA06Y — DALYTRAN-RECORD (350 bytes)."""

    dalytran_id: str = ""                                   # PIC X(16)
    dalytran_type_cd: str = ""                              # PIC X(02)
    dalytran_cat_cd: int = 0                                # PIC 9(04)
    dalytran_source: str = ""                               # PIC X(10)
    dalytran_desc: str = ""                                 # PIC X(100)
    dalytran_amt: Decimal = field(default_factory=lambda: Decimal("0.00"))
    dalytran_merchant_id: int = 0                           # PIC 9(09)
    dalytran_merchant_name: str = ""                        # PIC X(50)
    dalytran_merchant_city: str = ""                        # PIC X(50)
    dalytran_merchant_zip: str = ""                         # PIC X(10)
    dalytran_card_num: str = ""                             # PIC X(16)
    dalytran_orig_ts: str = ""                              # PIC X(26)
    dalytran_proc_ts: str = ""                              # PIC X(26)

    @classmethod
    def from_record(cls, line: str) -> DailyTransactionRecord:
        """Parse a fixed-width record line."""
        padded = line.ljust(RECORD_LENGTH)
        return cls(
            dalytran_id=decode_alphanumeric(padded[0:16]),
            dalytran_type_cd=decode_alphanumeric(padded[16:18]),
            dalytran_cat_cd=decode_unsigned_numeric(padded[18:22]),
            dalytran_source=decode_alphanumeric(padded[22:32]),
            dalytran_desc=decode_alphanumeric(padded[32:132]),
            dalytran_amt=decode_signed_numeric(padded[132:143], 2),
            dalytran_merchant_id=decode_unsigned_numeric(padded[143:152]),
            dalytran_merchant_name=decode_alphanumeric(padded[152:202]),
            dalytran_merchant_city=decode_alphanumeric(padded[202:252]),
            dalytran_merchant_zip=decode_alphanumeric(padded[252:262]),
            dalytran_card_num=decode_alphanumeric(padded[262:278]),
            dalytran_orig_ts=decode_alphanumeric(padded[278:304]),
            dalytran_proc_ts=decode_alphanumeric(padded[304:330]),
        )

    def to_record(self) -> str:
        """Serialize to a 350-character fixed-width line."""
        parts = [
            encode_alphanumeric(self.dalytran_id, 16),
            encode_alphanumeric(self.dalytran_type_cd, 2),
            encode_unsigned_numeric(self.dalytran_cat_cd, 4),
            encode_alphanumeric(self.dalytran_source, 10),
            encode_alphanumeric(self.dalytran_desc, 100),
            encode_signed_numeric(self.dalytran_amt, 11, 2),
            encode_unsigned_numeric(self.dalytran_merchant_id, 9),
            encode_alphanumeric(self.dalytran_merchant_name, 50),
            encode_alphanumeric(self.dalytran_merchant_city, 50),
            encode_alphanumeric(self.dalytran_merchant_zip, 10),
            encode_alphanumeric(self.dalytran_card_num, 16),
            encode_alphanumeric(self.dalytran_orig_ts, 26),
            encode_alphanumeric(self.dalytran_proc_ts, 26),
        ]
        data = "".join(parts)
        return data.ljust(RECORD_LENGTH)
