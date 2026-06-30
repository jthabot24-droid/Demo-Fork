"""CVEXPORT -- Multi-record export layout (RECLN 500).

This copybook uses REDEFINES to overlay different record-type structures
onto the same 460-byte ``EXPORT-RECORD-DATA`` area.  It also demonstrates
OCCURS (address lines x3, phone numbers x2) and mixed storage (COMP,
COMP-3, zoned-decimal).

COBOL layout (abbreviated)::

    01  EXPORT-RECORD.
        05  EXPORT-REC-TYPE           PIC X(1).
        05  EXPORT-TIMESTAMP          PIC X(26).
        05  EXPORT-TIMESTAMP-R REDEFINES EXPORT-TIMESTAMP.
            10  EXPORT-DATE           PIC X(10).
            10  EXPORT-DATE-TIME-SEP  PIC X(1).
            10  EXPORT-TIME           PIC X(15).
        05  EXPORT-SEQUENCE-NUM       PIC 9(9) COMP.
        05  EXPORT-BRANCH-ID          PIC X(4).
        05  EXPORT-REGION-CODE        PIC X(5).
        05  EXPORT-RECORD-DATA        PIC X(460).
        -- then five REDEFINES of EXPORT-RECORD-DATA for:
           Customer, Account, Transaction, Card-Xref, Card

In Python we model the *header* as ``ExportRecord`` and each variant
payload as its own dataclass.  The ``rec_type`` field selects which
payload to populate:
    'C' → ExportCustomerData
    'A' → ExportAccountData
    'T' → ExportTransactionData
    'X' → ExportCardXrefData
    'D' → ExportCardData   (card Data)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


# ---------------------------------------------------------------------------
# Payload variants (one per REDEFINES)
# ---------------------------------------------------------------------------


@dataclass
class ExportCustomerData:
    """EXPORT-CUSTOMER-DATA -- REDEFINES EXPORT-RECORD-DATA.

    Notable COBOL features modelled here:
    * ``OCCURS 3 TIMES`` on address lines → ``addr_lines: list[str]``
    * ``OCCURS 2 TIMES`` on phone numbers → ``phone_nums: list[str]``
    * ``PIC 9(09) COMP`` on cust-id → binary integer
    * ``PIC 9(03) COMP-3`` on FICO score → packed-decimal integer
    """

    exp_cust_id: int = 0                       # PIC 9(09) COMP
    exp_cust_first_name: str = ""              # PIC X(25)
    exp_cust_middle_name: str = ""             # PIC X(25)
    exp_cust_last_name: str = ""               # PIC X(25)
    exp_cust_addr_lines: list[str] = field(    # OCCURS 3 TIMES, PIC X(50)
        default_factory=lambda: ["", "", ""]
    )
    exp_cust_addr_state_cd: str = ""           # PIC X(02)
    exp_cust_addr_country_cd: str = ""         # PIC X(03)
    exp_cust_addr_zip: str = ""                # PIC X(10)
    exp_cust_phone_nums: list[str] = field(    # OCCURS 2 TIMES, PIC X(15)
        default_factory=lambda: ["", ""]
    )
    exp_cust_ssn: int = 0                      # PIC 9(09)  zoned
    exp_cust_govt_issued_id: str = ""          # PIC X(20)
    exp_cust_dob_yyyy_mm_dd: str = ""          # PIC X(10)
    exp_cust_eft_account_id: str = ""          # PIC X(10)
    exp_cust_pri_card_holder_ind: str = ""     # PIC X(01)
    exp_cust_fico_credit_score: int = 0        # PIC 9(03) COMP-3

    STORAGE_NOTES: str = (
        "COMP on cust_id (binary); COMP-3 on fico_credit_score (packed-decimal)"
    )


@dataclass
class ExportAccountData:
    """EXPORT-ACCOUNT-DATA -- REDEFINES EXPORT-RECORD-DATA.

    Mixed storage: COMP-3 for curr_bal and cash_credit_limit,
    COMP for curr_cyc_debit, zoned-decimal for credit_limit and
    curr_cyc_credit.
    """

    exp_acct_id: int = 0                                    # PIC 9(11) zoned
    exp_acct_active_status: str = ""                        # PIC X(01)
    exp_acct_curr_bal: Decimal = Decimal("0.00")            # PIC S9(10)V99 COMP-3
    exp_acct_credit_limit: Decimal = Decimal("0.00")        # PIC S9(10)V99 zoned
    exp_acct_cash_credit_limit: Decimal = Decimal("0.00")   # PIC S9(10)V99 COMP-3
    exp_acct_open_date: str = ""                            # PIC X(10)
    exp_acct_expiration_date: str = ""                      # PIC X(10)
    exp_acct_reissue_date: str = ""                         # PIC X(10)
    exp_acct_curr_cyc_credit: Decimal = Decimal("0.00")     # PIC S9(10)V99 zoned
    exp_acct_curr_cyc_debit: Decimal = Decimal("0.00")      # PIC S9(10)V99 COMP
    exp_acct_addr_zip: str = ""                             # PIC X(10)
    exp_acct_group_id: str = ""                             # PIC X(10)

    STORAGE_NOTES: str = (
        "COMP-3 on curr_bal, cash_credit_limit; "
        "COMP on curr_cyc_debit; zoned on credit_limit, curr_cyc_credit"
    )


@dataclass
class ExportTransactionData:
    """EXPORT-TRANSACTION-DATA -- REDEFINES EXPORT-RECORD-DATA.

    COMP-3 for tran_amt; COMP for merchant_id.
    """

    exp_tran_id: str = ""                                   # PIC X(16)
    exp_tran_type_cd: str = ""                              # PIC X(02)
    exp_tran_cat_cd: int = 0                                # PIC 9(04) zoned
    exp_tran_source: str = ""                               # PIC X(10)
    exp_tran_desc: str = ""                                 # PIC X(100)
    exp_tran_amt: Decimal = Decimal("0.00")                 # PIC S9(09)V99 COMP-3
    exp_tran_merchant_id: int = 0                           # PIC 9(09) COMP
    exp_tran_merchant_name: str = ""                        # PIC X(50)
    exp_tran_merchant_city: str = ""                        # PIC X(50)
    exp_tran_merchant_zip: str = ""                         # PIC X(10)
    exp_tran_card_num: str = ""                             # PIC X(16)
    exp_tran_orig_ts: str = ""                              # PIC X(26)
    exp_tran_proc_ts: str = ""                              # PIC X(26)

    STORAGE_NOTES: str = "COMP-3 on tran_amt; COMP on merchant_id"


@dataclass
class ExportCardXrefData:
    """EXPORT-CARD-XREF-DATA -- REDEFINES EXPORT-RECORD-DATA.

    COMP on acct_id.
    """

    exp_xref_card_num: str = ""       # PIC X(16)
    exp_xref_cust_id: int = 0         # PIC 9(09) zoned
    exp_xref_acct_id: int = 0         # PIC 9(11) COMP

    STORAGE_NOTES: str = "COMP on acct_id"


@dataclass
class ExportCardData:
    """EXPORT-CARD-DATA -- REDEFINES EXPORT-RECORD-DATA.

    COMP on acct_id and cvv_cd.
    """

    exp_card_num: str = ""                # PIC X(16)
    exp_card_acct_id: int = 0             # PIC 9(11) COMP
    exp_card_cvv_cd: int = 0              # PIC 9(03) COMP
    exp_card_embossed_name: str = ""      # PIC X(50)
    exp_card_expiration_date: str = ""    # PIC X(10)
    exp_card_active_status: str = ""      # PIC X(01)

    STORAGE_NOTES: str = "COMP on acct_id, cvv_cd"


# ---------------------------------------------------------------------------
# Envelope record
# ---------------------------------------------------------------------------

# REDEFINES mapping: rec_type code → payload type
EXPORT_PAYLOAD_TYPES = {
    "C": ExportCustomerData,
    "A": ExportAccountData,
    "T": ExportTransactionData,
    "X": ExportCardXrefData,
    "D": ExportCardData,
}


@dataclass
class ExportRecord:
    """CVEXPORT -- export envelope (500 bytes total).

    The ``EXPORT-TIMESTAMP`` field has a REDEFINES that splits it into
    ``EXPORT-DATE`` (10) + separator (1) + ``EXPORT-TIME`` (15).  In
    Python we store the full 26-char timestamp *and* provide properties
    for the sub-fields.
    """

    RECORD_LENGTH: int = 500

    export_rec_type: str = ""               # PIC X(1)
    export_timestamp: str = ""              # PIC X(26)
    export_sequence_num: int = 0            # PIC 9(9) COMP  -- binary
    export_branch_id: str = ""              # PIC X(4)
    export_region_code: str = ""            # PIC X(5)

    # The payload -- one of the five REDEFINES variants above, or None
    payload: Optional[
        ExportCustomerData
        | ExportAccountData
        | ExportTransactionData
        | ExportCardXrefData
        | ExportCardData
    ] = None

    # -- REDEFINES helpers for EXPORT-TIMESTAMP-R --

    @property
    def export_date(self) -> str:
        """EXPORT-DATE PIC X(10) -- first 10 chars of timestamp."""
        return self.export_timestamp[:10]

    @property
    def export_time(self) -> str:
        """EXPORT-TIME PIC X(15) -- chars 12..26 of timestamp."""
        return self.export_timestamp[11:26]
