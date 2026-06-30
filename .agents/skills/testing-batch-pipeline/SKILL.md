---
name: testing-carddemo-batch-pipeline
description: Test the CardDemo Python batch pipeline (POSTTRAN, INTCALC, Statement) end-to-end. Use when verifying batch processing logic, ETL loads, or fixed-width file I/O changes.
---

# Testing the CardDemo Python Batch Pipeline

## Overview

The Python batch pipeline under `python/` ports COBOL batch programs to Python. It processes fixed-width ASCII flat files through ETL → POSTTRAN → INTCALC → Statement generation.

## Prerequisites

- Python environment with the package installed: `cd python && pip install -e ".[dev]"`
- No external services needed — uses SQLite for testing
- Data fixtures live in `app/data/ASCII/*.txt`

## Running the Full Pipeline

```bash
cd python
python -m carddemo.runner \
  --data-dir ../app/data/ASCII \
  --db sqlite:////tmp/test.db \
  --steps load,posttran,intcalc,statement \
  --parm-date 2024-06-15 \
  --output-dir /tmp/output
```

## Running Unit Tests

```bash
cd python && python -m pytest tests/ -v
```

52 tests covering: models, fixed-width parser, ETL, POSTTRAN, INTCALC, statement, runner, validation.

## Key Assertions for E2E Testing

### ETL Load Step
- `dailytran.txt` is NOT loaded during the `load` step (it's sequential input for POSTTRAN)
- After `load`: transactions table should have 0 records
- Expected record counts: accounts=50, customers=50, cards=50, card_xref=50, disc_groups=51, tran_cat_bal=50, tran_types=7, tran_categories=18

### POSTTRAN (Transaction Posting)
- Processes 300 daily transactions from `dailytran.txt`
- Expected: ~262 posted, ~38 rejected (exact numbers may vary if data changes)
- posted + rejected must always = 300
- Reject codes: 100 (invalid card), 101 (missing account), 102 (overlimit), 103 (expired)

### INTCALC (Interest Calculation)
- Processes TranCatBal records (50 initial + new ones from POSTTRAN)
- Writes interest transactions with type_cd='01', cat_cd='0005'
- DEFAULT discount group lookup must work (key stored as stripped "DEFAULT", not padded)
- Most interest amounts should be non-zero (formula: `balance * rate / 1200`)

### Statement Generation
- Generates `statements.txt` (plain-text) and `statements.html`
- 50 statements (one per account)
- HTML output must use `html.escape()` for user-sourced data

### Fixed-Width Round-Trip
- Parse any `.txt` file and write it back → output must be byte-identical to input
- Test with `acctdata.txt` (300 bytes/record) or `dailytran.txt` (350 bytes/record)

## Common Issues

- **ETL strips whitespace** via `_to_str()`. If lookup keys include padding in the code (e.g., `"DEFAULT".ljust(10)`), they won't match the stripped DB values. Always use stripped keys.
- **Daily transactions** are NOT pre-loaded into the transactions table. They flow through POSTTRAN validation first. If you see 300 records in `transactions` after just the `load` step, the bug has regressed.
- **Interest amounts of 0.00** for all records likely means the DEFAULT group rate lookup is broken (padding mismatch).

## Devin Secrets Needed

None — all testing is local with SQLite and fixture files.
