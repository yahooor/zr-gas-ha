"""Tests for zr_gas.models — TierConfig and dataclasses."""

import math

import pytest

from zr_gas.models import TierConfig, ZrGasBill, MonthlyStat, YearlyStat


# ── TierConfig.get_tier_info ──────────────────────────────────────────


class TestGetTierInfo:
    """Tests for TierConfig.get_tier_info(annual_usage)."""

    def test_tier1_zero_usage(self, tier_config_default):
        tier, price, remaining = tier_config_default.get_tier_info(0)
        assert tier == 1
        assert price == 2.99
        assert remaining == 400.0

    def test_tier1_near_boundary(self, tier_config_default):
        tier, price, remaining = tier_config_default.get_tier_info(399)
        assert tier == 1
        assert price == 2.99
        assert remaining == 1.0

    def test_tier2_at_boundary(self, tier_config_default):
        """annual_usage == tier_2_start should land in tier 2."""
        tier, price, remaining = tier_config_default.get_tier_info(400)
        assert tier == 2
        assert price == 3.44
        assert remaining == 1280.0

    def test_tier2_middle(self, tier_config_default):
        tier, price, remaining = tier_config_default.get_tier_info(1000)
        assert tier == 2
        assert price == 3.44
        assert remaining == 680.0

    def test_tier2_near_upper_boundary(self, tier_config_default):
        tier, price, remaining = tier_config_default.get_tier_info(1679)
        assert tier == 2
        assert price == 3.44
        assert remaining == 1.0

    def test_tier3_at_boundary(self, tier_config_default):
        """annual_usage == tier_3_start should land in tier 3."""
        tier, price, remaining = tier_config_default.get_tier_info(1680)
        assert tier == 3
        assert price == 4.34
        assert remaining == float("inf")

    def test_tier3_well_above(self, tier_config_default):
        tier, price, remaining = tier_config_default.get_tier_info(2000)
        assert tier == 3
        assert price == 4.34
        assert remaining == float("inf")

    def test_tier3_very_large_usage(self, tier_config_default):
        tier, price, remaining = tier_config_default.get_tier_info(99999)
        assert tier == 3
        assert price == 4.34
        assert remaining == float("inf")

    def test_custom_config(self, tier_config_custom):
        tier, price, remaining = tier_config_custom.get_tier_info(0)
        assert tier == 1
        assert price == 2.50
        assert remaining == 300.0

    def test_custom_config_tier2(self, tier_config_custom):
        tier, price, remaining = tier_config_custom.get_tier_info(300)
        assert tier == 2
        assert price == 3.00
        assert remaining == 900.0

    def test_custom_config_tier3(self, tier_config_custom):
        tier, price, remaining = tier_config_custom.get_tier_info(1200)
        assert tier == 3
        assert price == 4.00
        assert remaining == float("inf")

    def test_negative_usage_still_tier1(self, tier_config_default):
        """Negative usage should still return tier 1."""
        tier, price, remaining = tier_config_default.get_tier_info(-10)
        assert tier == 1
        assert price == 2.99
        assert remaining == 410.0


# ── TierConfig.calculate_usage_from_cost ───────────────────────────────


