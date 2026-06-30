"""Shared helpers and result types used across the CardDemo migration.

Mirrors utility logic originally found in COBOL programs and copybooks
such as CSMSG01Y (common messages) and inline validation helpers.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Optional


# ---------------------------------------------------------------------------
# Validation result
# ---------------------------------------------------------------------------


@dataclass
class ValidationError:
    """A single validation failure."""

    code: int
    message: str
    field: str = ""


@dataclass
class ValidationResult:
    """Outcome of a validation run."""

    is_valid: bool = True
    errors: list[ValidationError] = field(default_factory=list)

    resolved_acct_id: Optional[int] = None
    resolved_card_num: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers -- faithfully replicate COBOL semantics
# ---------------------------------------------------------------------------

_DATE_FMT_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
_AMOUNT_FMT_RE = re.compile(r"^[+\-]\d{8}\.\d{2}$")


def is_blank(value: str) -> bool:
    """Mirrors COBOL ``= SPACES OR LOW-VALUES``."""
    return value is None or value.strip() == "" or value == "\x00" * len(value)


def is_numeric(value: str) -> bool:
    """Mirrors COBOL ``IS NUMERIC`` check for unsigned integer strings."""
    return value.strip().isdigit()


def validate_date_format(date_str: str) -> bool:
    """Check YYYY-MM-DD structural format (COBOL positional checks)."""
    return bool(_DATE_FMT_RE.match(date_str.strip()))


def validate_date_value(date_str: str) -> bool:
    """Replaces the CSUTLDTC call.

    The original COBOL suppresses message 2513 (future-date warning), so we
    accept future dates as valid.
    """
    try:
        datetime.strptime(date_str.strip(), "%Y-%m-%d")
        return True
    except ValueError:
        return False


def validate_amount_format(amt_str: str) -> bool:
    """Validate the COBOL amount format ``+/-99999999.99``.

    COBOL checks (1-indexed positions):
    * pos 1 must be '+' or '-'
    * pos 2-9 must be numeric (8 digits)
    * pos 10 must be '.'
    * pos 11-12 must be numeric (2 digits)
    """
    return bool(_AMOUNT_FMT_RE.match(amt_str.strip()))


def decimal_field(default: str = "0.00") -> Decimal:
    """Return a ``Decimal`` suitable for a monetary dataclass field default."""
    return Decimal(default)
