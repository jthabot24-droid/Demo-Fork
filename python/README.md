# CardDemo Python Migrations

PySpark and Python implementations of CardDemo COBOL batch programs.

## Modules

| Module | COBOL Source | Description |
|--------|-------------|-------------|
| `transaction_validation.py` | `COTRN02C.cbl` / `CBTRN02C.cbl` | Validation logic (online + batch) |
| `cbtrn02c_posting.py` | `CBTRN02C.cbl` | POSTTRAN batch posting job (PySpark) |

## Setup

```bash
pip install -r requirements.txt
```

Java 8, 11, or 17 is required for PySpark.

## Running tests

```bash
cd python/
pytest -v
```

## Running the POSTTRAN job

The posting job reads six data files (Parquet, CSV, or JSON) and writes updated
outputs:

```bash
spark-submit cbtrn02c_posting.py \
    --dalytran data/dalytran \
    --tranfile data/tranfile \
    --xreffile data/xreffile \
    --dalyrejs data/dalyrejs \
    --acctfile data/acctfile \
    --tcatbalf data/tcatbalf \
    --format parquet
```

Exit code is **0** if all transactions posted successfully, or **4** if any were
rejected (matching the COBOL `RETURN-CODE` behaviour).

### Input files

| Flag | COBOL DD | Layout | Description |
|------|----------|--------|-------------|
| `--dalytran` | `DALYTRAN` | CVTRA06Y | Daily transactions (sequential input) |
| `--xreffile` | `XREFFILE` | CVACT03Y | Card-to-account cross-reference |
| `--acctfile` | `ACCTFILE` | CVACT01Y | Account master (read + updated) |
| `--tcatbalf` | `TCATBALF` | CVTRA01Y | Transaction category balance (read + updated) |

### Output files

| Flag | COBOL DD | Layout | Description |
|------|----------|--------|-------------|
| `--tranfile` | `TRANFILE` | CVTRA05Y | Posted transactions |
| `--dalyrejs` | `DALYREJS` | - | Rejected transactions with reason codes |
| `--acctfile` | `ACCTFILE` | CVACT01Y | Updated account master (overwritten) |
| `--tcatbalf` | `TCATBALF` | CVTRA01Y | Updated category balances (overwritten) |
