"""Tests for the carddemo.dataaccess package.

Verifies that the in-memory (pandas-backed) repositories correctly
implement the VSAM KSDS + AIX keyed-access patterns.
"""

from decimal import Decimal

import pandas as pd
import pytest

from carddemo.dataaccess import (
    InMemoryAccountRepository,
    InMemoryCardRepository,
    InMemoryCardXrefRepository,
    InMemoryCustomerRepository,
    InMemoryDisclosureGroupRepository,
    InMemoryTranCatBalRepository,
    InMemoryTransactionRepository,
)
from carddemo.models import (
    AccountRecord,
    CardRecord,
    CardXrefRecord,
    CustomerRecord,
    DisclosureGroupRecord,
    TranCatBalRecord,
    TransactionRecord,
)


# ===================================================================
# Account Repository
# ===================================================================


class TestAccountRepository:
    @pytest.fixture()
    def repo(self):
        df = pd.DataFrame([
            {
                "acct_id": 80000000001,
                "acct_active_status": "Y",
                "acct_curr_bal": Decimal("1500.00"),
                "acct_credit_limit": Decimal("5000.00"),
                "acct_cash_credit_limit": Decimal("1000.00"),
                "acct_open_date": "2020-01-15",
                "acct_expiration_date": "2027-12-31",
                "acct_reissue_date": "",
                "acct_curr_cyc_credit": Decimal("500.00"),
                "acct_curr_cyc_debit": Decimal("100.00"),
                "acct_addr_zip": "98101",
                "acct_group_id": "GROUP01",
            },
        ])
        return InMemoryAccountRepository(df)

    def test_find_by_id_existing(self, repo):
        acct = repo.find_by_id(80000000001)
        assert acct is not None
        assert acct.acct_id == 80000000001
        assert acct.acct_curr_bal == Decimal("1500.00")
        assert acct.acct_group_id == "GROUP01"

    def test_find_by_id_missing(self, repo):
        assert repo.find_by_id(99999999999) is None

    def test_update(self, repo):
        acct = repo.find_by_id(80000000001)
        acct.acct_curr_bal = Decimal("2000.00")
        repo.update(acct)
        updated = repo.find_by_id(80000000001)
        assert updated.acct_curr_bal == Decimal("2000.00")

    def test_update_missing_raises(self, repo):
        acct = AccountRecord(acct_id=99999999999)
        with pytest.raises(KeyError):
            repo.update(acct)

    def test_add(self, repo):
        new_acct = AccountRecord(
            acct_id=80000000002,
            acct_curr_bal=Decimal("0.00"),
            acct_credit_limit=Decimal("3000.00"),
        )
        repo.add(new_acct)
        found = repo.find_by_id(80000000002)
        assert found is not None
        assert found.acct_credit_limit == Decimal("3000.00")

    def test_iter_all(self, repo):
        records = list(repo.iter_all())
        assert len(records) == 1
        assert records[0].acct_id == 80000000001


# ===================================================================
# Card Cross-Reference Repository
# ===================================================================


class TestCardXrefRepository:
    @pytest.fixture()
    def repo(self):
        df = pd.DataFrame([
            {"xref_card_num": "4111111111111111", "xref_cust_id": 100000001, "xref_acct_id": 80000000001},
            {"xref_card_num": "4222222222222222", "xref_cust_id": 100000002, "xref_acct_id": 80000000002},
        ])
        return InMemoryCardXrefRepository(df)

    def test_find_by_card_num(self, repo):
        xref = repo.find_by_card_num("4111111111111111")
        assert xref is not None
        assert xref.xref_acct_id == 80000000001

    def test_find_by_card_num_missing(self, repo):
        assert repo.find_by_card_num("0000000000000000") is None

    def test_find_by_acct_id(self, repo):
        xref = repo.find_by_acct_id(80000000002)
        assert xref is not None
        assert xref.xref_card_num == "4222222222222222"

    def test_find_by_acct_id_missing(self, repo):
        assert repo.find_by_acct_id(99999999999) is None

    def test_16_byte_zero_padded_key(self, repo):
        """Verify fixed-width 16-byte key semantics."""
        assert repo.find_by_card_num("4111111111111111") is not None
        assert repo.find_by_card_num("411111111111111") is None  # 15 chars

    def test_iter_all(self, repo):
        records = list(repo.iter_all())
        assert len(records) == 2


