"""Data-access layer replacing VSAM file operations.

Provides a ``Repository`` abstraction that loads fixed-width ASCII sample files
into pandas DataFrames keyed the same way as the COBOL ``RECORD KEY`` fields,
offering get-by-key and sequential-iteration access to mirror VSAM ``RANDOM``
and ``SEQUENTIAL`` access modes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generic, Iterator, Optional, TypeVar

import pandas as pd

from carddemo.models.account import AccountRecord
from carddemo.models.card_xref import CardXrefRecord
from carddemo.models.customer import CustomerRecord
from carddemo.models.daily_transaction import DailyTransactionRecord
from carddemo.models.transaction import TransactionRecord

T = TypeVar("T")


class Repository(Generic[T]):
    """Base repository providing VSAM-like access over a flat file.

    Parameters
    ----------
    record_cls:
        The dataclass type that has ``from_record(line)`` and ``to_record()``
        methods.
    key_field:
        The dataclass attribute name used as the primary key (mirrors VSAM
        ``RECORD KEY``).
    alt_key_fields:
        Optional alternate key fields (mirrors VSAM ``ALTERNATE INDEX``).
    """

    def __init__(
        self,
        record_cls: type[T],
        key_field: str,
        alt_key_fields: Optional[list[str]] = None,
    ) -> None:
        self._record_cls = record_cls
        self._key_field = key_field
        self._alt_key_fields = alt_key_fields or []
        self._records: list[T] = []
        self._df: Optional[pd.DataFrame] = None

    def load(self, filepath: str | Path) -> pd.DataFrame:
        """Load a fixed-width ASCII file and return a DataFrame.

        Each line of the file is parsed via ``record_cls.from_record()``.
        The resulting DataFrame has one column per dataclass field.
        """
        filepath = Path(filepath)
        records: list[T] = []
        with open(filepath, "r", encoding="ascii", errors="replace") as fh:
            for line in fh:
                stripped = line.rstrip("\n").rstrip("\r")
                if not stripped:
                    continue
                records.append(self._record_cls.from_record(stripped))

        self._records = records
        if records:
            self._df = pd.DataFrame(
                [vars(r) for r in records]
            )
        else:
            self._df = pd.DataFrame()
        return self._df

    @property
    def dataframe(self) -> pd.DataFrame:
        """Access the loaded DataFrame."""
        if self._df is None:
            return pd.DataFrame()
        return self._df

    def get(self, key_value: object) -> Optional[T]:
        """VSAM RANDOM access — retrieve a single record by primary key."""
        for rec in self._records:
            if getattr(rec, self._key_field) == key_value:
                return rec
        return None

    def get_by_alt_key(self, alt_key: str, value: object) -> Optional[T]:
        """Retrieve a single record by an alternate key field."""
        for rec in self._records:
            if getattr(rec, alt_key) == value:
                return rec
        return None

    def iterate(self) -> Iterator[T]:
        """VSAM SEQUENTIAL access — iterate records in file order."""
        yield from self._records

    def __len__(self) -> int:
        return len(self._records)


class AccountRepository(Repository[AccountRecord]):
    """Repository for ACCTDATA (VSAM key: ``acct_id``)."""

    def __init__(self) -> None:
        super().__init__(AccountRecord, "acct_id")


class CardXrefRepository(Repository[CardXrefRecord]):
    """Repository for CARDXREF (VSAM key: ``xref_card_num``, AIX: ``xref_acct_id``)."""

    def __init__(self) -> None:
        super().__init__(
            CardXrefRecord,
            "xref_card_num",
            alt_key_fields=["xref_acct_id"],
        )


class TransactionRepository(Repository[TransactionRecord]):
    """Repository for TRANSACT (VSAM key: ``tran_id``, AIX: ``tran_card_num``)."""

    def __init__(self) -> None:
        super().__init__(
            TransactionRecord,
            "tran_id",
            alt_key_fields=["tran_card_num"],
        )


class DailyTransactionRepository(Repository[DailyTransactionRecord]):
    """Repository for DALYTRAN (VSAM key: ``dalytran_id``)."""

    def __init__(self) -> None:
        super().__init__(DailyTransactionRecord, "dalytran_id")


class CustomerRepository(Repository[CustomerRecord]):
    """Repository for CUSTDATA (VSAM key: ``cust_id``)."""

    def __init__(self) -> None:
        super().__init__(CustomerRecord, "cust_id")
