"""CVCUS01Y — CUSTOMER-RECORD (500 bytes).

COBOL layout::

    01  CUSTOMER-RECORD.
        05  CUST-ID                           PIC 9(09).
        05  CUST-FIRST-NAME                   PIC X(25).
        05  CUST-MIDDLE-NAME                  PIC X(25).
        05  CUST-LAST-NAME                    PIC X(25).
        05  CUST-ADDR-LINE-1                  PIC X(50).
        05  CUST-ADDR-LINE-2                  PIC X(50).
        05  CUST-ADDR-LINE-3                  PIC X(50).
        05  CUST-ADDR-STATE-CD                PIC X(02).
        05  CUST-ADDR-COUNTRY-CD              PIC X(03).
        05  CUST-ADDR-ZIP                     PIC X(10).
        05  CUST-PHONE-NUM-1                  PIC X(15).
        05  CUST-PHONE-NUM-2                  PIC X(15).
        05  CUST-SSN                          PIC 9(09).
        05  CUST-GOVT-ISSUED-ID               PIC X(20).
        05  CUST-DOB-YYYY-MM-DD               PIC X(10).
        05  CUST-EFT-ACCOUNT-ID               PIC X(10).
        05  CUST-PRI-CARD-HOLDER-IND          PIC X(01).
        05  CUST-FICO-CREDIT-SCORE            PIC 9(03).
        05  FILLER                            PIC X(168).
"""

from __future__ import annotations

from dataclasses import dataclass

from carddemo.codec import (
    decode_alphanumeric,
    decode_unsigned_numeric,
    encode_alphanumeric,
    encode_unsigned_numeric,
)

RECORD_LENGTH = 500


@dataclass
class CustomerRecord:
    """CVCUS01Y — CUSTOMER-RECORD (500 bytes)."""

    cust_id: int = 0                    # PIC 9(09)
    cust_first_name: str = ""           # PIC X(25)
    cust_middle_name: str = ""          # PIC X(25)
    cust_last_name: str = ""            # PIC X(25)
    cust_addr_line_1: str = ""          # PIC X(50)
    cust_addr_line_2: str = ""          # PIC X(50)
    cust_addr_line_3: str = ""          # PIC X(50)
    cust_addr_state_cd: str = ""        # PIC X(02)
    cust_addr_country_cd: str = ""      # PIC X(03)
    cust_addr_zip: str = ""             # PIC X(10)
    cust_phone_num_1: str = ""          # PIC X(15)
    cust_phone_num_2: str = ""          # PIC X(15)
    cust_ssn: int = 0                   # PIC 9(09)
    cust_govt_issued_id: str = ""       # PIC X(20)
    cust_dob_yyyy_mm_dd: str = ""       # PIC X(10)
    cust_eft_account_id: str = ""       # PIC X(10)
    cust_pri_card_holder_ind: str = ""  # PIC X(01)
    cust_fico_credit_score: int = 0     # PIC 9(03)

    @classmethod
    def from_record(cls, line: str) -> CustomerRecord:
        """Parse a fixed-width record line."""
        padded = line.ljust(RECORD_LENGTH)
        return cls(
            cust_id=decode_unsigned_numeric(padded[0:9]),
            cust_first_name=decode_alphanumeric(padded[9:34]),
            cust_middle_name=decode_alphanumeric(padded[34:59]),
            cust_last_name=decode_alphanumeric(padded[59:84]),
            cust_addr_line_1=decode_alphanumeric(padded[84:134]),
            cust_addr_line_2=decode_alphanumeric(padded[134:184]),
            cust_addr_line_3=decode_alphanumeric(padded[184:234]),
            cust_addr_state_cd=decode_alphanumeric(padded[234:236]),
            cust_addr_country_cd=decode_alphanumeric(padded[236:239]),
            cust_addr_zip=decode_alphanumeric(padded[239:249]),
            cust_phone_num_1=decode_alphanumeric(padded[249:264]),
            cust_phone_num_2=decode_alphanumeric(padded[264:279]),
            cust_ssn=decode_unsigned_numeric(padded[279:288]),
            cust_govt_issued_id=decode_alphanumeric(padded[288:308]),
            cust_dob_yyyy_mm_dd=decode_alphanumeric(padded[308:318]),
            cust_eft_account_id=decode_alphanumeric(padded[318:328]),
            cust_pri_card_holder_ind=decode_alphanumeric(padded[328:329]),
            cust_fico_credit_score=decode_unsigned_numeric(padded[329:332]),
        )

    def to_record(self) -> str:
        """Serialize to a 500-character fixed-width line."""
        parts = [
            encode_unsigned_numeric(self.cust_id, 9),
            encode_alphanumeric(self.cust_first_name, 25),
            encode_alphanumeric(self.cust_middle_name, 25),
            encode_alphanumeric(self.cust_last_name, 25),
            encode_alphanumeric(self.cust_addr_line_1, 50),
            encode_alphanumeric(self.cust_addr_line_2, 50),
            encode_alphanumeric(self.cust_addr_line_3, 50),
            encode_alphanumeric(self.cust_addr_state_cd, 2),
            encode_alphanumeric(self.cust_addr_country_cd, 3),
            encode_alphanumeric(self.cust_addr_zip, 10),
            encode_alphanumeric(self.cust_phone_num_1, 15),
            encode_alphanumeric(self.cust_phone_num_2, 15),
            encode_unsigned_numeric(self.cust_ssn, 9),
            encode_alphanumeric(self.cust_govt_issued_id, 20),
            encode_alphanumeric(self.cust_dob_yyyy_mm_dd, 10),
            encode_alphanumeric(self.cust_eft_account_id, 10),
            encode_alphanumeric(self.cust_pri_card_holder_ind, 1),
            encode_unsigned_numeric(self.cust_fico_credit_score, 3),
        ]
        data = "".join(parts)
        return data.ljust(RECORD_LENGTH)
