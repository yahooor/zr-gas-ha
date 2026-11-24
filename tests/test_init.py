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

# Import the __init__ module — HA mocks are set up in conftest.py
import zr_gas
from zr_gas.models import MonthlyStat, TierConfig, ZrGasBill

importlib.reload(zr_gas)

_calculate_monthly_stats = zr_gas._calculate_monthly_stats
_calculate_yearly_stats = zr_gas._calculate_yearly_stats
_calculate_tier_cycle_start = zr_gas._calculate_tier_cycle_start
_calculate_annual_usage = zr_gas._calculate_annual_usage
_pick_bills = zr_gas._pick_bills


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
            summary = _calculate_annual_usage(monthly, tier_config)
            annual_usage, tier_num, tier_price, cycle_start = (
                summary.usage,
                summary.tier,
                summary.tier_price,
                summary.cycle_start,
            )

        assert annual_usage == pytest.approx(100.0)
        assert tier_num == 1
        assert tier_price == 2.99
        assert cycle_start == "2026-01-01"

    def test_empty_monthly_stats(self):
        tier_config = TierConfig(tier_cycle_start_md="01-01")
        fake_now = datetime(2026, 6, 15, 12, 0, 0, tzinfo=ZoneInfo("Asia/Shanghai"))
        with patch("zr_gas.dt_util.now", return_value=fake_now):
            summary = _calculate_annual_usage([], tier_config)
            annual_usage, tier_num, tier_price, cycle_start = (
                summary.usage,
                summary.tier,
                summary.tier_price,
                summary.cycle_start,
            )

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
            summary = _calculate_annual_usage(monthly, tier_config)
            annual_usage, tier_num, cycle_start = (summary.usage, summary.tier, summary.cycle_start)

        assert annual_usage == pytest.approx(100.0)  # 30+50+20, excludes 2025-06
        assert tier_num == 1
        assert cycle_start == "2025-07-01"


# ── build_api_client（双数据源客户端工厂） ────────────────────────────


class TestBuildApiClient:
    """build_api_client must map source → correct API client class."""

    def test_mp_source(self):
        from zr_gas import build_api_client
        from zr_gas.api import ZrGasMpApi

        api = build_api_client(None, "mp", "tok", "uid", "mas")
        assert isinstance(api, ZrGasMpApi)
        assert api.access_token == "tok"
        assert api.x_mas_app_info == "mas"

    def test_pay_source(self):
        from zr_gas import build_api_client
        from zr_gas.api import ZrGasPayApi

        api = build_api_client(None, "pay", "tok", "uid", "mas")
        assert isinstance(api, ZrGasPayApi)
        assert api.access_token == "tok"
        assert api.x_mas_app_info == ""  # 缴费端不使用 x-mas-app-info

    def test_legacy_entry_without_source_defaults_to_mp(self):
        """旧版配置条目没有 source 字段 → 默认在线端（向后兼容）."""
        from zr_gas import build_api_client
        from zr_gas.api import ZrGasMpApi

        api = build_api_client(None, "mp", "tok", "uid")
        assert isinstance(api, ZrGasMpApi)


# ── v2.1.0: tier_remaining（阶梯剩余额度） ────────────────────────────


class TestTierRemaining:
    def test_remaining_in_tier_1(self):
        monthly = [MonthlyStat(month="2026-05", gas_num=193.0, gas_cost=801.04)]
        cfg = TierConfig()
        summary = _calculate_annual_usage(monthly, cfg)
        usage, tier, remaining = summary.usage, summary.tier, summary.remaining
        assert usage == (193.0 if tier == 1 else 2000.0)
        assert tier == 1
        assert remaining == pytest.approx(400 - 193)

    def test_remaining_zero_in_top_tier(self):
        monthly = [MonthlyStat(month="2026-05", gas_num=2000.0, gas_cost=8000.0)]
        cfg = TierConfig()
        summary = _calculate_annual_usage(monthly, cfg)
        usage, tier, remaining = summary.usage, summary.tier, summary.remaining
        assert usage == (193.0 if tier == 1 else 2000.0)
        assert tier == 3
        assert remaining == float("inf")


# ── v2.2.0: _pick_bills（当前/上一账单）与 AnnualSummary 费用 ──────────


class TestPickBills:
    def _b(self, period, qty, amount):
        return ZrGasBill(period=period, usage_volume=qty, usage_amount=amount, unit_price=2.99)

    def test_current_period_matched(self):
        bills = [
            self._b("202605", 49, 201.39),
            self._b("202610", 10, 30),
            self._b("202608", 73, 300.03),
        ]
        matched, prev = _pick_bills(bills, "202610")
        assert matched.usage_volume == 10
        assert prev.period == "202608"

    def test_fallback_to_latest(self):
        bills = [self._b("202605", 49, 201.39), self._b("202608", 73, 300.03)]
        matched, prev = _pick_bills(bills, "202610")  # 当前月无账单
        assert matched.usage_volume == 73
        assert prev.usage_volume == 49
        assert prev.period == "202605"

    def test_pick_periods_aggregates_rows_and_excludes_non_previous_month(self):
        bills = [
            self._b("204103", 8, 26),
            self._b("204103", 3, 11),
            self._b("204108", 1, 3),
            self._b("204108", 9, 27),
            self._b("204112", 90, 900),
        ]
        matched, prev = _pick_bills(bills, "204108")
        assert (matched.period, matched.usage_volume, matched.usage_amount) == ("204108", 10, 30)
        assert (prev.period, prev.usage_volume, prev.usage_amount) == ("204103", 11, 37)
        latest, _ = _pick_bills(bills, "204109")
        assert latest.period == "204108"

    def test_eighteen_rows_seventeen_periods_previous_is_august(self):
        periods = [f"2040{month:02d}" for month in range(1, 13)]
        periods.extend(["204101", "204102", "204105", "204108", "204111"])
        bills = [self._b(period, 1, 3) for period in periods]
        bills.append(self._b("204111", 2, 6))
        assert len(bills) == 18 and len({bill.period for bill in bills}) == 17
        matched, previous = _pick_bills(bills, "204111")
        assert matched.period == "204111" and matched.usage_volume == 3
        assert previous.period == "204108" and previous.usage_volume == 1

    def test_single_bill_no_previous(self):
        matched, prev = _pick_bills([self._b("202608", 73, 300.03)], "202610")
        assert matched.usage_volume == 73
        assert prev is None

    def test_empty(self):
        assert _pick_bills([], "202610") == (None, None)


