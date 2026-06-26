# CardDemo COBOL-to-Python Migration Plan

## Overview

This document defines the phased migration of the CardDemo mainframe credit-card
management application from COBOL/CICS/VSAM to Python.  Each phase is designed
to be independently testable, with strict parity tests against the original
COBOL behaviour.

---

## Dependency Map

```
Phase 0  ──►  Phase 1  ──►  Phase 2  ──►  Phase 3
  │              │              │              │
  │              │              │              └─► Phase 4 (optional)
  │              │              │
  data models    business       batch          online/CICS
  & storage      logic          pipeline       UI layer
```

| Artifact (COBOL)         | Python target                        | Phase |
|:-------------------------|:-------------------------------------|:-----:|
| Copybooks (app/cpy/)     | `python/models/`                     |   0   |
| VSAM KSDS files (CSD)    | `python/data/` (store abstraction)   |   0   |
| Sample data (app/data/)  | `python/data/seed.py`                |   0   |
| Transaction validation   | `python/transaction_validation.py`   |   1   |
| CBACT04C (interest calc) | `python/interest_calculation.py`     |   1   |
| CBTRN02C (post daily)    | `python/transaction_posting.py`      |   1   |
| CBTRN01C (tran driver)   | `python/transaction_posting.py`      |   1   |
| CBACT01C-03C (acct maint)| `python/batch/account_maintenance.py`|   2   |
| CBSTM03A (statements)    | `python/batch/statements.py`         |   2   |
| CBTRN03C (tran report)   | `python/batch/transaction_report.py` |   2   |
| CBEXPORT / CBIMPORT      | `python/batch/export_import.py`      |   2   |
| JCL job orchestration    | `python/batch/pipeline.py`           |   2   |
| COSGN00C (signon)        | `python/online/auth.py`              |   3   |
| COMEN01C (menu)          | `python/online/menu.py`              |   3   |
| COACTVWC / COACTUPC      | `python/online/account.py`           |   3   |
| COCRDLIC/COCRDSLC/COCRDUPC| `python/online/card.py`             |   3   |
| COTRN00C/01C/02C         | `python/online/transaction.py`       |   3   |
| CORPT00C                 | `python/online/reports.py`           |   3   |
| COBIL00C                 | `python/online/billing.py`           |   3   |
| COUSR00C-03C             | `python/online/user_admin.py`        |   3   |
| COADM01C                 | `python/online/admin.py`             |   3   |
| BMS maps                 | Web UI templates                     |   3   |
| COPAUA0C (IMS+DB2+MQ)    | `python/optional/authorization.py`   |   4   |
| Transaction-type DB2 pgms| `python/optional/tran_type_db2.py`   |   4   |
| MQ account extractions   | `python/optional/mq_extract.py`      |   4   |

---

## Phase 0 -- Data & Record Layouts (Foundation)

### Scope
Translate every COBOL copybook into a Python dataclass and replace VSAM
KSDS indexed file access with a Python data-access abstraction backed by
CSV or SQLite.

### Source COBOL Artifacts
| Copybook   | Record                    | Length | Key field(s)                |
|:-----------|:--------------------------|-------:|:----------------------------|
| CVACT01Y   | ACCOUNT-RECORD            |    300 | ACCT-ID                     |
| CVACT02Y   | CARD-RECORD               |    150 | CARD-NUM                    |
| CVCUS01Y   | CUSTOMER-RECORD           |    500 | CUST-ID                     |
| CVACT03Y   | CARD-XREF-RECORD          |     50 | XREF-CARD-NUM (alt: XREF-ACCT-ID) |
| CVTRA05Y   | TRAN-RECORD               |    350 | TRAN-ID                     |
| CVTRA06Y   | DALYTRAN-RECORD           |    350 | DALYTRAN-ID                 |
| CSUSR01Y   | SEC-USER-DATA             |     80 | SEC-USR-ID                  |
| CVTRA01Y   | TRAN-CAT-BAL-RECORD       |     50 | composite: ACCT-ID+TYPE+CAT |
| CVTRA02Y   | DIS-GROUP-RECORD          |     50 | composite: GROUP+TYPE+CAT   |
| CVTRA03Y   | TRAN-TYPE-RECORD          |     60 | TRAN-TYPE                   |
| CVTRA04Y   | TRAN-CAT-RECORD           |     60 | composite: TYPE+CAT         |

