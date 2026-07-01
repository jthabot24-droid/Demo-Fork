# CBSTM03A Statement Generation -- Python Migration

Python port of the CardDemo COBOL batch program `CBSTM03A.CBL` (CREASTMT job),
which prints account statements from transaction data in two formats: plain text
(fixed 80-byte records) and HTML (fixed 100-byte records).

## Modules

| File | Description |
|------|-------------|
| `cbstm03a_statement.py` | Main statement generation logic (port of `CBSTM03A.CBL`) |
| `cbstm03b_io.py` | VSAM I/O helper reproducing `CBSTM03B.CBL` file-access semantics |

## Running the job

```bash
cd python/
python cbstm03a_statement.py \
    TRNX.csv XREF.csv CUST.csv ACCT.csv \
    statement.txt statement.html
```

Input files are CSV with headers matching the COBOL copybook field names
(lowercase, underscored). See `fixtures/` for examples.

## Running the regression test

```bash
cd python/
pip install -r requirements.txt
python -m pytest test_cbstm03a_statement.py -v
```

The test compares generated output byte-for-byte against the committed reference
files in `reference/`.

## Regenerating reference files

If the expected output legitimately changes, regenerate with:

```bash
cd python/
python cbstm03a_statement.py \
    fixtures/trnx.csv fixtures/xref.csv \
    fixtures/cust.csv fixtures/acct.csv \
    reference/expected_statement.txt \
    reference/expected_statement.html
```

Then commit the updated reference files.

## Design notes

- All monetary arithmetic uses `decimal.Decimal` (never `float`) to match COBOL
  packed-decimal (`COMP-3`) precision.
- COBOL numeric edit pictures (`PIC 9(9).99-`, `PIC Z(9).99-`) are reproduced
  exactly, including trailing sign placement and zero suppression.
- The COBOL `STRING ... DELIMITED BY` semantics are ported faithfully for name
  and address construction.
- Input data is loaded via pandas DataFrames (CSV files), keyed on the same
  fields as the original COBOL VSAM record layouts.
- The MVS control-block walk (PSA/TCB/TIOT) and `ALTER`/`GO TO` state machine
  are replaced by straight-line Python control flow.
