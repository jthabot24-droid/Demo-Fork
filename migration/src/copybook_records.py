"""Fixed-width field parsers and serializers matching CardDemo COBOL copybooks.

Handles ASCII zoned-decimal overpunch signs for signed numeric fields (PIC S9).
All monetary/decimal fields use ``decimal.Decimal`` scaled to 2 places with
``ROUND_DOWN`` (COBOL default truncation toward zero).

Copybooks covered:
  CVTRA06Y  DALYTRAN-RECORD        350 bytes
  CVTRA05Y  TRAN-RECORD            350 bytes
  CVACT01Y  ACCOUNT-RECORD         300 bytes
  CVACT03Y  CARD-XREF-RECORD        50 bytes
  CVTRA01Y  TRAN-CAT-BAL-RECORD     50 bytes
  CVTRA02Y  DIS-GROUP-RECORD        50 bytes
  CUSTREC   CUSTOMER-RECORD        500 bytes
  COSTM01   TRNX-RECORD            350 bytes
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN
from typing import Optional


# ---------------------------------------------------------------------------
# ASCII zoned-decimal overpunch sign tables
# ---------------------------------------------------------------------------

_POSITIVE_OVERPUNCH = {str(d): chr(c) for d, c in enumerate(
    [0x7B, 0x41, 0x42, 0x43, 0x44, 0x45, 0x46, 0x47, 0x48, 0x49]
)}  # 0-9 -> {, A-I

_NEGATIVE_OVERPUNCH = {str(d): chr(c) for d, c in enumerate(
    [0x7D, 0x4A, 0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x50, 0x51, 0x52]
)}  # 0-9 -> }, J-R

_OVERPUNCH_DECODE = {}
for _d in range(10):
    _OVERPUNCH_DECODE[_POSITIVE_OVERPUNCH[str(_d)]] = (str(_d), 1)
    _OVERPUNCH_DECODE[_NEGATIVE_OVERPUNCH[str(_d)]] = (str(_d), -1)
# Plain digits are treated as positive (unsigned fields)
for _d in range(10):
    _OVERPUNCH_DECODE[str(_d)] = (str(_d), 1)


TWO_PLACES = Decimal("0.01")


def _trunc2(value: Decimal) -> Decimal:
    """Truncate toward zero to 2 decimal places (COBOL default, no ROUNDED)."""
    return value.quantize(TWO_PLACES, rounding=ROUND_DOWN)


# ---------------------------------------------------------------------------
# Low-level parse / format helpers
# ---------------------------------------------------------------------------

def parse_str(record: str, offset: int, length: int) -> str:
    """Extract a fixed-width alphanumeric field (right-stripped)."""
    return record[offset:offset + length]


def parse_str_stripped(record: str, offset: int, length: int) -> str:
    return record[offset:offset + length].rstrip()


def parse_signed_decimal(record: str, offset: int, total_len: int,
                         dec_places: int) -> Decimal:
    """Parse a COBOL PIC S9(n)V9(m) zoned-decimal field with overpunch sign."""
    raw = record[offset:offset + total_len]
    if not raw or raw.isspace():
        return Decimal("0.00")
    last_char = raw[-1]
    digit, sign = _OVERPUNCH_DECODE.get(last_char, (last_char, 1))
    digits = raw[:-1] + digit
    # Insert decimal point
    int_part = digits[:len(digits) - dec_places]
    dec_part = digits[len(digits) - dec_places:]
    value = Decimal(f"{int_part}.{dec_part}")
    if sign < 0:
        value = -value
    return _trunc2(value)


def format_signed_decimal(value: Decimal, total_len: int,
                          dec_places: int) -> str:
    """Serialize a Decimal into COBOL zoned-decimal with ASCII overpunch sign."""
    value = _trunc2(value)
    is_negative = value < 0
    abs_val = abs(value)
    int_digits = total_len - dec_places
    # Multiply to remove decimal point
    raw_int = int(abs_val * (10 ** dec_places))
    digits = str(raw_int).zfill(total_len)
    digits = digits[-total_len:]  # Truncate to fit
    last_digit = digits[-1]
    table = _NEGATIVE_OVERPUNCH if is_negative else _POSITIVE_OVERPUNCH
    overpunch = table[last_digit]
    return digits[:-1] + overpunch


def format_unsigned_numeric(value: int, length: int) -> str:
    """Format an unsigned integer into PIC 9(n) zero-padded."""
    return str(abs(value)).zfill(length)[-length:]


def format_str(value: str, length: int) -> str:
    """Left-justify and space-pad/truncate a string to exactly `length` chars."""
    return value.ljust(length)[:length]


# ---------------------------------------------------------------------------
# Record dataclasses
# ---------------------------------------------------------------------------

@dataclass
class DalytranRecord:
    """CVTRA06Y — DALYTRAN-RECORD (350 bytes)."""
    dalytran_id: str = ""
    dalytran_type_cd: str = ""
    dalytran_cat_cd: str = ""
    dalytran_source: str = ""
    dalytran_desc: str = ""
    dalytran_amt: Decimal = field(default_factory=lambda: Decimal("0.00"))
    dalytran_merchant_id: str = ""
    dalytran_merchant_name: str = ""
    dalytran_merchant_city: str = ""
    dalytran_merchant_zip: str = ""
    dalytran_card_num: str = ""
    dalytran_orig_ts: str = ""
    dalytran_proc_ts: str = ""

    RECORD_LEN = 350

    _LAYOUT = [
        ("dalytran_id",            0,  16, "X"),
        ("dalytran_type_cd",      16,   2, "X"),
        ("dalytran_cat_cd",       18,   4, "9"),
        ("dalytran_source",       22,  10, "X"),
        ("dalytran_desc",         32, 100, "X"),
        ("dalytran_amt",         132,  11, "S9V", 9, 2),
        ("dalytran_merchant_id", 143,   9, "9"),
        ("dalytran_merchant_name",152, 50, "X"),
        ("dalytran_merchant_city",202, 50, "X"),
        ("dalytran_merchant_zip", 252, 10, "X"),
        ("dalytran_card_num",    262,  16, "X"),
        ("dalytran_orig_ts",     278,  26, "X"),
        ("dalytran_proc_ts",     304,  26, "X"),
        # FILLER 330-349 (20 bytes)
    ]


@dataclass
class TranRecord:
    """CVTRA05Y — TRAN-RECORD (350 bytes)."""
    tran_id: str = ""
    tran_type_cd: str = ""
    tran_cat_cd: str = ""
    tran_source: str = ""
    tran_desc: str = ""
    tran_amt: Decimal = field(default_factory=lambda: Decimal("0.00"))
    tran_merchant_id: str = ""
    tran_merchant_name: str = ""
    tran_merchant_city: str = ""
    tran_merchant_zip: str = ""
    tran_card_num: str = ""
    tran_orig_ts: str = ""
    tran_proc_ts: str = ""

    RECORD_LEN = 350

    _LAYOUT = [
        ("tran_id",            0,  16, "X"),
        ("tran_type_cd",      16,   2, "X"),
        ("tran_cat_cd",       18,   4, "9"),
        ("tran_source",       22,  10, "X"),
        ("tran_desc",         32, 100, "X"),
        ("tran_amt",         132,  11, "S9V", 9, 2),
        ("tran_merchant_id", 143,   9, "9"),
        ("tran_merchant_name",152, 50, "X"),
        ("tran_merchant_city",202, 50, "X"),
        ("tran_merchant_zip", 252, 10, "X"),
        ("tran_card_num",    262,  16, "X"),
        ("tran_orig_ts",     278,  26, "X"),
        ("tran_proc_ts",     304,  26, "X"),
    ]


@dataclass
class AccountRecord:
    """CVACT01Y — ACCOUNT-RECORD (300 bytes)."""
    acct_id: str = ""
    acct_active_status: str = ""
    acct_curr_bal: Decimal = field(default_factory=lambda: Decimal("0.00"))
    acct_credit_limit: Decimal = field(default_factory=lambda: Decimal("0.00"))
    acct_cash_credit_limit: Decimal = field(
        default_factory=lambda: Decimal("0.00"))
    acct_open_date: str = ""
    acct_expiraion_date: str = ""
    acct_reissue_date: str = ""
    acct_curr_cyc_credit: Decimal = field(
        default_factory=lambda: Decimal("0.00"))
    acct_curr_cyc_debit: Decimal = field(
        default_factory=lambda: Decimal("0.00"))
    acct_addr_zip: str = ""
    acct_group_id: str = ""

    RECORD_LEN = 300

    _LAYOUT = [
        ("acct_id",               0, 11, "9"),
        ("acct_active_status",   11,  1, "X"),
        ("acct_curr_bal",        12, 12, "S9V", 10, 2),
        ("acct_credit_limit",    24, 12, "S9V", 10, 2),
        ("acct_cash_credit_limit", 36, 12, "S9V", 10, 2),
        ("acct_open_date",       48, 10, "X"),
        ("acct_expiraion_date",  58, 10, "X"),
        ("acct_reissue_date",    68, 10, "X"),
        ("acct_curr_cyc_credit", 78, 12, "S9V", 10, 2),
        ("acct_curr_cyc_debit",  90, 12, "S9V", 10, 2),
        ("acct_addr_zip",       102, 10, "X"),
        ("acct_group_id",       112, 10, "X"),
        # FILLER 122-299 (178 bytes)
    ]


@dataclass
class CardXrefRecord:
    """CVACT03Y — CARD-XREF-RECORD (50 bytes)."""
    xref_card_num: str = ""
    xref_cust_id: str = ""
    xref_acct_id: str = ""

    RECORD_LEN = 50

    _LAYOUT = [
        ("xref_card_num",  0, 16, "X"),
        ("xref_cust_id",  16,  9, "9"),
        ("xref_acct_id",  25, 11, "9"),
        # FILLER 36-49 (14 bytes)
    ]


@dataclass
class TranCatBalRecord:
    """CVTRA01Y — TRAN-CAT-BAL-RECORD (50 bytes)."""
    trancat_acct_id: str = ""
    trancat_type_cd: str = ""
    trancat_cd: str = ""
    tran_cat_bal: Decimal = field(default_factory=lambda: Decimal("0.00"))

    RECORD_LEN = 50

    _LAYOUT = [
        ("trancat_acct_id",  0, 11, "9"),
        ("trancat_type_cd", 11,  2, "X"),
        ("trancat_cd",      13,  4, "9"),
        ("tran_cat_bal",    17, 11, "S9V", 9, 2),
        # FILLER 28-49 (22 bytes)
    ]


@dataclass
class DisGroupRecord:
    """CVTRA02Y — DIS-GROUP-RECORD (50 bytes)."""
    dis_acct_group_id: str = ""
    dis_tran_type_cd: str = ""
    dis_tran_cat_cd: str = ""
    dis_int_rate: Decimal = field(default_factory=lambda: Decimal("0.00"))

    RECORD_LEN = 50

    _LAYOUT = [
        ("dis_acct_group_id",  0, 10, "X"),
        ("dis_tran_type_cd",  10,  2, "X"),
        ("dis_tran_cat_cd",   12,  4, "9"),
        ("dis_int_rate",      16,  6, "S9V", 4, 2),
        # FILLER 22-49 (28 bytes)
    ]


@dataclass
class CustomerRecord:
    """CUSTREC — CUSTOMER-RECORD (500 bytes)."""
    cust_id: str = ""
    cust_first_name: str = ""
    cust_middle_name: str = ""
    cust_last_name: str = ""
    cust_addr_line_1: str = ""
    cust_addr_line_2: str = ""
    cust_addr_line_3: str = ""
    cust_addr_state_cd: str = ""
    cust_addr_country_cd: str = ""
    cust_addr_zip: str = ""
    cust_phone_num_1: str = ""
    cust_phone_num_2: str = ""
    cust_ssn: str = ""
    cust_govt_issued_id: str = ""
    cust_dob_yyyymmdd: str = ""
    cust_eft_account_id: str = ""
    cust_pri_card_holder_ind: str = ""
    cust_fico_credit_score: str = ""

    RECORD_LEN = 500

    _LAYOUT = [
        ("cust_id",                   0,   9, "9"),
        ("cust_first_name",           9,  25, "X"),
        ("cust_middle_name",         34,  25, "X"),
        ("cust_last_name",           59,  25, "X"),
        ("cust_addr_line_1",         84,  50, "X"),
        ("cust_addr_line_2",        134,  50, "X"),
        ("cust_addr_line_3",        184,  50, "X"),
        ("cust_addr_state_cd",      234,   2, "X"),
        ("cust_addr_country_cd",    236,   3, "X"),
        ("cust_addr_zip",           239,  10, "X"),
        ("cust_phone_num_1",        249,  15, "X"),
        ("cust_phone_num_2",        264,  15, "X"),
        ("cust_ssn",                279,   9, "9"),
        ("cust_govt_issued_id",     288,  20, "X"),
        ("cust_dob_yyyymmdd",       308,  10, "X"),
        ("cust_eft_account_id",     318,  10, "X"),
        ("cust_pri_card_holder_ind", 328,  1, "X"),
        ("cust_fico_credit_score",  329,   3, "9"),
        # FILLER 332-499 (168 bytes)
    ]


@dataclass
class TrnxRecord:
    """COSTM01 — TRNX-RECORD (350 bytes). Key = CARD-NUM + TRAN-ID."""
    trnx_card_num: str = ""
    trnx_id: str = ""
    trnx_type_cd: str = ""
    trnx_cat_cd: str = ""
    trnx_source: str = ""
    trnx_desc: str = ""
    trnx_amt: Decimal = field(default_factory=lambda: Decimal("0.00"))
    trnx_merchant_id: str = ""
    trnx_merchant_name: str = ""
    trnx_merchant_city: str = ""
    trnx_merchant_zip: str = ""
    trnx_orig_ts: str = ""
    trnx_proc_ts: str = ""

    RECORD_LEN = 350

    _LAYOUT = [
        ("trnx_card_num",         0, 16, "X"),
        ("trnx_id",              16, 16, "X"),
        ("trnx_type_cd",         32,  2, "X"),
        ("trnx_cat_cd",          34,  4, "9"),
        ("trnx_source",          38, 10, "X"),
        ("trnx_desc",            48,100, "X"),
        ("trnx_amt",            148, 11, "S9V", 9, 2),
        ("trnx_merchant_id",    159,  9, "9"),
        ("trnx_merchant_name",  168, 50, "X"),
        ("trnx_merchant_city",  218, 50, "X"),
        ("trnx_merchant_zip",   268, 10, "X"),
        ("trnx_orig_ts",        278, 26, "X"),
        ("trnx_proc_ts",        304, 26, "X"),
        # FILLER 330-349 (20 bytes)
    ]


# ---------------------------------------------------------------------------
# Generic parse / serialize driven by _LAYOUT
# ---------------------------------------------------------------------------

def _parse_record(record_cls, line: str):
    """Parse a fixed-width line into a record dataclass instance."""
    # Right-pad to expected length if line is short
    padded = line.ljust(record_cls.RECORD_LEN)
    kwargs = {}
    for entry in record_cls._LAYOUT:
        name, offset, length = entry[0], entry[1], entry[2]
        field_type = entry[3]
        if field_type == "S9V":
            int_digits, dec_places = entry[4], entry[5]
            kwargs[name] = parse_signed_decimal(
                padded, offset, length, dec_places)
        else:
            kwargs[name] = parse_str(padded, offset, length)
    return record_cls(**kwargs)


def _serialize_record(rec, record_cls) -> str:
    """Serialize a record dataclass instance to a fixed-width string."""
    buf = [" "] * record_cls.RECORD_LEN
    for entry in record_cls._LAYOUT:
        name, offset, length = entry[0], entry[1], entry[2]
        field_type = entry[3]
        value = getattr(rec, name)
        if field_type == "S9V":
            int_digits, dec_places = entry[4], entry[5]
            formatted = format_signed_decimal(value, length, dec_places)
        elif field_type == "9":
            formatted = format_str(value, length)
        else:
            formatted = format_str(value, length)
        for i, ch in enumerate(formatted):
            buf[offset + i] = ch
    return "".join(buf)


# ---------------------------------------------------------------------------
# Public parse / serialize functions
# ---------------------------------------------------------------------------

def parse_dalytran(line: str) -> DalytranRecord:
    return _parse_record(DalytranRecord, line)

def serialize_dalytran(rec: DalytranRecord) -> str:
    return _serialize_record(rec, DalytranRecord)

def parse_tran(line: str) -> TranRecord:
    return _parse_record(TranRecord, line)

def serialize_tran(rec: TranRecord) -> str:
    return _serialize_record(rec, TranRecord)

def parse_account(line: str) -> AccountRecord:
    return _parse_record(AccountRecord, line)

def serialize_account(rec: AccountRecord) -> str:
    return _serialize_record(rec, AccountRecord)

def parse_card_xref(line: str) -> CardXrefRecord:
    return _parse_record(CardXrefRecord, line)

def serialize_card_xref(rec: CardXrefRecord) -> str:
    return _serialize_record(rec, CardXrefRecord)

def parse_tran_cat_bal(line: str) -> TranCatBalRecord:
    return _parse_record(TranCatBalRecord, line)

def serialize_tran_cat_bal(rec: TranCatBalRecord) -> str:
    return _serialize_record(rec, TranCatBalRecord)

def parse_dis_group(line: str) -> DisGroupRecord:
    return _parse_record(DisGroupRecord, line)

def serialize_dis_group(rec: DisGroupRecord) -> str:
    return _serialize_record(rec, DisGroupRecord)

def parse_customer(line: str) -> CustomerRecord:
    return _parse_record(CustomerRecord, line)

def serialize_customer(rec: CustomerRecord) -> str:
    return _serialize_record(rec, CustomerRecord)

def parse_trnx(line: str) -> TrnxRecord:
    return _parse_record(TrnxRecord, line)

def serialize_trnx(rec: TrnxRecord) -> str:
    return _serialize_record(rec, TrnxRecord)


# ---------------------------------------------------------------------------
# File-level loaders
# ---------------------------------------------------------------------------

def load_file(path: str, parse_fn):
    """Read a fixed-width file and return a list of parsed records."""
    records = []
    with open(path, "r") as f:
        for line in f:
            line = line.rstrip("\n").rstrip("\r")
            if line:
                records.append(parse_fn(line))
    return records


def write_file(path: str, records, serialize_fn):
    """Write a list of records to a fixed-width file (one record per line)."""
    with open(path, "w") as f:
        for rec in records:
            f.write(serialize_fn(rec) + "\n")
