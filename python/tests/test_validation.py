"""Tests for the golden-master validation harness."""

from decimal import Decimal

from carddemo.validation import compare_records


class TestCompareRecords:
    def test_identical_records(self):
        records = [
            {"field_a": "hello", "field_b": Decimal("1.23")},
            {"field_a": "world", "field_b": Decimal("4.56")},
        ]
        result = compare_records(records, records)
        assert result.passed
        assert result.matching == 2

    def test_detects_differences(self):
        expected = [{"field_a": "hello"}]
        actual = [{"field_a": "world"}]
        result = compare_records(expected, actual)
        assert not result.passed
        assert len(result.differences) == 1
        assert result.differences[0].field_name == "field_a"

    def test_normalizes_timestamps(self):
        expected = [{"tran_proc_ts": "2024-01-01-10.00.00.000000"}]
        actual = [{"tran_proc_ts": "2025-06-15-14.30.22.123456"}]
        result = compare_records(expected, actual, timestamp_fields={"tran_proc_ts"})
        assert result.passed

    def test_different_lengths(self):
        expected = [{"a": "1"}, {"a": "2"}]
        actual = [{"a": "1"}]
        result = compare_records(expected, actual)
        assert not result.passed
        assert result.total_expected == 2
        assert result.total_actual == 1
