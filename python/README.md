# CardDemo Python Migrations

Python implementations of CardDemo COBOL batch programs, using `pandas` for
VSAM lookups and `decimal.Decimal` for packed-decimal arithmetic fidelity.

## Modules

| Module | COBOL Source | Function |
|---|---|---|
| `transaction_validation.py` | `COTRN02C.cbl`, `CBTRN02C.cbl` | Online & batch transaction validation |
| `cbact04c_interest.py` | `CBACT04C.cbl` | INTCALC interest calculation batch job |

## Prerequisites

```bash
pip install -r requirements.txt
```

## Running the interest calculation job

```python
from decimal import Decimal
import pandas as pd
from cbact04c_interest import run_interest_calculation

# Load DataFrames from your data source (CSV, database, etc.)
tcatbal_df = pd.read_csv("tcatbal.csv")       # TCATBALF
xref_df    = pd.read_csv("xref.csv")          # XREFFILE
discgrp_df = pd.read_csv("discgrp.csv")       # DISCGRP
account_df = pd.read_csv("accounts.csv")       # ACCTFILE

# PARM-DATE: the run date passed via EXTERNAL-PARMS in the original JCL
parm_date = "2026-06-15"

transactions, updated_accounts = run_interest_calculation(
    tcatbal_df, xref_df, discgrp_df, account_df, parm_date
)
```

The `parm_date` parameter corresponds to the COBOL `PARM-DATE` field
(`PIC X(10)`) passed via `PROCEDURE DIVISION USING EXTERNAL-PARMS`.
It is used as a prefix for the generated transaction IDs.

## Running the tests

```bash
cd python/
pytest -v
```
