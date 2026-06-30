# CardDemo Python Migration

Python port of the CardDemo mainframe credit card management application.
This directory contains the first execution increment: the financial-core
data model, data-access layer, and highest-precision-risk batch logic.

## What Has Been Migrated

### Data Model (`carddemo/models/`)

Every COBOL copybook under `app/cpy/` that defines a record layout has been
translated into a Python `dataclass`, preserving fixed-width field widths,
signed/unsigned semantics, and `COMP`/`COMP-3`/zoned-decimal distinctions.
All monetary fields use `decimal.Decimal`.

| Copybook   | Python Module            | Record                         | RECLN |
|:-----------|:-------------------------|:-------------------------------|------:|
| CVACT01Y   | `models/account.py`      | `AccountRecord`                |   300 |
| CVACT02Y   | `models/card.py`         | `CardRecord`                   |   150 |
| CVACT03Y   | `models/card_xref.py`    | `CardXrefRecord`               |    50 |
| CVCUS01Y   | `models/customer.py`     | `CustomerRecord`               |   500 |
| CVTRA05Y   | `models/transaction.py`  | `TransactionRecord`            |   350 |
| CVTRA06Y   | `models/transaction.py`  | `DailyTransactionRecord`       |   350 |
| CVTRA01Y   | `models/transaction_category.py` | `TranCatBalRecord`      |    50 |
| CVTRA02Y   | `models/disclosure_group.py` | `DisclosureGroupRecord`    |    50 |
| CVTRA03Y   | `models/transaction_category.py` | `TranTypeRecord`        |    60 |
| CVTRA04Y   | `models/transaction_category.py` | `TranCatRecord`         |    60 |
| CSUSR01Y   | `models/user_security.py`| `SecUserData`                  |    80 |
| CVEXPORT   | `models/export.py`       | `ExportRecord` + 5 payloads    |   500 |

The `CVEXPORT` copybook demonstrates `REDEFINES` (five record-type overlays
on the same 460-byte area) and `OCCURS` (address lines x3, phone numbers x2),
plus mixed `COMP`/`COMP-3` storage -- all modeled explicitly.

### Data-Access Layer (`carddemo/dataaccess/`)

Abstract repository interfaces in `repository.py` replace
`ORGANIZATION IS INDEXED / RECORD KEY / ALTERNATE RECORD KEY` patterns.
Concrete in-memory (pandas-backed) implementations in `in_memory.py`
preserve the same fixed-width keys (e.g. 16-byte zero-padded card numbers).

| COBOL File  | Repository Interface        | Key Fields                      |
|:------------|:----------------------------|:--------------------------------|
| ACCTFILE    | `AccountRepository`         | `acct_id` (PK)                  |
| CARDFILE    | `CardRepository`            | `card_num` (PK)                 |
| XREFFILE    | `CardXrefRepository`        | `xref_card_num` (PK), `xref_acct_id` (AIX) |
| CUSTFILE    | `CustomerRepository`        | `cust_id` (PK)                  |
| DISCGRP     | `DisclosureGroupRepository` | composite (group_id, type_cd, cat_cd) |
| TCATBALF    | `TranCatBalRepository`      | composite (acct_id, type_cd, cat_cd) |
| TRANSACT    | `TransactionRepository`     | `tran_id` (PK)                  |

### Validation Logic (`carddemo/validation/`)

Migrated from `COTRN02C.cbl` (online) and `CBTRN02C.cbl` (batch).
The original `python/transaction_validation.py` is now a backward-compatible
shim re-exporting from the package.

### Batch Programs (`carddemo/batch/`)

| COBOL Program | JCL Job   | Python Module              | Function                    |
|:--------------|:----------|:---------------------------|:----------------------------|
| CBACT04C      | INTCALC   | `batch/interest_calc.py`   | Interest calculation        |
| CBTRN02C      | POSTTRAN  | `batch/post_transactions.py` | Post daily transactions   |