### Target Python Modules
- `python/models/__init__.py` -- re-exports all model dataclasses
- `python/models/account.py` -- `AccountRecord`
- `python/models/card.py` -- `CardRecord`
- `python/models/customer.py` -- `CustomerRecord`
- `python/models/card_xref.py` -- `CardXrefRecord`
- `python/models/transaction.py` -- `TransactionRecord`
- `python/models/daily_transaction.py` -- `DailyTransactionRecord`
- `python/models/user_security.py` -- `UserSecurityRecord`
- `python/models/tran_cat_balance.py` -- `TranCatBalanceRecord`
- `python/models/disclosure_group.py` -- `DisclosureGroupRecord`
- `python/data/store.py` -- `VsamStore` ABC + `InMemoryVsamStore`
- `python/data/seed.py` -- fixed-width ASCII parser, seed loader

### Prerequisites
None (this is the foundation phase).

### Parity-Testing Strategy
- Round-trip tests: construct a record, serialize, deserialize, verify equality.
- Field-width assertions: validate that `str` field defaults honour COBOL PIC
  lengths; `Decimal` fields match `PIC S9(n)V99` precision.
- Seed-data tests: parse every line of `app/data/ASCII/*` and verify the
  resulting dataclass instances have sensible values (non-empty keys, balanced
  sign-digit encoding).
- Store CRUD tests: write, read-by-key, rewrite, delete, sequential scan.

---

## Phase 1 -- Business Logic & Validation

### Scope
Port pure-logic COBOL paragraphs that do not depend on CICS or screen I/O.
Refactor the existing `transaction_validation.py` to consume Phase 0 models
and data stores.

### Source COBOL Artifacts
| Program    | Key Paragraphs                                    |
|:-----------|:--------------------------------------------------|
| COTRN02C   | VALIDATE-INPUT-KEY-FIELDS, VALIDATE-INPUT-DATA-FIELDS |
| CBTRN02C   | 1500-VALIDATE-TRAN, 2000-POST-TRANSACTION, 2700-UPDATE-TCATBAL, 2800-UPDATE-ACCOUNT-REC |
| CBACT04C   | 1300-COMPUTE-INTEREST, 1200-GET-INTEREST-RATE, 1050-UPDATE-ACCOUNT |
| CBTRN01C   | Transaction driver logic                          |

### Target Python Modules
- `python/transaction_validation.py` -- refactored (imports from `models/`)
- `python/interest_calculation.py` -- `compute_interest()` from CBACT04C
- `python/transaction_posting.py` -- `post_transaction()`, `update_account()`,
  `update_tran_cat_balance()` from CBTRN02C

### Prerequisites
Phase 0 complete (models and data stores available).

### Parity-Testing Strategy
- Existing `test_transaction_validation.py` tests continue to pass unchanged.
- New tests under `python/tests/` verify:
  - Interest calculation against hand-computed examples matching COBOL formula
    `monthly_interest = (tran_cat_bal * dis_int_rate) / 1200`.
  - Transaction posting updates `acct_curr_bal`, `acct_curr_cyc_credit`,
    `acct_curr_cyc_debit` correctly (positive amounts to credit, negative to
    debit), and writes a valid `TransactionRecord`.
  - TCATBAL create-or-update logic mirrors COBOL 2700-A / 2700-B.

---

## Phase 2 -- Batch Pipeline (not implemented in this task)

