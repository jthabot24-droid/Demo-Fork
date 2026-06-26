"""CVTRA05Y — TRAN-RECORD (350 bytes).

COBOL layout::

    01  TRAN-RECORD.
        05  TRAN-ID                           PIC X(16).
        05  TRAN-TYPE-CD                      PIC X(02).
        05  TRAN-CAT-CD                       PIC 9(04).
        05  TRAN-SOURCE                       PIC X(10).
        05  TRAN-DESC                         PIC X(100).
        05  TRAN-AMT                          PIC S9(09)V99.
        05  TRAN-MERCHANT-ID                  PIC 9(09).
        05  TRAN-MERCHANT-NAME                PIC X(50).
        05  TRAN-MERCHANT-CITY                PIC X(50).
        05  TRAN-MERCHANT-ZIP                 PIC X(10).
        05  TRAN-CARD-NUM                     PIC X(16).
        05  TRAN-ORIG-TS                      PIC X(26).
        05  TRAN-PROC-TS                      PIC X(26).
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
class TransactionRecord:
    """CVTRA05Y — TRAN-RECORD (350 bytes)."""

    tran_id: str = ""                                       # PIC X(16)
    tran_type_cd: str = ""                                  # PIC X(02)
    tran_cat_cd: int = 0                                    # PIC 9(04)
    tran_source: str = ""                                   # PIC X(10)
    tran_desc: str = ""                                     # PIC X(100)
    tran_amt: Decimal = field(default_factory=lambda: Decimal("0.00"))
    tran_merchant_id: int = 0                               # PIC 9(09)
    tran_merchant_name: str = ""                            # PIC X(50)
    tran_merchant_city: str = ""                            # PIC X(50)
    tran_merchant_zip: str = ""                             # PIC X(10)
    tran_card_num: str = ""                                 # PIC X(16)
    tran_orig_ts: str = ""                                  # PIC X(26)
    tran_proc_ts: str = ""                                  # PIC X(26)

    @classmethod
    def from_record(cls, line: str) -> TransactionRecord:
        """Parse a fixed-width record line."""
        padded = line.ljust(RECORD_LENGTH)
        return cls(
            tran_id=decode_alphanumeric(padded[0:16]),
            tran_type_cd=decode_alphanumeric(padded[16:18]),
            tran_cat_cd=decode_unsigned_numeric(padded[18:22]),
            tran_source=decode_alphanumeric(padded[22:32]),
            tran_desc=decode_alphanumeric(padded[32:132]),
            tran_amt=decode_signed_numeric(padded[132:143], 2),
            tran_merchant_id=decode_unsigned_numeric(padded[143:152]),
            tran_merchant_name=decode_alphanumeric(padded[152:202]),
            tran_merchant_city=decode_alphanumeric(padded[202:252]),
            tran_merchant_zip=decode_alphanumeric(padded[252:262]),
            tran_card_num=decode_alphanumeric(padded[262:278]),
            tran_orig_ts=decode_alphanumeric(padded[278:304]),
            tran_proc_ts=decode_alphanumeric(padded[304:330]),
        )

    def to_record(self) -> str:
        """Serialize to a 350-character fixed-width line."""
        parts = [
            encode_alphanumeric(self.tran_id, 16),
            encode_alphanumeric(self.tran_type_cd, 2),
            encode_unsigned_numeric(self.tran_cat_cd, 4),
            encode_alphanumeric(self.tran_source, 10),
            encode_alphanumeric(self.tran_desc, 100),
            encode_signed_numeric(self.tran_amt, 11, 2),
            encode_unsigned_numeric(self.tran_merchant_id, 9),
            encode_alphanumeric(self.tran_merchant_name, 50),
            encode_alphanumeric(self.tran_merchant_city, 50),
            encode_alphanumeric(self.tran_merchant_zip, 10),
            encode_alphanumeric(self.tran_card_num, 16),
            encode_alphanumeric(self.tran_orig_ts, 26),
            encode_alphanumeric(self.tran_proc_ts, 26),
        ]
        data = "".join(parts)
        return data.ljust(RECORD_LENGTH)
