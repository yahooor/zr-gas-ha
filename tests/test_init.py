"""Tests for zr_gas.__init__ utility functions.

Tests the pure-logic helper functions extracted from the integration module:
- _calculate_monthly_stats
- _calculate_yearly_stats
- _calculate_tier_cycle_start (mocked dt_util)
- _calculate_annual_usage
"""

import importlib
from datetime import datetime
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from zr_gas.models import TierConfig, ZrGasBill, MonthlyStat

# Import the __init__ module — HA mocks are set up in conftest.py
import zr_gas
importlib.reload(zr_gas)

_calculate_monthly_stats = zr_gas._calculate_monthly_stats
_calculate_yearly_stats = zr_gas._calculate_yearly_stats
_calculate_tier_cycle_start = zr_gas._calculate_tier_cycle_start
_calculate_annual_usage = zr_gas._calculate_annual_usage


# ── _calculate_monthly_stats ──────────────────────────────────────────


class TestCalculateMonthlyStats:

    def test_empty_list(self):
        result = _calculate_monthly_stats([])
        assert result == []

    def test_single_bill(self):
        bills = [ZrGasBill(period="202603", usage_volume=10.0, usage_amount=29.9, unit_price=2.99)]
        result = _calculate_monthly_stats(bills)
        assert len(result) == 1
        assert result[0].month == "2026-03"
        assert result[0].gas_num == 10.0
        assert result[0].gas_cost == 29.9

    def test_multiple_bills_same_month(self):
        """Multiple bills in the same month should be aggregated."""
        bills = [
            ZrGasBill(period="202603", usage_volume=10.0, usage_amount=29.9, unit_price=2.99),
            ZrGasBill(period="202603", usage_volume=5.0, usage_amount=17.2, unit_price=3.44),
        ]
        result = _calculate_monthly_stats(bills)
        assert len(result) == 1
        assert result[0].month == "2026-03"
        assert result[0].gas_num == 15.0
        assert result[0].gas_cost == pytest.approx(47.1)

    def test_multiple_months_sorted(self):
        """Results should be sorted by month."""
        bills = [
            ZrGasBill(period="202605", usage_volume=20.0, usage_amount=60.0, unit_price=3.0),
            ZrGasBill(period="202603", usage_volume=10.0, usage_amount=30.0, unit_price=3.0),
            ZrGasBill(period="202604", usage_volume=15.0, usage_amount=45.0, unit_price=3.0),
        ]
        result = _calculate_monthly_stats(bills)
        assert len(result) == 3
        assert result[0].month == "2026-03"
        assert result[1].month == "2026-04"
        assert result[2].month == "2026-05"

    def test_invalid_period_skipped(self):
        """Bills with invalid/short period should be skipped."""
        bills = [
            ZrGasBill(period="202603", usage_volume=10.0, usage_amount=30.0, unit_price=3.0),
            ZrGasBill(period="", usage_volume=5.0, usage_amount=15.0, unit_price=3.0),
            ZrGasBill(period="ABC", usage_volume=3.0, usage_amount=9.0, unit_price=3.0),
        ]
        result = _calculate_monthly_stats(bills)
        assert len(result) == 1
        assert result[0].month == "2026-03"

    def test_none_period_skipped(self):
        """Bill with None period should be skipped."""
        bills = [
            ZrGasBill(period="202603", usage_volume=10.0, usage_amount=30.0, unit_price=3.0),
            ZrGasBill(period=None, usage_volume=5.0, usage_amount=15.0, unit_price=3.0),
        ]
        result = _calculate_monthly_stats(bills)
        assert len(result) == 1


# ── _calculate_yearly_stats ──────────────────────────────────────────


class TestCalculateYearlyStats:

    def test_empty_list(self):
        result = _calculate_yearly_stats([])
        assert result == []

    def test_single_year(self):
        monthly = [
            MonthlyStat(month="2026-01", gas_num=20.0, gas_cost=60.0),
            MonthlyStat(month="2026-02", gas_num=15.0, gas_cost=45.0),
        ]
        result = _calculate_yearly_stats(monthly)
        assert len(result) == 1
        assert result[0].year == "2026"
        assert result[0].gas_num == 35.0
        assert result[0].gas_cost == 105.0

    def test_multiple_years(self):
        monthly = [
            MonthlyStat(month="2025-12", gas_num=30.0, gas_cost=90.0),
            MonthlyStat(month="2026-01", gas_num=20.0, gas_cost=60.0),
        ]
        result = _calculate_yearly_stats(monthly)
        assert len(result) == 2
        assert result[0].year == "2025"
        assert result[0].gas_num == 30.0
        assert result[1].year == "2026"
        assert result[1].gas_num == 20.0


