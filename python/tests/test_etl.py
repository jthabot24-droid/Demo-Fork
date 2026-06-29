"""Tests for ETL loading from ASCII flat files."""

from decimal import Decimal

from carddemo.etl import (
    load_accounts,
    load_card_xref,
    load_cards,
    load_customers,
    load_disc_groups,
    load_tran_cat_bal,
    load_tran_categories,
    load_tran_types,
)
from carddemo.models import (
    Account,
    Card,
    CardXref,
    Customer,
    DiscGroup,
    TranCat,
    TranCatBal,
    TranType,
)


class TestLoadAccounts:
    def test_record_count(self, session, data_dir):
        n = load_accounts(session, data_dir / "acctdata.txt")
        assert n == 50

    def test_first_record_values(self, session, data_dir):
        load_accounts(session, data_dir / "acctdata.txt")
        session.commit()
        acct = session.get(Account, "00000000001")
        assert acct is not None
        assert acct.acct_active_status == "Y"
        assert Decimal(str(acct.acct_curr_bal)) == Decimal("194.00")
        assert Decimal(str(acct.acct_credit_limit)) == Decimal("2020.00")
        assert acct.acct_open_date == "2014-11-20"
        assert acct.acct_expiration_date == "2025-05-20"


class TestLoadCustomers:
    def test_record_count(self, session, data_dir):
        n = load_customers(session, data_dir / "custdata.txt")
        assert n == 50


class TestLoadCards:
    def test_record_count(self, session, data_dir):
        n = load_cards(session, data_dir / "carddata.txt")
        assert n == 50


class TestLoadCardXref:
    def test_record_count(self, session, data_dir):
        n = load_card_xref(session, data_dir / "cardxref.txt")
        assert n == 50

    def test_first_record(self, session, data_dir):
        load_card_xref(session, data_dir / "cardxref.txt")
        session.commit()
        xref = session.get(CardXref, "0500024453765740")
        assert xref is not None
        assert xref.xref_cust_id == "000000050"
        assert xref.xref_acct_id == "00000000050"


class TestLoadDiscGroups:
    def test_record_count(self, session, data_dir):
        n = load_disc_groups(session, data_dir / "discgrp.txt")
        assert n == 51

    def test_interest_rate(self, session, data_dir):
        load_disc_groups(session, data_dir / "discgrp.txt")
        session.commit()
        dg = session.get(DiscGroup, ("A000000000", "01", "0001"))
        assert dg is not None
        assert Decimal(str(dg.dis_int_rate)) == Decimal("15.00")


class TestLoadTranCatBal:
    def test_record_count(self, session, data_dir):
        n = load_tran_cat_bal(session, data_dir / "tcatbal.txt")
        assert n == 50


class TestLoadTranTypes:
    def test_record_count(self, session, data_dir):
        n = load_tran_types(session, data_dir / "trantype.txt")
        assert n == 7


class TestLoadTranCategories:
    def test_record_count(self, session, data_dir):
        n = load_tran_categories(session, data_dir / "trancatg.txt")
        assert n == 18