Key COBOL control flow faithfully replicated:
- **Interest formula**: `monthly_int = (category_balance * annual_rate) / 1200`
- **Account break logic**: update previous account on acct-id change
- **Disclosure group fallback**: try account's group, then `DEFAULT`
- **Last-failure-wins**: no short-circuit in batch validation (overlimit vs. expiration)
- **Category balance create/update**: VSAM record create on first access

## What Remains (Out of Scope for This Increment)

### Online CICS/BMS Layer (~29 programs)

The online transaction-processing programs (listed in `README.md` lines 269-294)
require rebuilding the CICS pseudo-conversational model and BMS screen maps:

| Transaction | Program  | Function                |
|:------------|:---------|:------------------------|
| CC00        | COSGN00C | Signon                  |
| CM00        | COMEN01C | Main Menu               |
| CAVW        | COACTVWC | Account View            |
| CAUP        | COACTUPC | Account Update          |
| CCLI        | COCRDLIC | Credit Card List        |
| CCDL        | COCRDSLC | Credit Card View        |
| CCUP        | COCRDUPC | Credit Card Update      |
| CT00        | COTRN00C | Transaction List        |
| CT01        | COTRN01C | Transaction View        |
| CT02        | COTRN02C | Transaction Add         |
| CR00        | CORPT00C | Transaction Reports     |
| CB00        | COBIL00C | Bill Payment            |
| CU00-CU03   | COUSRxxC | User Management         |
| CA00        | COADM01C | Admin Menu              |

### JCL Batch Orchestration

The JCL job sequence (POSTTRAN → INTCALC → COMBTRAN → CREASTMT) needs a
Python-native orchestrator or workflow engine.

| Job      | Program  | Status       |
|:---------|:---------|:-------------|
| POSTTRAN | CBTRN02C | **Migrated** |
| INTCALC  | CBACT04C | **Migrated** |
| COMBTRAN | SORT     | Not started  |
| CREASTMT | CBSTM03A | Not started  |
| TRANREPT | CBTRN03C | Not started  |

### Other Components

- **RACF security** re-implementation
- **Optional DB2/IMS/MQ subsystems** (authorization, transaction type management)
- **EBCDIC data file parsing** (the `app/data/EBCDIC/` files)
- **Remaining batch utilities** (CBEXPORT, CBIMPORT, etc.)

## Running Tests

```bash
cd python/
pip install -r requirements.txt
pytest -v
```

All 118 tests should pass, including the 43 pre-existing tests from
`test_transaction_validation.py`.

## Dependencies

See `requirements.txt`:
- `pandas>=2.0` -- in-memory data-access backing store
- `pytest>=7.0` -- test framework

## Package Structure

```
python/
├── carddemo/
│   ├── __init__.py
│   ├── models/           # COBOL copybook → Python dataclass
│   │   ├── account.py         (CVACT01Y)
│   │   ├── card.py            (CVACT02Y)
│   │   ├── card_xref.py       (CVACT03Y)
│   │   ├── common.py          (helpers, ValidationError/Result)
│   │   ├── customer.py        (CVCUS01Y)
│   │   ├── disclosure_group.py (CVTRA02Y)
│   │   ├── export.py          (CVEXPORT -- REDEFINES/OCCURS)
│   │   ├── transaction.py     (CVTRA05Y, CVTRA06Y)
│   │   ├── transaction_category.py (CVTRA01Y, CVTRA03Y, CVTRA04Y)
│   │   └── user_security.py   (CSUSR01Y)
│   ├── dataaccess/       # Repository interfaces + in-memory impl
│   │   ├── repository.py      (abstract interfaces)
│   │   └── in_memory.py       (pandas-backed)
│   ├── batch/            # Ported batch programs
│   │   ├── interest_calc.py   (CBACT04C / INTCALC)
│   │   └── post_transactions.py (CBTRN02C / POSTTRAN)
│   └── validation/       # Transaction validation
│       └── transaction_validation.py (COTRN02C + CBTRN02C)
├── transaction_validation.py  # backward-compatible shim
├── test_transaction_validation.py  # original 43 tests
├── test_models.py         # 33 model tests
├── test_dataaccess.py     # 23 data-access tests
├── test_batch.py          # 19 batch tests
├── requirements.txt
└── README.md              # this file
```
