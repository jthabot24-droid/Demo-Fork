# CardDemo Mainframe-to-Python Migration Plan

## Overview

This document describes a six-phase migration of the CardDemo mainframe
application (COBOL/CICS/VSAM/JCL) to Python.  Each phase is designed to be
independently testable so that the migrated code can be validated against the
original COBOL output before proceeding to the next phase.

The existing partial migration (`transaction_validation.py`) covers validation
logic from `COTRN02C` (online) and `CBTRN02C` (batch).  This plan builds on
those conventions: `dataclass` copybook mirrors, `decimal.Decimal` for
packed-decimal arithmetic, and pandas DataFrames for VSAM lookups.

---

## Phase 0 — Assessment & Golden-Dataset Test Harness

**Goal:** Establish the project structure, capture a golden dataset from the
sample data in `app/data/ASCII/`, and build a parity-test harness that will be
reused by every subsequent phase.

### Artefacts

| Artefact | Description |
|---|---|
| `python/carddemo/` | Top-level Python package |
| `python/carddemo/models/` | Copybook dataclass models (Phase 1) |
| `python/carddemo/data/` | Data-access / repository layer (Phase 2) |
| `python/carddemo/batch/` | Batch program ports (Phase 3) |
| `python/carddemo/online/` | Online/CICS program ports (Phase 4) |
| `python/tests/` | Test package (parity tests, unit tests) |
| `python/MIGRATION.md` | This document |

### Acceptance Criteria

- `pytest` discovers and passes all existing `test_transaction_validation.py`
  tests.
- A parity-test scaffold exists that can load a COBOL-format input file, run a
  Python function, and assert equality against an expected golden output using
  `Decimal` comparisons for monetary fields.

---

## Phase 1 — Copybook Record Models

**Goal:** Create Python `dataclass` equivalents for every VSAM-backed copybook,
with field-accurate types and fixed-width `from_record` / `to_record` methods
that can round-trip the ASCII sample data files.

### Copybooks Covered

| Copybook | Record Name | Record Length | VSAM File | Python Module |
|---|---|---|---|---|
| `CVACT01Y` | ACCOUNT-RECORD | 300 | ACCTDATA | `carddemo/models/account.py` |
| `CVACT02Y` | CARD-DATA-RECORD | 150 | CARDDATA | `carddemo/models/card.py` (stub) |
| `CVACT03Y` | CARD-XREF-RECORD | 50 | CARDXREF | `carddemo/models/card_xref.py` |
| `CVTRA05Y` | TRAN-RECORD | 350 | TRANSACT | `carddemo/models/transaction.py` |
| `CVTRA06Y` | DALYTRAN-RECORD | 350 | DALYTRAN | `carddemo/models/daily_transaction.py` |
| `CVCUS01Y` | CUSTOMER-RECORD | 500 | CUSTDATA | `carddemo/models/customer.py` |
| `CSUSR01Y` | SEC-USER-DATA | 80 | USRSEC | `carddemo/models/user_security.py` (stub) |
| `CVTRA01Y` | TRAN-CAT-BAL-RECORD | 50 | TCATBALF | `carddemo/models/tran_cat_bal.py` (stub) |
| `CVTRA02Y` | DISCGRP-RECORD | 50 | DISCGRP | `carddemo/models/disclosure_group.py` (stub) |
| `CVTRA03Y` | TRAN-TYPE-RECORD | 60 | TRANTYPE | `carddemo/models/tran_type.py` (stub) |
| `CVTRA04Y` | TRAN-CAT-RECORD | 60 | TRANCATG | `carddemo/models/tran_category.py` (stub) |

### Dependencies

- None beyond the Python standard library and `decimal`.

### Acceptance Criteria

- `from_record(line)` parses every line of each ASCII sample data file without
  error.
- `to_record()` reproduces the original fixed-width line byte-for-byte
  (round-trip).
- Signed numeric fields (`PIC S9(n)V99`) are correctly decoded from the COBOL
  zoned-decimal ASCII overpunch format to `Decimal`.

---

## Phase 2 — Data-Access Layer (VSAM Replacement)

**Goal:** Provide a `Repository` abstraction that loads fixed-width sample files
into pandas DataFrames, keyed the same way as the COBOL `RECORD KEY` fields, and
offers get-by-key and sequential-iteration access to mirror VSAM `RANDOM` and
`SEQUENTIAL` access modes.

