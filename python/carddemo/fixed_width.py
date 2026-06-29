"""Fixed-width record parser and writer for CardDemo flat files.

The ASCII ``.txt`` data files under ``app/data/ASCII/`` use COBOL
display-format conventions:

* Alphanumeric fields (``PIC X(n)``) are left-justified, space-padded.
* Unsigned numeric fields (``PIC 9(n)``) are right-justified, zero-padded.
* Signed numeric fields (``PIC S9(m)V9(n)``) use *zoned-decimal sign
  overpunch* on the **last** byte:

  Positive: ``{ A B C D E F G H I`` → digits ``0 1 2 3 4 5 6 7 8 9``
  Negative: ``} J K L M N O P Q R`` → digits ``0 1 2 3 4 5 6 7 8 9``

Each field spec is a tuple ``(name, width, kind)`` where *kind* is one of:

* ``"X"``  — alphanumeric (returned as ``str``)
* ``"9"``  — unsigned numeric (returned as ``str``, preserving leading zeros)
* ``"S9"`` — signed zoned-decimal (returned as ``Decimal``).
  Requires an extra ``(integer_digits, decimal_digits)`` parameter.
* ``"FILLER"`` — padding bytes (skipped on read, space-filled on write)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, Sequence

# ── sign-overpunch lookup tables ──────────────────────────────────

_POS_OVERPUNCH = "{ABCDEFGHI"        # index == digit value
_NEG_OVERPUNCH = "}JKLMNOPQR"

_OVERPUNCH_DIGIT: dict[str, tuple[int, int]] = {}  # char → (digit, sign)
for _d in range(10):
    _OVERPUNCH_DIGIT[_POS_OVERPUNCH[_d]] = (_d, 1)
    _OVERPUNCH_DIGIT[_NEG_OVERPUNCH[_d]] = (_d, -1)

# Also handle plain digits (unsigned last byte)
for _d in range(10):
    _OVERPUNCH_DIGIT[str(_d)] = (_d, 1)

FieldSpec = tuple  # (name, width, kind, ...)


def _decode_signed(raw: str, int_digits: int, dec_digits: int) -> Decimal:
    """Decode a zoned-decimal field with sign overpunch."""
    if not raw or raw.isspace():
        return Decimal("0.00")
    last_char = raw[-1]
    digit, sign = _OVERPUNCH_DIGIT.get(last_char, (0, 1))
    digits_str = raw[:-1] + str(digit)
    if len(digits_str) != int_digits + dec_digits:
        digits_str = digits_str.zfill(int_digits + dec_digits)
    int_part = digits_str[:int_digits]
    dec_part = digits_str[int_digits:]
    value = Decimal(f"{int_part}.{dec_part}")
    return value * sign


def _encode_signed(value: Decimal, int_digits: int, dec_digits: int) -> str:
    """Encode a Decimal into zoned-decimal with sign overpunch."""
    sign = -1 if value < 0 else 1
    abs_val = abs(value)
    int_part = int(abs_val)
    dec_part = int(round((abs_val - int_part) * (10 ** dec_digits)))
    total_digits = int_digits + dec_digits
    digits_str = f"{int_part:0{int_digits}d}{dec_part:0{dec_digits}d}"
    if len(digits_str) > total_digits:
        digits_str = digits_str[:total_digits]
    last_digit = int(digits_str[-1])
    overpunch = _POS_OVERPUNCH[last_digit] if sign >= 0 else _NEG_OVERPUNCH[last_digit]
    return digits_str[:-1] + overpunch


# ── generic parser / writer ───────────────────────────────────────


def parse_record(line: str, spec: Sequence[FieldSpec]) -> dict[str, Any]:
    """Parse a single fixed-width line into a dict according to *spec*.

    The line is right-padded with spaces to the full record length if
    it is shorter (handles trimmed trailing FILLER).
    """
    total_width = sum(s[1] for s in spec)
    line = line.ljust(total_width)
    result: dict[str, Any] = {}
    offset = 0
    for field_def in spec:
        name = field_def[0]
        width = field_def[1]
        kind = field_def[2]
        raw = line[offset : offset + width]
        offset += width
        if kind == "FILLER":
            continue
        if kind == "X":
            result[name] = raw
        elif kind == "9":
            result[name] = raw
        elif kind == "S9":
            int_d, dec_d = field_def[3], field_def[4]
            result[name] = _decode_signed(raw, int_d, dec_d)
        else:
            result[name] = raw
    return result


def write_record(data: dict[str, Any], spec: Sequence[FieldSpec]) -> str:
    """Serialize a dict to a fixed-width string according to *spec*."""
    parts: list[str] = []
    for field_def in spec:
        name = field_def[0]
        width = field_def[1]
        kind = field_def[2]
        if kind == "FILLER":
            parts.append(" " * width)
            continue
        value = data.get(name, "")
        if kind == "X":
            parts.append(str(value).ljust(width)[:width])
        elif kind == "9":
            parts.append(str(value).zfill(width)[:width])
        elif kind == "S9":
            int_d, dec_d = field_def[3], field_def[4]
            parts.append(_encode_signed(Decimal(str(value)), int_d, dec_d))
        else:
            parts.append(str(value).ljust(width)[:width])
    return "".join(parts)


# ── record-layout specifications ──────────────────────────────────
# Derived directly from the COBOL copybooks in app/cpy/

ACCOUNT_SPEC: list[FieldSpec] = [
    ("acct_id",               11, "9"),
    ("acct_active_status",     1, "X"),
    ("acct_curr_bal",         12, "S9", 10, 2),
    ("acct_credit_limit",     12, "S9", 10, 2),
    ("acct_cash_credit_limit",12, "S9", 10, 2),
    ("acct_open_date",        10, "X"),
    ("acct_expiration_date",  10, "X"),
    ("acct_reissue_date",     10, "X"),
    ("acct_curr_cyc_credit",  12, "S9", 10, 2),
    ("acct_curr_cyc_debit",   12, "S9", 10, 2),
    ("acct_addr_zip",         10, "X"),
    ("acct_group_id",         10, "X"),
    ("_filler",              178, "FILLER"),
]

CUSTOMER_SPEC: list[FieldSpec] = [
    ("cust_id",                9, "9"),
    ("cust_first_name",       25, "X"),
    ("cust_middle_name",      25, "X"),
    ("cust_last_name",        25, "X"),
    ("cust_addr_line_1",      50, "X"),
    ("cust_addr_line_2",      50, "X"),
    ("cust_addr_line_3",      50, "X"),
    ("cust_addr_state_cd",     2, "X"),
    ("cust_addr_country_cd",   3, "X"),
    ("cust_addr_zip",         10, "X"),
    ("cust_phone_num_1",      15, "X"),
    ("cust_phone_num_2",      15, "X"),
    ("cust_ssn",               9, "9"),
    ("cust_govt_issued_id",   20, "X"),
    ("cust_dob_yyyy_mm_dd",   10, "X"),
    ("cust_eft_account_id",   10, "X"),
    ("cust_pri_card_holder_ind", 1, "X"),
    ("cust_fico_credit_score", 3, "9"),
    ("_filler",              168, "FILLER"),
]

CARD_SPEC: list[FieldSpec] = [
    ("card_num",              16, "X"),
    ("card_acct_id",          11, "9"),
    ("card_cvv_cd",            3, "9"),
    ("card_embossed_name",    50, "X"),
    ("card_expiration_date",  10, "X"),
    ("card_active_status",     1, "X"),
    ("_filler",               59, "FILLER"),
]

CARD_XREF_SPEC: list[FieldSpec] = [
    ("xref_card_num",         16, "X"),
    ("xref_cust_id",           9, "9"),
    ("xref_acct_id",          11, "9"),
    ("_filler",               14, "FILLER"),
]

TRANSACTION_SPEC: list[FieldSpec] = [
    ("tran_id",               16, "X"),
    ("tran_type_cd",           2, "X"),
    ("tran_cat_cd",            4, "9"),
    ("tran_source",           10, "X"),
    ("tran_desc",            100, "X"),
    ("tran_amt",              11, "S9", 9, 2),
    ("tran_merchant_id",       9, "9"),
    ("tran_merchant_name",    50, "X"),
    ("tran_merchant_city",    50, "X"),
    ("tran_merchant_zip",     10, "X"),
    ("tran_card_num",         16, "X"),
    ("tran_orig_ts",          26, "X"),
    ("tran_proc_ts",          26, "X"),
    ("_filler",               20, "FILLER"),
]

DAILY_TRANSACTION_SPEC: list[FieldSpec] = [
    ("dalytran_id",           16, "X"),
    ("dalytran_type_cd",       2, "X"),
    ("dalytran_cat_cd",        4, "9"),
    ("dalytran_source",       10, "X"),
    ("dalytran_desc",        100, "X"),
    ("dalytran_amt",          11, "S9", 9, 2),
    ("dalytran_merchant_id",   9, "9"),
    ("dalytran_merchant_name", 50, "X"),
    ("dalytran_merchant_city", 50, "X"),
    ("dalytran_merchant_zip",  10, "X"),
    ("dalytran_card_num",     16, "X"),
    ("dalytran_orig_ts",      26, "X"),
    ("dalytran_proc_ts",      26, "X"),
    ("_filler",               20, "FILLER"),
]

TRAN_CAT_BAL_SPEC: list[FieldSpec] = [
    ("trancat_acct_id",       11, "9"),
    ("trancat_type_cd",        2, "X"),
    ("trancat_cd",             4, "9"),
    ("tran_cat_bal",          11, "S9", 9, 2),
    ("_filler",               22, "FILLER"),
]

DISC_GROUP_SPEC: list[FieldSpec] = [
    ("dis_acct_group_id",     10, "X"),
    ("dis_tran_type_cd",       2, "X"),
    ("dis_tran_cat_cd",        4, "9"),
    ("dis_int_rate",           6, "S9", 4, 2),
    ("_filler",               28, "FILLER"),
]

TRAN_TYPE_SPEC: list[FieldSpec] = [
    ("tran_type",              2, "X"),
    ("tran_type_desc",        50, "X"),
    ("_filler",                8, "FILLER"),
]

TRAN_CAT_SPEC: list[FieldSpec] = [
    ("tran_type_cd",           2, "X"),
    ("tran_cat_cd",            4, "9"),
    ("tran_cat_type_desc",    50, "X"),
    ("_filler",                4, "FILLER"),
]

USER_SECURITY_SPEC: list[FieldSpec] = [
    ("sec_usr_id",             8, "X"),
    ("sec_usr_fname",         20, "X"),
    ("sec_usr_lname",         20, "X"),
    ("sec_usr_pwd",            8, "X"),
    ("sec_usr_type",           1, "X"),
    ("_filler",               23, "FILLER"),
]


# ── convenience functions ─────────────────────────────────────────


def read_file(path: str, spec: Sequence[FieldSpec]) -> list[dict[str, Any]]:
    """Read all records from a fixed-width flat file."""
    records: list[dict[str, Any]] = []
    with open(path, "r", encoding="ascii", errors="replace") as fh:
        for line in fh:
            line = line.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            records.append(parse_record(line, spec))
    return records


def write_file(
    path: str,
    records: Sequence[dict[str, Any]],
    spec: Sequence[FieldSpec],
) -> None:
    """Write records to a fixed-width flat file."""
    with open(path, "w", encoding="ascii", newline="\n") as fh:
        for rec in records:
            fh.write(write_record(rec, spec) + "\n")
