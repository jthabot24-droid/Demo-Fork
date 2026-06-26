"""Fixed-width ASCII record parser and data-store seeder.

Parses the mainframe-format ASCII data files in ``app/data/ASCII/`` and
populates ``InMemoryVsamStore`` instances for each VSAM file.

The ASCII files use EBCDIC-style **zoned-decimal overpunch** encoding for
signed numeric fields (``PIC S9(n)V99``):

    Positive: { = 0, A = 1, B = 2, ... I = 9
    Negative: } = 0, J = 1, K = 2, ... R = 9
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import NamedTuple, Optional, Sequence

from data.store import InMemoryVsamStore
from models.account import AccountRecord
from models.card import CardRecord
from models.card_xref import CardXrefRecord
from models.customer import CustomerRecord
from models.daily_transaction import DailyTransactionRecord
from models.disclosure_group import DisclosureGroupRecord
from models.tran_cat_balance import TranCatBalanceRecord
from models.transaction import TransactionRecord
from models.user_security import UserSecurityRecord

# ── Overpunch tables ────────────────────────────────────────────────

_POS_OVERPUNCH = {"{": 0, "A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7, "H": 8, "I": 9}
_NEG_OVERPUNCH = {"}": 0, "J": 1, "K": 2, "L": 3, "M": 4, "N": 5, "O": 6, "P": 7, "Q": 8, "R": 9}


def _decode_signed_decimal(raw: str, decimal_places: int = 2) -> Decimal:
    """Decode a zoned-decimal overpunch string into a ``Decimal``.

    >>> _decode_signed_decimal("00000001940{")
    Decimal('1940.00')
    >>> _decode_signed_decimal("0000001940J")
    Decimal('-1940.01')
    """
    if not raw or raw.isspace():
        return Decimal("0.00")

    last = raw[-1]
    sign = 1
    digit = 0

    if last in _POS_OVERPUNCH:
        digit = _POS_OVERPUNCH[last]
        sign = 1
    elif last in _NEG_OVERPUNCH:
        digit = _NEG_OVERPUNCH[last]
        sign = -1
    elif last.isdigit():
        digit = int(last)
        sign = 1
    else:
        return Decimal("0.00")

    digits = raw[:-1] + str(digit)
    int_val = int(digits) * sign
    return Decimal(int_val) / Decimal(10 ** decimal_places)


# ── Field specification ─────────────────────────────────────────────

class FieldSpec(NamedTuple):
    name: Optional[str]  # None = filler (skip)
    length: int
    kind: str  # 'str', 'int', 'signed_decimal'
    decimal_places: int = 2


# ── Record layouts (one per copybook) ───────────────────────────────

ACCOUNT_FIELDS: list[FieldSpec] = [
    FieldSpec("acct_id", 11, "int"),
    FieldSpec("acct_active_status", 1, "str"),
    FieldSpec("acct_curr_bal", 12, "signed_decimal"),
    FieldSpec("acct_credit_limit", 12, "signed_decimal"),
    FieldSpec("acct_cash_credit_limit", 12, "signed_decimal"),
    FieldSpec("acct_open_date", 10, "str"),
    FieldSpec("acct_expiration_date", 10, "str"),
    FieldSpec("acct_reissue_date", 10, "str"),
    FieldSpec("acct_curr_cyc_credit", 12, "signed_decimal"),
    FieldSpec("acct_curr_cyc_debit", 12, "signed_decimal"),
    FieldSpec("acct_addr_zip", 10, "str"),
    FieldSpec("acct_group_id", 10, "str"),
    FieldSpec(None, 178, "str"),  # FILLER
]

CARD_FIELDS: list[FieldSpec] = [
    FieldSpec("card_num", 16, "str"),
    FieldSpec("card_acct_id", 11, "int"),
    FieldSpec("card_cvv_cd", 3, "int"),
    FieldSpec("card_embossed_name", 50, "str"),
    FieldSpec("card_expiration_date", 10, "str"),
    FieldSpec("card_active_status", 1, "str"),
    FieldSpec(None, 59, "str"),  # FILLER
]

CUSTOMER_FIELDS: list[FieldSpec] = [
    FieldSpec("cust_id", 9, "int"),
    FieldSpec("cust_first_name", 25, "str"),
    FieldSpec("cust_middle_name", 25, "str"),
    FieldSpec("cust_last_name", 25, "str"),
    FieldSpec("cust_addr_line_1", 50, "str"),
    FieldSpec("cust_addr_line_2", 50, "str"),
    FieldSpec("cust_addr_line_3", 50, "str"),
    FieldSpec("cust_addr_state_cd", 2, "str"),
    FieldSpec("cust_addr_country_cd", 3, "str"),
    FieldSpec("cust_addr_zip", 10, "str"),
    FieldSpec("cust_phone_num_1", 15, "str"),
    FieldSpec("cust_phone_num_2", 15, "str"),
    FieldSpec("cust_ssn", 9, "int"),
    FieldSpec("cust_govt_issued_id", 20, "str"),
    FieldSpec("cust_dob_yyyy_mm_dd", 10, "str"),
    FieldSpec("cust_eft_account_id", 10, "str"),
    FieldSpec("cust_pri_card_holder_ind", 1, "str"),
    FieldSpec("cust_fico_credit_score", 3, "int"),
    FieldSpec(None, 168, "str"),  # FILLER
]

CARD_XREF_FIELDS: list[FieldSpec] = [
    FieldSpec("xref_card_num", 16, "str"),
    FieldSpec("xref_cust_id", 9, "int"),
    FieldSpec("xref_acct_id", 11, "int"),
    FieldSpec(None, 14, "str"),  # FILLER
]

_TRAN_COMMON: list[FieldSpec] = [
    FieldSpec(None, 16, "str"),   # tran_id / dalytran_id placeholder
    FieldSpec(None, 2, "str"),    # type_cd placeholder
    FieldSpec(None, 4, "int"),    # cat_cd placeholder
    FieldSpec(None, 10, "str"),   # source placeholder
    FieldSpec(None, 100, "str"),  # desc placeholder
    FieldSpec(None, 11, "signed_decimal"),  # amt placeholder
    FieldSpec(None, 9, "int"),    # merchant_id placeholder
    FieldSpec(None, 50, "str"),   # merchant_name placeholder
    FieldSpec(None, 50, "str"),   # merchant_city placeholder
    FieldSpec(None, 10, "str"),   # merchant_zip placeholder
    FieldSpec(None, 16, "str"),   # card_num placeholder
    FieldSpec(None, 26, "str"),   # orig_ts placeholder
    FieldSpec(None, 26, "str"),   # proc_ts placeholder
    FieldSpec(None, 20, "str"),   # FILLER
]

TRANSACTION_FIELDS: list[FieldSpec] = [
    FieldSpec("tran_id", 16, "str"),
    FieldSpec("tran_type_cd", 2, "str"),
    FieldSpec("tran_cat_cd", 4, "int"),
    FieldSpec("tran_source", 10, "str"),
    FieldSpec("tran_desc", 100, "str"),
    FieldSpec("tran_amt", 11, "signed_decimal"),
    FieldSpec("tran_merchant_id", 9, "int"),
    FieldSpec("tran_merchant_name", 50, "str"),
    FieldSpec("tran_merchant_city", 50, "str"),
    FieldSpec("tran_merchant_zip", 10, "str"),
    FieldSpec("tran_card_num", 16, "str"),
    FieldSpec("tran_orig_ts", 26, "str"),
    FieldSpec("tran_proc_ts", 26, "str"),
    FieldSpec(None, 20, "str"),  # FILLER
]

DAILY_TRAN_FIELDS: list[FieldSpec] = [
    FieldSpec("dalytran_id", 16, "str"),
    FieldSpec("dalytran_type_cd", 2, "str"),
    FieldSpec("dalytran_cat_cd", 4, "int"),
    FieldSpec("dalytran_source", 10, "str"),
    FieldSpec("dalytran_desc", 100, "str"),
    FieldSpec("dalytran_amt", 11, "signed_decimal"),
    FieldSpec("dalytran_merchant_id", 9, "int"),
    FieldSpec("dalytran_merchant_name", 50, "str"),
    FieldSpec("dalytran_merchant_city", 50, "str"),
    FieldSpec("dalytran_merchant_zip", 10, "str"),
    FieldSpec("dalytran_card_num", 16, "str"),
    FieldSpec("dalytran_orig_ts", 26, "str"),
    FieldSpec("dalytran_proc_ts", 26, "str"),
    FieldSpec(None, 20, "str"),  # FILLER
]

USER_SECURITY_FIELDS: list[FieldSpec] = [
    FieldSpec("sec_usr_id", 8, "str"),
    FieldSpec("sec_usr_fname", 20, "str"),
    FieldSpec("sec_usr_lname", 20, "str"),
    FieldSpec("sec_usr_pwd", 8, "str"),
    FieldSpec("sec_usr_type", 1, "str"),
    FieldSpec(None, 23, "str"),  # FILLER
]

TRAN_CAT_BAL_FIELDS: list[FieldSpec] = [
    FieldSpec("trancat_acct_id", 11, "int"),
    FieldSpec("trancat_type_cd", 2, "str"),
    FieldSpec("trancat_cd", 4, "int"),
    FieldSpec("tran_cat_bal", 11, "signed_decimal"),
    FieldSpec(None, 22, "str"),  # FILLER
]

DISCLOSURE_GROUP_FIELDS: list[FieldSpec] = [
    FieldSpec("dis_acct_group_id", 10, "str"),
    FieldSpec("dis_tran_type_cd", 2, "str"),
    FieldSpec("dis_tran_cat_cd", 4, "int"),
    FieldSpec("dis_int_rate", 6, "signed_decimal"),
    FieldSpec(None, 28, "str"),  # FILLER
]

# ── Generic parser ──────────────────────────────────────────────────


def _expected_length(field_specs: Sequence[FieldSpec]) -> int:
    return sum(f.length for f in field_specs)


def parse_fixed_width(raw: str, field_specs: Sequence[FieldSpec]) -> dict:
    """Parse a single fixed-width record into a dict of field values."""
    result: dict = {}
    offset = 0
    for spec in field_specs:
        chunk = raw[offset : offset + spec.length]
        offset += spec.length
        if spec.name is None:
            continue
        if spec.kind == "str":
            result[spec.name] = chunk.strip()
        elif spec.kind == "int":
            stripped = chunk.strip()
            result[spec.name] = int(stripped) if stripped else 0
        elif spec.kind == "signed_decimal":
            result[spec.name] = _decode_signed_decimal(chunk, spec.decimal_places)
    return result


def read_records(path: Path, record_length: int) -> list[str]:
    """Read a fixed-width file and return individual record strings.

    Handles records that may span multiple text lines (mainframe FB format).
    Records are separated by one or more blank lines, or the file is one
    continuous stream of ``record_length``-char blocks.
    """
    text = path.read_text(errors="replace")

    # Strategy 1: if the file uses blank-line separators between records
    # (common for the CardDemo ASCII exports), split on blank lines and
    # join continuation lines.
    blocks = text.split("\n\n")
    records: list[str] = []
    for block in blocks:
        joined = "".join(block.split("\n"))
        if not joined.strip():
            continue
        # Pad to record_length in case trailing spaces were stripped
        padded = joined.ljust(record_length)
        records.append(padded)

    if records:
        return records

    # Strategy 2: continuous stream — split every record_length chars
    flat = text.replace("\n", "")
    return [
        flat[i : i + record_length].ljust(record_length)
        for i in range(0, len(flat), record_length)
        if flat[i : i + record_length].strip()
    ]


# ── Store factories ─────────────────────────────────────────────────


def seed_accounts(data_dir: Path) -> InMemoryVsamStore[AccountRecord]:
    store: InMemoryVsamStore[AccountRecord] = InMemoryVsamStore(
        AccountRecord, lambda r: f"{r.acct_id:011d}"
    )
    path = data_dir / "acctdata.txt"
    if path.exists():
        for raw in read_records(path, AccountRecord.RECORD_LENGTH):
            vals = parse_fixed_width(raw, ACCOUNT_FIELDS)
            store.upsert(AccountRecord(**vals))
    return store


def seed_cards(data_dir: Path) -> InMemoryVsamStore[CardRecord]:
    store: InMemoryVsamStore[CardRecord] = InMemoryVsamStore(
        CardRecord, lambda r: r.card_num
    )
    path = data_dir / "carddata.txt"
    if path.exists():
        for raw in read_records(path, CardRecord.RECORD_LENGTH):
            vals = parse_fixed_width(raw, CARD_FIELDS)
            store.upsert(CardRecord(**vals))
    return store


def seed_customers(data_dir: Path) -> InMemoryVsamStore[CustomerRecord]:
    store: InMemoryVsamStore[CustomerRecord] = InMemoryVsamStore(
        CustomerRecord, lambda r: f"{r.cust_id:09d}"
    )
    path = data_dir / "custdata.txt"
    if path.exists():
        for raw in read_records(path, CustomerRecord.RECORD_LENGTH):
            vals = parse_fixed_width(raw, CUSTOMER_FIELDS)
            store.upsert(CustomerRecord(**vals))
    return store


def seed_card_xrefs(data_dir: Path) -> InMemoryVsamStore[CardXrefRecord]:
    store: InMemoryVsamStore[CardXrefRecord] = InMemoryVsamStore(
        CardXrefRecord, lambda r: r.xref_card_num
    )
    path = data_dir / "cardxref.txt"
    if path.exists():
        for raw in read_records(path, CardXrefRecord.RECORD_LENGTH):
            vals = parse_fixed_width(raw, CARD_XREF_FIELDS)
            store.upsert(CardXrefRecord(**vals))
    return store


def seed_transactions(data_dir: Path) -> InMemoryVsamStore[TransactionRecord]:
    store: InMemoryVsamStore[TransactionRecord] = InMemoryVsamStore(
        TransactionRecord, lambda r: r.tran_id
    )
    # No transaction data file in the seed data (transactions are generated)
    return store


def seed_daily_transactions(data_dir: Path) -> InMemoryVsamStore[DailyTransactionRecord]:
    store: InMemoryVsamStore[DailyTransactionRecord] = InMemoryVsamStore(
        DailyTransactionRecord, lambda r: r.dalytran_id
    )
    path = data_dir / "dailytran.txt"
    if path.exists():
        for raw in read_records(path, DailyTransactionRecord.RECORD_LENGTH):
            vals = parse_fixed_width(raw, DAILY_TRAN_FIELDS)
            store.upsert(DailyTransactionRecord(**vals))
    return store


def seed_tran_cat_balances(data_dir: Path) -> InMemoryVsamStore[TranCatBalanceRecord]:
    store: InMemoryVsamStore[TranCatBalanceRecord] = InMemoryVsamStore(
        TranCatBalanceRecord, lambda r: r.key
    )
    path = data_dir / "tcatbal.txt"
    if path.exists():
        for raw in read_records(path, TranCatBalanceRecord.RECORD_LENGTH):
            vals = parse_fixed_width(raw, TRAN_CAT_BAL_FIELDS)
            store.upsert(TranCatBalanceRecord(**vals))
    return store


def seed_disclosure_groups(data_dir: Path) -> InMemoryVsamStore[DisclosureGroupRecord]:
    store: InMemoryVsamStore[DisclosureGroupRecord] = InMemoryVsamStore(
        DisclosureGroupRecord, lambda r: r.key
    )
    path = data_dir / "discgrp.txt"
    if path.exists():
        for raw in read_records(path, DisclosureGroupRecord.RECORD_LENGTH):
            vals = parse_fixed_width(raw, DISCLOSURE_GROUP_FIELDS)
            store.upsert(DisclosureGroupRecord(**vals))
    return store


def seed_all(data_dir: Path) -> dict[str, InMemoryVsamStore]:
    """Seed all stores from the ASCII data directory.

    Returns a dict mapping VSAM file names (from CARDDEMO.CSD) to stores.
    """
    return {
        "ACCTDAT": seed_accounts(data_dir),
        "CARDDAT": seed_cards(data_dir),
        "CUSTDAT": seed_customers(data_dir),
        "CCXREF": seed_card_xrefs(data_dir),
        "TRANSACT": seed_transactions(data_dir),
        "DALYTRAN": seed_daily_transactions(data_dir),
        "TCATBAL": seed_tran_cat_balances(data_dir),
        "DISCGRP": seed_disclosure_groups(data_dir),
    }