### VSAM Files and Keys

| VSAM File | Record Key | Alternate Keys | Python Repository |
|---|---|---|---|
| ACCTDATA (ACCTFILE) | `acct_id` | — | `AccountRepository` |
| CARDDATA (CARDFILE) | `card_num` | — | (stub) |
| CARDXREF (XREFFILE) | `xref_card_num` | `xref_acct_id` | `CardXrefRepository` |
| TRANSACT (TRANFILE) | `tran_id` | `tran_card_num` (AIX) | `TransactionRepository` |
| DALYTRAN | `dalytran_id` | — | `DailyTransactionRepository` |
| CUSTDATA (CUSTFILE) | `cust_id` | — | `CustomerRepository` |
| USRSEC (DUSRSECJ) | `sec_usr_id` | — | (stub) |
| TCATBALF | `tran_cat_key` | — | (stub) |
| DISCGRP | `discgrp_key` | — | (stub) |
| TRANCATG | `tran_cat_cd` | — | (stub) |
| TRANTYPE | `tran_type_cd` | — | (stub) |

### Dependencies

- `pandas` (already in `requirements.txt`).
- Phase 1 models for record parsing.

### Acceptance Criteria

- `Repository.load(filepath)` reads the ASCII flat file and returns a DataFrame
  with correctly typed columns.
- `get(key)` returns a single record (or `None`); iteration yields records in
  file order.
- Unit tests verify load/get/iterate against the sample data in
  `app/data/ASCII/`.

---

## Phase 3 — Batch Programs

**Goal:** Port each batch COBOL program to a Python module under
`carddemo/batch/`.

### Programs

| Job | COBOL Program | Function | Python Module |
|---|---|---|---|
| POSTTRAN | `CBTRN02C` | Post daily transactions | `batch/post_transactions.py` (validation already migrated) |
| INTCALC | `CBACT04C` | Interest calculations | `batch/interest_calc.py` |
| CREASTMT | `CBSTM03A` | Produce statements | `batch/create_statement.py` |
| TRANREPT | `CBTRN03C` | Transaction report | `batch/transaction_report.py` |
| — | `CBACT01C` | Account file processing | `batch/account_file.py` |
| — | `CBACT02C` | Account file utilities | `batch/account_util.py` |
| — | `CBACT03C` | Account file utilities | `batch/account_util2.py` |
| — | `CBCUS01C` | Customer file processing | `batch/customer_file.py` |
| — | `CBTRN01C` | Transaction file init | `batch/transaction_init.py` |
| — | `CBEXPORT` | Data export | `batch/export.py` |
| — | `CBIMPORT` | Data import | `batch/data_import.py` |

### Dependencies

- Phase 1 (models) and Phase 2 (data-access layer).

### Acceptance Criteria

- Each batch program produces byte-identical output when run against the golden
  dataset, compared field-by-field with `Decimal` precision for monetary values.
- Batch programs accept the same input files as the COBOL originals.

---

## Phase 4 — Online / CICS Programs as Services

**Goal:** Port CICS online programs to Python functions or lightweight service
handlers under `carddemo/online/`.

### Programs

| Transaction | COBOL Program | Function | Python Module |
|---|---|---|---|
| CC00 | `COSGN00C` | Sign-on | `online/signon.py` |
| CM00 | `COMEN01C` | Main menu | `online/main_menu.py` |
| CA00 | `COADM01C` | Admin menu | `online/admin_menu.py` |
| CAVW | `COACTVWC` | Account view | `online/account_view.py` |
| CAUP | `COACTUPC` | Account update | `online/account_update.py` |
| CCLI | `COCRDLIC` | Card list | `online/card_list.py` |
| CCDL | `COCRDSLC` | Card view | `online/card_view.py` |
| CCUP | `COCRDUPC` | Card update | `online/card_update.py` |
| CT00 | `COTRN00C` | Transaction list | `online/transaction_list.py` |
| CT01 | `COTRN01C` | Transaction view | `online/transaction_view.py` |
| CT02 | `COTRN02C` | Transaction add | `online/transaction_add.py` (validation migrated) |
| CR00 | `CORPT00C` | Reports | `online/reports.py` |
| CB00 | `COBIL00C` | Bill payment | `online/bill_payment.py` |
| CU00 | `COUSR00C` | User list | `online/user_list.py` |
| CU01 | `COUSR01C` | User add | `online/user_add.py` |
| CU02 | `COUSR02C` | User update | `online/user_update.py` |
| CU03 | `COUSR03C` | User delete | `online/user_delete.py` |

