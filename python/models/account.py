"""CVACT01Y -- ACCOUNT-RECORD (300 bytes)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class AccountRecord:
    """Python mirror of the COBOL ACCOUNT-RECORD copybook (CVACT01Y).

    Monetary fields use ``decimal.Decimal`` to match COBOL packed-decimal
    precision (``PIC S9(10)V99``).
    """

    acct_id: int = 0                                    # PIC 9(11)
    acct_active_status: str = ""                        # PIC X(01)
    acct_curr_bal: Decimal = Decimal("0.00")             # PIC S9(10)V99
    acct_credit_limit: Decimal = Decimal("0.00")         # PIC S9(10)V99
    acct_cash_credit_limit: Decimal = Decimal("0.00")    # PIC S9(10)V99
    acct_open_date: str = ""                             # PIC X(10)
    acct_expiration_date: str = ""                       # PIC X(10)
    acct_reissue_date: str = ""                          # PIC X(10)
    acct_curr_cyc_credit: Decimal = Decimal("0.00")      # PIC S9(10)V99
    acct_curr_cyc_debit: Decimal = Decimal("0.00")       # PIC S9(10)V99
    acct_addr_zip: str = ""                              # PIC X(10)
    acct_group_id: str = ""                              # PIC X(10)

    RECORD_LENGTH: int = 300
