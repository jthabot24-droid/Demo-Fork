"""ETL scripts — load ``.PS`` / ASCII flat files into the relational DB.

Replaces the JCL ``IDCAMS REPRO`` steps (e.g. ``ACCTFILE.jcl`` lines 56-61,
``TRANCATG.jcl``) with Python equivalents.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy.orm import Session

from carddemo.fixed_width import (
    ACCOUNT_SPEC,
    CARD_SPEC,
    CARD_XREF_SPEC,
    CUSTOMER_SPEC,
    DAILY_TRANSACTION_SPEC,
    DISC_GROUP_SPEC,
    TRAN_CAT_BAL_SPEC,
    TRAN_CAT_SPEC,
    TRAN_TYPE_SPEC,
    TRANSACTION_SPEC,
    USER_SECURITY_SPEC,
    FieldSpec,
    read_file,
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
    Transaction,
    UserSecurity,
)

log = logging.getLogger(__name__)


def _to_str(v: Any) -> str:
    if isinstance(v, Decimal):
        return str(v)
    return str(v).strip() if v is not None else ""


# ── generic loader ────────────────────────────────────────────────


def _load_records(
    session: Session,
    orm_class: type,
    records: Sequence[dict[str, Any]],
    key_fields: Sequence[str],
    field_map: dict[str, str] | None = None,
) -> int:
    """Merge *records* into the DB, returning the count loaded."""
    field_map = field_map or {}
    count = 0
    for rec in records:
        kwargs: dict[str, Any] = {}
        for k, v in rec.items():
            col = field_map.get(k, k)
            kwargs[col] = v if isinstance(v, Decimal) else _to_str(v)
        session.merge(orm_class(**kwargs))
        count += 1
    session.flush()
    return count


# ── per-file loaders ──────────────────────────────────────────────


def load_accounts(session: Session, path: str | Path) -> int:
    records = read_file(str(path), ACCOUNT_SPEC)
    return _load_records(session, Account, records, ["acct_id"])


def load_customers(session: Session, path: str | Path) -> int:
    records = read_file(str(path), CUSTOMER_SPEC)
    return _load_records(session, Customer, records, ["cust_id"])


def load_cards(session: Session, path: str | Path) -> int:
    records = read_file(str(path), CARD_SPEC)
    return _load_records(session, Card, records, ["card_num"])


def load_card_xref(session: Session, path: str | Path) -> int:
    records = read_file(str(path), CARD_XREF_SPEC)
    return _load_records(session, CardXref, records, ["xref_card_num"])


def load_transactions(session: Session, path: str | Path) -> int:
    records = read_file(str(path), TRANSACTION_SPEC)
    return _load_records(session, Transaction, records, ["tran_id"])


def load_tran_cat_bal(session: Session, path: str | Path) -> int:
    records = read_file(str(path), TRAN_CAT_BAL_SPEC)
    return _load_records(
        session, TranCatBal, records,
        ["trancat_acct_id", "trancat_type_cd", "trancat_cd"],
    )


def load_disc_groups(session: Session, path: str | Path) -> int:
    records = read_file(str(path), DISC_GROUP_SPEC)
    return _load_records(
        session, DiscGroup, records,
        ["dis_acct_group_id", "dis_tran_type_cd", "dis_tran_cat_cd"],
    )


def load_tran_types(session: Session, path: str | Path) -> int:
    records = read_file(str(path), TRAN_TYPE_SPEC)
    return _load_records(session, TranType, records, ["tran_type"])


def load_tran_categories(session: Session, path: str | Path) -> int:
    records = read_file(str(path), TRAN_CAT_SPEC)
    return _load_records(session, TranCat, records, ["tran_type_cd", "tran_cat_cd"])


def load_user_security(session: Session, path: str | Path) -> int:
    records = read_file(str(path), USER_SECURITY_SPEC)
    return _load_records(session, UserSecurity, records, ["sec_usr_id"])


# ── bulk loader ───────────────────────────────────────────────────

_FILE_MAP: dict[str, tuple] = {
    "acctdata.txt":  (load_accounts,         "accounts"),
    "custdata.txt":  (load_customers,         "customers"),
    "carddata.txt":  (load_cards,             "cards"),
    "cardxref.txt":  (load_card_xref,         "card_xref"),
    "discgrp.txt":   (load_disc_groups,       "disc_groups"),
    "tcatbal.txt":   (load_tran_cat_bal,      "tran_cat_bal"),
    "trantype.txt":  (load_tran_types,        "tran_types"),
    "trancatg.txt":  (load_tran_categories,   "tran_categories"),
    # NOTE: dailytran.txt is NOT loaded here.  It is sequential input
    # read directly by POSTTRAN (batch/posttran.py), mirroring the COBOL
    # pipeline where DALYTRAN-FILE is never REPRO'd into TRANSACT.
}


def load_all(session: Session, data_dir: str | Path) -> dict[str, int]:
    """Load every known flat file from *data_dir* into the DB.

    Returns a mapping of ``{description: record_count}``.
    """
    data_dir = Path(data_dir)
    results: dict[str, int] = {}
    for filename, (loader, desc) in _FILE_MAP.items():
        path = data_dir / filename
        if path.exists():
            n = loader(session, path)
            results[desc] = n
            log.info("Loaded %d records into %s", n, desc)
        else:
            log.warning("File not found, skipping: %s", path)
    session.commit()
    return results
