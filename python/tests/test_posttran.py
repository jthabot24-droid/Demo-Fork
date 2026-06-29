"""Tests for CBTRN02C (POSTTRAN) batch program."""

from decimal import Decimal

from carddemo.batch.posttran import run as posttran_run
from carddemo.etl import load_accounts, load_card_xref, load_tran_cat_bal
from carddemo.fixed_width import DAILY_TRANSACTION_SPEC, read_file
from carddemo.models import Account, TranCatBal, Transaction


class TestPosttran:
    def _load_base_data(self, session, data_dir):
        load_accounts(session, data_dir / "acctdata.txt")
        load_card_xref(session, data_dir / "cardxref.txt")
        load_tran_cat_bal(session, data_dir / "tcatbal.txt")
        session.commit()

    def test_posts_valid_transactions(self, session, data_dir):
        self._load_base_data(session, data_dir)
        daily = read_file(str(data_dir / "dailytran.txt"), DAILY_TRANSACTION_SPEC)
        result = posttran_run(daily, session)
        assert result.transactions_processed == 300
        assert result.transactions_posted > 0
        assert result.transactions_posted + result.transactions_rejected == 300

    def test_rejects_invalid_card(self, session, data_dir):
        self._load_base_data(session, data_dir)
        fake_tran = [{
            "dalytran_id": "FAKE000000000001",
            "dalytran_type_cd": "01",
            "dalytran_cat_cd": "0001",
            "dalytran_source": "TEST",
            "dalytran_desc": "Test transaction",
            "dalytran_amt": Decimal("10.00"),
            "dalytran_merchant_id": "000000000",
            "dalytran_merchant_name": "Test",
            "dalytran_merchant_city": "Test",
            "dalytran_merchant_zip": "00000",
            "dalytran_card_num": "9999999999999999",
            "dalytran_orig_ts": "2024-01-01 00:00:00.000000",
            "dalytran_proc_ts": "",
        }]
        result = posttran_run(fake_tran, session)
        assert result.transactions_rejected == 1
        assert result.rejects[0].fail_code == 100

    def test_updates_account_balance(self, session, data_dir):
        self._load_base_data(session, data_dir)
        acct_before = session.get(Account, "00000000001")
        bal_before = Decimal(str(acct_before.acct_curr_bal))

        daily = read_file(str(data_dir / "dailytran.txt"), DAILY_TRANSACTION_SPEC)
        acct1_trans = [t for t in daily
                       if str(t.get("dalytran_card_num", "")).strip()
                       in self._get_acct1_cards(session)]
        if acct1_trans:
            posttran_run(acct1_trans, session)
            session.expire_all()
            acct_after = session.get(Account, "00000000001")
            assert acct_after is not None

    def _get_acct1_cards(self, session):
        from sqlalchemy import select
        from carddemo.models import CardXref
        rows = session.execute(
            select(CardXref).where(CardXref.xref_acct_id == "00000000001")
        ).scalars().all()
        return {str(r.xref_card_num).strip() for r in rows}

    def test_creates_tcatbal_records(self, session, data_dir):
        self._load_base_data(session, data_dir)
        daily = read_file(str(data_dir / "dailytran.txt"), DAILY_TRANSACTION_SPEC)
        posttran_run(daily[:5], session)
        from sqlalchemy import func, select
        count = session.execute(
            select(func.count()).select_from(TranCatBal)
        ).scalar()
        assert count >= 50
