# CBSTM03A Statement Generation -- Python Migration

Python port of the CardDemo CREASTMT batch job (`app/cbl/CBSTM03A.CBL` +
`app/cbl/CBSTM03B.CBL`).  Reads transaction, cross-reference, customer, and
account data and produces plain-text (80-byte records) and HTML (100-byte
records) account statements.

## Modules

| File | COBOL Source | Purpose |
|------|-------------|---------|
| `cbstm03b_io.py` | `CBSTM03B.CBL` | I/O layer -- loads CSV data and provides sequential / keyed access with COBOL-compatible return codes (`00`, `10`, `23`) |
| `cbstm03a_statement.py` | `CBSTM03A.CBL` | Statement generation -- pre-loads transactions by card, iterates xref records, formats and writes statements |

## Running the Job

```bash
cd python/
pip install -r requirements.txt

python cbstm03a_statement.py \
    fixtures/trnx.csv fixtures/xref.csv \
    fixtures/cust.csv fixtures/acct.csv \
    output_statement.txt output_statement.html
```

Arguments: `<trnx.csv> <xref.csv> <cust.csv> <acct.csv> <stmt_out> <html_out>`

Input CSVs must have columns matching the COBOL copybook field names
(see docstrings in `cbstm03b_io.py` for the full layouts).

## Running the Regression Test

```bash
cd python/
pip install -r requirements.txt
python -m pytest test_cbstm03a_statement.py -v
```

The test compares generated output byte-for-byte against committed reference
files in `reference/`.

## Regenerating Reference Files

If the expected output legitimately changes (e.g. a formatting correction),
regenerate the reference files:

```bash
python cbstm03a_statement.py \
    fixtures/trnx.csv fixtures/xref.csv \
    fixtures/cust.csv fixtures/acct.csv \
    reference/expected_statement.txt reference/expected_statement.html
```

Then commit the updated reference files and verify the tests pass.

## Test Fixture Data

Small, fixed data set under `fixtures/`:

- **trnx.csv** -- 3 transactions across 2 cards (includes a negative amount
  to exercise trailing-minus sign formatting)
- **xref.csv** -- 2 card cross-reference records
- **cust.csv** -- 2 customer records
- **acct.csv** -- 2 account records

## COBOL Numeric Edit Patterns

The highest-risk area for byte mismatches.  These are reproduced exactly:

| COBOL Picture | Python function | Example (value 1500.75) | Width |
|---------------|----------------|------------------------|-------|
| `PIC 9(9).99-` | `format_pic_9_99_minus()` | `000001500.75 ` | 13 |
| `PIC Z(9).99-` | `format_pic_z_99_minus()` | `     1500.75 ` | 13 |

Trailing sign: `-` for negative, space for non-negative.
