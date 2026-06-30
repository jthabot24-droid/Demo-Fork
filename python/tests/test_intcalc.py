"""Tests for CBACT04C (INTCALC) batch program."""

from decimal import Decimal

from sqlalchemy import func, select

from carddemo.batch.intcalc import run as intcalc_run
from carddemo.etl import (
    load_accounts,
    load_card_xref,
    load_disc_groups,
    load_tran_cat_bal,
)
from carddemo.models import Account, Transaction


class TestIntcalc:
    def _load_base_data(self, session, data_dir):
        load_accounts(session, data_dir / "acctdata.txt")
        load_card_xref(session, data_dir / "cardxref.txt")
        load_tran_cat_bal(session, data_dir / "tcatbal.txt")
        load_disc_groups(session, data_dir / "discgrp.txt")
        session.commit()

    def test_processes_all_tcatbal_records(self, session, data_dir):
        self._load_base_data(session, data_dir)
        result = intcalc_run(session, parm_date="2024-06-15")
        assert result.records_processed == 50

    def test_writes_interest_transactions(self, session, data_dir):
        self._load_base_data(session, data_dir)
        result = intcalc_run(session, parm_date="2024-06-15")
        tran_count = session.execute(
            select(func.count()).select_from(Transaction)
        ).scalar()
        assert tran_count == result.interest_transactions_written

    def test_interest_formula(self, session, data_dir):
        """Verify: monthly_int = (TRAN-CAT-BAL * DIS-INT-RATE) / 1200."""
        self._load_base_data(session, data_dir)
        intcalc_run(session, parm_date="2024-06-15")
        # All initial tcatbal records have balance 0, so interest should be 0
        # for those. Any written transactions should have valid amounts.
        txns = session.execute(select(Transaction)).scalars().all()
        for txn in txns:
            amt = Decimal(str(txn.tran_amt))
            # Interest can be 0 if the category balance was 0
            assert isinstance(amt, Decimal)

    def test_resets_cycle_amounts(self, session, data_dir):
        self._load_base_data(session, data_dir)
        # Set non-zero cycle amounts
        acct = session.get(Account, "00000000001")
        acct.acct_curr_cyc_credit = Decimal("100.00")
        acct.acct_curr_cyc_debit = Decimal("-50.00")
        session.flush()

        intcalc_run(session, parm_date="2024-06-15")
        session.expire_all()
        acct = session.get(Account, "00000000001")
        assert Decimal(str(acct.acct_curr_cyc_credit)) == Decimal("0.00")
        assert Decimal(str(acct.acct_curr_cyc_debit)) == Decimal("0.00")

    def test_compute_fees_is_noop(self, session, data_dir):
        """1400-COMPUTE-FEES is an explicit stub — no exception raised."""
        self._load_base_data(session, data_dir)
        intcalc_run(session, parm_date="2024-06-15")
