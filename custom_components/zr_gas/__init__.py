"""The 中燃在线 (ZR Gas) integration for Home Assistant.

This integration monitors gas account balance and usage through the
ZR Gas (中燃在线) cloud API. It creates sensor entities for each
bound gas customer account.

Setup flow:
  1. User logs in via SMS verification code (mobile + captcha + SMS code)
  2. Integration discovers bound gas customer accounts
  3. For each account, a DataUpdateCoordinator is created
  4. Sensor platform is forwarded for entity creation
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)
import homeassistant.util.dt as dt_util

from .api import ZrGasAPI, ZrGasApiError, ZrGasAuthError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BALANCE_THRESHOLD,
    CONF_BILL_YEARS,
    CONF_CUSTOMERS,
    CONF_TIER_1_PRICE,
    CONF_TIER_2_PRICE,
    CONF_TIER_2_START,
    CONF_TIER_3_PRICE,
    CONF_TIER_3_START,
    CONF_TIER_CYCLE_START,
    CONF_UPDATE_INTERVAL,
    CONF_USER_ID,
    CONF_X_MAS_APP_INFO,
    DEFAULT_BALANCE_THRESHOLD,
    DEFAULT_BILL_YEARS,
    DEFAULT_TIER_1_PRICE,
    DEFAULT_TIER_2_PRICE,
    DEFAULT_TIER_2_START,
    DEFAULT_TIER_3_PRICE,
    DEFAULT_TIER_3_START,
    DEFAULT_TIER_CYCLE_START,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .models import (
    MonthlyStat,
    TierConfig,
    YearlyStat,
    ZrGasBill,
    ZrGasDeviceData,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR, Platform.BUTTON]


def _build_tier_config(options: dict[str, Any]) -> TierConfig:
    """从 Options 构建 TierConfig 实例。"""
    return TierConfig(
        tier_2_start=float(options.get(CONF_TIER_2_START, DEFAULT_TIER_2_START)),
        tier_3_start=float(options.get(CONF_TIER_3_START, DEFAULT_TIER_3_START)),
        tier_1_price=float(options.get(CONF_TIER_1_PRICE, DEFAULT_TIER_1_PRICE)),
        tier_2_price=float(options.get(CONF_TIER_2_PRICE, DEFAULT_TIER_2_PRICE)),
        tier_3_price=float(options.get(CONF_TIER_3_PRICE, DEFAULT_TIER_3_PRICE)),
        tier_cycle_start_md=options.get(
            CONF_TIER_CYCLE_START, DEFAULT_TIER_CYCLE_START
        ),
    )


def _calculate_monthly_stats(bills: list[ZrGasBill]) -> list[MonthlyStat]:
    """从账单列表计算自然月统计。

    将同月的账单汇总为一条 MonthlyStat。
    API 返回的 period 格式为 YYYYMM。

    Args:
        bills: 全部账单列表

    Returns:
        按月汇总的统计列表
    """
    month_map: dict[str, MonthlyStat] = {}
    for bill in bills:
        if not bill.period or len(bill.period) < 6:
            continue
        # 格式化为 YYYY-MM
        month_key = f"{bill.period[:4]}-{bill.period[4:6]}"
        if month_key not in month_map:
            month_map[month_key] = MonthlyStat(
                month=month_key, gas_num=0.0, gas_cost=0.0
            )
        month_map[month_key].gas_num += bill.usage_volume
        month_map[month_key].gas_cost += bill.usage_amount

    result = sorted(month_map.values(), key=lambda m: m.month)
    return result


def _calculate_yearly_stats(monthly_stats: list[MonthlyStat]) -> list[YearlyStat]:
    """从月度统计汇总年度统计。

    Args:
        monthly_stats: 月度统计列表

    Returns:
        按年汇总的统计列表
    """
    year_map: dict[str, YearlyStat] = {}
    for ms in monthly_stats:
        year_key = ms.month[:4]
        if year_key not in year_map:
            year_map[year_key] = YearlyStat(
                year=year_key, gas_num=0.0, gas_cost=0.0
            )
        year_map[year_key].gas_num += ms.gas_num
        year_map[year_key].gas_cost += ms.gas_cost

    return sorted(year_map.values(), key=lambda y: y.year)


def _calculate_tier_cycle_start(tier_cycle_start_md: str) -> str:
    """根据阶梯周期起始月日计算当前周期的起始日期。

    例如 tier_cycle_start_md="01-01" → 当前周期从今年1月1日起
    例如 tier_cycle_start_md="12-31" → 当前周期从去年12月31日起

    Args:
        tier_cycle_start_md: 阶梯周期起始月日，格式 MM-DD

    Returns:
        当前阶梯周期起始日 YYYY-MM-DD
    """
    now = dt_util.now()
    try:
        sm = int(tier_cycle_start_md[:2])
        sd = int(tier_cycle_start_md[3:5])
    except (ValueError, IndexError):
        sm, sd = 1, 1

    # 构建今年的周期起始日
    try:
        md_this_year = datetime(now.year, sm, sd, tzinfo=dt_util.DEFAULT_TIME_ZONE)
    except ValueError:
        md_this_year = datetime(now.year, 1, 1, tzinfo=dt_util.DEFAULT_TIME_ZONE)

    if now >= md_this_year:
        return md_this_year.strftime("%Y-%m-%d")
    else:
        return datetime(now.year - 1, sm, sd, tzinfo=dt_util.DEFAULT_TIME_ZONE).strftime(
            "%Y-%m-%d"
        )


def _calculate_annual_usage(
    monthly_stats: list[MonthlyStat],
    tier_config: TierConfig,
) -> tuple[float, int, float, str]:
    """计算当前阶梯周期的累计用气量。

    从阶梯周期起始月份开始累加月度用量。

    Args:
        monthly_stats: 月度统计列表
        tier_config: 阶梯气价配置

    Returns:
        (annual_usage, current_tier, current_tier_price, cycle_start)
    """
    cycle_start = _calculate_tier_cycle_start(tier_config.tier_cycle_start_md)
    cycle_year = int(cycle_start[:4])
    cycle_month = int(cycle_start[5:7])

    annual_usage = 0.0
    for ms in monthly_stats:
        try:
            ms_year = int(ms.month[:4])
            ms_month = int(ms.month[5:7])
        except (ValueError, IndexError):
            continue
        # 判断是否在当前阶梯周期内
        # 简单规则：从周期起始月份开始累加
        ms_val = ms_year * 12 + ms_month
        cycle_val = cycle_year * 12 + cycle_month
        if ms_val >= cycle_val:
            annual_usage += ms.gas_num

    tier_num, tier_price, _remaining = tier_config.get_tier_info(annual_usage)
    return annual_usage, tier_num, tier_price, cycle_start


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up 中燃在线 from a config entry.

    Creates an API client using HA's shared aiohttp session,
    initializes coordinators for each bound gas account, and
    forwards setup to the sensor platform.

    Args:
        hass: Home Assistant instance.
        entry: Config entry with access token and account info.

    Returns:
        True if setup was successful.
    """
    hass.data.setdefault(DOMAIN, {})

    access_token = entry.data[CONF_ACCESS_TOKEN]
    user_id = entry.data.get(CONF_USER_ID, "")
    x_mas_app_info = entry.data.get(CONF_X_MAS_APP_INFO, "")
    customers = entry.data.get(CONF_CUSTOMERS, [])
    update_interval_seconds = entry.options.get(
        CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
    )
    tier_config = _build_tier_config(entry.options)
    bill_years = entry.options.get(CONF_BILL_YEARS, DEFAULT_BILL_YEARS)
    balance_threshold = entry.options.get(
        CONF_BALANCE_THRESHOLD, DEFAULT_BALANCE_THRESHOLD
    )

    # Use HA's shared aiohttp session (avoids resource leaks)
    session = async_get_clientsession(hass)

    # Create API client
    api = ZrGasAPI(
        session,
        access_token=access_token,
        user_id=user_id,
        x_mas_app_info=x_mas_app_info,
    )

    # Create a coordinator for each customer account
    coordinators: dict[str, ZrGasDataUpdateCoordinator] = {}

    for customer in customers:
        cust_code = customer.get("cust_code", "")
        cust_name = customer.get("cust_name", "")

        coordinator = ZrGasDataUpdateCoordinator(
            hass=hass,
            api=api,
            cust_code=cust_code,
            cust_name=cust_name,
            update_interval_seconds=update_interval_seconds,
            tier_config=tier_config,
            bill_years=bill_years,
            balance_threshold=balance_threshold,
        )

        # First refresh with error tolerance
        try:
            await coordinator.async_config_entry_first_refresh()
        except (UpdateFailed, ConfigEntryAuthFailed):
            _LOGGER.warning(
                "Initial data fetch failed for %s, will retry on schedule",
                cust_code,
            )
            # Don't fail setup — coordinator will retry on its schedule

        coordinators[cust_code] = coordinator

    # Store coordinators in hass.data (session is managed by HA)
    hass.data[DOMAIN][entry.entry_id] = {
        "api": api,
        "coordinators": coordinators,
    }

    # Forward to sensor platform
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a 中燃在线 config entry.

    Args:
        hass: Home Assistant instance.
        entry: Config entry to unload.

    Returns:
        True if unload was successful.
    """
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload a config entry when options change.

    Args:
        hass: Home Assistant instance.
        entry: Config entry to reload.
    """
    await hass.config_entries.async_reload(entry.entry_id)


