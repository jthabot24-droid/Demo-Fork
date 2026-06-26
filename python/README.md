# CardDemo COBOL-to-Python Migration

Python reimplementation of selected batch programs from the AWS CardDemo
mainframe application. Each module preserves the original COBOL paragraph
names (in docstrings) and replicates the documented control flow, including
known quirks such as "last-failure-wins" error handling.

## Migrated Programs

| COBOL source | Python module | Description |
|---|---|---|
| `COTRN02C.cbl` / `CBTRN02C.cbl` (validation only) | `transaction_validation.py` | Online and batch transaction validation |
| `CBTRN02C.cbl` (full program) | `post_transactions.py` | Batch daily-transaction posting (read, validate, post, reject) |
| `CBACT04C.cbl` | `interest_calc.py` | Batch interest calculation |

## Data Conventions

- COBOL copybook record layouts are modelled as `@dataclass` classes.
- VSAM indexed/sequential file I/O is replaced by `pandas` DataFrames.
- All monetary fields use `decimal.Decimal` (matching COBOL `PIC S9(n)V99`).
- Timestamps follow the DB2 format `YYYY-MM-DD-HH.MM.SS.mm0000`.

### Input DataFrames

Each function expects DataFrames whose columns correspond to the
COBOL copybook fields. Column names use the Python `snake_case`
equivalents listed in the dataclass definitions.

**`post_daily_transactions`** (from `post_transactions.py`):

| DataFrame | Copybook | Key columns |
|---|---|---|
| `daily_trans_df` | CVTRA06Y | `dalytran_card_num`, `dalytran_amt`, `dalytran_type_cd`, `dalytran_cat_cd`, ... |
| `xref_df` | CVACT03Y | `xref_card_num`, `xref_acct_id` |
| `account_df` | CVACT01Y | `acct_id`, `acct_curr_bal`, `acct_credit_limit`, `acct_expiration_date`, ... |
| `tcatbal_df` | CVTRA01Y | `trancat_acct_id`, `trancat_type_cd`, `trancat_cd`, `tran_cat_bal` |

**`calculate_interest`** (from `interest_calc.py`):

| DataFrame | Copybook | Key columns |
|---|---|---|
| `tcatbal_df` | CVTRA01Y | `trancat_acct_id`, `trancat_type_cd`, `trancat_cd`, `tran_cat_bal` |
| `xref_df` | CVACT03Y | `xref_acct_id`, `xref_card_num` |
| `account_df` | CVACT01Y | `acct_id`, `acct_curr_bal`, `acct_group_id`, ... |
| `discgrp_df` | CVTRA02Y | `dis_acct_group_id`, `dis_tran_type_cd`, `dis_tran_cat_cd`, `dis_int_rate` |

## Running

```bash
# Install dependencies
pip install -r python/requirements.txt

# Run all tests
pytest python/ -v

# Run a single test module
pytest python/test_post_transactions.py -v
pytest python/test_interest_calc.py -v
```
