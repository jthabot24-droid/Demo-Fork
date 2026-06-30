"""CVACT01Y -- ACCOUNT-RECORD (RECLN 300).

COBOL layout::

    01  ACCOUNT-RECORD.
        05  ACCT-ID                           PIC 9(11).
        05  ACCT-ACTIVE-STATUS                PIC X(01).
        05  ACCT-CURR-BAL                     PIC S9(10)V99.
        05  ACCT-CREDIT-LIMIT                 PIC S9(10)V99.
        05  ACCT-CASH-CREDIT-LIMIT            PIC S9(10)V99.
        05  ACCT-OPEN-DATE                    PIC X(10).
        05  ACCT-EXPIRAION-DATE               PIC X(10).
        05  ACCT-REISSUE-DATE                 PIC X(10).
        05  ACCT-CURR-CYC-CREDIT              PIC S9(10)V99.
        05  ACCT-CURR-CYC-DEBIT               PIC S9(10)V99.
        05  ACCT-ADDR-ZIP                     PIC X(10).
        05  ACCT-GROUP-ID                     PIC X(10).
        05  FILLER                            PIC X(178).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class AccountRecord:
    """Python equivalent of CVACT01Y ACCOUNT-RECORD (300 bytes)."""

    RECORD_LENGTH: int = 300

    acct_id: int = 0                                       # PIC 9(11)
    acct_active_status: str = ""                            # PIC X(01)
    acct_curr_bal: Decimal = Decimal("0.00")                # PIC S9(10)V99
    acct_credit_limit: Decimal = Decimal("0.00")            # PIC S9(10)V99
    acct_cash_credit_limit: Decimal = Decimal("0.00")       # PIC S9(10)V99
    acct_open_date: str = ""                                # PIC X(10)
    acct_expiration_date: str = ""                           # PIC X(10)  -- note COBOL typo EXPIRAION
    acct_reissue_date: str = ""                             # PIC X(10)
    acct_curr_cyc_credit: Decimal = Decimal("0.00")         # PIC S9(10)V99
    acct_curr_cyc_debit: Decimal = Decimal("0.00")          # PIC S9(10)V99
    acct_addr_zip: str = ""                                 # PIC X(10)
    acct_group_id: str = ""                                 # PIC X(10)
    # FILLER PIC X(178) -- not stored

    # Fixed-width field widths matching COBOL PIC clauses
    FIELD_WIDTHS: dict = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.FIELD_WIDTHS = {
            "acct_id": 11,
            "acct_active_status": 1,
            "acct_curr_bal": 12,           # S9(10)V99 → 12 display digits
            "acct_credit_limit": 12,
            "acct_cash_credit_limit": 12,
            "acct_open_date": 10,
            "acct_expiration_date": 10,
            "acct_reissue_date": 10,
            "acct_curr_cyc_credit": 12,
            "acct_curr_cyc_debit": 12,
            "acct_addr_zip": 10,
            "acct_group_id": 10,
        }
