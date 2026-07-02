"""Plain-Python migration of CBACT04C.cbl — INTCALC interest calculator.

Original COBOL: app/cbl/CBACT04C.cbl
Reads the transaction-category-balance file sequentially (ordered by account),
computes monthly interest for each category using rates from the disclosure-
group file, accumulates per-account totals, updates account records, and
writes interest transaction records.

Formula (paragraph 1300-COMPUTE-INTEREST):
    monthly_int = (TRAN-CAT-BAL * DIS-INT-RATE) / 1200
    truncated to 2 decimal places (ROUND_DOWN).

PARM-DATE is accepted as a function argument (JCL: PARM='2022071800').
"""

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_DOWN

from migration.src.copybook_records import (
    TranCatBalRecord, DisGroupRecord, AccountRecord, CardXrefRecord,
    TranRecord,
    parse_tran_cat_bal, parse_dis_group, parse_account, parse_card_xref,
    serialize_tran, serialize_account,
    load_file, write_file, format_str, _trunc2,
)


TWO_PLACES = Decimal("0.01")


@dataclass
class IntcalcResult:
    """Summary returned by run_intcalc."""
    record_count: int = 0
    interest_transactions: list = field(default_factory=list)
    updated_accounts: dict = field(default_factory=dict)


def _lookup_interest_rate(
    acct_group_id: str,
    tran_type_cd: str,
    tran_cat_cd: str,
    discgrp_map: dict,
) -> Decimal:
    """Look up interest rate; fall back to DEFAULT group if not found."""
    key = (acct_group_id, tran_type_cd, tran_cat_cd)
    rec = discgrp_map.get(key)
    if rec is not None:
        return rec.dis_int_rate

    default_key = (format_str("DEFAULT", 10), tran_type_cd, tran_cat_cd)
    rec = discgrp_map.get(default_key)
    if rec is not None:
        return rec.dis_int_rate

    return Decimal("0.00")


def compute_monthly_interest(balance: Decimal, rate: Decimal) -> Decimal:
    """(TRAN-CAT-BAL * DIS-INT-RATE) / 1200 truncated to 2 decimals."""
    return _trunc2((balance * rate) / Decimal("1200"))


def make_db2_timestamp_from_parm(parm_date: str) -> str:
    """Build a DB2-format timestamp from PARM-DATE for interest transactions."""
    # PARM-DATE is like '2022071800' (YYYYMMDDXX)
    yyyy = parm_date[0:4]
    mm = parm_date[4:6]
    dd = parm_date[6:8]
    return f"{yyyy}-{mm}-{dd}-00.00.00.000000"


def run_intcalc(
    tcatbal_path: str,
    discgrp_path: str,
    account_path: str,
    xref_path: str,
    transact_output_path: str = None,
    account_output_path: str = None,
    parm_date: str = "2022071800",
    timestamp_override: str = None,
) -> IntcalcResult:
    """Execute the INTCALC interest calculation job."""
    tcatbal_records = load_file(tcatbal_path, parse_tran_cat_bal)
    discgrp_records = load_file(discgrp_path, parse_dis_group)
    account_records = load_file(account_path, parse_account)
    xref_records = load_file(xref_path, parse_card_xref)

    return run_intcalc_pure(
        tcatbal_records, discgrp_records, account_records, xref_records,
        parm_date, transact_output_path, account_output_path,
        timestamp_override)


def run_intcalc_pure(
    tcatbal_records: list,
    discgrp_records: list,
    account_records: list,
    xref_records: list,
    parm_date: str = "2022071800",
    transact_output_path: str = None,
    account_output_path: str = None,
    timestamp_override: str = None,
) -> IntcalcResult:
    """Pure-Python INTCALC logic (no file I/O dependency for unit testing)."""
    # Build maps
    discgrp_map = {}
    for rec in discgrp_records:
        key = (rec.dis_acct_group_id, rec.dis_tran_type_cd, rec.dis_tran_cat_cd)
        discgrp_map[key] = rec

    account_map = {}
    for rec in account_records:
        account_map[rec.acct_id] = rec

    # Build xref lookup by acct_id (alternate key, as COBOL does)
    xref_by_acct = {}
    for rec in xref_records:
        xref_by_acct[rec.xref_acct_id] = rec

    ts = timestamp_override or make_db2_timestamp_from_parm(parm_date)
    result = IntcalcResult()
    tranid_suffix = 0

    last_acct_num = None
    total_int = Decimal("0.00")
    first_time = True
    current_acct = None
    current_xref = None

    for tcatbal in tcatbal_records:
        result.record_count += 1

        if tcatbal.trancat_acct_id != last_acct_num:
            # Account break
            if not first_time and current_acct is not None:
                _update_account(current_acct, total_int)
            else:
                first_time = False

            total_int = Decimal("0.00")
            last_acct_num = tcatbal.trancat_acct_id

            current_acct = account_map.get(tcatbal.trancat_acct_id)
            current_xref = xref_by_acct.get(tcatbal.trancat_acct_id)

        if current_acct is None:
            continue

        # Look up interest rate
        acct_group_id = current_acct.acct_group_id
        int_rate = _lookup_interest_rate(
            acct_group_id, tcatbal.trancat_type_cd, tcatbal.trancat_cd,
            discgrp_map)

        if int_rate == Decimal("0.00"):
            continue

        # Compute interest
        monthly_int = compute_monthly_interest(tcatbal.tran_cat_bal, int_rate)
        total_int = _trunc2(total_int + monthly_int)

        # Write interest transaction record
        tranid_suffix += 1
        tran = _build_interest_tran(
            current_acct, current_xref, monthly_int, parm_date,
            tranid_suffix, ts)
        result.interest_transactions.append(tran)

    # Final account update after last record
    if current_acct is not None and last_acct_num is not None:
        _update_account(current_acct, total_int)

    result.updated_accounts = account_map

    # Write outputs
    if transact_output_path:
        write_file(transact_output_path, result.interest_transactions,
                   serialize_tran)

    if account_output_path:
        write_file(account_output_path, list(account_map.values()),
                   serialize_account)

    return result


def _update_account(acct: AccountRecord, total_int: Decimal):
    """Paragraph 1050-UPDATE-ACCOUNT: add interest to balance, zero cycle."""
    acct.acct_curr_bal = _trunc2(acct.acct_curr_bal + total_int)
    acct.acct_curr_cyc_credit = Decimal("0.00")
    acct.acct_curr_cyc_debit = Decimal("0.00")


def _build_interest_tran(
    acct: AccountRecord,
    xref: CardXrefRecord,
    monthly_int: Decimal,
    parm_date: str,
    suffix: int,
    timestamp: str,
) -> TranRecord:
    """Paragraph 1300-B-WRITE-TX: build an interest transaction record."""
    tran_id = parm_date + f"{suffix:06d}"
    card_num = xref.xref_card_num if xref else format_str("", 16)
    acct_id_str = acct.acct_id.strip()
    desc = format_str(f"Int. for a/c {acct_id_str}", 100)

    return TranRecord(
        tran_id=format_str(tran_id, 16),
        tran_type_cd="01",
        tran_cat_cd="0005",
        tran_source=format_str("System", 10),
        tran_desc=desc,
        tran_amt=monthly_int,
        tran_merchant_id="000000000",
        tran_merchant_name=format_str("", 50),
        tran_merchant_city=format_str("", 50),
        tran_merchant_zip=format_str("", 10),
        tran_card_num=card_num,
        tran_orig_ts=format_str(timestamp, 26),
        tran_proc_ts=format_str(timestamp, 26),
    )