class ZrGasDataUpdateCoordinator(DataUpdateCoordinator[ZrGasDeviceData]):
    """Coordinator to fetch and manage data for a single gas customer account.

    Each bound gas customer gets its own coordinator instance that
    periodically fetches account info and billing data from the API.

    Features (inspired by reference integrations):
    - Parallel data fetching with asyncio.gather
    - Preserves old data on error (avoids sensor state loss)
    - Proper auth error handling for reauth flow
    - Tiered gas pricing calculation
    - Monthly/yearly statistics aggregation

    Attributes:
        cust_code: Customer code for this account.
        cust_name: Customer name for this account.
        tier_config: Tiered gas pricing configuration.
        bill_years: Number of years to query bills.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: ZrGasAPI,
        cust_code: str,
        cust_name: str,
        update_interval_seconds: int,
        tier_config: TierConfig,
        bill_years: int = DEFAULT_BILL_YEARS,
        balance_threshold: float = DEFAULT_BALANCE_THRESHOLD,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance.
            api: ZrGasAPI client instance.
            cust_code: Customer code.
            cust_name: Customer name.
            update_interval_seconds: Refresh interval in seconds.
            tier_config: Tiered gas pricing configuration.
            bill_years: Number of years to query bills.
            balance_threshold: Balance alert threshold in CNY.
        """
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"ZR Gas {cust_name} ({cust_code})",
            update_interval=timedelta(seconds=update_interval_seconds),
        )
        self._api = api
        self.cust_code = cust_code
        self.cust_name = cust_name
        self.tier_config = tier_config
        self.bill_years = bill_years
        self.balance_threshold = balance_threshold

    async def _async_update_data(self) -> ZrGasDeviceData:
        """Fetch data from the ZR Gas API.

        Uses asyncio.gather for parallel data fetching (inspired by
        ha_hfcrgas/sycfgas). On error, preserves previous data to
        avoid sensor state loss.

        Returns:
            Aggregated device data for sensor updates.

        Raises:
            ConfigEntryAuthFailed: If the access token has expired.
            UpdateFailed: If the API call fails for other reasons.
        """
        try:
            # Parallel data fetching for better performance
            now = dt_util.now()
            current_period = now.strftime("%Y%m")
            # 可配置的账单查询范围
            start_year = now.year - self.bill_years
            start_period = f"{start_year}{now.strftime('%m')}"

            detail_task = self._api.get_cust_info(
                self.cust_code, self.cust_name
            )
            bills_task = self._api.get_customer_money_list(
                self.cust_code, start_period, current_period
            )

            detail, bills = await asyncio.gather(
                detail_task, bills_task, return_exceptions=True
            )

            # Handle exceptions from parallel tasks
            if isinstance(detail, ZrGasAuthError):
                raise ConfigEntryAuthFailed(
                    f"Authentication failed for {self.cust_name}: {detail}"
                ) from detail
            if isinstance(detail, Exception):
                raise UpdateFailed(
                    f"Error fetching detail for {self.cust_name}: {detail}"
                ) from detail
            if isinstance(bills, ZrGasAuthError):
                raise ConfigEntryAuthFailed(
                    f"Authentication failed for {self.cust_name}: {bills}"
                ) from bills
            if isinstance(bills, Exception):
                _LOGGER.warning(
                    "Failed to fetch bills for %s: %s", self.cust_name, bills
                )
                bills = []

            # Find the most recent bill for monthly usage/cost
            monthly_usage = 0.0
            monthly_cost = 0.0
            period = current_period
            unit_price = 0.0

            bill_list: list[ZrGasBill] = bills if isinstance(bills, list) else []
            if bill_list:
                bill_list.sort(key=lambda b: b.period)
                # Try to find the bill matching the current period first
                current_bill = None
                for bill in bill_list:
                    if bill.period == current_period:
                        current_bill = bill
                        break
                # Fallback to the last bill if no exact period match
                matched_bill = current_bill or bill_list[-1]
                monthly_usage = matched_bill.usage_volume
                monthly_cost = matched_bill.usage_amount
                period = matched_bill.period
                unit_price = matched_bill.unit_price

            # ── 统计计算 ──────────────────────────────────────
            monthly_stats = _calculate_monthly_stats(bill_list)
            yearly_stats = _calculate_yearly_stats(monthly_stats)

            # ── 阶梯气价计算 ──────────────────────────────────
            annual_usage, current_tier, current_tier_price, tier_cycle_start = (
                _calculate_annual_usage(monthly_stats, self.tier_config)
            )

            return ZrGasDeviceData(
                balance=detail.balance,
                cust_code=detail.cust_code,
                cust_name=detail.cust_name,
                cust_address=detail.cust_address,
                monthly_usage=monthly_usage,
                monthly_cost=monthly_cost,
                period=period,
                unit_price=unit_price,
                owe_money=detail.owe_money,
                last_record=detail.last_record,
                qty_meter_balance=detail.qty_meter_balance,
                purch_times=detail.purch_times,
                last_record_time=detail.last_record_time,
                meter_no=detail.meter_no,
                meter_form_name=detail.meter_form_name,
                card_no=detail.card_no,
                comp_name=detail.comp_name,
                cust_status=detail.cust_status,
                fee=detail.fee,
                annual_usage=annual_usage,
                current_tier=current_tier,
                current_tier_price=current_tier_price,
                tier_cycle_start=tier_cycle_start,
                monthly_stats=monthly_stats,
                yearly_stats=yearly_stats,
            )

        except ConfigEntryAuthFailed:
            # Notify user about expired token via HA repairs/notifications
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                f"token_expired_{self.cust_code}",
                is_fixable=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key="token_expired",
                translation_placeholders={
                    "cust_name": self.cust_name,
                },
            )
            raise
        except UpdateFailed:
            raise
        except ZrGasAuthError as err:
            raise ConfigEntryAuthFailed(
                f"Authentication failed for {self.cust_name}: {err}"
            ) from err
        except ZrGasApiError as err:
            raise UpdateFailed(
                f"Error fetching data for {self.cust_name}: {err}"
            ) from err
        except Exception as err:
            raise UpdateFailed(
                f"Unexpected error for {self.cust_name}: {err}"
            ) from err
        else:
            # Data fetched successfully — clear any previous token-expired issue
            ir.async_delete_issue(
                self.hass, DOMAIN, f"token_expired_{self.cust_code}"
            )

            # ── Balance threshold alert ────────────────────────
            if detail.balance < self.balance_threshold:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"balance_low_{self.cust_code}",
                    is_fixable=False,
                    severity=ir.IssueSeverity.WARNING,
                    translation_key="balance_low",
                    translation_placeholders={
                        "cust_name": self.cust_name,
                        "balance": f"{detail.balance:.2f}",
                        "threshold": f"{self.balance_threshold:.2f}",
                    },
                )
            else:
                ir.async_delete_issue(
                    self.hass, DOMAIN, f"balance_low_{self.cust_code}"
                )

            _LOGGER.debug(
                "Data updated for %s: balance=%.2f, usage=%.2f, cost=%.2f, "
                "annual=%.2f, tier=%d",
                self.cust_name,
                detail.balance,
                monthly_usage,
                monthly_cost,
                annual_usage,
                current_tier,
            )
