# CardDemo COBOL-to-Python Migration

Python re-implementations of three CardDemo batch COBOL programs.

| COBOL Program | Python Module | Description |
|---|---|---|
| `CBTRN02C.cbl` | `src/cbtrn02c_pyspark.py` | POSTTRAN daily transaction posting (PySpark) |
| `CBACT04C.cbl` | `src/cbact04c.py` | INTCALC monthly interest calculator |
| `CBSTM03A.CBL` | `src/cbstm03a.py` | CREASTMT account statement generator |

Shared fixed-width record parsing lives in `src/copybook_records.py`.

## Prerequisites

- Python 3.10+
- Java 11+ (required by PySpark)

## Setup

```bash
cd migration
pip install -r requirements.txt
```

## Running Tests

```bash
cd migration
python -m pytest tests/ -v
```

## Module Usage

### POSTTRAN (PySpark)

```python
from src.cbtrn02c_pyspark import run_posttran

result = run_posttran(
    dailytran_path="path/to/dailytran.txt",
    xref_path="path/to/cardxref.txt",
    account_path="path/to/acctdata.txt",
    tcatbal_path="path/to/tcatbal.txt",
    posted_output_path="path/to/posted/",
    rejects_output_path="path/to/rejects/",
)
```

### INTCALC

```python
from src.cbact04c import run_intcalc

result = run_intcalc(
    tcatbal_path="path/to/tcatbal.txt",
    discgrp_path="path/to/discgrp.txt",
    account_path="path/to/acctdata.txt",
    xref_path="path/to/cardxref.txt",
    transact_output_path="path/to/transact.txt",
    account_output_path="path/to/acctdata_out.txt",
    parm_date="2022071800",
)
```

### CREASTMT

```python
from src.cbstm03a import run_creastmt

run_creastmt(
    trnx_path="path/to/transact.txt",
    xref_path="path/to/cardxref.txt",
    cust_path="path/to/custdata.txt",
    acct_path="path/to/acctdata.txt",
    stmt_output_path="path/to/statement.txt",
    html_output_path="path/to/statement.html",
)
```
