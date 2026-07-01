"""
I/O layer migrated from CBSTM03B.CBL.

CBSTM03B is a subroutine called by CBSTM03A for all data-file I/O.
It handles four VSAM files:

* TRNXFILE -- transactions (INDEXED, SEQUENTIAL access for full scan)
* XREFFILE -- card cross-reference (INDEXED, SEQUENTIAL access)
* CUSTFILE -- customer master (INDEXED, RANDOM access by CUST-ID)
* ACCTFILE -- account master (INDEXED, RANDOM access by ACCT-ID)

This Python module reproduces the same access semantics using pandas
DataFrames loaded from CSV files.  Return codes mirror the COBOL file
status codes used by CBSTM03B:

* '00' -- success
* '10' -- end-of-file (sequential read past last record)
* '23' -- record not found (keyed read)

Copybook field layouts
----------------------
* COSTM01  -- TRNX-RECORD  (350 bytes)
* CVACT03Y -- CARD-XREF-RECORD (50 bytes)
* CUSTREC  -- CUSTOMER-RECORD  (500 bytes)
* CVACT01Y -- ACCOUNT-RECORD   (300 bytes)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

import pandas as pd


RC_OK = "00"
RC_EOF = "10"
RC_NOT_FOUND = "23"


@dataclass
class TrnxRecord:
    """COSTM01 -- TRNX-RECORD (350 bytes)."""

    trnx_card_num: str = ""       # PIC X(16)
    trnx_id: str = ""             # PIC X(16)
    trnx_type_cd: str = ""        # PIC X(02)
    trnx_cat_cd: str = ""         # PIC 9(04)
    trnx_source: str = ""         # PIC X(10)
    trnx_desc: str = ""           # PIC X(100)
    trnx_amt: Decimal = Decimal("0.00")  # PIC S9(09)V99
    trnx_merchant_id: str = ""    # PIC 9(09)
    trnx_merchant_name: str = ""  # PIC X(50)
    trnx_merchant_city: str = ""  # PIC X(50)
    trnx_merchant_zip: str = ""   # PIC X(10)
    trnx_orig_ts: str = ""        # PIC X(26)
    trnx_proc_ts: str = ""        # PIC X(26)


@dataclass
class XrefRecord:
    """CVACT03Y -- CARD-XREF-RECORD (50 bytes)."""

    xref_card_num: str = ""  # PIC X(16)
    xref_cust_id: str = ""   # PIC 9(09)
    xref_acct_id: str = ""   # PIC 9(11)


@dataclass
class CustomerRecord:
    """CUSTREC -- CUSTOMER-RECORD (500 bytes)."""

    cust_id: str = ""                   # PIC 9(09)
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
    cust_ssn: str = ""                  # PIC 9(09)
    cust_govt_issued_id: str = ""       # PIC X(20)
    cust_dob_yyyymmdd: str = ""         # PIC X(10)
    cust_eft_account_id: str = ""       # PIC X(10)
    cust_pri_card_holder_ind: str = ""  # PIC X(01)
    cust_fico_credit_score: str = ""    # PIC 9(03)


@dataclass
class AccountRecord:
    """CVACT01Y -- ACCOUNT-RECORD (300 bytes)."""

    acct_id: str = ""                    # PIC 9(11)
    acct_active_status: str = ""         # PIC X(01)
    acct_curr_bal: Decimal = Decimal("0.00")   # PIC S9(10)V99
    acct_credit_limit: Decimal = Decimal("0.00")
    acct_cash_credit_limit: Decimal = Decimal("0.00")
    acct_open_date: str = ""             # PIC X(10)
    acct_expiration_date: str = ""       # PIC X(10)
    acct_reissue_date: str = ""          # PIC X(10)
    acct_curr_cyc_credit: Decimal = Decimal("0.00")
    acct_curr_cyc_debit: Decimal = Decimal("0.00")
    acct_addr_zip: str = ""              # PIC X(10)
    acct_group_id: str = ""              # PIC X(10)


def _parse_trnx_record(row: Dict[str, Any]) -> TrnxRecord:
    return TrnxRecord(
        trnx_card_num=str(row.get("trnx_card_num", "")),
        trnx_id=str(row.get("trnx_id", "")),
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


def _parse_xref_record(row: Dict[str, Any]) -> XrefRecord:
    return XrefRecord(
        xref_card_num=str(row.get("xref_card_num", "")),
        xref_cust_id=str(row.get("xref_cust_id", "")),
        xref_acct_id=str(row.get("xref_acct_id", "")),
    )


def _parse_customer_record(row: Dict[str, Any]) -> CustomerRecord:
    return CustomerRecord(
        cust_id=str(row.get("cust_id", "")),
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


def _parse_account_record(row: Dict[str, Any]) -> AccountRecord:
    return AccountRecord(
        acct_id=str(row.get("acct_id", "")),
        acct_active_status=str(row.get("acct_active_status", "")),
        acct_curr_bal=Decimal(str(row.get("acct_curr_bal", "0.00"))),
        acct_credit_limit=Decimal(str(row.get("acct_credit_limit", "0.00"))),
        acct_cash_credit_limit=Decimal(
            str(row.get("acct_cash_credit_limit", "0.00"))
        ),
        acct_open_date=str(row.get("acct_open_date", "")),
        acct_expiration_date=str(row.get("acct_expiration_date", "")),
        acct_reissue_date=str(row.get("acct_reissue_date", "")),
        acct_curr_cyc_credit=Decimal(
            str(row.get("acct_curr_cyc_credit", "0.00"))
        ),
        acct_curr_cyc_debit=Decimal(
            str(row.get("acct_curr_cyc_debit", "0.00"))
        ),
        acct_addr_zip=str(row.get("acct_addr_zip", "")),
        acct_group_id=str(row.get("acct_group_id", "")),
    )


class FileStore:
    """Reproduces CBSTM03B's I/O layer.

    Each VSAM file is loaded from a CSV into a list of dataclass records.
    Sequential and keyed access is provided with COBOL-compatible return
    codes.
    """

    def __init__(
        self,
        trnx_path: str,
        xref_path: str,
        cust_path: str,
        acct_path: str,
    ) -> None:
        self._paths = {
            "TRNXFILE": trnx_path,
            "XREFFILE": xref_path,
            "CUSTFILE": cust_path,
            "ACCTFILE": acct_path,
        }
        self._data: Dict[str, List[Any]] = {}
        self._cursors: Dict[str, int] = {}
        self._open: Dict[str, bool] = {}

    def open(self, dd_name: str) -> str:
        """Open a file (load CSV data). Returns RC."""
        path = self._paths.get(dd_name)
        if path is None:
            return "92"
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
        if dd_name == "TRNXFILE":
            self._data[dd_name] = [
                _parse_trnx_record(row) for _, row in df.iterrows()
            ]
        elif dd_name == "XREFFILE":
            self._data[dd_name] = [
                _parse_xref_record(row) for _, row in df.iterrows()
            ]
        elif dd_name == "CUSTFILE":
            self._data[dd_name] = [
                _parse_customer_record(row) for _, row in df.iterrows()
            ]
        elif dd_name == "ACCTFILE":
            self._data[dd_name] = [
                _parse_account_record(row) for _, row in df.iterrows()
            ]
        self._cursors[dd_name] = 0
        self._open[dd_name] = True
        return RC_OK

    def read_sequential(self, dd_name: str) -> tuple[str, Optional[Any]]:
        """Sequential read. Returns (RC, record_or_None)."""
        if not self._open.get(dd_name):
            return ("92", None)
        records = self._data.get(dd_name, [])
        cursor = self._cursors.get(dd_name, 0)
        if cursor >= len(records):
            return (RC_EOF, None)
        record = records[cursor]
        self._cursors[dd_name] = cursor + 1
        return (RC_OK, record)

    def read_by_key(
        self, dd_name: str, key: str, key_len: int
    ) -> tuple[str, Optional[Any]]:
        """Keyed read. Returns (RC, record_or_None)."""
        if not self._open.get(dd_name):
            return ("92", None)
        records = self._data.get(dd_name, [])
        search_key = key[:key_len].strip()
        for rec in records:
            if dd_name == "CUSTFILE":
                if rec.cust_id.strip() == search_key:
                    return (RC_OK, rec)
            elif dd_name == "ACCTFILE":
                if rec.acct_id.strip() == search_key:
                    return (RC_OK, rec)
        return (RC_NOT_FOUND, None)

    def close(self, dd_name: str) -> str:
        """Close a file. Returns RC."""
        self._open[dd_name] = False
        return RC_OK