### Dependencies

- Phases 1-3.
- A CICS COMMAREA abstraction (TBD — simple dict/dataclass).

### Acceptance Criteria

- Each service function produces the same COMMAREA-equivalent output as the
  COBOL program for a set of representative inputs.
- Screen-flow integration tests cover the main user and admin paths.

---

## Phase 5 — JCL Orchestration to Python Job Runner

**Goal:** Replace JCL job streams with a Python job runner that orchestrates
batch programs in the correct sequence with proper file open/close semantics.

### JCL Jobs

| JCL | Purpose | Python Equivalent |
|---|---|---|
| `CLOSEFIL.jcl` | Close VSAM files | Repository context-manager `__exit__` |
| `OPENFIL.jcl` | Open VSAM files | Repository context-manager `__enter__` |
| `ACCTFILE.jcl` | Load account data | `job_runner.load_accounts()` |
| `CARDFILE.jcl` | Load card data | `job_runner.load_cards()` |
| `CUSTFILE.jcl` | Load customer data | `job_runner.load_customers()` |
| `XREFFILE.jcl` | Load cross-ref | `job_runner.load_xref()` |
| `TRANFILE.jcl` | Load transactions | `job_runner.load_transactions()` |
| `TRANBKP.jcl` | Backup transactions | `job_runner.backup_transactions()` |
| `POSTTRAN.jcl` | Post transactions | `job_runner.post_transactions()` |
| `INTCALC.jcl` | Interest calc | `job_runner.interest_calc()` |
| `COMBTRAN.jcl` | Combine trans | `job_runner.combine_transactions()` |
| `CREASTMT.JCL` | Create statements | `job_runner.create_statements()` |
| `DISCGRP.jcl` | Load disclosure groups | `job_runner.load_disclosure_groups()` |
| `TCATBALF.jcl` | Load category balances | `job_runner.load_cat_balances()` |
| `TRANCATG.jcl` | Load categories | `job_runner.load_categories()` |
| `TRANTYPE.jcl` | Load trans types | `job_runner.load_tran_types()` |
| `DUSRSECJ.jcl` | Load user security | `job_runner.load_user_security()` |
| `DEFGDGB.jcl` | Setup GDG bases | N/A (no GDG equivalent needed) |
| `WAITSTEP.jcl` | Timer wait | `time.sleep()` / scheduler |

### Dependencies

- Phases 1-4.

### Acceptance Criteria

- The full batch cycle (load → post → interest → combine → statement) runs
  end-to-end in Python and produces equivalent output to the JCL sequence.

---

## Phase 6 — Parallel-Run Reconciliation & Cutover

**Goal:** Run COBOL and Python side-by-side, comparing outputs, then cut over.

### Activities

1. **Parallel-run harness** — feed identical input to both COBOL and Python,
   capture outputs, diff field-by-field.
2. **Reconciliation reports** — flag any discrepancies with record IDs and
   field-level deltas.
3. **Performance baseline** — measure Python throughput against COBOL batch
   timings.
4. **Cutover checklist** — decommission COBOL artefacts, update operational
   procedures.

### Dependencies

- All previous phases.

### Acceptance Criteria

- Zero field-level discrepancies on the full sample dataset for three
  consecutive parallel runs.
- Python batch cycle completes within 2× the COBOL elapsed time (or better).

---

## Current Status

| Phase | Status | Notes |
|---|---|---|
| 0 | **In Progress** | Package layout, test harness, this document |
| 1 | **In Progress** | Core copybook models implemented (CVACT01Y, CVACT03Y, CVTRA05Y, CVTRA06Y, CVCUS01Y) |
| 2 | **In Progress** | Repository abstraction with DataFrame-backed access |
| 3 | Not Started | Batch programs — stubs only |
| 4 | Not Started | Online programs — stubs only |
| 5 | Not Started | Job runner — design only |
| 6 | Not Started | Parallel-run — design only |
