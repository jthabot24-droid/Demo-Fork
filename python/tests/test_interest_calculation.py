"""Parity tests for interest calculation (CBACT04C).

Validates that the Python port produces the same results as the COBOL
formula: ``COMPUTE WS-MONTHLY-INT = (TRAN-CAT-BAL * DIS-INT-RATE) / 1200``
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from data.store import InMemoryVsamStore
from interest_calculation import InterestResult, compute_interest
from models.account import AccountRecord
from models.card_xref import CardXrefRecord
from models.disclosure_group import DisclosureGroupRecord
from models.tran_cat_balance import TranCatBalanceRecord
from models.transaction import TransactionRecord


class TestInterestFormula:
    """Verify the core formula against hand-computed values."""

    def test_basic_interest(
        self, account_store, xref_store, tcatbal_store, discgrp_store, transaction_store
    ):
        """Account 1, category (01, 0001): bal=12000, rate=18%.

        COBOL: (12000 * 18) / 1200 = 180.00
        """
        result = compute_interest(
            tcatbal_store, account_store, xref_store, discgrp_store, transaction_store
        )
        assert result.transactions_written > 0
        assert result.accounts_processed == 2

        # Check that interest transactions were written
        trans = transaction_store.read_all()
        assert len(trans) >= 1

        # Find the interest for acct 1, type 01, cat 1 (rate 18%)
        # Expected: (12000 * 18) / 1200 = 180.00
        interest_trans = [t for t in trans if t.tran_card_num == "4000000000000001" and t.tran_type_cd == "01"]
        assert len(interest_trans) == 1
        assert interest_trans[0].tran_amt == Decimal("180.00")

    def test_second_category_interest(
        self, account_store, xref_store, tcatbal_store, discgrp_store, transaction_store
    ):
        """Account 1, category (02, 0002): bal=6000, rate=24%.

        COBOL: (6000 * 24) / 1200 = 120.00
        """
        compute_interest(
            tcatbal_store, account_store, xref_store, discgrp_store, transaction_store
        )
        trans = transaction_store.read_all()
        interest_trans = [t for t in trans if t.tran_card_num == "4000000000000001" and t.tran_type_cd == "02"]
        assert len(interest_trans) == 1
        assert interest_trans[0].tran_amt == Decimal("120.00")

    def test_total_interest_accumulated(
        self, account_store, xref_store, tcatbal_store, discgrp_store, transaction_store
    ):
        """Total interest across all accounts should be sum of individual charges."""
        result = compute_interest(
            tcatbal_store, account_store, xref_store, discgrp_store, transaction_store
        )
        # Acct 1: (12000*18)/1200 + (6000*24)/1200 = 180 + 120 = 300
        # Acct 2: (3000*18)/1200 = 45
        assert result.total_interest == Decimal("345.00")

    def test_account_balance_updated_with_interest(
        self, account_store, xref_store, tcatbal_store, discgrp_store, transaction_store
    ):
        """After interest calc, account balance should include accrued interest."""
        original_bal_1 = account_store.read(f"{1:011d}").acct_curr_bal
        original_bal_2 = account_store.read(f"{2:011d}").acct_curr_bal

        compute_interest(
            tcatbal_store, account_store, xref_store, discgrp_store, transaction_store
        )

        acct1 = account_store.read(f"{1:011d}")
        acct2 = account_store.read(f"{2:011d}")

        assert acct1.acct_curr_bal == original_bal_1 + Decimal("300.00")
        assert acct2.acct_curr_bal == original_bal_2 + Decimal("45.00")

    def test_cycle_accumulators_reset(
        self, account_store, xref_store, tcatbal_store, discgrp_store, transaction_store
    ):
        """After interest calc, cycle credit/debit should be reset to zero."""
        compute_interest(
            tcatbal_store, account_store, xref_store, discgrp_store, transaction_store
        )
        acct1 = account_store.read(f"{1:011d}")
        assert acct1.acct_curr_cyc_credit == Decimal("0.00")
        assert acct1.acct_curr_cyc_debit == Decimal("0.00")


class TestInterestEdgeCases:
    """Edge cases for the interest calculator."""

    def test_zero_rate_skipped(
        self, account_store, xref_store, transaction_store
    ):
        """A disclosure group with rate=0 should produce no interest transaction."""
        tcatbal: InMemoryVsamStore[TranCatBalanceRecord] = InMemoryVsamStore(
            TranCatBalanceRecord, lambda r: r.key
        )
        tcatbal.write(TranCatBalanceRecord(
            trancat_acct_id=1, trancat_type_cd="01", trancat_cd=1,
            tran_cat_bal=Decimal("5000.00"),
        ))
        discgrp: InMemoryVsamStore[DisclosureGroupRecord] = InMemoryVsamStore(
            DisclosureGroupRecord, lambda r: r.key
        )
        discgrp.write(DisclosureGroupRecord(
            dis_acct_group_id="A000000000", dis_tran_type_cd="01",
            dis_tran_cat_cd=1, dis_int_rate=Decimal("0.00"),
        ))
        result = compute_interest(
            tcatbal, account_store, xref_store, discgrp, transaction_store
        )
        assert result.transactions_written == 0

    def test_missing_disclosure_group_skipped(
        self, account_store, xref_store, transaction_store
    ):
        """No matching disclosure group -> no interest."""
        tcatbal: InMemoryVsamStore[TranCatBalanceRecord] = InMemoryVsamStore(
            TranCatBalanceRecord, lambda r: r.key
        )
        tcatbal.write(TranCatBalanceRecord(
            trancat_acct_id=1, trancat_type_cd="99", trancat_cd=9999,
            tran_cat_bal=Decimal("5000.00"),
        ))
        discgrp: InMemoryVsamStore[DisclosureGroupRecord] = InMemoryVsamStore(
            DisclosureGroupRecord, lambda r: r.key
        )
        result = compute_interest(
            tcatbal, account_store, xref_store, discgrp, transaction_store
        )
        assert result.transactions_written == 0

    def test_empty_tcatbal_produces_no_output(self, transaction_store):
        """No TCATBAL records -> no processing."""
        empty_tcatbal: InMemoryVsamStore[TranCatBalanceRecord] = InMemoryVsamStore(
            TranCatBalanceRecord, lambda r: r.key
        )
        empty_acct: InMemoryVsamStore[AccountRecord] = InMemoryVsamStore(
            AccountRecord, lambda r: f"{r.acct_id:011d}"
        )
        empty_xref: InMemoryVsamStore[CardXrefRecord] = InMemoryVsamStore(
            CardXrefRecord, lambda r: r.xref_card_num
        )
        empty_disc: InMemoryVsamStore[DisclosureGroupRecord] = InMemoryVsamStore(
            DisclosureGroupRecord, lambda r: r.key
        )
        result = compute_interest(
            empty_tcatbal, empty_acct, empty_xref, empty_disc, transaction_store
        )
        assert result.accounts_processed == 0
        assert result.transactions_written == 0