# ===================================================================
# Disclosure Group Repository
# ===================================================================


class TestDisclosureGroupRepository:
    @pytest.fixture()
    def repo(self):
        df = pd.DataFrame([
            {
                "dis_acct_group_id": "GROUP01",
                "dis_tran_type_cd": "01",
                "dis_tran_cat_cd": 5000,
                "dis_int_rate": Decimal("18.00"),
            },
            {
                "dis_acct_group_id": "DEFAULT",
                "dis_tran_type_cd": "01",
                "dis_tran_cat_cd": 5000,
                "dis_int_rate": Decimal("21.99"),
            },
        ])
        return InMemoryDisclosureGroupRepository(df)

    def test_find_by_key(self, repo):
        rec = repo.find_by_key("GROUP01", "01", 5000)
        assert rec is not None
        assert rec.dis_int_rate == Decimal("18.00")

    def test_find_by_key_missing(self, repo):
        assert repo.find_by_key("NOGROUP", "01", 5000) is None

    def test_default_fallback(self, repo):
        rec = repo.find_by_key("DEFAULT", "01", 5000)
        assert rec is not None
        assert rec.dis_int_rate == Decimal("21.99")


# ===================================================================
# Transaction Category Balance Repository
# ===================================================================


class TestTranCatBalRepository:
    @pytest.fixture()
    def repo(self):
        df = pd.DataFrame([
            {
                "trancat_acct_id": 80000000001,
                "trancat_type_cd": "01",
                "trancat_cd": 5000,
                "tran_cat_bal": Decimal("1000.00"),
            },
        ])
        return InMemoryTranCatBalRepository(df)

    def test_find_by_key(self, repo):
        rec = repo.find_by_key(80000000001, "01", 5000)
        assert rec is not None
        assert rec.tran_cat_bal == Decimal("1000.00")

    def test_find_by_key_missing(self, repo):
        assert repo.find_by_key(99999999999, "01", 5000) is None

    def test_add(self, repo):
        new_rec = TranCatBalRecord(
            trancat_acct_id=80000000002,
            trancat_type_cd="02",
            trancat_cd=3000,
            tran_cat_bal=Decimal("500.00"),
        )
        repo.add(new_rec)
        found = repo.find_by_key(80000000002, "02", 3000)
        assert found is not None
        assert found.tran_cat_bal == Decimal("500.00")

    def test_update(self, repo):
        rec = repo.find_by_key(80000000001, "01", 5000)
        rec.tran_cat_bal = Decimal("2000.00")
        repo.update(rec)
        updated = repo.find_by_key(80000000001, "01", 5000)
        assert updated.tran_cat_bal == Decimal("2000.00")

    def test_update_missing_raises(self, repo):
        rec = TranCatBalRecord(
            trancat_acct_id=99999999999,
            trancat_type_cd="01",
            trancat_cd=5000,
        )
        with pytest.raises(KeyError):
            repo.update(rec)


# ===================================================================
# Transaction Repository
# ===================================================================


class TestTransactionRepository:
    @pytest.fixture()
    def repo(self):
        return InMemoryTransactionRepository()

    def test_add_and_find(self, repo):
        tran = TransactionRecord(
            tran_id="2026-06-30000001",
            tran_type_cd="01",
            tran_cat_cd=5,
            tran_source="System",
            tran_desc="Test",
            tran_amt=Decimal("75.00"),
            tran_merchant_id=0,
            tran_card_num="4111111111111111",
            tran_orig_ts="2026-06-30-12.00.00.000000",
            tran_proc_ts="2026-06-30-12.00.00.000000",
        )
        repo.add(tran)
        found = repo.find_by_id("2026-06-30000001")
        assert found is not None
        assert found.tran_amt == Decimal("75.00")
        assert found.tran_source == "System"

    def test_find_missing(self, repo):
        assert repo.find_by_id("NONEXISTENT") is None

    def test_iter_all_empty(self, repo):
        assert list(repo.iter_all()) == []