# ── _calculate_tier_cycle_start ──────────────────────────────────────


class TestCalculateTierCycleStart:

    def test_jan_1_mid_year(self):
        fake_now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("zr_gas.dt_util.now", return_value=fake_now):
            result = _calculate_tier_cycle_start("01-01")
            assert result == "2026-01-01"

    def test_jan_1_early_jan(self):
        fake_now = datetime(2026, 1, 1, 0, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("zr_gas.dt_util.now", return_value=fake_now):
            result = _calculate_tier_cycle_start("01-01")
            assert result == "2026-01-01"

    def test_jul_1_before_jul(self):
        fake_now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("zr_gas.dt_util.now", return_value=fake_now):
            result = _calculate_tier_cycle_start("07-01")
            assert result == "2025-07-01"

    def test_jul_1_after_jul(self):
        fake_now = datetime(2026, 9, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("zr_gas.dt_util.now", return_value=fake_now):
            result = _calculate_tier_cycle_start("07-01")
            assert result == "2026-07-01"

    def test_dec_31(self):
        fake_now = datetime(2026, 1, 5, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("zr_gas.dt_util.now", return_value=fake_now):
            result = _calculate_tier_cycle_start("12-31")
            assert result == "2025-12-31"

    def test_dec_31_in_dec(self):
        fake_now = datetime(2026, 12, 31, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("zr_gas.dt_util.now", return_value=fake_now):
            result = _calculate_tier_cycle_start("12-31")
            assert result == "2026-12-31"

    def test_invalid_format_fallback(self):
        fake_now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("zr_gas.dt_util.now", return_value=fake_now):
            result = _calculate_tier_cycle_start("invalid")
            assert result == "2026-01-01"

    def test_empty_string_fallback(self):
        fake_now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("zr_gas.dt_util.now", return_value=fake_now):
            result = _calculate_tier_cycle_start("")
            assert result == "2026-01-01"

    def test_invalid_date_fallback(self):
        """Invalid date like 02-30 should fall back to Jan 1."""
        fake_now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("zr_gas.dt_util.now", return_value=fake_now):
            result = _calculate_tier_cycle_start("02-30")
            assert result == "2026-01-01"


# ── _calculate_annual_usage ──────────────────────────────────────────


class TestCalculateAnnualUsage:

    def test_basic_accumulation(self):
        monthly = [
            MonthlyStat(month="2026-01", gas_num=50.0, gas_cost=149.5),
            MonthlyStat(month="2026-02", gas_num=30.0, gas_cost=89.7),
            MonthlyStat(month="2026-03", gas_num=20.0, gas_cost=59.8),
        ]
        tier_config = TierConfig(tier_cycle_start_md="01-01")
        fake_now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("zr_gas.dt_util.now", return_value=fake_now):
            annual_usage, tier_num, tier_price, cycle_start = _calculate_annual_usage(monthly, tier_config)

        assert annual_usage == pytest.approx(100.0)
        assert tier_num == 1
        assert tier_price == 2.99
        assert cycle_start == "2026-01-01"

    def test_empty_monthly_stats(self):
        tier_config = TierConfig(tier_cycle_start_md="01-01")
        fake_now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("zr_gas.dt_util.now", return_value=fake_now):
            annual_usage, tier_num, tier_price, cycle_start = _calculate_annual_usage([], tier_config)

        assert annual_usage == 0.0
        assert tier_num == 1
        assert tier_price == 2.99
        assert cycle_start == "2026-01-01"

    def test_cross_year_boundary(self):
        """Cycle starts mid-year, so should include months from previous year."""
        monthly = [
            MonthlyStat(month="2025-06", gas_num=40.0, gas_cost=120.0),
            MonthlyStat(month="2025-07", gas_num=30.0, gas_cost=103.2),
            MonthlyStat(month="2025-12", gas_num=50.0, gas_cost=172.0),
            MonthlyStat(month="2026-01", gas_num=20.0, gas_cost=68.8),
        ]
        tier_config = TierConfig(tier_cycle_start_md="07-01")
        fake_now = datetime(2026, 3, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("zr_gas.dt_util.now", return_value=fake_now):
            annual_usage, tier_num, tier_price, cycle_start = _calculate_annual_usage(monthly, tier_config)

        assert annual_usage == pytest.approx(100.0)  # 30+50+20, excludes 2025-06
        assert tier_num == 1
        assert cycle_start == "2025-07-01"
