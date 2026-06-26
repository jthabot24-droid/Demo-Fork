"""CVCUS01Y -- CUSTOMER-RECORD (500 bytes)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class CustomerRecord:
    """Python mirror of the COBOL CUSTOMER-RECORD copybook (CVCUS01Y)."""

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

    RECORD_LENGTH: int = 500
