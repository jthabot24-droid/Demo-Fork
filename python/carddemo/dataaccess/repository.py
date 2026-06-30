"""Abstract repository interfaces replacing VSAM keyed-file access.

Each interface mirrors a COBOL ``SELECT ... ORGANIZATION IS INDEXED``
file-control entry.  The concrete implementation in ``in_memory.py``
backs these with pandas DataFrames; alternative implementations could
use SQLAlchemy, DuckDB, or another relational store.

Key semantics preserved from COBOL/VSAM:

* **KSDS primary key** → ``find_by_<key>(key) -> Optional[record]``
* **Alternate index (AIX)** → ``find_by_<alt_key>(key) -> Optional[record]``
* **Sequential read** → ``iter_all() -> Iterator[record]``
* **REWRITE** → ``update(record)``
* **WRITE** → ``add(record)``
* Fixed-width keys (e.g. 16-byte zero-padded card numbers) are
  maintained by callers -- the repository does not pad or truncate.
"""

from __future__ import annotations

import abc
from typing import Iterator, Optional

from carddemo.models.account import AccountRecord
from carddemo.models.card import CardRecord
from carddemo.models.card_xref import CardXrefRecord
from carddemo.models.customer import CustomerRecord
from carddemo.models.disclosure_group import DisclosureGroupRecord
from carddemo.models.transaction import TransactionRecord
from carddemo.models.transaction_category import TranCatBalRecord


class AccountRepository(abc.ABC):
    """ACCTFILE -- ORGANIZATION IS INDEXED, RECORD KEY IS FD-ACCT-ID."""

    @abc.abstractmethod
    def find_by_id(self, acct_id: int) -> Optional[AccountRecord]:
        ...

    @abc.abstractmethod
    def update(self, record: AccountRecord) -> None:
        ...

    @abc.abstractmethod
    def add(self, record: AccountRecord) -> None:
        ...

    @abc.abstractmethod
    def iter_all(self) -> Iterator[AccountRecord]:
        ...


class CardRepository(abc.ABC):
    """CARDFILE -- RECORD KEY IS FD-CARD-NUM."""

    @abc.abstractmethod
    def find_by_card_num(self, card_num: str) -> Optional[CardRecord]:
        ...

    @abc.abstractmethod
    def iter_all(self) -> Iterator[CardRecord]:
        ...


class CardXrefRepository(abc.ABC):
    """XREFFILE -- RECORD KEY IS FD-XREF-CARD-NUM,
    ALTERNATE RECORD KEY IS FD-XREF-ACCT-ID.
    """

    @abc.abstractmethod
    def find_by_card_num(self, card_num: str) -> Optional[CardXrefRecord]:
        ...

    @abc.abstractmethod
    def find_by_acct_id(self, acct_id: int) -> Optional[CardXrefRecord]:
        ...

    @abc.abstractmethod
    def iter_all(self) -> Iterator[CardXrefRecord]:
        ...


class CustomerRepository(abc.ABC):
    """CUSTFILE -- RECORD KEY IS FD-CUST-ID."""

    @abc.abstractmethod
    def find_by_id(self, cust_id: int) -> Optional[CustomerRecord]:
        ...

    @abc.abstractmethod
    def iter_all(self) -> Iterator[CustomerRecord]:
        ...


class DisclosureGroupRepository(abc.ABC):
    """DISCGRP -- RECORD KEY IS FD-DISCGRP-KEY (group_id + type_cd + cat_cd)."""

    @abc.abstractmethod
    def find_by_key(
        self,
        acct_group_id: str,
        tran_type_cd: str,
        tran_cat_cd: int,
    ) -> Optional[DisclosureGroupRecord]:
        ...

    @abc.abstractmethod
    def iter_all(self) -> Iterator[DisclosureGroupRecord]:
        ...


class TranCatBalRepository(abc.ABC):
    """TCATBALF -- RECORD KEY IS FD-TRAN-CAT-KEY (acct_id + type_cd + cat_cd).
    Sequential access for interest calc; random access for posting.
    """

    @abc.abstractmethod
    def find_by_key(
        self,
        acct_id: int,
        type_cd: str,
        cat_cd: int,
    ) -> Optional[TranCatBalRecord]:
        ...

    @abc.abstractmethod
    def add(self, record: TranCatBalRecord) -> None:
        ...

    @abc.abstractmethod
    def update(self, record: TranCatBalRecord) -> None:
        ...

    @abc.abstractmethod
    def iter_all(self) -> Iterator[TranCatBalRecord]:
        ...


class TransactionRepository(abc.ABC):
    """TRANSACT -- RECORD KEY IS FD-TRANS-ID."""

    @abc.abstractmethod
    def find_by_id(self, tran_id: str) -> Optional[TransactionRecord]:
        ...

    @abc.abstractmethod
    def add(self, record: TransactionRecord) -> None:
        ...

    @abc.abstractmethod
    def iter_all(self) -> Iterator[TransactionRecord]:
        ...
