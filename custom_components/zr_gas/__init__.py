"""The 中燃在线 (ZR Gas) integration for Home Assistant.

This integration monitors gas account balance and usage through the
ZR Gas (中燃在线) cloud API. It creates sensor entities for each
bound gas customer account.

Setup flow:
  1. User provides accessToken (obtained from WeChat mini-program)
  2. Integration validates token and discovers bound accounts
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
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import ZrGasAPI, ZrGasApiError, ZrGasAuthError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BALANCE_THRESHOLD,
    CONF_UPDATE_INTERVAL,
    CONF_USER_ID,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .models import ZrGasBill, ZrGasDeviceData

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.SENSOR]


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
    customers = entry.data.get("customers", [])
    update_interval_seconds = entry.options.get(
        CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
    )

    # Use HA's shared aiohttp session (avoids resource leaks)
    session = async_get_clientsession(hass)

    # Create API client
    api = ZrGasAPI(session, access_token, user_id=user_id)

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

    Attributes:
        cust_code: Customer code for this account.
        cust_name: Customer name for this account.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        api: ZrGasAPI,
        cust_code: str,
        cust_name: str,
        update_interval_seconds: int,
    ) -> None:
        """Initialize the coordinator.

        Args:
            hass: Home Assistant instance.
            api: ZrGasAPI client instance.
            cust_code: Customer code.
            cust_name: Customer name.
            update_interval_seconds: Refresh interval in seconds.
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
            now = datetime.now()
            current_period = now.strftime("%Y%m")
            start_period = f"{now.year - 1}{now.strftime('%m')}"

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
                latest_bill = bill_list[-1]
                monthly_usage = latest_bill.usage_volume
                monthly_cost = latest_bill.usage_amount
                period = latest_bill.period
                unit_price = latest_bill.unit_price

            return ZrGasDeviceData(
                balance=detail.balance,
                cust_code=detail.cust_code,
                cust_name=detail.cust_name,
                cust_address=detail.cust_address,
                monthly_usage=monthly_usage,
                monthly_cost=monthly_cost,
                period=period,
                unit_price=unit_price,
            )

        except ConfigEntryAuthFailed:
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
