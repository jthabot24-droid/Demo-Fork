"""
PySpark migration of CBTRN02C.cbl -- POSTTRAN batch transaction posting.

Migrates the CardDemo batch posting job from COBOL to PySpark, preserving
all validation rules, posting logic, counting, and return-code behaviour.

COBOL source: app/cbl/CBTRN02C.cbl
Copybooks: CVTRA06Y, CVTRA05Y, CVACT03Y, CVACT01Y, CVTRA01Y

The six COBOL files are modeled as PySpark DataFrames:

  DALYTRAN  - input daily transactions (sequential)       [CVTRA06Y]
  TRANFILE  - output posted transactions (keyed)          [CVTRA05Y]
  XREFFILE  - card-to-account cross-reference (input)     [CVACT03Y]
  DALYREJS  - output rejected transactions
  ACCTFILE  - account master (input/output, updated)      [CVACT01Y]
  TCATBALF  - transaction category balance (input/output) [CVTRA01Y]

Processing is sequential (each posted transaction updates account state
visible to subsequent validations), matching the COBOL mainline loop.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Callable, Dict, List, Optional, Tuple

import pandas as pd
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import types as T

from transaction_validation import (
    DailyTransactionRecord,
    ValidationResult,
    validate_batch_transaction,
)

# ---------------------------------------------------------------------------
# COBOL abend -> Python exception  (9999-ABEND-PROGRAM / CEE3ABD)
# ---------------------------------------------------------------------------


class AbendError(Exception):
    """Maps COBOL CEE3ABD (Language Environment abend) to a Python exception."""

    def __init__(self, message: str, abend_code: int = 999):
        self.abend_code = abend_code
        super().__init__(f"ABEND {abend_code}: {message}")


# ---------------------------------------------------------------------------
# Batch result  (mirrors WS-COUNTERS + RETURN-CODE)
# ---------------------------------------------------------------------------


@dataclass
class BatchResult:
    """Outcome of the POSTTRAN batch run."""

    transaction_count: int = 0
    reject_count: int = 0
    return_code: int = 0


# ---------------------------------------------------------------------------
# Spark schemas matching COBOL copybook record layouts
# ---------------------------------------------------------------------------

# CVTRA06Y -- DALYTRAN-RECORD (350 bytes)
DALYTRAN_SCHEMA = T.StructType(
    [
        T.StructField("dalytran_id", T.StringType()),  # PIC X(16)
        T.StructField("dalytran_type_cd", T.StringType()),  # PIC X(02)
        T.StructField("dalytran_cat_cd", T.IntegerType()),  # PIC 9(04)
        T.StructField("dalytran_source", T.StringType()),  # PIC X(10)
        T.StructField("dalytran_desc", T.StringType()),  # PIC X(100)
        T.StructField("dalytran_amt", T.DecimalType(11, 2)),  # PIC S9(09)V99
        T.StructField("dalytran_merchant_id", T.IntegerType()),  # PIC 9(09)
        T.StructField("dalytran_merchant_name", T.StringType()),  # PIC X(50)
        T.StructField("dalytran_merchant_city", T.StringType()),  # PIC X(50)
        T.StructField("dalytran_merchant_zip", T.StringType()),  # PIC X(10)
        T.StructField("dalytran_card_num", T.StringType()),  # PIC X(16)
        T.StructField("dalytran_orig_ts", T.StringType()),  # PIC X(26)
        T.StructField("dalytran_proc_ts", T.StringType()),  # PIC X(26)
    ]
)

# CVTRA05Y -- TRAN-RECORD (350 bytes)
TRANFILE_SCHEMA = T.StructType(
    [
        T.StructField("tran_id", T.StringType()),  # PIC X(16)
        T.StructField("tran_type_cd", T.StringType()),  # PIC X(02)
        T.StructField("tran_cat_cd", T.IntegerType()),  # PIC 9(04)
        T.StructField("tran_source", T.StringType()),  # PIC X(10)
        T.StructField("tran_desc", T.StringType()),  # PIC X(100)
        T.StructField("tran_amt", T.DecimalType(11, 2)),  # PIC S9(09)V99
        T.StructField("tran_merchant_id", T.IntegerType()),  # PIC 9(09)
        T.StructField("tran_merchant_name", T.StringType()),  # PIC X(50)
        T.StructField("tran_merchant_city", T.StringType()),  # PIC X(50)
        T.StructField("tran_merchant_zip", T.StringType()),  # PIC X(10)
        T.StructField("tran_card_num", T.StringType()),  # PIC X(16)
        T.StructField("tran_orig_ts", T.StringType()),  # PIC X(26)
        T.StructField("tran_proc_ts", T.StringType()),  # PIC X(26)
    ]
)

# CVACT03Y -- CARD-XREF-RECORD (50 bytes)
XREFFILE_SCHEMA = T.StructType(
    [
        T.StructField("xref_card_num", T.StringType()),  # PIC X(16)
        T.StructField("xref_cust_id", T.LongType()),  # PIC 9(09)
        T.StructField("xref_acct_id", T.LongType()),  # PIC 9(11)
    ]
)

# CVACT01Y -- ACCOUNT-RECORD (300 bytes)
ACCTFILE_SCHEMA = T.StructType(
    [
        T.StructField("acct_id", T.LongType()),  # PIC 9(11)
        T.StructField("acct_active_status", T.StringType()),  # PIC X(01)
        T.StructField("acct_curr_bal", T.DecimalType(12, 2)),  # PIC S9(10)V99
        T.StructField("acct_credit_limit", T.DecimalType(12, 2)),  # PIC S9(10)V99
        T.StructField("acct_cash_credit_limit", T.DecimalType(12, 2)),  # PIC S9(10)V99
        T.StructField("acct_open_date", T.StringType()),  # PIC X(10)
        T.StructField("acct_expiration_date", T.StringType()),  # PIC X(10)
        T.StructField("acct_reissue_date", T.StringType()),  # PIC X(10)
        T.StructField("acct_curr_cyc_credit", T.DecimalType(12, 2)),  # PIC S9(10)V99
        T.StructField("acct_curr_cyc_debit", T.DecimalType(12, 2)),  # PIC S9(10)V99
        T.StructField("acct_addr_zip", T.StringType()),  # PIC X(10)
        T.StructField("acct_group_id", T.StringType()),  # PIC X(10)
    ]
)

# CVTRA01Y -- TRAN-CAT-BAL-RECORD (50 bytes)
TCATBALF_SCHEMA = T.StructType(
    [
        T.StructField("trancat_acct_id", T.LongType()),  # PIC 9(11)
        T.StructField("trancat_type_cd", T.StringType()),  # PIC X(02)
        T.StructField("trancat_cd", T.IntegerType()),  # PIC 9(04)
        T.StructField("tran_cat_bal", T.DecimalType(11, 2)),  # PIC S9(09)V99
    ]
)

# Reject output -- daily tran data + validation trailer
DALYREJS_SCHEMA = T.StructType(
    [
        T.StructField("dalytran_id", T.StringType()),
        T.StructField("dalytran_type_cd", T.StringType()),
        T.StructField("dalytran_cat_cd", T.IntegerType()),
        T.StructField("dalytran_source", T.StringType()),
        T.StructField("dalytran_desc", T.StringType()),
        T.StructField("dalytran_amt", T.DecimalType(11, 2)),
        T.StructField("dalytran_merchant_id", T.IntegerType()),
        T.StructField("dalytran_merchant_name", T.StringType()),
        T.StructField("dalytran_merchant_city", T.StringType()),
        T.StructField("dalytran_merchant_zip", T.StringType()),
        T.StructField("dalytran_card_num", T.StringType()),
        T.StructField("dalytran_orig_ts", T.StringType()),
        T.StructField("dalytran_proc_ts", T.StringType()),
        # WS-VALIDATION-TRAILER
        T.StructField("reject_reason_code", T.IntegerType()),  # PIC 9(04)
        T.StructField("reject_reason_desc", T.StringType()),  # PIC X(76)
    ]
)

# Monetary columns in the account DataFrame that must use Decimal
_ACCT_MONETARY_COLS = [
    "acct_curr_bal",
    "acct_credit_limit",
    "acct_cash_credit_limit",
    "acct_curr_cyc_credit",
    "acct_curr_cyc_debit",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_decimal(val: object) -> Decimal:
    """Safely convert a value to Decimal, defaulting to 0.00."""
    if val is None:
        return Decimal("0.00")
    if isinstance(val, Decimal):
        return val
    return Decimal(str(val))


def _ensure_decimal_columns(df: pd.DataFrame, cols: List[str]) -> pd.DataFrame:
    """Convert specified columns to Decimal for exact arithmetic."""
    for col in cols:
        if col in df.columns:
            df[col] = df[col].apply(_to_decimal)
    return df


def _get_db2_format_timestamp() -> str:
    """Z-GET-DB2-FORMAT-TIMESTAMP: produce a DB2-style timestamp string.

    Format: ``YYYY-MM-DD-HH.MM.SS.cc0000``  (26 characters)

    Maps the COBOL FUNCTION CURRENT-DATE fields into the DB2 timestamp
    layout defined in WORKING-STORAGE.
    """
    now = datetime.now()
    centiseconds = now.microsecond // 10000
    return (
        f"{now.year:04d}-{now.month:02d}-{now.day:02d}-"
        f"{now.hour:02d}.{now.minute:02d}.{now.second:02d}."
        f"{centiseconds:02d}0000"
    )


def _row_to_daily_tran(row: pd.Series) -> DailyTransactionRecord:
    """Convert a pandas row to a DailyTransactionRecord dataclass."""
    return DailyTransactionRecord(
        dalytran_id=str(row["dalytran_id"]),
        dalytran_type_cd=str(row["dalytran_type_cd"]),
        dalytran_cat_cd=int(row["dalytran_cat_cd"]),
        dalytran_source=str(row["dalytran_source"]),
        dalytran_desc=str(row["dalytran_desc"]),
        dalytran_amt=_to_decimal(row["dalytran_amt"]),
        dalytran_merchant_id=int(row["dalytran_merchant_id"]),
        dalytran_merchant_name=str(row["dalytran_merchant_name"]),
        dalytran_merchant_city=str(row["dalytran_merchant_city"]),
        dalytran_merchant_zip=str(row["dalytran_merchant_zip"]),
        dalytran_card_num=str(row["dalytran_card_num"]),
        dalytran_orig_ts=str(row["dalytran_orig_ts"]),
        dalytran_proc_ts=str(row["dalytran_proc_ts"]),
    )


def _create_df(
    spark: SparkSession, records: List[dict], schema: T.StructType
) -> DataFrame:
    """Create a Spark DataFrame from a list of dicts, handling empty lists."""
    if not records:
        return spark.createDataFrame([], schema=schema)
    field_names = [f.name for f in schema.fields]
    tuples = [tuple(r[name] for name in field_names) for r in records]
    return spark.createDataFrame(tuples, schema=schema)


# ---------------------------------------------------------------------------
# Posting helpers  (2000-POST-TRANSACTION sub-paragraphs)
# ---------------------------------------------------------------------------


def _update_tcatbal(
    tran: DailyTransactionRecord,
    acct_id: int,
    tcatbal_dict: Dict[Tuple[int, str, int], Decimal],
) -> None:
    """2700-UPDATE-TCATBAL: update or create a transaction category balance.

    If the key (acct_id, type_cd, cat_cd) is not found, a new record is
    created (2700-A) with balance = dalytran_amt.  Otherwise the existing
    balance is incremented (2700-B).
    """
    key = (acct_id, tran.dalytran_type_cd, tran.dalytran_cat_cd)

    if key in tcatbal_dict:
        # 2700-B-UPDATE-TCATBAL-REC: ADD DALYTRAN-AMT TO TRAN-CAT-BAL
        tcatbal_dict[key] = tcatbal_dict[key] + tran.dalytran_amt
    else:
        # 2700-A-CREATE-TCATBAL-REC: INITIALIZE + ADD
        tcatbal_dict[key] = Decimal("0.00") + tran.dalytran_amt


def _update_account(
    tran: DailyTransactionRecord,
    acct_id: int,
    acct_pd: pd.DataFrame,
) -> None:
    """2800-UPDATE-ACCOUNT-REC: update account balances after posting.

    ::

        ADD DALYTRAN-AMT TO ACCT-CURR-BAL
        IF DALYTRAN-AMT >= 0
           ADD DALYTRAN-AMT TO ACCT-CURR-CYC-CREDIT
        ELSE
           ADD DALYTRAN-AMT TO ACCT-CURR-CYC-DEBIT
    """
    mask = acct_pd["acct_id"] == acct_id
    idx = acct_pd.index[mask]

    if len(idx) == 0:
        raise AbendError(f"Account record {acct_id} not found during REWRITE")

    i = idx[0]
    acct_pd.at[i, "acct_curr_bal"] = (
        acct_pd.at[i, "acct_curr_bal"] + tran.dalytran_amt
    )

    if tran.dalytran_amt >= 0:
        acct_pd.at[i, "acct_curr_cyc_credit"] = (
            acct_pd.at[i, "acct_curr_cyc_credit"] + tran.dalytran_amt
        )
    else:
        acct_pd.at[i, "acct_curr_cyc_debit"] = (
            acct_pd.at[i, "acct_curr_cyc_debit"] + tran.dalytran_amt
        )


def _post_transaction(
    tran: DailyTransactionRecord,
    val_result: ValidationResult,
    acct_pd: pd.DataFrame,
    tcatbal_dict: Dict[Tuple[int, str, int], Decimal],
    timestamp_fn: Callable[[], str],
) -> dict:
    """2000-POST-TRANSACTION: build posted record, update account and tcatbal.

    Execution order matches COBOL:
      1. Map daily-tran fields to transaction-record fields
      2. 2700-UPDATE-TCATBAL
      3. 2800-UPDATE-ACCOUNT-REC
      4. (the caller collects the posted record for 2900-WRITE)
    """
    acct_id = val_result.resolved_acct_id
    proc_ts = timestamp_fn()

    # Field mapping: DALYTRAN -> TRAN-RECORD
    posted = {
        "tran_id": tran.dalytran_id,
        "tran_type_cd": tran.dalytran_type_cd,
        "tran_cat_cd": tran.dalytran_cat_cd,
        "tran_source": tran.dalytran_source,
        "tran_desc": tran.dalytran_desc,
        "tran_amt": tran.dalytran_amt,
        "tran_merchant_id": tran.dalytran_merchant_id,
        "tran_merchant_name": tran.dalytran_merchant_name,
        "tran_merchant_city": tran.dalytran_merchant_city,
        "tran_merchant_zip": tran.dalytran_merchant_zip,
        "tran_card_num": tran.dalytran_card_num,
        "tran_orig_ts": tran.dalytran_orig_ts,
        "tran_proc_ts": proc_ts,
    }

    _update_tcatbal(tran, acct_id, tcatbal_dict)
    _update_account(tran, acct_id, acct_pd)

    return posted


def _build_reject_record(
    tran: DailyTransactionRecord, val_result: ValidationResult
) -> dict:
    """2500-WRITE-REJECT-REC: build reject record from transaction + validation trailer."""
    error = val_result.errors[0]
    return {
        "dalytran_id": tran.dalytran_id,
        "dalytran_type_cd": tran.dalytran_type_cd,
        "dalytran_cat_cd": tran.dalytran_cat_cd,
        "dalytran_source": tran.dalytran_source,
        "dalytran_desc": tran.dalytran_desc,
        "dalytran_amt": tran.dalytran_amt,
        "dalytran_merchant_id": tran.dalytran_merchant_id,
        "dalytran_merchant_name": tran.dalytran_merchant_name,
        "dalytran_merchant_city": tran.dalytran_merchant_city,
        "dalytran_merchant_zip": tran.dalytran_merchant_zip,
        "dalytran_card_num": tran.dalytran_card_num,
        "dalytran_orig_ts": tran.dalytran_orig_ts,
        "dalytran_proc_ts": tran.dalytran_proc_ts,
        "reject_reason_code": error.code,
        "reject_reason_desc": error.message,
    }


# ---------------------------------------------------------------------------
# Core batch driver
# ---------------------------------------------------------------------------


def run_posttran(
    spark: SparkSession,
    dalytran_df: DataFrame,
    xref_df: DataFrame,
    acct_df: DataFrame,
    tcatbal_df: Optional[DataFrame],
    timestamp_fn: Optional[Callable[[], str]] = None,
) -> Tuple[BatchResult, DataFrame, DataFrame, DataFrame, DataFrame]:
    """Execute the POSTTRAN batch job (CBTRN02C main loop).

    Parameters
    ----------
    spark : SparkSession
    dalytran_df : DataFrame -- daily transactions input  (DALYTRAN / CVTRA06Y)
    xref_df : DataFrame     -- card cross-reference      (XREFFILE / CVACT03Y)
    acct_df : DataFrame     -- account master             (ACCTFILE / CVACT01Y)
    tcatbal_df : DataFrame  -- transaction category bal   (TCATBALF / CVTRA01Y)
    timestamp_fn : callable -- override _get_db2_format_timestamp (for testing)

    Returns
    -------
    (BatchResult, posted_df, rejects_df, updated_acct_df, updated_tcatbal_df)
    """
    if timestamp_fn is None:
        timestamp_fn = _get_db2_format_timestamp

    # -- Convert reference / mutable data to pandas for sequential processing --
    xref_pd = xref_df.toPandas()
    acct_pd = acct_df.toPandas()
    _ensure_decimal_columns(acct_pd, _ACCT_MONETARY_COLS)

    # Build tcatbal mutable state: dict keyed by (acct_id, type_cd, cat_cd)
    tcatbal_dict: Dict[Tuple[int, str, int], Decimal] = {}
    if tcatbal_df is not None and tcatbal_df.count() > 0:
        tcatbal_pd = tcatbal_df.toPandas()
        for _, row in tcatbal_pd.iterrows():
            key = (
                int(row["trancat_acct_id"]),
                str(row["trancat_type_cd"]),
                int(row["trancat_cd"]),
            )
            tcatbal_dict[key] = _to_decimal(row["tran_cat_bal"])

    # Collect daily transactions preserving sequential input order
    dalytran_pd = dalytran_df.toPandas()

    posted_records: List[dict] = []
    reject_records: List[dict] = []
    result = BatchResult()

    print("START OF EXECUTION OF PROGRAM CBTRN02C")

    # -- Main loop (PERFORM UNTIL END-OF-FILE = 'Y') --
    for _, row in dalytran_pd.iterrows():
        tran = _row_to_daily_tran(row)
        result.transaction_count += 1

        # 1500-VALIDATE-TRAN (reuses existing validation module)
        val_result = validate_batch_transaction(tran, xref_pd, acct_pd)

        if val_result.is_valid:
            # 2000-POST-TRANSACTION
            posted = _post_transaction(
                tran, val_result, acct_pd, tcatbal_dict, timestamp_fn
            )
            posted_records.append(posted)
        else:
            # Increment WS-REJECT-COUNT; 2500-WRITE-REJECT-REC
            result.reject_count += 1
            reject = _build_reject_record(tran, val_result)
            reject_records.append(reject)

    # -- After loop: display counts and set return code --
    print(f"TRANSACTIONS PROCESSED :{result.transaction_count:09d}")
    print(f"TRANSACTIONS REJECTED  :{result.reject_count:09d}")

    if result.reject_count > 0:
        result.return_code = 4

    print("END OF EXECUTION OF PROGRAM CBTRN02C")

    # -- Convert results back to Spark DataFrames --
    posted_df = _create_df(spark, posted_records, TRANFILE_SCHEMA)
    rejects_df = _create_df(spark, reject_records, DALYREJS_SCHEMA)

    # Updated account master
    acct_records = acct_pd.to_dict(orient="records")
    updated_acct_df = _create_df(spark, acct_records, ACCTFILE_SCHEMA)

    # Updated transaction category balances
    tcatbal_records = [
        {
            "trancat_acct_id": acct_id,
            "trancat_type_cd": type_cd,
            "trancat_cd": cat_cd,
            "tran_cat_bal": bal,
        }
        for (acct_id, type_cd, cat_cd), bal in tcatbal_dict.items()
    ]
    updated_tcatbal_df = _create_df(spark, tcatbal_records, TCATBALF_SCHEMA)

    return result, posted_df, rejects_df, updated_acct_df, updated_tcatbal_df


# ---------------------------------------------------------------------------
# CLI entry point  (spark-submit)
# ---------------------------------------------------------------------------


def main() -> None:
    """Run POSTTRAN as a standalone Spark job.

    Usage::

        spark-submit cbtrn02c_posting.py \\
            --dalytran <path> --tranfile <path> --xreffile <path> \\
            --dalyrejs <path> --acctfile <path> --tcatbalf <path> \\
            [--format parquet|csv|json]
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="POSTTRAN -- Post Daily Transactions (CBTRN02C migration)"
    )
    parser.add_argument(
        "--dalytran", required=True, help="Input daily transactions path"
    )
    parser.add_argument(
        "--tranfile", required=True, help="Output posted transactions path"
    )
    parser.add_argument(
        "--xreffile", required=True, help="Card cross-reference input path"
    )
    parser.add_argument(
        "--dalyrejs", required=True, help="Output rejects path"
    )
    parser.add_argument(
        "--acctfile", required=True, help="Account master path (read & overwritten)"
    )
    parser.add_argument(
        "--tcatbalf", required=True, help="Transaction category balance path (read & overwritten)"
    )
    parser.add_argument(
        "--format",
        default="parquet",
        choices=["parquet", "csv", "json"],
        help="Data file format (default: parquet)",
    )
    args = parser.parse_args()

    spark = SparkSession.builder.appName("POSTTRAN-CBTRN02C").getOrCreate()

    try:
        read_fn = {
            "parquet": lambda path, schema: spark.read.schema(schema).parquet(path),
            "csv": lambda path, schema: (
                spark.read.schema(schema).option("header", "true").csv(path)
            ),
            "json": lambda path, schema: spark.read.schema(schema).json(path),
        }[args.format]

        dalytran_df = read_fn(args.dalytran, DALYTRAN_SCHEMA)
        xref_df = read_fn(args.xreffile, XREFFILE_SCHEMA)
        acct_df = read_fn(args.acctfile, ACCTFILE_SCHEMA)
        tcatbal_df = read_fn(args.tcatbalf, TCATBALF_SCHEMA)

        result, posted_df, rejects_df, updated_acct_df, updated_tcatbal_df = (
            run_posttran(spark, dalytran_df, xref_df, acct_df, tcatbal_df)
        )

        write_fn = {
            "parquet": lambda df, path: df.write.mode("overwrite").parquet(path),
            "csv": lambda df, path: (
                df.write.mode("overwrite").option("header", "true").csv(path)
            ),
            "json": lambda df, path: df.write.mode("overwrite").json(path),
        }[args.format]

        write_fn(posted_df, args.tranfile)
        write_fn(rejects_df, args.dalyrejs)
        write_fn(updated_acct_df, args.acctfile)
        write_fn(updated_tcatbal_df, args.tcatbalf)

    finally:
        spark.stop()

    sys.exit(result.return_code)


if __name__ == "__main__":
    main()
