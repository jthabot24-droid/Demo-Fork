"""Shared fixtures for Phase 0 / Phase 1 tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from data.store import InMemoryVsamStore
from models.account import AccountRecord
from models.card_xref import CardXrefRecord
from models.daily_transaction import DailyTransactionRecord
from models.disclosure_group import DisclosureGroupRecord
from models.tran_cat_balance import TranCatBalanceRecord
from models.transaction import TransactionRecord


# ── Account store fixture ───────────────────────────────────────────

@pytest.fixture()
def account_store() -> InMemoryVsamStore[AccountRecord]:
    store: InMemoryVsamStore[AccountRecord] = InMemoryVsamStore(
        AccountRecord, lambda r: f"{r.acct_id:011d}"
    )
    store.write(AccountRecord(
        acct_id=1,
        acct_active_status="Y",
        acct_curr_bal=Decimal("1940.00"),
        acct_credit_limit=Decimal("20200.00"),
        acct_cash_credit_limit=Decimal("10200.00"),
        acct_open_date="2014-11-20",
        acct_expiration_date="2025-05-20",
        acct_reissue_date="2025-05-20",
        acct_curr_cyc_credit=Decimal("500.00"),
        acct_curr_cyc_debit=Decimal("-100.00"),
        acct_group_id="A000000000",
    ))
    store.write(AccountRecord(
        acct_id=2,
        acct_active_status="Y",
        acct_curr_bal=Decimal("1580.00"),
        acct_credit_limit=Decimal("61300.00"),
        acct_cash_credit_limit=Decimal("54480.00"),
        acct_open_date="2013-06-19",
        acct_expiration_date="2024-08-11",
        acct_reissue_date="2024-08-11",
        acct_curr_cyc_credit=Decimal("0.00"),
        acct_curr_cyc_debit=Decimal("0.00"),
        acct_group_id="A000000000",
    ))
    return store


# ── Cross-reference store fixture ──────────────────────────────────

@pytest.fixture()
def xref_store() -> InMemoryVsamStore[CardXrefRecord]:
    store: InMemoryVsamStore[CardXrefRecord] = InMemoryVsamStore(
        CardXrefRecord, lambda r: r.xref_card_num
    )
    store.write(CardXrefRecord(
        xref_card_num="4000000000000001",
        xref_cust_id=1,
        xref_acct_id=1,
    ))
    store.write(CardXrefRecord(
        xref_card_num="4000000000000002",
        xref_cust_id=2,
        xref_acct_id=2,
    ))
    return store


# ── Transaction store fixture ──────────────────────────────────────

@pytest.fixture()
def transaction_store() -> InMemoryVsamStore[TransactionRecord]:
    return InMemoryVsamStore(TransactionRecord, lambda r: r.tran_id)


# ── Transaction-category-balance store fixture ─────────────────────

@pytest.fixture()
def tcatbal_store() -> InMemoryVsamStore[TranCatBalanceRecord]:
    store: InMemoryVsamStore[TranCatBalanceRecord] = InMemoryVsamStore(
        TranCatBalanceRecord, lambda r: r.key
    )
    store.write(TranCatBalanceRecord(
        trancat_acct_id=1,
        trancat_type_cd="01",
        trancat_cd=1,
        tran_cat_bal=Decimal("12000.00"),
    ))
    store.write(TranCatBalanceRecord(
        trancat_acct_id=1,
        trancat_type_cd="02",
        trancat_cd=2,
        tran_cat_bal=Decimal("6000.00"),
    ))
    store.write(TranCatBalanceRecord(
        trancat_acct_id=2,
        trancat_type_cd="01",
        trancat_cd=1,
        tran_cat_bal=Decimal("3000.00"),
    ))
    return store


# ── Disclosure-group store fixture ─────────────────────────────────

@pytest.fixture()
def discgrp_store() -> InMemoryVsamStore[DisclosureGroupRecord]:
    store: InMemoryVsamStore[DisclosureGroupRecord] = InMemoryVsamStore(
        DisclosureGroupRecord, lambda r: r.key
    )
    # 18% APR for group A000000000, type 01, cat 0001
    store.write(DisclosureGroupRecord(
        dis_acct_group_id="A000000000",
        dis_tran_type_cd="01",
        dis_tran_cat_cd=1,
        dis_int_rate=Decimal("18.00"),
    ))
    # 24% APR for group A000000000, type 02, cat 0002
    store.write(DisclosureGroupRecord(
        dis_acct_group_id="A000000000",
        dis_tran_type_cd="02",
        dis_tran_cat_cd=2,
        dis_int_rate=Decimal("24.00"),
    ))
    return store


# ── Daily-transaction store fixture ────────────────────────────────

@pytest.fixture()
def daily_store() -> InMemoryVsamStore[DailyTransactionRecord]:
    store: InMemoryVsamStore[DailyTransactionRecord] = InMemoryVsamStore(
        DailyTransactionRecord, lambda r: r.dalytran_id
    )
    store.write(DailyTransactionRecord(
        dalytran_id="DLY0000000000001",
        dalytran_type_cd="01",
        dalytran_cat_cd=1,
        dalytran_source="ONLINE",
        dalytran_desc="TEST PURCHASE",
        dalytran_amt=Decimal("100.00"),
        dalytran_merchant_id=123456789,
        dalytran_merchant_name="TEST MERCHANT",
        dalytran_merchant_city="NEW YORK",
        dalytran_merchant_zip="10001",
        dalytran_card_num="4000000000000001",
        dalytran_orig_ts="2024-01-15-10.30.00.000000",
        dalytran_proc_ts="",
    ))
    return store
