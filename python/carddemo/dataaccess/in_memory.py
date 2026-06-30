"""In-memory (pandas-backed) implementations of the repository interfaces.

Each repository stores records in a ``pandas.DataFrame`` using the same
column names as the COBOL record fields.  Fixed-width keys (e.g. 16-byte
zero-padded card numbers) are stored as-is and compared exactly.

This mirrors how the existing ``transaction_validation.py`` used pandas
DataFrames for VSAM lookups.
"""

from __future__ import annotations

from typing import Iterator, Optional

import pandas as pd

from carddemo.models.account import AccountRecord
from carddemo.models.card import CardRecord
from carddemo.models.card_xref import CardXrefRecord
from carddemo.models.customer import CustomerRecord
from carddemo.models.disclosure_group import DisclosureGroupRecord
from carddemo.models.transaction import TransactionRecord
from carddemo.models.transaction_category import TranCatBalRecord

from carddemo.dataaccess.repository import (
    AccountRepository,
    CardRepository,
    CardXrefRepository,
    CustomerRepository,
    DisclosureGroupRepository,
    TranCatBalRepository,
    TransactionRepository,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record_to_dict(record: object) -> dict:
    """Convert a dataclass record to a dict, excluding class-level metadata."""
    d = {}
    for k, v in record.__dict__.items():
        if k.startswith("RECORD_LENGTH") or k.startswith("FIELD_WIDTHS"):
            continue
        d[k] = v
    return d


# ---------------------------------------------------------------------------
# Account
# ---------------------------------------------------------------------------


class InMemoryAccountRepository(AccountRepository):
    """ACCTFILE backed by a pandas DataFrame keyed on ``acct_id``."""

    def __init__(self, df: Optional[pd.DataFrame] = None) -> None:
        if df is not None:
            self._df = df.copy()
        else:
            self._df = pd.DataFrame(
                columns=[
                    "acct_id", "acct_active_status", "acct_curr_bal",
                    "acct_credit_limit", "acct_cash_credit_limit",
                    "acct_open_date", "acct_expiration_date", "acct_reissue_date",
                    "acct_curr_cyc_credit", "acct_curr_cyc_debit",
                    "acct_addr_zip", "acct_group_id",
                ]
            )

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    def find_by_id(self, acct_id: int) -> Optional[AccountRecord]:
        matches = self._df.loc[self._df["acct_id"] == acct_id]
        if matches.empty:
            return None
        row = matches.iloc[0]
        return AccountRecord(
            acct_id=int(row["acct_id"]),
            acct_active_status=str(row.get("acct_active_status", "")),
            acct_curr_bal=row.get("acct_curr_bal", AccountRecord.acct_curr_bal),
            acct_credit_limit=row.get("acct_credit_limit", AccountRecord.acct_credit_limit),
            acct_cash_credit_limit=row.get("acct_cash_credit_limit", AccountRecord.acct_cash_credit_limit),
            acct_open_date=str(row.get("acct_open_date", "")),
            acct_expiration_date=str(row.get("acct_expiration_date", "")),
            acct_reissue_date=str(row.get("acct_reissue_date", "")),
            acct_curr_cyc_credit=row.get("acct_curr_cyc_credit", AccountRecord.acct_curr_cyc_credit),
            acct_curr_cyc_debit=row.get("acct_curr_cyc_debit", AccountRecord.acct_curr_cyc_debit),
            acct_addr_zip=str(row.get("acct_addr_zip", "")),
            acct_group_id=str(row.get("acct_group_id", "")),
        )

    def update(self, record: AccountRecord) -> None:
        idx = self._df.index[self._df["acct_id"] == record.acct_id]
        if idx.empty:
            raise KeyError(f"Account {record.acct_id} not found for update")
        d = _record_to_dict(record)
        for col, val in d.items():
            if col in self._df.columns:
                self._df.at[idx[0], col] = val

    def add(self, record: AccountRecord) -> None:
        d = _record_to_dict(record)
        self._df = pd.concat(
            [self._df, pd.DataFrame([d])], ignore_index=True
        )

    def iter_all(self) -> Iterator[AccountRecord]:
        for _, row in self._df.iterrows():
            yield self.find_by_id(int(row["acct_id"]))  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Card
# ---------------------------------------------------------------------------


class InMemoryCardRepository(CardRepository):
    """CARDFILE backed by pandas, keyed on ``card_num``."""

    def __init__(self, df: Optional[pd.DataFrame] = None) -> None:
        if df is not None:
            self._df = df.copy()
        else:
            self._df = pd.DataFrame(
                columns=[
                    "card_num", "card_acct_id", "card_cvv_cd",
                    "card_embossed_name", "card_expiration_date",
                    "card_active_status",
                ]
            )

    def find_by_card_num(self, card_num: str) -> Optional[CardRecord]:
        matches = self._df.loc[self._df["card_num"] == card_num]
        if matches.empty:
            return None
        row = matches.iloc[0]
        return CardRecord(
            card_num=str(row["card_num"]),
            card_acct_id=int(row["card_acct_id"]),
            card_cvv_cd=int(row["card_cvv_cd"]),
            card_embossed_name=str(row["card_embossed_name"]),
            card_expiration_date=str(row["card_expiration_date"]),
            card_active_status=str(row["card_active_status"]),
        )

    def iter_all(self) -> Iterator[CardRecord]:
        for _, row in self._df.iterrows():
            yield self.find_by_card_num(str(row["card_num"]))  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Card Cross-Reference
# ---------------------------------------------------------------------------


class InMemoryCardXrefRepository(CardXrefRepository):
    """XREFFILE with primary key ``xref_card_num`` and AIX ``xref_acct_id``."""

    def __init__(self, df: Optional[pd.DataFrame] = None) -> None:
        if df is not None:
            self._df = df.copy()
        else:
            self._df = pd.DataFrame(
                columns=["xref_card_num", "xref_cust_id", "xref_acct_id"]
            )

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    def find_by_card_num(self, card_num: str) -> Optional[CardXrefRecord]:
        matches = self._df.loc[self._df["xref_card_num"] == card_num]
        if matches.empty:
            return None
        row = matches.iloc[0]
        return CardXrefRecord(
            xref_card_num=str(row["xref_card_num"]),
            xref_cust_id=int(row["xref_cust_id"]),
            xref_acct_id=int(row["xref_acct_id"]),
        )

    def find_by_acct_id(self, acct_id: int) -> Optional[CardXrefRecord]:
        matches = self._df.loc[self._df["xref_acct_id"] == acct_id]
        if matches.empty:
            return None
        row = matches.iloc[0]
        return CardXrefRecord(
            xref_card_num=str(row["xref_card_num"]),
            xref_cust_id=int(row["xref_cust_id"]),
            xref_acct_id=int(row["xref_acct_id"]),
        )

    def iter_all(self) -> Iterator[CardXrefRecord]:
        for _, row in self._df.iterrows():
            yield CardXrefRecord(
                xref_card_num=str(row["xref_card_num"]),
                xref_cust_id=int(row["xref_cust_id"]),
                xref_acct_id=int(row["xref_acct_id"]),
            )


# ---------------------------------------------------------------------------
# Customer
# ---------------------------------------------------------------------------


class InMemoryCustomerRepository(CustomerRepository):
    """CUSTFILE keyed on ``cust_id``."""

    def __init__(self, df: Optional[pd.DataFrame] = None) -> None:
        if df is not None:
            self._df = df.copy()
        else:
            self._df = pd.DataFrame(columns=["cust_id"])

    def find_by_id(self, cust_id: int) -> Optional[CustomerRecord]:
        matches = self._df.loc[self._df["cust_id"] == cust_id]
        if matches.empty:
            return None
        row = matches.iloc[0]
        return CustomerRecord(
            cust_id=int(row["cust_id"]),
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
            cust_ssn=int(row.get("cust_ssn", 0)),
            cust_govt_issued_id=str(row.get("cust_govt_issued_id", "")),
            cust_dob_yyyy_mm_dd=str(row.get("cust_dob_yyyy_mm_dd", "")),
            cust_eft_account_id=str(row.get("cust_eft_account_id", "")),
            cust_pri_card_holder_ind=str(row.get("cust_pri_card_holder_ind", "")),
            cust_fico_credit_score=int(row.get("cust_fico_credit_score", 0)),
        )

    def iter_all(self) -> Iterator[CustomerRecord]:
        for _, row in self._df.iterrows():
            yield self.find_by_id(int(row["cust_id"]))  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Disclosure Group
# ---------------------------------------------------------------------------


class InMemoryDisclosureGroupRepository(DisclosureGroupRepository):
    """DISCGRP keyed on composite (group_id, type_cd, cat_cd)."""

    def __init__(self, df: Optional[pd.DataFrame] = None) -> None:
        if df is not None:
            self._df = df.copy()
        else:
            self._df = pd.DataFrame(
                columns=[
                    "dis_acct_group_id", "dis_tran_type_cd",
                    "dis_tran_cat_cd", "dis_int_rate",
                ]
            )

    def find_by_key(
        self,
        acct_group_id: str,
        tran_type_cd: str,
        tran_cat_cd: int,
    ) -> Optional[DisclosureGroupRecord]:
        matches = self._df.loc[
            (self._df["dis_acct_group_id"] == acct_group_id)
            & (self._df["dis_tran_type_cd"] == tran_type_cd)
            & (self._df["dis_tran_cat_cd"] == tran_cat_cd)
        ]
        if matches.empty:
            return None
        row = matches.iloc[0]
        return DisclosureGroupRecord(
            dis_acct_group_id=str(row["dis_acct_group_id"]),
            dis_tran_type_cd=str(row["dis_tran_type_cd"]),
            dis_tran_cat_cd=int(row["dis_tran_cat_cd"]),
            dis_int_rate=row["dis_int_rate"],
        )

    def iter_all(self) -> Iterator[DisclosureGroupRecord]:
        for _, row in self._df.iterrows():
            yield DisclosureGroupRecord(
                dis_acct_group_id=str(row["dis_acct_group_id"]),
                dis_tran_type_cd=str(row["dis_tran_type_cd"]),
                dis_tran_cat_cd=int(row["dis_tran_cat_cd"]),
                dis_int_rate=row["dis_int_rate"],
            )


# ---------------------------------------------------------------------------
# Transaction Category Balance
# ---------------------------------------------------------------------------


class InMemoryTranCatBalRepository(TranCatBalRepository):
    """TCATBALF keyed on composite (acct_id, type_cd, cat_cd)."""

    def __init__(self, df: Optional[pd.DataFrame] = None) -> None:
        if df is not None:
            self._df = df.copy()
        else:
            self._df = pd.DataFrame(
                columns=[
                    "trancat_acct_id", "trancat_type_cd",
                    "trancat_cd", "tran_cat_bal",
                ]
            )

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    def find_by_key(
        self,
        acct_id: int,
        type_cd: str,
        cat_cd: int,
    ) -> Optional[TranCatBalRecord]:
        matches = self._df.loc[
            (self._df["trancat_acct_id"] == acct_id)
            & (self._df["trancat_type_cd"] == type_cd)
            & (self._df["trancat_cd"] == cat_cd)
        ]
        if matches.empty:
            return None
        row = matches.iloc[0]
        return TranCatBalRecord(
            trancat_acct_id=int(row["trancat_acct_id"]),
            trancat_type_cd=str(row["trancat_type_cd"]),
            trancat_cd=int(row["trancat_cd"]),
            tran_cat_bal=row["tran_cat_bal"],
        )

    def add(self, record: TranCatBalRecord) -> None:
        d = _record_to_dict(record)
        self._df = pd.concat(
            [self._df, pd.DataFrame([d])], ignore_index=True
        )

    def update(self, record: TranCatBalRecord) -> None:
        mask = (
            (self._df["trancat_acct_id"] == record.trancat_acct_id)
            & (self._df["trancat_type_cd"] == record.trancat_type_cd)
            & (self._df["trancat_cd"] == record.trancat_cd)
        )
        idx = self._df.index[mask]
        if idx.empty:
            raise KeyError(
                f"TranCatBal record not found for key: "
                f"{record.trancat_acct_id}/{record.trancat_type_cd}/{record.trancat_cd}"
            )
        self._df.at[idx[0], "tran_cat_bal"] = record.tran_cat_bal

    def iter_all(self) -> Iterator[TranCatBalRecord]:
        for _, row in self._df.iterrows():
            yield TranCatBalRecord(
                trancat_acct_id=int(row["trancat_acct_id"]),
                trancat_type_cd=str(row["trancat_type_cd"]),
                trancat_cd=int(row["trancat_cd"]),
                tran_cat_bal=row["tran_cat_bal"],
            )


# ---------------------------------------------------------------------------
# Transaction
# ---------------------------------------------------------------------------


class InMemoryTransactionRepository(TransactionRepository):
    """TRANSACT keyed on ``tran_id``."""

    def __init__(self, df: Optional[pd.DataFrame] = None) -> None:
        if df is not None:
            self._df = df.copy()
        else:
            self._df = pd.DataFrame(
                columns=[
                    "tran_id", "tran_type_cd", "tran_cat_cd", "tran_source",
                    "tran_desc", "tran_amt", "tran_merchant_id",
                    "tran_merchant_name", "tran_merchant_city",
                    "tran_merchant_zip", "tran_card_num",
                    "tran_orig_ts", "tran_proc_ts",
                ]
            )

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    def find_by_id(self, tran_id: str) -> Optional[TransactionRecord]:
        matches = self._df.loc[self._df["tran_id"] == tran_id]
        if matches.empty:
            return None
        row = matches.iloc[0]
        return TransactionRecord(
            tran_id=str(row["tran_id"]),
            tran_type_cd=str(row["tran_type_cd"]),
            tran_cat_cd=int(row["tran_cat_cd"]),
            tran_source=str(row["tran_source"]),
            tran_desc=str(row["tran_desc"]),
            tran_amt=row["tran_amt"],
            tran_merchant_id=int(row["tran_merchant_id"]),
            tran_merchant_name=str(row["tran_merchant_name"]),
            tran_merchant_city=str(row["tran_merchant_city"]),
            tran_merchant_zip=str(row["tran_merchant_zip"]),
            tran_card_num=str(row["tran_card_num"]),
            tran_orig_ts=str(row["tran_orig_ts"]),
            tran_proc_ts=str(row["tran_proc_ts"]),
        )

    def add(self, record: TransactionRecord) -> None:
        d = _record_to_dict(record)
        self._df = pd.concat(
            [self._df, pd.DataFrame([d])], ignore_index=True
        )

    def iter_all(self) -> Iterator[TransactionRecord]:
        for _, row in self._df.iterrows():
            yield self.find_by_id(str(row["tran_id"]))  # type: ignore[misc]
