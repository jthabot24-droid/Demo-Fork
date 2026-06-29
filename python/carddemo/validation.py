"""Golden-master validation harness.

Runs the Python batch pipeline against the same flat-file inputs
used by the COBOL system and diffs the outputs, normalizing
timestamps to allow comparison.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Sequence

from carddemo.fixed_width import FieldSpec, parse_record


@dataclass
class DiffEntry:
    """A single field-level difference between two records."""

    record_index: int
    field_name: str
    expected: Any
    actual: Any


@dataclass
class ValidationResult:
    """Result of comparing two sets of records."""

    total_expected: int = 0
    total_actual: int = 0
    matching: int = 0
    differences: list[DiffEntry] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return (
            self.total_expected == self.total_actual
            and len(self.differences) == 0
        )


_TS_PATTERN = re.compile(r"\d{4}-\d{2}-\d{2}-\d{2}\.\d{2}\.\d{2}\.\d+")


def _normalize_value(value: Any, is_timestamp_field: bool = False) -> str:
    """Normalize a value for comparison."""
    if isinstance(value, Decimal):
        return str(value.normalize())
    s = str(value).strip()
    if is_timestamp_field:
        s = _TS_PATTERN.sub("<TIMESTAMP>", s)
    return s


TIMESTAMP_FIELDS = {"tran_proc_ts", "tran_orig_ts", "dalytran_proc_ts"}


def compare_records(
    expected: Sequence[dict[str, Any]],
    actual: Sequence[dict[str, Any]],
    skip_fields: set[str] | None = None,
    timestamp_fields: set[str] | None = None,
) -> ValidationResult:
    """Compare two lists of parsed records field-by-field.

    Parameters
    ----------
    expected, actual:
        Lists of record dicts (from ``fixed_width.parse_record``).
    skip_fields:
        Field names to ignore during comparison (e.g. FILLER).
    timestamp_fields:
        Fields whose values should be timestamp-normalized before
        comparison.
    """
    skip = skip_fields or set()
    ts_fields = timestamp_fields or TIMESTAMP_FIELDS
    result = ValidationResult(
        total_expected=len(expected),
        total_actual=len(actual),
    )

    for i, (exp, act) in enumerate(zip(expected, actual)):
        all_match = True
        for key in exp:
            if key in skip or key.startswith("_"):
                continue
            is_ts = key in ts_fields
            e_val = _normalize_value(exp[key], is_ts)
            a_val = _normalize_value(act.get(key, ""), is_ts)
            if e_val != a_val:
                result.differences.append(
                    DiffEntry(record_index=i, field_name=key,
                              expected=e_val, actual=a_val)
                )
                all_match = False
        if all_match:
            result.matching += 1

    if len(expected) != len(actual):
        extra = abs(len(expected) - len(actual))
        source = "expected" if len(expected) > len(actual) else "actual"
        for i in range(min(len(expected), len(actual)),
                       max(len(expected), len(actual))):
            result.differences.append(
                DiffEntry(record_index=i, field_name="<record>",
                          expected=f"present in {source}",
                          actual="missing")
            )

    return result
