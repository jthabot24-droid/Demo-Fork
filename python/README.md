# CardDemo — COBOL-to-Python Migration

Python port of the AWS CardDemo mainframe credit-card management application.

## Migration Approach

The migration follows a phased strategy that keeps the original COBOL
source intact for parallel-run validation:

| Phase | Scope | Status |
|-------|-------|--------|
| **0** | Discovery, project scaffold, test harness | Done |
| **1** | Data model, fixed-width I/O, ETL loaders | Done |
| **2** | Batch programs (POSTTRAN, INTCALC, statement generation), CLI runner | Done |
| **3** | Online programs (CICS/BMS → web API) | Future |
| **4** | Optional extensions (DB2/IMS/MQ modules) | Future |
| **5** | Parallel-run cutover & decommission | Future |

## Persistence

* **Local / dev:** SQLite (default `carddemo.db`)
* **Production:** PostgreSQL — install the `pg` extra: `pip install -e ".[pg]"`

VSAM KSDS primary keys map to SQL primary keys.  Alternate indexes
(e.g. `CARDDATA` AIX on `CARD-ACCT-ID`, `CARDXREF` AIX on `XREF-ACCT-ID`)
map to secondary database indexes.

## Project Structure

```
python/
├── pyproject.toml              # PEP 621 project metadata
├── README.md                   # This file
├── carddemo/
│   ├── __init__.py
│   ├── models.py               # Dataclasses + SQLAlchemy ORM
│   ├── fixed_width.py          # Fixed-width parser/writer (PIC clause fidelity)
│   ├── etl.py                  # ETL loaders (.PS flat files → DB)
│   ├── validation.py           # Golden-master diffing harness
│   ├── runner.py               # CLI batch sequencer (replaces JCL orchestration)
│   └── batch/
│       ├── __init__.py
│       ├── posttran.py         # CBTRN02C — transaction posting
│       ├── intcalc.py          # CBACT04C — interest calculation
│       └── statement.py        # CBSTM03A/B — statement generation
├── tests/
│   ├── conftest.py             # Fixtures using app/data/ASCII golden masters
│   ├── test_fixed_width.py
│   ├── test_models.py
│   ├── test_etl.py
│   ├── test_posttran.py
│   ├── test_intcalc.py
│   ├── test_statement.py
│   ├── test_runner.py
│   └── test_validation.py
├── transaction_validation.py   # Earlier PR — kept for reference
└── test_transaction_validation.py
```

## Record Layouts (from COBOL copybooks)

| File | Copybook | RECLN | KSDS Key | Notes |
|------|----------|------:|----------|-------|
| `ACCTDATA` | `CVACT01Y` | 300 | `ACCT-ID` 9(11) | Account master |
| `CARDDATA` | `CVACT02Y` | 150 | `CARD-NUM` X(16) | AIX on `CARD-ACCT-ID` |
| `CARDXREF` | `CVACT03Y` | 50 | `XREF-CARD-NUM` X(16) | AIX on `XREF-ACCT-ID` |
| `CUSTDATA` | `CVCUS01Y` | 500 | `CUST-ID` 9(09) | Customer data |
| `TRANSACT` | `CVTRA05Y` | 350 | `TRAN-ID` X(16) | Posted transactions |
| `DALYTRAN` | `CVTRA06Y` | 350 | Sequential | Daily transaction input |
| `TCATBALF` | `CVTRA01Y` | 50 | Composite 17 | Category balances |
| `DISCGRP` | `CVTRA02Y` | 50 | Composite 16 | Disclosure/interest rates |
| `TRANTYPE` | `CVTRA03Y` | 60 | `TRAN-TYPE` X(02) | Transaction type lookup |
| `TRANCATG` | `CVTRA04Y` | 60 | Composite 6 | Transaction category lookup |
| `USRSEC` | `CSUSR01Y` | 80 | RRDS | User security |

All monetary fields use `Decimal` to preserve COBOL `PIC S9(m)V9(n)` precision.
Signed zoned-decimal (overpunch) encoding is handled by `fixed_width.py`.

## Quick Start

```bash
cd python/

# Install in dev mode
pip install -e ".[dev]"

# Run the full batch pipeline
python -m carddemo.runner \
    --data-dir ../app/data/ASCII \
    --db sqlite:///carddemo.db \
    --steps load,posttran,intcalc,statement \
    --parm-date 2024-06-15

# Run tests
pytest
```

## Batch Programs Ported

### CBTRN02C — POSTTRAN (Transaction Posting)

Reads the daily-transaction file and posts valid transactions:

* **Validation:** card-number lookup (XREF), account existence,
  overlimit check (`credit_limit >= cyc_credit - cyc_debit + amt`),
  account-expiration check
* **Posting:** copies daily-tran fields → transaction record, generates
  DB2-format timestamp, updates TCATBAL and account balances
* **Rejects:** invalid transactions logged with fail code and reason

### CBACT04C — INTCALC (Interest Calculation)

Iterates TCATBAL records, computes `monthly_int = (balance × rate) / 1200`,
writes interest-charge transactions, and updates account balances.
`1400-COMPUTE-FEES` is preserved as a no-op stub.

### CBSTM03A/CBSTM03B — Statement Generation

Generates plain-text and HTML account statements.  The COBOL
`CALL 'CBSTM03B'` I/O subprogram pattern is collapsed into a single
Python module that queries the database directly.

## Golden-Master Data

The test fixtures use the existing `.txt` files under `app/data/ASCII/`:

| File | Records | Description |
|------|--------:|-------------|
| `acctdata.txt` | 50 | Account master |
| `carddata.txt` | 50 | Card records |
| `cardxref.txt` | 50 | Card cross-reference |
| `custdata.txt` | 50 | Customer data |
| `dailytran.txt` | 300 | Daily transactions |
| `discgrp.txt` | 51 | Disclosure groups |
| `tcatbal.txt` | 50 | Transaction category balances |
| `trantype.txt` | 7 | Transaction types |
| `trancatg.txt` | 18 | Transaction categories |
