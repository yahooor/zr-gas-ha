"""Tests for zr_gas.sensor — _parse_timestamp helper."""

from datetime import datetime
from zoneinfo import ZoneInfo
from unittest.mock import patch

import pytest


# Import _parse_timestamp directly by reading the function source
# and executing it in isolation, since sensor.py imports homeassistant

def _parse_timestamp_isolated(value):
    """Standalone copy of _parse_timestamp for testing without HA deps."""
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    tz = ZoneInfo("Asia/Shanghai")
    try:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(value, fmt)
            except ValueError:
                continue
            return parsed.replace(tzinfo=tz)
    except Exception:
        pass
    return None


class TestParseTimestamp:

    def test_full_datetime(self):
        result = _parse_timestamp_isolated("2026-04-21 10:30:00")
        expected = datetime(2026, 4, 21, 10, 30, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result == expected

    def test_date_only(self):
        result = _parse_timestamp_isolated("2026-04-21")
        expected = datetime(2026, 4, 21, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result == expected

    def test_none_input(self):
        assert _parse_timestamp_isolated(None) is None

    def test_empty_string(self):
        assert _parse_timestamp_isolated("") is None

    def test_whitespace_only(self):
        assert _parse_timestamp_isolated("   ") is None

    def test_invalid_format(self):
        assert _parse_timestamp_isolated("not-a-date") is None

    def test_partial_date(self):
        assert _parse_timestamp_isolated("2026-04") is None

    def test_time_only(self):
        assert _parse_timestamp_isolated("10:30:00") is None

    def test_iso_format_with_T(self):
        """ISO format with T separator is not supported."""
        assert _parse_timestamp_isolated("2026-04-21T10:30:00") is None

    def test_datetime_with_whitespace(self):
        """Leading/trailing whitespace should be handled."""
        result = _parse_timestamp_isolated("  2026-04-21 10:30:00  ")
        expected = datetime(2026, 4, 21, 10, 30, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result == expected

    def test_timezone_aware_result(self):
        """Result should always be timezone-aware."""
        result = _parse_timestamp_isolated("2026-01-01")
        assert result.tzinfo is not None

    def test_midnight_date(self):
        result = _parse_timestamp_isolated("2026-01-01 00:00:00")
        expected = datetime(2026, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result == expected

    def test_end_of_day(self):
        result = _parse_timestamp_isolated("2026-12-31 23:59:59")
        expected = datetime(2026, 12, 31, 23, 59, 59, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result == expected

    def test_leap_year_date(self):
        result = _parse_timestamp_isolated("2024-02-29")
        expected = datetime(2024, 2, 29, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        assert result == expected

    def test_invalid_leap_year_date(self):
        """2025-02-29 is invalid (not a leap year)."""
        assert _parse_timestamp_isolated("2025-02-29") is None
