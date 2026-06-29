"""Tests for the data model and DB schema."""

from decimal import Decimal

from carddemo.models import (
    Account,
    Card,
    CardXref,
    Customer,
    DiscGroup,
    TranCat,
    TranCatBal,
    TranType,
    Transaction,
    UserSecurity,
    init_db,
)


class TestSchemaCreation:
    def test_all_tables_created(self, engine):
        from sqlalchemy import inspect

        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        expected = {
            "accounts", "customers", "cards", "card_xref",
            "transactions", "tran_cat_bal", "disc_groups",
            "tran_types", "tran_categories", "user_security",
        }
        assert expected.issubset(tables)


class TestAccountCRUD:
    def test_insert_and_retrieve(self, session):
        acct = Account(
            acct_id="00000000001",
            acct_active_status="Y",
            acct_curr_bal=Decimal("194.00"),
            acct_credit_limit=Decimal("2020.00"),
        )
        session.add(acct)
        session.flush()
        loaded = session.get(Account, "00000000001")
        assert loaded is not None
        assert Decimal(str(loaded.acct_curr_bal)) == Decimal("194.00")

    def test_update_balance(self, session):
        acct = Account(acct_id="00000000099", acct_curr_bal=Decimal("100.00"))
        session.add(acct)
        session.flush()
        acct.acct_curr_bal = Decimal(str(acct.acct_curr_bal)) + Decimal("50.00")
        session.flush()
        loaded = session.get(Account, "00000000099")
        assert Decimal(str(loaded.acct_curr_bal)) == Decimal("150.00")


class TestTranCatBalCompositeKey:
    def test_composite_primary_key(self, session):
        tcb = TranCatBal(
            trancat_acct_id="00000000001",
            trancat_type_cd="01",
            trancat_cd="0001",
            tran_cat_bal=Decimal("500.00"),
        )
        session.add(tcb)
        session.flush()
        loaded = session.get(TranCatBal, ("00000000001", "01", "0001"))
        assert loaded is not None
        assert Decimal(str(loaded.tran_cat_bal)) == Decimal("500.00")


class TestDiscGroupCompositeKey:
    def test_composite_primary_key(self, session):
        dg = DiscGroup(
            dis_acct_group_id="A000000000",
            dis_tran_type_cd="01",
            dis_tran_cat_cd="0001",
            dis_int_rate=Decimal("15.00"),
        )
        session.add(dg)
        session.flush()
        loaded = session.get(DiscGroup, ("A000000000", "01", "0001"))
        assert loaded is not None
        assert Decimal(str(loaded.dis_int_rate)) == Decimal("15.00")
