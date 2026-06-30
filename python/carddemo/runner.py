"""CLI workflow runner — replaces JCL orchestration.

Mirrors the job sequence in ``scripts/run_full_batch.sh``:

1. Load reference data (ACCTFILE, CARDFILE, XREFFILE, CUSTFILE,
   DISCGRP, TCATBALF, TRANTYPE, DUSRSECJ)
2. Load daily transactions (DALYTRAN)
3. POSTTRAN — post daily transactions (CBTRN02C)
4. INTCALC — calculate interest (CBACT04C)
5. (Future) COMBTRAN, TRANIDX, statement generation

Usage::

    python -m carddemo.runner --data-dir ../app/data/ASCII \\
                              --db sqlite:///carddemo.db \\
                              --steps load,posttran,intcalc,statement
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from carddemo.models import get_engine, get_session, init_db

log = logging.getLogger("carddemo")


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(name)s %(levelname)s  %(message)s",
        datefmt="%H:%M:%S",
    )


def _step_load(session, data_dir: Path) -> None:
    from carddemo.etl import load_all

    log.info("=== STEP: Load reference & daily data ===")
    counts = load_all(session, data_dir)
    for desc, n in counts.items():
        log.info("  %-30s %d records", desc, n)


def _step_posttran(session, data_dir: Path) -> None:
    from carddemo.batch.posttran import run as posttran_run
    from carddemo.fixed_width import DAILY_TRANSACTION_SPEC, read_file

    log.info("=== STEP: POSTTRAN (CBTRN02C) ===")
    daily_path = data_dir / "dailytran.txt"
    if not daily_path.exists():
        log.error("Daily transaction file not found: %s", daily_path)
        return
    daily_trans = read_file(str(daily_path), DAILY_TRANSACTION_SPEC)
    result = posttran_run(daily_trans, session)
    log.info(
        "  Processed=%d  Posted=%d  Rejected=%d",
        result.transactions_processed,
        result.transactions_posted,
        result.transactions_rejected,
    )


def _step_intcalc(session, parm_date: str = "") -> None:
    from carddemo.batch.intcalc import run as intcalc_run

    log.info("=== STEP: INTCALC (CBACT04C) ===")
    result = intcalc_run(session, parm_date=parm_date)
    log.info(
        "  TCB records=%d  Interest TXNs=%d",
        result.records_processed,
        result.interest_transactions_written,
    )


def _step_statement(session, output_dir: Path) -> None:
    from carddemo.batch.statement import run as stmt_run

    log.info("=== STEP: Statement Generation (CBSTM03A) ===")
    stmt_path = output_dir / "statements.txt"
    html_path = output_dir / "statements.html"
    result = stmt_run(session, stmt_path=stmt_path, html_path=html_path)
    log.info(
        "  Accounts=%d  Transactions=%d",
        result.accounts_processed,
        result.transactions_included,
    )


ALL_STEPS = ("load", "posttran", "intcalc", "statement")


def run_batch(
    data_dir: str | Path,
    db_url: str = "sqlite:///carddemo.db",
    steps: tuple[str, ...] = ALL_STEPS,
    parm_date: str = "",
    output_dir: str | Path | None = None,
) -> None:
    """Run the batch pipeline."""
    data_dir = Path(data_dir)
    output_dir = Path(output_dir) if output_dir else data_dir

    engine = get_engine(db_url)
    init_db(engine)
    session = get_session(engine)

    try:
        if "load" in steps:
            _step_load(session, data_dir)
        if "posttran" in steps:
            _step_posttran(session, data_dir)
        if "intcalc" in steps:
            _step_intcalc(session, parm_date)
        if "statement" in steps:
            _step_statement(session, output_dir)
    finally:
        session.close()

    log.info("Batch pipeline complete.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="CardDemo batch pipeline — Python port of JCL orchestration",
    )
    parser.add_argument(
        "--data-dir",
        required=True,
        help="Path to the ASCII data directory (e.g. app/data/ASCII)",
    )
    parser.add_argument(
        "--db",
        default="sqlite:///carddemo.db",
        help="SQLAlchemy DB URL (default: sqlite:///carddemo.db)",
    )
    parser.add_argument(
        "--steps",
        default=",".join(ALL_STEPS),
        help=f"Comma-separated steps to run (default: {','.join(ALL_STEPS)})",
    )
    parser.add_argument(
        "--parm-date",
        default="",
        help="Date parameter for INTCALC (YYYY-MM-DD); defaults to today",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help="Output directory for statements (defaults to --data-dir)",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    _setup_logging(args.verbose)
    steps = tuple(s.strip() for s in args.steps.split(","))

    run_batch(
        data_dir=args.data_dir,
        db_url=args.db,
        steps=steps,
        parm_date=args.parm_date,
        output_dir=args.output_dir,
    )


if __name__ == "__main__":
    main()
