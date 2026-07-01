"""
I/O helper reproducing the CBSTM03B subroutine behaviour.

CBSTM03B handles four VSAM files for the statement-generation job:

* **TRNXFILE** -- transactions, INDEXED, SEQUENTIAL access (key = card+id)
* **XREFFILE** -- card cross-reference, INDEXED, SEQUENTIAL access
* **CUSTFILE** -- customer master, INDEXED, RANDOM access (key = cust-id)
* **ACCTFILE** -- account master, INDEXED, RANDOM access (key = acct-id)

Operations communicated via the WS-M03B-AREA control block:

* ``O`` -- open
* ``R`` -- sequential read
* ``K`` -- keyed (random) read
* ``C`` -- close

Return codes:

* ``'00'`` -- success
* ``'10'`` -- end-of-file (sequential read past last record)

All monetary values use ``decimal.Decimal``; data is loaded from CSV
files via *pandas* DataFrames, matching the conventions in
``transaction_validation.py``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Iterator, List, Optional

import pandas as pd

# ---------------------------------------------------------------------------
# Return-code constants (match COBOL 2-char codes)
# ---------------------------------------------------------------------------
RC_OK = "00"
RC_EOF = "10"
RC_ERROR = "99"

# ---------------------------------------------------------------------------
# Record dataclasses -- mirror COBOL copybook layouts
# ---------------------------------------------------------------------------


@dataclass
class TransactionRecord:
    """COSTM01 -- TRNX-RECORD (350 bytes).

    Fields correspond 1-to-1 with the COBOL PIC clauses.
    """

    trnx_card_num: str = ""       # PIC X(16)
    trnx_id: str = ""             # PIC X(16)
    trnx_type_cd: str = ""        # PIC X(02)
    trnx_cat_cd: str = ""         # PIC 9(04)
    trnx_source: str = ""         # PIC X(10)
    trnx_desc: str = ""           # PIC X(100)
    trnx_amt: Decimal = field(default_factory=lambda: Decimal("0.00"))
    trnx_merchant_id: str = ""    # PIC 9(09)
    trnx_merchant_name: str = ""  # PIC X(50)
    trnx_merchant_city: str = ""  # PIC X(50)
    trnx_merchant_zip: str = ""   # PIC X(10)
    trnx_orig_ts: str = ""        # PIC X(26)
    trnx_proc_ts: str = ""        # PIC X(26)


@dataclass
class XrefRecord:
    """CVACT03Y -- CARD-XREF-RECORD (50 bytes)."""

    xref_card_num: str = ""   # PIC X(16)
    xref_cust_id: str = ""    # PIC 9(09)
    xref_acct_id: str = ""    # PIC 9(11)


@dataclass
class CustomerRecord:
    """CUSTREC -- CUSTOMER-RECORD (500 bytes)."""

    cust_id: str = ""                    # PIC 9(09)
    cust_first_name: str = ""            # PIC X(25)
    cust_middle_name: str = ""           # PIC X(25)
    cust_last_name: str = ""             # PIC X(25)
    cust_addr_line_1: str = ""           # PIC X(50)
    cust_addr_line_2: str = ""           # PIC X(50)
    cust_addr_line_3: str = ""           # PIC X(50)
    cust_addr_state_cd: str = ""         # PIC X(02)
    cust_addr_country_cd: str = ""       # PIC X(03)
    cust_addr_zip: str = ""              # PIC X(10)
    cust_phone_num_1: str = ""           # PIC X(15)
    cust_phone_num_2: str = ""           # PIC X(15)
    cust_ssn: str = ""                   # PIC 9(09)
    cust_govt_issued_id: str = ""        # PIC X(20)
    cust_dob_yyyymmdd: str = ""          # PIC X(10)
    cust_eft_account_id: str = ""        # PIC X(10)
    cust_pri_card_holder_ind: str = ""   # PIC X(01)
    cust_fico_credit_score: str = ""     # PIC 9(03)


@dataclass
class AccountRecord:
    """CVACT01Y -- ACCOUNT-RECORD (300 bytes)."""

    acct_id: str = ""                     # PIC 9(11)
    acct_active_status: str = ""          # PIC X(01)
    acct_curr_bal: Decimal = field(default_factory=lambda: Decimal("0.00"))
    acct_credit_limit: Decimal = field(default_factory=lambda: Decimal("0.00"))
    acct_cash_credit_limit: Decimal = field(default_factory=lambda: Decimal("0.00"))
    acct_open_date: str = ""              # PIC X(10)
    acct_expiration_date: str = ""        # PIC X(10)
    acct_reissue_date: str = ""           # PIC X(10)
    acct_curr_cyc_credit: Decimal = field(default_factory=lambda: Decimal("0.00"))
    acct_curr_cyc_debit: Decimal = field(default_factory=lambda: Decimal("0.00"))
    acct_addr_zip: str = ""               # PIC X(10)
    acct_group_id: str = ""               # PIC X(10)


# ---------------------------------------------------------------------------
# DataFrame → record helpers
# ---------------------------------------------------------------------------

def _row_to_transaction(row: pd.Series) -> TransactionRecord:
    return TransactionRecord(
        trnx_card_num=str(row["trnx_card_num"]),
        trnx_id=str(row["trnx_id"]),
        trnx_type_cd=str(row.get("trnx_type_cd", "")),
        trnx_cat_cd=str(row.get("trnx_cat_cd", "")),
        trnx_source=str(row.get("trnx_source", "")),
        trnx_desc=str(row.get("trnx_desc", "")),
        trnx_amt=Decimal(str(row.get("trnx_amt", "0.00"))),
        trnx_merchant_id=str(row.get("trnx_merchant_id", "")),
        trnx_merchant_name=str(row.get("trnx_merchant_name", "")),
        trnx_merchant_city=str(row.get("trnx_merchant_city", "")),
        trnx_merchant_zip=str(row.get("trnx_merchant_zip", "")),
        trnx_orig_ts=str(row.get("trnx_orig_ts", "")),
        trnx_proc_ts=str(row.get("trnx_proc_ts", "")),
    )


def _row_to_xref(row: pd.Series) -> XrefRecord:
    return XrefRecord(
        xref_card_num=str(row["xref_card_num"]),
        xref_cust_id=str(row["xref_cust_id"]),
        xref_acct_id=str(row["xref_acct_id"]),
    )


def _row_to_customer(row: pd.Series) -> CustomerRecord:
    return CustomerRecord(
        cust_id=str(row["cust_id"]),
        cust_first_name=str(row.get("cust_first_name", "")),
        cust_middle_name=str(row.get("cust_middle_name", "")),
        cust_last_name=str(row.get("cust_last_name", "")),
        cust_addr_line_1=str(row.get("cust_addr_line_1", "")),
        cust_addr_line_2=str(row.get("cust_addr_line_2", "")),
        cust_addr_line_3=str(row.get("cust_addr_line_3", "")),
        cust_addr_state_cd=str(row.get("cust_addr_state_cd", "")),
        cust_addr_country_cd=str(row.get("cust_addr_country_cd", "")),
        cust_addr_zip=str(row.get("cust_addr_zip", "")),
        cust_phone_num_1=str(row.get("cust_phone_num_1", "")),
        cust_phone_num_2=str(row.get("cust_phone_num_2", "")),
        cust_ssn=str(row.get("cust_ssn", "")),
        cust_govt_issued_id=str(row.get("cust_govt_issued_id", "")),
        cust_dob_yyyymmdd=str(row.get("cust_dob_yyyymmdd", "")),
        cust_eft_account_id=str(row.get("cust_eft_account_id", "")),
        cust_pri_card_holder_ind=str(row.get("cust_pri_card_holder_ind", "")),
        cust_fico_credit_score=str(row.get("cust_fico_credit_score", "")),
    )


def _row_to_account(row: pd.Series) -> AccountRecord:
    return AccountRecord(
        acct_id=str(row["acct_id"]),
        acct_active_status=str(row.get("acct_active_status", "")),
        acct_curr_bal=Decimal(str(row.get("acct_curr_bal", "0.00"))),
        acct_credit_limit=Decimal(str(row.get("acct_credit_limit", "0.00"))),
        acct_cash_credit_limit=Decimal(str(row.get("acct_cash_credit_limit", "0.00"))),
        acct_open_date=str(row.get("acct_open_date", "")),
        acct_expiration_date=str(row.get("acct_expiration_date", "")),
        acct_reissue_date=str(row.get("acct_reissue_date", "")),
        acct_curr_cyc_credit=Decimal(str(row.get("acct_curr_cyc_credit", "0.00"))),
        acct_curr_cyc_debit=Decimal(str(row.get("acct_curr_cyc_debit", "0.00"))),
        acct_addr_zip=str(row.get("acct_addr_zip", "")),
        acct_group_id=str(row.get("acct_group_id", "")),
    )


# ---------------------------------------------------------------------------
# VSAM-style file wrappers
# ---------------------------------------------------------------------------


class VsamSequentialFile:
    """Sequential-access VSAM file (TRNXFILE, XREFFILE).

    Records are read one at a time in key order.
    """

    def __init__(self, df: pd.DataFrame, row_converter):
        self._df = df
        self._converter = row_converter
        self._iter: Optional[Iterator] = None
        self._is_open = False

    def open(self) -> str:
        self._iter = self._df.iterrows()
        self._is_open = True
        return RC_OK

    def read(self):
        if not self._is_open:
            return RC_ERROR, None
        try:
            _, row = next(self._iter)
            return RC_OK, self._converter(row)
        except StopIteration:
            return RC_EOF, None

    def close(self) -> str:
        self._is_open = False
        self._iter = None
        return RC_OK


class VsamKeyedFile:
    """Random (keyed) access VSAM file (CUSTFILE, ACCTFILE).

    Records are read by primary key.
    """

    def __init__(self, df: pd.DataFrame, key_column: str, row_converter):
        self._df = df
        self._key_column = key_column
        self._converter = row_converter
        self._is_open = False

    def open(self) -> str:
        self._is_open = True
        return RC_OK

    def read_by_key(self, key: str):
        if not self._is_open:
            return RC_ERROR, None
        matches = self._df[self._df[self._key_column].astype(str) == str(key)]
        if matches.empty:
            return RC_ERROR, None
        return RC_OK, self._converter(matches.iloc[0])

    def close(self) -> str:
        self._is_open = False
        return RC_OK


# ---------------------------------------------------------------------------
# FileManager -- coordinates all four files (mirrors CBSTM03B dispatch)
# ---------------------------------------------------------------------------


class FileManager:
    """Top-level I/O manager reproducing CBSTM03B's file dispatch.

    Instantiate with pandas DataFrames (or CSV file paths) for the four
    input files; call ``open_all`` / ``close_all`` and the individual
    read methods.
    """

    def __init__(
        self,
        trnx_df: pd.DataFrame,
        xref_df: pd.DataFrame,
        cust_df: pd.DataFrame,
        acct_df: pd.DataFrame,
    ):
        self.trnx_file = VsamSequentialFile(trnx_df, _row_to_transaction)
        self.xref_file = VsamSequentialFile(xref_df, _row_to_xref)
        self.cust_file = VsamKeyedFile(cust_df, "cust_id", _row_to_customer)
        self.acct_file = VsamKeyedFile(acct_df, "acct_id", _row_to_account)

    # -- convenience --

    def open_all(self) -> None:
        for f in (self.trnx_file, self.xref_file, self.cust_file, self.acct_file):
            rc = f.open()
            if rc not in (RC_OK, "04"):
                raise RuntimeError(f"Failed to open file: rc={rc}")

    def close_all(self) -> None:
        for f in (self.trnx_file, self.xref_file, self.cust_file, self.acct_file):
            rc = f.close()
            if rc not in (RC_OK, "04"):
                raise RuntimeError(f"Failed to close file: rc={rc}")

    # -- TRNXFILE (sequential) --

    def read_transaction(self):
        return self.trnx_file.read()

    # -- XREFFILE (sequential) --

    def read_xref(self):
        return self.xref_file.read()

    # -- CUSTFILE (keyed) --

    def read_customer(self, cust_id: str):
        return self.cust_file.read_by_key(cust_id)

    # -- ACCTFILE (keyed) --

    def read_account(self, acct_id: str):
        return self.acct_file.read_by_key(acct_id)

    # -- Factory from CSV paths --

    @classmethod
    def from_csv_files(
        cls,
        trnx_path: str,
        xref_path: str,
        cust_path: str,
        acct_path: str,
    ) -> "FileManager":
        trnx_df = pd.read_csv(trnx_path, dtype=str).fillna("")
        xref_df = pd.read_csv(xref_path, dtype=str).fillna("")
        cust_df = pd.read_csv(cust_path, dtype=str).fillna("")
        acct_df = pd.read_csv(acct_path, dtype=str).fillna("")
        return cls(trnx_df, xref_df, cust_df, acct_df)
