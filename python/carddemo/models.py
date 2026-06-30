"""Data models for CardDemo — dataclasses and SQLAlchemy ORM.

Record layouts derived from COBOL copybooks in ``app/cpy/``.
Every monetary/numeric field uses ``Decimal`` to preserve
COBOL packed/zoned-decimal precision.

Persistence
-----------
SQLite for local/dev, PostgreSQL for production.  VSAM KSDS keys map
to primary keys; alternate indexes map to unique/non-unique secondary
indexes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import (
    Column,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


# ───────────────────────────────────────────────────────────────────
# SQLAlchemy base
# ───────────────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


# ───────────────────────────────────────────────────────────────────
# ACCOUNT — CVACT01Y.cpy  (RECLN 300, KSDS key len 11)
# VSAM cluster: ACCTDATA  (app/jcl/ACCTFILE.jcl)
# ───────────────────────────────────────────────────────────────────


@dataclass
class AccountRecord:
    """Pure-Python mirror of the COBOL ``ACCOUNT-RECORD``."""

    acct_id: str = ""                                  # PIC 9(11)
    acct_active_status: str = ""                       # PIC X(01)
    acct_curr_bal: Decimal = Decimal("0.00")           # PIC S9(10)V99
    acct_credit_limit: Decimal = Decimal("0.00")       # PIC S9(10)V99
    acct_cash_credit_limit: Decimal = Decimal("0.00")  # PIC S9(10)V99
    acct_open_date: str = ""                           # PIC X(10)
    acct_expiration_date: str = ""                     # PIC X(10)
    acct_reissue_date: str = ""                        # PIC X(10)
    acct_curr_cyc_credit: Decimal = Decimal("0.00")    # PIC S9(10)V99
    acct_curr_cyc_debit: Decimal = Decimal("0.00")     # PIC S9(10)V99
    acct_addr_zip: str = ""                            # PIC X(10)
    acct_group_id: str = ""                            # PIC X(10)

    RECORD_LENGTH: int = field(default=300, init=False, repr=False)


class Account(Base):
    __tablename__ = "accounts"

    acct_id = Column(String(11), primary_key=True)
    acct_active_status = Column(String(1), nullable=False, default="Y")
    acct_curr_bal = Column(Numeric(12, 2), nullable=False, default=0)
    acct_credit_limit = Column(Numeric(12, 2), nullable=False, default=0)
    acct_cash_credit_limit = Column(Numeric(12, 2), nullable=False, default=0)
    acct_open_date = Column(String(10), nullable=False, default="")
    acct_expiration_date = Column(String(10), nullable=False, default="")
    acct_reissue_date = Column(String(10), nullable=False, default="")
    acct_curr_cyc_credit = Column(Numeric(12, 2), nullable=False, default=0)
    acct_curr_cyc_debit = Column(Numeric(12, 2), nullable=False, default=0)
    acct_addr_zip = Column(String(10), nullable=False, default="")
    acct_group_id = Column(String(10), nullable=False, default="")


# ───────────────────────────────────────────────────────────────────
# CUSTOMER — CVCUS01Y.cpy  (RECLN 500)
# VSAM cluster: CUSTDATA  (app/jcl/CUSTFILE.jcl)
# ───────────────────────────────────────────────────────────────────


@dataclass
class CustomerRecord:
    """Pure-Python mirror of the COBOL ``CUSTOMER-RECORD``."""

    cust_id: str = ""                    # PIC 9(09)
    cust_first_name: str = ""            # PIC X(25)
    cust_middle_name: str = ""           # PIC X(25)
    cust_last_name: str = ""             # PIC X(25)
    cust_addr_line_1: str = ""           # PIC X(50)
    cust_addr_line_2: str = ""           # PIC X(50)
    cust_addr_line_3: str = ""           # PIC X(50)
    cust_addr_state_cd: str = ""         # PIC X(02)
    cust_addr_country_cd: str = ""       # PIC X(03)
    cust_addr_zip: str = ""              # PIC X(10)
    cust_phone_num_1: str = ""           # PIC X(15)
    cust_phone_num_2: str = ""           # PIC X(15)
    cust_ssn: str = ""                   # PIC 9(09)
    cust_govt_issued_id: str = ""        # PIC X(20)
    cust_dob_yyyy_mm_dd: str = ""        # PIC X(10)
    cust_eft_account_id: str = ""        # PIC X(10)
    cust_pri_card_holder_ind: str = ""   # PIC X(01)
    cust_fico_credit_score: str = ""     # PIC 9(03)

    RECORD_LENGTH: int = field(default=500, init=False, repr=False)


class Customer(Base):
    __tablename__ = "customers"

    cust_id = Column(String(9), primary_key=True)
    cust_first_name = Column(String(25), nullable=False, default="")
    cust_middle_name = Column(String(25), nullable=False, default="")
    cust_last_name = Column(String(25), nullable=False, default="")
    cust_addr_line_1 = Column(String(50), nullable=False, default="")
    cust_addr_line_2 = Column(String(50), nullable=False, default="")
    cust_addr_line_3 = Column(String(50), nullable=False, default="")
    cust_addr_state_cd = Column(String(2), nullable=False, default="")
    cust_addr_country_cd = Column(String(3), nullable=False, default="")
    cust_addr_zip = Column(String(10), nullable=False, default="")
    cust_phone_num_1 = Column(String(15), nullable=False, default="")
    cust_phone_num_2 = Column(String(15), nullable=False, default="")
    cust_ssn = Column(String(9), nullable=False, default="")
    cust_govt_issued_id = Column(String(20), nullable=False, default="")
    cust_dob_yyyy_mm_dd = Column(String(10), nullable=False, default="")
    cust_eft_account_id = Column(String(10), nullable=False, default="")
    cust_pri_card_holder_ind = Column(String(1), nullable=False, default="")
    cust_fico_credit_score = Column(String(3), nullable=False, default="")


# ───────────────────────────────────────────────────────────────────
# CARD — CVACT02Y.cpy  (RECLN 150, KSDS key 16)
# VSAM cluster: CARDDATA  (app/jcl/CARDFILE.jcl)
# AIX on CARD-ACCT-ID (app/jcl/CARDFILE.jcl lines 83–92)
# ───────────────────────────────────────────────────────────────────


@dataclass
class CardRecord:
    """Pure-Python mirror of the COBOL ``CARD-RECORD``."""

    card_num: str = ""                # PIC X(16)
    card_acct_id: str = ""            # PIC 9(11)
    card_cvv_cd: str = ""             # PIC 9(03)
    card_embossed_name: str = ""      # PIC X(50)
    card_expiration_date: str = ""    # PIC X(10)
    card_active_status: str = ""      # PIC X(01)

    RECORD_LENGTH: int = field(default=150, init=False, repr=False)


class Card(Base):
    __tablename__ = "cards"

    card_num = Column(String(16), primary_key=True)
    card_acct_id = Column(String(11), nullable=False, index=True)
    card_cvv_cd = Column(String(3), nullable=False, default="")
    card_embossed_name = Column(String(50), nullable=False, default="")
    card_expiration_date = Column(String(10), nullable=False, default="")
    card_active_status = Column(String(1), nullable=False, default="Y")


# ───────────────────────────────────────────────────────────────────
# CARD CROSS-REFERENCE — CVACT03Y.cpy  (RECLN 50, KSDS key 16)
# VSAM cluster: CARDXREF  (app/jcl/XREFFILE.jcl)
# AIX on XREF-ACCT-ID
# ───────────────────────────────────────────────────────────────────


@dataclass
class CardXrefRecord:
    """Pure-Python mirror of the COBOL ``CARD-XREF-RECORD``."""

    xref_card_num: str = ""   # PIC X(16)
    xref_cust_id: str = ""    # PIC 9(09)
    xref_acct_id: str = ""    # PIC 9(11)

    RECORD_LENGTH: int = field(default=50, init=False, repr=False)


class CardXref(Base):
    __tablename__ = "card_xref"

    xref_card_num = Column(String(16), primary_key=True)
    xref_cust_id = Column(String(9), nullable=False, index=True)
    xref_acct_id = Column(String(11), nullable=False, index=True)


# ───────────────────────────────────────────────────────────────────
# TRANSACTION — CVTRA05Y.cpy  (RECLN 350, KSDS key 16)
# VSAM cluster: TRANSACT  (app/jcl/TRANFILE.jcl)
# AIX path on TRAN-CARD-NUM
# ───────────────────────────────────────────────────────────────────


@dataclass
class TransactionRecord:
    """Pure-Python mirror of the COBOL ``TRAN-RECORD``."""

    tran_id: str = ""                              # PIC X(16)
    tran_type_cd: str = ""                         # PIC X(02)
    tran_cat_cd: str = ""                          # PIC 9(04)
    tran_source: str = ""                          # PIC X(10)
    tran_desc: str = ""                            # PIC X(100)
    tran_amt: Decimal = Decimal("0.00")            # PIC S9(09)V99
    tran_merchant_id: str = ""                     # PIC 9(09)
    tran_merchant_name: str = ""                   # PIC X(50)
    tran_merchant_city: str = ""                   # PIC X(50)
    tran_merchant_zip: str = ""                    # PIC X(10)
    tran_card_num: str = ""                        # PIC X(16)
    tran_orig_ts: str = ""                         # PIC X(26)
    tran_proc_ts: str = ""                         # PIC X(26)

    RECORD_LENGTH: int = field(default=350, init=False, repr=False)


class Transaction(Base):
    __tablename__ = "transactions"

    tran_id = Column(String(16), primary_key=True)
    tran_type_cd = Column(String(2), nullable=False, default="")
    tran_cat_cd = Column(String(4), nullable=False, default="")
    tran_source = Column(String(10), nullable=False, default="")
    tran_desc = Column(String(100), nullable=False, default="")
    tran_amt = Column(Numeric(11, 2), nullable=False, default=0)
    tran_merchant_id = Column(String(9), nullable=False, default="")
    tran_merchant_name = Column(String(50), nullable=False, default="")
    tran_merchant_city = Column(String(50), nullable=False, default="")
    tran_merchant_zip = Column(String(10), nullable=False, default="")
    tran_card_num = Column(String(16), nullable=False, index=True)
    tran_orig_ts = Column(String(26), nullable=False, default="")
    tran_proc_ts = Column(String(26), nullable=False, default="")


# ───────────────────────────────────────────────────────────────────
# DAILY TRANSACTION — CVTRA06Y.cpy  (RECLN 350)
# Sequential input file read by CBTRN02C (POSTTRAN)
# ───────────────────────────────────────────────────────────────────


@dataclass
class DailyTransactionRecord:
    """Pure-Python mirror of the COBOL ``DALYTRAN-RECORD``."""

    dalytran_id: str = ""                              # PIC X(16)
    dalytran_type_cd: str = ""                         # PIC X(02)
    dalytran_cat_cd: str = ""                          # PIC 9(04)
    dalytran_source: str = ""                          # PIC X(10)
    dalytran_desc: str = ""                            # PIC X(100)
    dalytran_amt: Decimal = Decimal("0.00")            # PIC S9(09)V99
    dalytran_merchant_id: str = ""                     # PIC 9(09)
    dalytran_merchant_name: str = ""                   # PIC X(50)
    dalytran_merchant_city: str = ""                   # PIC X(50)
    dalytran_merchant_zip: str = ""                    # PIC X(10)
    dalytran_card_num: str = ""                        # PIC X(16)
    dalytran_orig_ts: str = ""                         # PIC X(26)
    dalytran_proc_ts: str = ""                         # PIC X(26)

    RECORD_LENGTH: int = field(default=350, init=False, repr=False)


# ───────────────────────────────────────────────────────────────────
# TRANSACTION CATEGORY BALANCE — CVTRA01Y.cpy  (RECLN 50, KSDS key 17)
# VSAM cluster: TCATBALF  (app/jcl/TCATBALF.jcl)
# ───────────────────────────────────────────────────────────────────


@dataclass
class TranCatBalRecord:
    """Pure-Python mirror of the COBOL ``TRAN-CAT-BAL-RECORD``."""

    trancat_acct_id: str = ""                          # PIC 9(11)
    trancat_type_cd: str = ""                          # PIC X(02)
    trancat_cd: str = ""                               # PIC 9(04)
    tran_cat_bal: Decimal = Decimal("0.00")            # PIC S9(09)V99

    RECORD_LENGTH: int = field(default=50, init=False, repr=False)


class TranCatBal(Base):
    __tablename__ = "tran_cat_bal"

    trancat_acct_id = Column(String(11), primary_key=True)
    trancat_type_cd = Column(String(2), primary_key=True)
    trancat_cd = Column(String(4), primary_key=True)
    tran_cat_bal = Column(Numeric(11, 2), nullable=False, default=0)


# ───────────────────────────────────────────────────────────────────
# DISCLOSURE GROUP — CVTRA02Y.cpy  (RECLN 50, KSDS key 16)
# VSAM cluster: DISCGRP   (app/jcl/DISCGRP.jcl)
# ───────────────────────────────────────────────────────────────────


@dataclass
class DiscGroupRecord:
    """Pure-Python mirror of the COBOL ``DIS-GROUP-RECORD``."""

    dis_acct_group_id: str = ""                        # PIC X(10)
    dis_tran_type_cd: str = ""                         # PIC X(02)
    dis_tran_cat_cd: str = ""                          # PIC 9(04)
    dis_int_rate: Decimal = Decimal("0.00")            # PIC S9(04)V99

    RECORD_LENGTH: int = field(default=50, init=False, repr=False)


class DiscGroup(Base):
    __tablename__ = "disc_groups"

    dis_acct_group_id = Column(String(10), primary_key=True)
    dis_tran_type_cd = Column(String(2), primary_key=True)
    dis_tran_cat_cd = Column(String(4), primary_key=True)
    dis_int_rate = Column(Numeric(6, 2), nullable=False, default=0)


# ───────────────────────────────────────────────────────────────────
# TRANSACTION TYPE — CVTRA03Y.cpy  (RECLN 60)
# VSAM cluster: TRANTYPE  (app/jcl/TRANTYPE.jcl)
# ───────────────────────────────────────────────────────────────────


@dataclass
class TranTypeRecord:
    """Pure-Python mirror of the COBOL ``TRAN-TYPE-RECORD``."""

    tran_type: str = ""                # PIC X(02)
    tran_type_desc: str = ""           # PIC X(50)

    RECORD_LENGTH: int = field(default=60, init=False, repr=False)


class TranType(Base):
    __tablename__ = "tran_types"

    tran_type = Column(String(2), primary_key=True)
    tran_type_desc = Column(String(50), nullable=False, default="")


# ───────────────────────────────────────────────────────────────────
# TRANSACTION CATEGORY — CVTRA04Y.cpy  (RECLN 60)
# VSAM cluster: TRANCATG  (app/jcl/TRANCATG.jcl)
# ───────────────────────────────────────────────────────────────────


@dataclass
class TranCatRecord:
    """Pure-Python mirror of the COBOL ``TRAN-CAT-RECORD``."""

    tran_type_cd: str = ""             # PIC X(02)
    tran_cat_cd: str = ""              # PIC 9(04)
    tran_cat_type_desc: str = ""       # PIC X(50)

    RECORD_LENGTH: int = field(default=60, init=False, repr=False)


class TranCat(Base):
    __tablename__ = "tran_categories"

    tran_type_cd = Column(String(2), primary_key=True)
    tran_cat_cd = Column(String(4), primary_key=True)
    tran_cat_type_desc = Column(String(50), nullable=False, default="")


# ───────────────────────────────────────────────────────────────────
# USER SECURITY — CSUSR01Y.cpy  (RRDS RECLN 80)
# VSAM cluster: USRSEC   (app/jcl/ESDSRRDS.jcl)
# ───────────────────────────────────────────────────────────────────


@dataclass
class UserSecurityRecord:
    """Pure-Python mirror of the COBOL ``SEC-USER-DATA``."""

    sec_usr_id: str = ""               # PIC X(08)
    sec_usr_fname: str = ""            # PIC X(20)
    sec_usr_lname: str = ""            # PIC X(20)
    sec_usr_pwd: str = ""              # PIC X(08)
    sec_usr_type: str = ""             # PIC X(01)

    RECORD_LENGTH: int = field(default=80, init=False, repr=False)


class UserSecurity(Base):
    __tablename__ = "user_security"

    sec_usr_id = Column(String(8), primary_key=True)
    sec_usr_fname = Column(String(20), nullable=False, default="")
    sec_usr_lname = Column(String(20), nullable=False, default="")
    sec_usr_pwd = Column(String(8), nullable=False, default="")
    sec_usr_type = Column(String(1), nullable=False, default="U")


# ───────────────────────────────────────────────────────────────────
# COMMAREA — COCOM01Y.cpy  (shared inter-program area)
# Kept as a dataclass for future Phase 3 (online) migration.
# ───────────────────────────────────────────────────────────────────


@dataclass
class CardDemoCommarea:
    """COBOL ``CARDDEMO-COMMAREA`` — scaffolded for Phase 3."""

    cdemo_from_tranid: str = ""        # PIC X(04)
    cdemo_from_program: str = ""       # PIC X(08)
    cdemo_to_tranid: str = ""          # PIC X(04)
    cdemo_to_program: str = ""         # PIC X(08)
    cdemo_user_id: str = ""            # PIC X(08)
    cdemo_user_type: str = ""          # PIC X(01)
    cdemo_pgm_context: int = 0         # PIC 9(01)
    cdemo_cust_id: str = ""            # PIC 9(09)
    cdemo_cust_fname: str = ""         # PIC X(25)
    cdemo_cust_mname: str = ""         # PIC X(25)
    cdemo_cust_lname: str = ""         # PIC X(25)
    cdemo_acct_id: str = ""            # PIC 9(11)
    cdemo_acct_status: str = ""        # PIC X(01)
    cdemo_card_num: str = ""           # PIC 9(16)
    cdemo_last_map: str = ""           # PIC X(7)
    cdemo_last_mapset: str = ""        # PIC X(7)


# ───────────────────────────────────────────────────────────────────
# Engine / session helper
# ───────────────────────────────────────────────────────────────────


def get_engine(url: str = "sqlite:///carddemo.db"):
    """Create a SQLAlchemy engine (default: local SQLite)."""
    return create_engine(url, echo=False)


def init_db(engine) -> None:
    """Create all tables."""
    Base.metadata.create_all(engine)


def get_session(engine) -> Session:
    """Return a new session bound to *engine*."""
    return sessionmaker(bind=engine)()
