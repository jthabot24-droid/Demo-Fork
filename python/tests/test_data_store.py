"""Tests for the VSAM-replacement data store (Phase 0)."""

from __future__ import annotations

import tempfile
from decimal import Decimal
from pathlib import Path

import pytest

from data.store import InMemoryVsamStore
from models.account import AccountRecord
from models.card_xref import CardXrefRecord


class TestInMemoryVsamStoreCRUD:
    """Basic CRUD operations matching VSAM KSDS semantics."""

    @pytest.fixture()
    def store(self) -> InMemoryVsamStore[AccountRecord]:
        return InMemoryVsamStore(
            AccountRecord, lambda r: f"{r.acct_id:011d}"
        )

    def test_write_and_read(self, store: InMemoryVsamStore[AccountRecord]) -> None:
        rec = AccountRecord(acct_id=42, acct_active_status="Y")
        store.write(rec)
        assert store.read(f"{42:011d}") is rec

    def test_read_missing_returns_none(self, store: InMemoryVsamStore[AccountRecord]) -> None:
        assert store.read("00000000099") is None

    def test_write_duplicate_raises(self, store: InMemoryVsamStore[AccountRecord]) -> None:
        rec = AccountRecord(acct_id=1)
        store.write(rec)
        with pytest.raises(KeyError, match="Duplicate key"):
            store.write(AccountRecord(acct_id=1))

    def test_rewrite_updates(self, store: InMemoryVsamStore[AccountRecord]) -> None:
        rec = AccountRecord(acct_id=1, acct_curr_bal=Decimal("100.00"))
        store.write(rec)
        updated = AccountRecord(acct_id=1, acct_curr_bal=Decimal("200.00"))
        store.rewrite(updated)
        assert store.read(f"{1:011d}").acct_curr_bal == Decimal("200.00")

    def test_rewrite_missing_raises(self, store: InMemoryVsamStore[AccountRecord]) -> None:
        with pytest.raises(KeyError, match="Key not found"):
            store.rewrite(AccountRecord(acct_id=999))

    def test_delete(self, store: InMemoryVsamStore[AccountRecord]) -> None:
        store.write(AccountRecord(acct_id=1))
        store.delete(f"{1:011d}")
        assert store.read(f"{1:011d}") is None

    def test_delete_missing_raises(self, store: InMemoryVsamStore[AccountRecord]) -> None:
        with pytest.raises(KeyError, match="Key not found"):
            store.delete("00000000001")

    def test_upsert_inserts_and_updates(self, store: InMemoryVsamStore[AccountRecord]) -> None:
        rec = AccountRecord(acct_id=1, acct_curr_bal=Decimal("100.00"))
        store.upsert(rec)
        assert len(store) == 1
        updated = AccountRecord(acct_id=1, acct_curr_bal=Decimal("200.00"))
        store.upsert(updated)
        assert len(store) == 1
        assert store.read(f"{1:011d}").acct_curr_bal == Decimal("200.00")


class TestSequentialAccess:
    """Sequential iteration should return records in key order."""

    def test_sequential_order(self) -> None:
        store: InMemoryVsamStore[AccountRecord] = InMemoryVsamStore(
            AccountRecord, lambda r: f"{r.acct_id:011d}"
        )
        for aid in [5, 2, 8, 1, 3]:
            store.write(AccountRecord(acct_id=aid))
        ids = [r.acct_id for r in store.read_sequential()]
        assert ids == [1, 2, 3, 5, 8]

    def test_read_all_returns_list(self) -> None:
        store: InMemoryVsamStore[AccountRecord] = InMemoryVsamStore(
            AccountRecord, lambda r: f"{r.acct_id:011d}"
        )
        store.write(AccountRecord(acct_id=1))
        store.write(AccountRecord(acct_id=2))
        assert len(store.read_all()) == 2


class TestDataFrameExport:
    """to_dataframe() should produce a usable pandas DataFrame."""

    def test_to_dataframe_columns(self) -> None:
        store: InMemoryVsamStore[CardXrefRecord] = InMemoryVsamStore(
            CardXrefRecord, lambda r: r.xref_card_num
        )
        store.write(CardXrefRecord(
            xref_card_num="4000000000000001", xref_cust_id=1, xref_acct_id=1
        ))
        df = store.to_dataframe()
        assert list(df.columns) == [
            "xref_card_num", "xref_cust_id", "xref_acct_id", "RECORD_LENGTH"
        ]
        assert len(df) == 1

    def test_empty_store_gives_empty_df(self) -> None:
        store: InMemoryVsamStore[AccountRecord] = InMemoryVsamStore(
            AccountRecord, lambda r: f"{r.acct_id:011d}"
        )
        df = store.to_dataframe()
        assert df.empty


class TestCsvRoundTrip:
    """CSV save / load round-trip preserves data."""

    def test_round_trip(self) -> None:
        store: InMemoryVsamStore[AccountRecord] = InMemoryVsamStore(
            AccountRecord, lambda r: f"{r.acct_id:011d}"
        )
        store.write(AccountRecord(
            acct_id=1, acct_curr_bal=Decimal("1234.56"), acct_active_status="Y"
        ))
        store.write(AccountRecord(
            acct_id=2, acct_curr_bal=Decimal("-99.99"), acct_active_status="N"
        ))

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            csv_path = Path(f.name)

        try:
            store.save_csv(csv_path)
            store2: InMemoryVsamStore[AccountRecord] = InMemoryVsamStore(
                AccountRecord, lambda r: f"{r.acct_id:011d}"
            )
            store2.load_csv(csv_path)
            assert len(store2) == 2
            r = store2.read(f"{1:011d}")
            assert r.acct_curr_bal == Decimal("1234.56")
            assert r.acct_active_status == "Y"
        finally:
            csv_path.unlink(missing_ok=True)