class TestAnnualSummaryCost:
    def test_cost_summed_within_cycle(self):
        monthly = [
            MonthlyStat(month="2025-12", gas_num=30.0, gas_cost=90.0),  # 上周期，不计
            MonthlyStat(month="2026-05", gas_num=49.0, gas_cost=201.39),
            MonthlyStat(month="2026-08", gas_num=73.0, gas_cost=300.03),
        ]
        summary = _calculate_annual_usage(monthly, TierConfig())
        assert summary.usage == pytest.approx(122.0)
        assert summary.cost == pytest.approx(501.42)
        assert summary.tier == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "snapshot_error", [None, TimeoutError(), zr_gas.ZrGasApiError("unavailable")]
)
@pytest.mark.parametrize("api_price", [None, 0])
async def test_coordinator_real_refresh_snapshot_failure_never_uses_crm(snapshot_error, api_price):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from zr_gas.models import ZrGasCustomerDetail, ZrGasMeterSnapshot, ZrGasPayment

    as_of = datetime(2041, 2, 12, 4, 5, 6, tzinfo=ZoneInfo("Asia/Shanghai"))
    api = SimpleNamespace(
        get_cust_info=AsyncMock(
            return_value=ZrGasCustomerDetail(
                "C01",
                "Example",
                "",
                0,
                qty_meter_balance=1249,
                last_record_time="2040-12-01",
                gas_price=api_price,
            )
        ),
        get_customer_money_list=AsyncMock(
            return_value=[
                ZrGasBill("204103", 3, 9, None),
                ZrGasBill("204108", 8, 24, None),
                ZrGasBill("204108", 2, 6, None),
            ]
        ),
        get_meter_info=AsyncMock(return_value=None),
        get_payment_log=AsyncMock(return_value=[ZrGasPayment(amount=0, qty=None)]),
        get_meter_snapshot=AsyncMock(
            return_value=ZrGasMeterSnapshot(39.42, as_of), side_effect=snapshot_error
        ),
    )
    coordinator = zr_gas.ZrGasDataUpdateCoordinator(
        SimpleNamespace(),
        api,
        "mp",
        "C01",
        "Example",
        21600,
        TierConfig(),
    )
    with patch("zr_gas.dt_util.now", return_value=datetime(2041, 11, 24, tzinfo=as_of.tzinfo)):
        data = await coordinator._async_update_data()
    assert data.monthly_usage == 10 and data.last_month_usage == 3
    assert data.period == "204108" and data.last_bill_period == "204103"
    assert data.gas_price == (3 if api_price is None else 0)
    assert data.price_source == ("derived" if api_price is None else "api")
    assert data.last_payment == 0 and data.payment_history[0].qty is None
    if snapshot_error:
        assert data.meter_snapshot is None
    else:
        assert data.meter_snapshot.volume == 39.42
        assert data.meter_snapshot.as_of == as_of


@pytest.mark.asyncio
async def test_partial_history_marks_derived_values_untrusted():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from zr_gas.models import ZrGasBillHistory, ZrGasCustomerDetail, is_bill_derived_unavailable

    api = SimpleNamespace(
        get_cust_info=AsyncMock(return_value=ZrGasCustomerDetail("C01", "Example", "", None)),
        get_customer_money_list=AsyncMock(
            return_value=ZrGasBillHistory(
                [
                    ZrGasBill("204103", 3, 9, 3),
                ],
                {2040},
            )
        ),
        get_meter_info=AsyncMock(return_value=None),
        get_payment_log=AsyncMock(return_value=[]),
        get_meter_snapshot=AsyncMock(return_value=None),
    )
    coordinator = zr_gas.ZrGasDataUpdateCoordinator(
        SimpleNamespace(),
        api,
        "mp",
        "C01",
        "Example",
        21600,
        TierConfig(),
    )
    with patch(
        "zr_gas.dt_util.now", return_value=datetime(2041, 11, 24, tzinfo=ZoneInfo("Asia/Shanghai"))
    ):
        data = await coordinator._async_update_data()
    assert data.bills_degraded is True and data.bill_missing_years == (2040,)
    assert data.price_source == "" and data.gas_price is None
    for key in (
        "monthly_usage",
        "last_month_usage",
        "annual_usage",
        "annual_cost",
        "tier_remaining",
    ):
        assert is_bill_derived_unavailable(data, key)
