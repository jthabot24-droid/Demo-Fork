"""VSAM KSDS replacement -- abstract store and in-memory/CSV implementation.

The ``VsamStore`` ABC mirrors the operations available on a COBOL VSAM KSDS
file: random read-by-key, sequential scan, write, rewrite, and delete.

``InMemoryVsamStore`` keeps records in a Python ``dict`` keyed by a caller-
supplied key function and can round-trip through CSV files for persistence.
"""

from __future__ import annotations

import csv
import io
from abc import ABC, abstractmethod
from dataclasses import asdict, fields
from decimal import Decimal
from pathlib import Path
from typing import Callable, Generic, Iterator, Optional, Type, TypeVar

import pandas as pd

T = TypeVar("T")


class VsamStore(ABC, Generic[T]):
    """Abstract base class modelling VSAM KSDS file operations."""

    @abstractmethod
    def read(self, key: str) -> Optional[T]:
        """Random read by primary key.  Returns ``None`` on key-not-found."""

    @abstractmethod
    def write(self, record: T) -> None:
        """Add a new record.  Raises ``KeyError`` if the key already exists."""

    @abstractmethod
    def rewrite(self, record: T) -> None:
        """Update an existing record in-place.  Raises ``KeyError`` if absent."""

    @abstractmethod
    def delete(self, key: str) -> None:
        """Delete a record by primary key.  Raises ``KeyError`` if absent."""

    @abstractmethod
    def read_sequential(self) -> Iterator[T]:
        """Yield all records in primary-key order."""

    @abstractmethod
    def read_all(self) -> list[T]:
        """Return every record as a list (primary-key order)."""

    @abstractmethod
    def to_dataframe(self) -> pd.DataFrame:
        """Export the store contents as a pandas DataFrame."""


class InMemoryVsamStore(VsamStore[T]):
    """Dictionary-backed VSAM KSDS store with optional CSV persistence.

    Parameters
    ----------
    record_type:
        The dataclass type stored in this file.
    key_func:
        A callable that extracts the primary-key string from a record.
    """

    def __init__(
        self,
        record_type: Type[T],
        key_func: Callable[[T], str],
    ) -> None:
        self._record_type = record_type
        self._key_func = key_func
        self._records: dict[str, T] = {}

    # ------------------------------------------------------------------
    # VSAM operations
    # ------------------------------------------------------------------

    def read(self, key: str) -> Optional[T]:
        return self._records.get(key)

    def write(self, record: T) -> None:
        key = self._key_func(record)
        if key in self._records:
            raise KeyError(f"Duplicate key: {key!r}")
        self._records[key] = record

    def rewrite(self, record: T) -> None:
        key = self._key_func(record)
        if key not in self._records:
            raise KeyError(f"Key not found: {key!r}")
        self._records[key] = record

    def delete(self, key: str) -> None:
        if key not in self._records:
            raise KeyError(f"Key not found: {key!r}")
        del self._records[key]

    def read_sequential(self) -> Iterator[T]:
        for key in sorted(self._records):
            yield self._records[key]

    def read_all(self) -> list[T]:
        return list(self.read_sequential())

    def __len__(self) -> int:
        return len(self._records)

    def __contains__(self, key: str) -> bool:
        return key in self._records

    # ------------------------------------------------------------------
    # Convenience: write-if-absent or update-if-present
    # ------------------------------------------------------------------

    def upsert(self, record: T) -> None:
        """Insert or update regardless of prior existence."""
        self._records[self._key_func(record)] = record

    # ------------------------------------------------------------------
    # DataFrame interop
    # ------------------------------------------------------------------

    def to_dataframe(self) -> pd.DataFrame:
        if not self._records:
            return pd.DataFrame()
        rows = [asdict(r) for r in self.read_sequential()]
        return pd.DataFrame(rows)

    # ------------------------------------------------------------------
    # CSV round-trip
    # ------------------------------------------------------------------

    def save_csv(self, path: Path | str) -> None:
        """Persist the store to a CSV file."""
        path = Path(path)
        all_records = self.read_all()
        if not all_records:
            path.write_text("")
            return
        fieldnames = [f.name for f in fields(self._record_type)]
        with path.open("w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fieldnames)
            writer.writeheader()
            for rec in all_records:
                writer.writerow(asdict(rec))

    def load_csv(self, path: Path | str) -> None:
        """Load records from a CSV file, replacing current contents."""
        path = Path(path)
        self._records.clear()
        if not path.exists() or path.stat().st_size == 0:
            return
        type_map = {f.name: f.type for f in fields(self._record_type)}
        with path.open(newline="") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                kwargs = {}
                for fname, raw in row.items():
                    ftype = type_map.get(fname, "str")
                    kwargs[fname] = _coerce(raw, ftype)
                record = self._record_type(**kwargs)
                self._records[self._key_func(record)] = record


def _coerce(raw: str, type_hint: str) -> object:
    """Convert a CSV string value to the appropriate Python type."""
    if "Decimal" in str(type_hint):
        return Decimal(raw) if raw else Decimal("0.00")
    if "int" in str(type_hint):
        return int(raw) if raw else 0
    return raw
