"""CVCUS01Y -- CUSTOMER-RECORD (RECLN 500).

COBOL layout::

    01  CUSTOMER-RECORD.
        05  CUST-ID                                 PIC 9(09).
        05  CUST-FIRST-NAME                         PIC X(25).
        05  CUST-MIDDLE-NAME                        PIC X(25).
        05  CUST-LAST-NAME                          PIC X(25).
        05  CUST-ADDR-LINE-1                        PIC X(50).
        05  CUST-ADDR-LINE-2                        PIC X(50).
        05  CUST-ADDR-LINE-3                        PIC X(50).
        05  CUST-ADDR-STATE-CD                      PIC X(02).
        05  CUST-ADDR-COUNTRY-CD                    PIC X(03).
        05  CUST-ADDR-ZIP                           PIC X(10).
        05  CUST-PHONE-NUM-1                        PIC X(15).
        05  CUST-PHONE-NUM-2                        PIC X(15).
        05  CUST-SSN                                PIC 9(09).
        05  CUST-GOVT-ISSUED-ID                     PIC X(20).
        05  CUST-DOB-YYYY-MM-DD                     PIC X(10).
        05  CUST-EFT-ACCOUNT-ID                     PIC X(10).
        05  CUST-PRI-CARD-HOLDER-IND                PIC X(01).
        05  CUST-FICO-CREDIT-SCORE                  PIC 9(03).
        05  FILLER                                  PIC X(168).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CustomerRecord:
    """Python equivalent of CVCUS01Y CUSTOMER-RECORD (500 bytes)."""

    RECORD_LENGTH: int = 500

    cust_id: int = 0                      # PIC 9(09)
    cust_first_name: str = ""             # PIC X(25)
    cust_middle_name: str = ""            # PIC X(25)
    cust_last_name: str = ""              # PIC X(25)
    cust_addr_line_1: str = ""            # PIC X(50)
    cust_addr_line_2: str = ""            # PIC X(50)
    cust_addr_line_3: str = ""            # PIC X(50)
    cust_addr_state_cd: str = ""          # PIC X(02)
    cust_addr_country_cd: str = ""        # PIC X(03)
    cust_addr_zip: str = ""               # PIC X(10)
    cust_phone_num_1: str = ""            # PIC X(15)
    cust_phone_num_2: str = ""            # PIC X(15)
    cust_ssn: int = 0                     # PIC 9(09)
    cust_govt_issued_id: str = ""         # PIC X(20)
    cust_dob_yyyy_mm_dd: str = ""         # PIC X(10)
    cust_eft_account_id: str = ""         # PIC X(10)
    cust_pri_card_holder_ind: str = ""    # PIC X(01)
    cust_fico_credit_score: int = 0       # PIC 9(03)
    # FILLER PIC X(168) -- not stored

    FIELD_WIDTHS: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.FIELD_WIDTHS = {
            "cust_id": 9,
            "cust_first_name": 25,
            "cust_middle_name": 25,
            "cust_last_name": 25,
            "cust_addr_line_1": 50,
            "cust_addr_line_2": 50,
            "cust_addr_line_3": 50,
            "cust_addr_state_cd": 2,
            "cust_addr_country_cd": 3,
            "cust_addr_zip": 10,
            "cust_phone_num_1": 15,
            "cust_phone_num_2": 15,
            "cust_ssn": 9,
            "cust_govt_issued_id": 20,
            "cust_dob_yyyy_mm_dd": 10,
            "cust_eft_account_id": 10,
            "cust_pri_card_holder_ind": 1,
            "cust_fico_credit_score": 3,
        }