class TestCalculateUsageFromCost:
    """Tests for TierConfig.calculate_usage_from_cost(start_usage, cost)."""

    def test_single_tier_simple(self, tier_config_default):
        """Cost within tier 1 only."""
        # 100 CNY / 2.99 per m³
        usage = tier_config_default.calculate_usage_from_cost(0, 100)
        assert usage == pytest.approx(100 / 2.99, rel=1e-6)

    def test_single_tier_zero_start(self, tier_config_default):
        usage = tier_config_default.calculate_usage_from_cost(0, 2.99)
        assert usage == pytest.approx(1.0, rel=1e-6)

    def test_cross_one_tier_boundary(self, tier_config_default):
        """Start near tier 1 end, cost crosses into tier 2."""
        # start_usage=350 → tier 1, remaining=50m³, cost_to_finish=50*2.99=149.5
        # remaining_cost = 200 - 149.5 = 50.5
        # usage in tier 2 = 50.5 / 3.44 ≈ 14.68
        # total = 50 + 14.68 ≈ 64.68
        usage = tier_config_default.calculate_usage_from_cost(350, 200)
        expected_tier1_remaining = 400 - 350  # 50
        expected_cost_tier1 = expected_tier1_remaining * 2.99  # 149.5
        expected_remaining_cost = 200 - expected_cost_tier1  # 50.5
        expected_tier2_usage = expected_remaining_cost / 3.44
        expected_total = expected_tier1_remaining + expected_tier2_usage
        assert usage == pytest.approx(expected_total, rel=1e-4)

    def test_cross_two_tier_boundaries(self, tier_config_default):
        """Start near tier 2 end, cost crosses into tier 3."""
        # start_usage=1600 → tier 2, remaining=80m³
        # cost_to_finish_tier2 = 80 * 3.44 = 275.2
        # remaining_cost after tier 2 = 2000 - 275.2 = 1724.8
        # usage in tier 3 = 1724.8 / 4.34 ≈ 397.42
        # total = 80 + 397.42 ≈ 477.42
        usage = tier_config_default.calculate_usage_from_cost(1600, 2000)
        expected_tier2_remaining = 1680 - 1600  # 80
        expected_cost_tier2 = expected_tier2_remaining * 3.44  # 275.2
        expected_remaining_cost = 2000 - expected_cost_tier2  # 1724.8
        expected_tier3_usage = expected_remaining_cost / 4.34
        expected_total = expected_tier2_remaining + expected_tier3_usage
        assert usage == pytest.approx(expected_total, rel=1e-4)

    def test_zero_cost(self, tier_config_default):
        """Zero cost should return 0 usage."""
        usage = tier_config_default.calculate_usage_from_cost(100, 0)
        assert usage == pytest.approx(0.0, abs=1e-6)

    def test_very_small_cost(self, tier_config_default):
        """Very small cost should return approximately 0."""
        usage = tier_config_default.calculate_usage_from_cost(100, 0.001)
        # 0.001 < 0.001 threshold, so returns 0
        assert usage == pytest.approx(0.0, abs=1e-6)

    def test_negative_cost(self, tier_config_default):
        """Negative cost should return 0 usage."""
        usage = tier_config_default.calculate_usage_from_cost(100, -50)
        assert usage == pytest.approx(0.0, abs=1e-6)

    def test_exact_tier_boundary_cost(self, tier_config_default):
        """Cost exactly finishes tier 1."""
        # start=0, cost = 400 * 2.99 = 1196
        cost = 400 * 2.99
        usage = tier_config_default.calculate_usage_from_cost(0, cost)
        assert usage == pytest.approx(400.0, rel=1e-4)

    def test_start_in_tier2(self, tier_config_default):
        """Start usage already in tier 2."""
        usage = tier_config_default.calculate_usage_from_cost(500, 34.4)
        # tier 2 price = 3.44, 34.4 / 3.44 = 10 m³
        assert usage == pytest.approx(10.0, rel=1e-4)

    def test_start_in_tier3(self, tier_config_default):
        """Start usage already in tier 3."""
        usage = tier_config_default.calculate_usage_from_cost(2000, 43.4)
        # tier 3 price = 4.34, 43.4 / 4.34 = 10 m³
        assert usage == pytest.approx(10.0, rel=1e-4)


# ── Dataclass construction ────────────────────────────────────────────


class TestDataclasses:
    """Basic construction tests for data models."""

    def test_zr_gas_bill(self):
        bill = ZrGasBill(period="202603", usage_volume=15.5, usage_amount=46.35, unit_price=2.99)
        assert bill.period == "202603"
        assert bill.usage_volume == 15.5

    def test_monthly_stat(self):
        ms = MonthlyStat(month="2026-03", gas_num=15.5, gas_cost=46.35)
        assert ms.month == "2026-03"

    def test_yearly_stat(self):
        ys = YearlyStat(year="2026", gas_num=186.0, gas_cost=556.14)
        assert ys.year == "2026"
