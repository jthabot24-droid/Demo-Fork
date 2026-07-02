"""PySpark migration of CBTRN02C.cbl — POSTTRAN daily transaction posting.

Original COBOL: app/cbl/CBTRN02C.cbl
Reads the daily transaction file, validates each transaction against the
card cross-reference and account master, posts valid transactions (updating
category balances and account records), and routes invalid ones to a
rejects output with a validation trailer.

Validation reasons:
  100 — Card number not found in xref
  101 — Account not found
  102 — Over credit limit
  103 — Transaction received after account expiration

Return code: 0 = all OK, 4 = at least one reject.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pyspark.sql import SparkSession, DataFrame

from migration.src.copybook_records import (
    DalytranRecord, TranRecord, AccountRecord, CardXrefRecord,
    TranCatBalRecord,
    parse_dalytran, serialize_dalytran,
    parse_tran, serialize_tran,
    parse_account, serialize_account,
    parse_card_xref, serialize_card_xref,
    parse_tran_cat_bal, serialize_tran_cat_bal,
    format_str, _trunc2,
)


REJECT_RECORD_LEN = 430  # 350-byte tran + 80-byte validation trailer


@dataclass
class PosttranResult:
    """Summary returned by run_posttran."""
    transaction_count: int = 0
    reject_count: int = 0
    return_code: int = 0
    posted_records: list = None
    reject_records: list = None
    updated_accounts: dict = None
    updated_tcatbals: dict = None

    def __post_init__(self):
        if self.posted_records is None:
            self.posted_records = []
        if self.reject_records is None:
            self.reject_records = []
        if self.updated_accounts is None:
            self.updated_accounts = {}
        if self.updated_tcatbals is None:
            self.updated_tcatbals = {}


def make_db2_timestamp(dt: Optional[datetime] = None) -> str:
    """Build a DB2-format timestamp string: YYYY-MM-DD-HH.MM.SS.mm0000"""
    if dt is None:
        dt = datetime.now()
    return (f"{dt.year:04d}-{dt.month:02d}-{dt.day:02d}-"
            f"{dt.hour:02d}.{dt.minute:02d}.{dt.second:02d}."
            f"{dt.microsecond // 10000:02d}0000")


def _format_validation_trailer(reason: int, desc: str) -> str:
    """Build an 80-byte validation trailer: 4-digit reason + 76-char desc."""
    return f"{reason:04d}" + format_str(desc, 76)


# ---------------------------------------------------------------------------
# Pure validation logic (no I/O)
# ---------------------------------------------------------------------------

def validate_transaction(
    dalytran: DalytranRecord,
    xref_map: dict,
    account_map: dict,
) -> tuple:
    """Validate a daily transaction.

    Returns (fail_reason, fail_desc, xref_record, account_record).
    fail_reason == 0 means valid.
    """
    card_num = dalytran.dalytran_card_num
    xref = xref_map.get(card_num)
    if xref is None:
        return (100, "INVALID CARD NUMBER FOUND", None, None)

    acct_id = xref.xref_acct_id
    acct = account_map.get(acct_id)
    if acct is None:
        return (101, "ACCOUNT RECORD NOT FOUND", xref, None)

    # Over-limit check: credit_limit < (cyc_credit - cyc_debit + tran_amt)
    temp_bal = acct.acct_curr_cyc_credit - acct.acct_curr_cyc_debit + dalytran.dalytran_amt
    fail_reason = 0
    fail_desc = ""

    if acct.acct_credit_limit < temp_bal:
        fail_reason = 102
        fail_desc = "OVERLIMIT TRANSACTION"

    # Expiry check (COBOL compares string: expiration_date < orig_ts first 10)
    orig_date = dalytran.dalytran_orig_ts[:10]
    if acct.acct_expiraion_date < orig_date:
        fail_reason = 103
        fail_desc = "TRANSACTION RECEIVED AFTER ACCT EXPIRATION"

    return (fail_reason, fail_desc, xref, acct)


# ---------------------------------------------------------------------------
# Pure posting logic (no I/O)
# ---------------------------------------------------------------------------

def post_transaction(
    dalytran: DalytranRecord,
    xref: CardXrefRecord,
    acct: AccountRecord,
    tcatbal_map: dict,
    timestamp: Optional[str] = None,
) -> tuple:
    """Post a valid transaction. Returns (tran_record, updated_acct, updated_tcatbal, created_new_tcatbal).

    Mutates acct and the tcatbal in tcatbal_map in place.
    """
    if timestamp is None:
        timestamp = make_db2_timestamp()

    # Build posted transaction record
    tran = TranRecord(
        tran_id=dalytran.dalytran_id,
        tran_type_cd=dalytran.dalytran_type_cd,
        tran_cat_cd=dalytran.dalytran_cat_cd,
        tran_source=dalytran.dalytran_source,
        tran_desc=dalytran.dalytran_desc,
        tran_amt=dalytran.dalytran_amt,
        tran_merchant_id=dalytran.dalytran_merchant_id,
        tran_merchant_name=dalytran.dalytran_merchant_name,
        tran_merchant_city=dalytran.dalytran_merchant_city,
        tran_merchant_zip=dalytran.dalytran_merchant_zip,
        tran_card_num=dalytran.dalytran_card_num,
        tran_orig_ts=dalytran.dalytran_orig_ts,
        tran_proc_ts=format_str(timestamp, 26),
    )

    # Update / create category balance (paragraph 2700)
    acct_id = xref.xref_acct_id
    tcatbal_key = (acct_id, dalytran.dalytran_type_cd, dalytran.dalytran_cat_cd)
    created_new = False

    if tcatbal_key in tcatbal_map:
        tcatbal = tcatbal_map[tcatbal_key]
        tcatbal.tran_cat_bal = _trunc2(tcatbal.tran_cat_bal + dalytran.dalytran_amt)
    else:
        tcatbal = TranCatBalRecord(
            trancat_acct_id=acct_id,
            trancat_type_cd=dalytran.dalytran_type_cd,
            trancat_cd=dalytran.dalytran_cat_cd,
            tran_cat_bal=_trunc2(dalytran.dalytran_amt),
        )
        tcatbal_map[tcatbal_key] = tcatbal
        created_new = True

    # Update account (paragraph 2800)
    acct.acct_curr_bal = _trunc2(acct.acct_curr_bal + dalytran.dalytran_amt)
    if dalytran.dalytran_amt >= Decimal("0"):
        acct.acct_curr_cyc_credit = _trunc2(
            acct.acct_curr_cyc_credit + dalytran.dalytran_amt)
    else:
        acct.acct_curr_cyc_debit = _trunc2(
            acct.acct_curr_cyc_debit + dalytran.dalytran_amt)

    return (tran, acct, tcatbal, created_new)


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def run_posttran(
    dailytran_path: str,
    xref_path: str,
    account_path: str,
    tcatbal_path: str,
    posted_output_path: Optional[str] = None,
    rejects_output_path: Optional[str] = None,
    spark: Optional[SparkSession] = None,
    timestamp_override: Optional[str] = None,
) -> PosttranResult:
    """Execute the POSTTRAN batch posting job.

    If ``spark`` is provided, input files are loaded as Spark DataFrames for
    parsing; otherwise plain Python file I/O is used. Business logic is
    always executed in pure Python for exact COBOL-identical semantics.
    """
    own_spark = False
    if spark is None:
        spark = (SparkSession.builder
                 .master("local[1]")
                 .appName("CBTRN02C_POSTTRAN")
                 .getOrCreate())
        own_spark = True

    try:
        return _run_posttran_impl(
            spark, dailytran_path, xref_path, account_path, tcatbal_path,
            posted_output_path, rejects_output_path, timestamp_override)
    finally:
        if own_spark:
            spark.stop()


def _run_posttran_impl(
    spark: SparkSession,
    dailytran_path: str,
    xref_path: str,
    account_path: str,
    tcatbal_path: str,
    posted_output_path: Optional[str],
    rejects_output_path: Optional[str],
    timestamp_override: Optional[str],
) -> PosttranResult:
    # Read files via Spark as text DataFrames, then collect for processing
    dalytran_df = spark.read.text(dailytran_path)
    xref_df = spark.read.text(xref_path)
    account_df = spark.read.text(account_path)
    tcatbal_df = spark.read.text(tcatbal_path)

    dalytran_lines = [row.value for row in dalytran_df.collect()]
    xref_lines = [row.value for row in xref_df.collect()]
    account_lines = [row.value for row in account_df.collect()]
    tcatbal_lines = [row.value for row in tcatbal_df.collect()]

    return run_posttran_pure(
        dalytran_lines, xref_lines, account_lines, tcatbal_lines,
        posted_output_path, rejects_output_path, timestamp_override)


def run_posttran_pure(
    dalytran_lines: list,
    xref_lines: list,
    account_lines: list,
    tcatbal_lines: list,
    posted_output_path: Optional[str] = None,
    rejects_output_path: Optional[str] = None,
    timestamp_override: Optional[str] = None,
) -> PosttranResult:
    """Pure-Python POSTTRAN logic (no Spark dependency for unit testing)."""
    # Build lookup maps
    xref_map = {}
    for line in xref_lines:
        if line.strip():
            rec = parse_card_xref(line)
            xref_map[rec.xref_card_num] = rec

    account_map = {}
    for line in account_lines:
        if line.strip():
            rec = parse_account(line)
            account_map[rec.acct_id] = rec

    tcatbal_map = {}
    for line in tcatbal_lines:
        if line.strip():
            rec = parse_tran_cat_bal(line)
            tcatbal_map[(rec.trancat_acct_id, rec.trancat_type_cd,
                         rec.trancat_cd)] = rec

    result = PosttranResult()

    for line in dalytran_lines:
        if not line.strip():
            continue
        dalytran = parse_dalytran(line)
        result.transaction_count += 1

        fail_reason, fail_desc, xref, acct = validate_transaction(
            dalytran, xref_map, account_map)

        if fail_reason == 0:
            ts = timestamp_override or make_db2_timestamp()
            tran, acct, tcatbal, created = post_transaction(
                dalytran, xref, acct, tcatbal_map, ts)
            result.posted_records.append(tran)
        else:
            result.reject_count += 1
            trailer = _format_validation_trailer(fail_reason, fail_desc)
            reject_line = serialize_dalytran(dalytran) + trailer
            result.reject_records.append(reject_line)

    if result.reject_count > 0:
        result.return_code = 4

    result.updated_accounts = account_map
    result.updated_tcatbals = tcatbal_map

    # Write outputs if paths provided
    if posted_output_path:
        with open(posted_output_path, "w") as f:
            for rec in result.posted_records:
                f.write(serialize_tran(rec) + "\n")

    if rejects_output_path:
        with open(rejects_output_path, "w") as f:
            for line in result.reject_records:
                f.write(line + "\n")

    return result