### Scope
Replace the JCL-driven batch job chain with a Python orchestrator.  Each
COBOL batch program becomes a Python function/class; the JCL sequencing
(CLOSEFIL -> ACCTFILE -> CARDFILE -> ... -> OPENFIL) becomes a DAG runner.

### Source COBOL Artifacts
- CBACT01C -- CBACT04C (account maintenance, interest calc)
- CBTRN01C -- CBTRN03C (transaction processing, reporting)
- CBSTM03A / CBSTM03B (statement generation)
- CBEXPORT / CBIMPORT (data export/import)
- JCL scripts in `app/jcl/`
- Control-M definitions in `app/scheduler/`

### Target Python Modules
- `python/batch/pipeline.py` -- orchestrator (replaces JCL sequence)
- `python/batch/account_maintenance.py` -- CBACT01C-03C
- `python/batch/statements.py` -- CBSTM03A/B
- `python/batch/transaction_report.py` -- CBTRN03C
- `python/batch/export_import.py` -- CBEXPORT/CBIMPORT

### Prerequisites
Phase 0 + Phase 1 complete.

### Parity-Testing Strategy
- End-to-end batch run using seed data; compare output files (transaction
  master, reject file, statement output) field-by-field against known-good
  COBOL output snapshots.
- Job-step ordering tests: verify the DAG runner respects the sequencing
  constraints documented in the README "Running Batch Jobs" section.

---

## Phase 3 -- Online / CICS Layer (not implemented in this task)

### Scope
Replace CICS transaction processing with a Python web application (e.g.
FastAPI or Flask).  BMS screen maps become HTML/API endpoints.  COMMAREA-
based inter-program communication becomes function calls or service calls.

### Source COBOL Artifacts
- COSGN00C (signon), COMEN01C (menu)
- COACTVWC / COACTUPC (account view/update)
- COCRDLIC / COCRDSLC / COCRDUPC (card list/view/update)
- COTRN00C / COTRN01C / COTRN02C (transaction list/view/add)
- CORPT00C (reports), COBIL00C (billing)
- COUSR00C-03C (user CRUD), COADM01C (admin menu)
- BMS mapsets in `app/bms/`

### Target Python Modules
- `python/online/` package with modules per functional area
- `python/online/auth.py` -- signon (replaces RACF/COSGN00C)
- `python/online/menu.py` -- navigation (replaces COMEN01C)
- `python/online/account.py`, `card.py`, `transaction.py`, etc.

### Prerequisites
Phase 0 + Phase 1 + Phase 2 complete.

### Parity-Testing Strategy
- Screen-flow integration tests: simulate user paths (login -> menu ->
  view account -> update -> verify) and assert identical business outcomes.
- API contract tests against captured COBOL COMMAREA payloads.

---

## Phase 4 -- Optional DB2 / IMS / MQ Modules (not implemented in this task)

### Scope
Port the optional extension modules that use DB2, IMS DB, and MQ.

### Source COBOL Artifacts
- `app/app-transaction-type-db2/` -- COBTUPDT, COTRTLIC, COTRTUPC
- `app/app-authorization-ims-db2-mq/` -- COPAUA0C, COPAUS0C, COPAUS1C,
  PAUDBUNL.CBL, CBPAUP0C
- MQ programs: CODATE01, COACCT01

### Target Python Modules
- `python/optional/tran_type_db2.py` -- transaction type CRUD (SQLAlchemy)
- `python/optional/authorization.py` -- pending authorization processing
- `python/optional/mq_extract.py` -- MQ-based account/date inquiries
  (replaced by REST or message-queue adapter)

### Prerequisites
Phase 0 + Phase 1 + Phase 3 complete (online layer provides the UI hooks).

### Parity-Testing Strategy
- DB2 modules: compare SQL results against reference datasets.
- MQ modules: mock message broker; verify request/response payloads match
  COBOL COMMAREA structures byte-for-byte.
- IMS modules: compare hierarchical query results against flat-file exports
  generated by PAUDBUNL.
