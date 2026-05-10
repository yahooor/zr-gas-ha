"""Diagnostics support for the 中燃在线 (ZR Gas) integration.

Provides diagnostic data export for troubleshooting via HA's
device diagnostics feature (Settings > Devices > ⋮ > Download diagnostics).
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from . import ZrGasDataUpdateCoordinator
from .const import CONF_ACCESS_TOKEN, CONF_USER_ID, DOMAIN


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: dict[str, Any]
) -> dict[str, Any]:
    """Return diagnostics for a device.

    Exports configuration (with sensitive fields masked), coordinator
    data, and last update status for troubleshooting.

    Args:
        hass: Home Assistant instance.
        entry: Config entry associated with the device.
        device: Device registry entry.

    Returns:
        Diagnostic data dict.
    """
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    coordinators: dict[str, ZrGasDataUpdateCoordinator] = entry_data.get(
        "coordinators", {}
    )

    # Find the coordinator matching this device
    device_id = list(device.get("identifiers", set()))[0][1] if device.get("identifiers") else ""
    coordinator = coordinators.get(device_id)

    # Mask sensitive config data
    config_data = {
        **entry.data,
        CONF_ACCESS_TOKEN: f"{entry.data.get(CONF_ACCESS_TOKEN, '')[:8]}***",
        CONF_USER_ID: entry.data.get(CONF_USER_ID, ""),
    }

    diagnostics: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "data": config_data,
            "options": dict(entry.options),
            "version": entry.version,
            "minor_version": entry.minor_version,
        },
    }

    if coordinator:
        data = coordinator.data
        diagnostics["coordinator"] = {
            "name": coordinator.name,
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "cust_code": coordinator.cust_code,
            "cust_name": coordinator.cust_name,
        }
        if data:
            diagnostics["data"] = {
                "balance": data.balance,
                "cust_code": data.cust_code,
                "cust_name": data.cust_name,
                "cust_address": data.cust_address,
                "monthly_usage": data.monthly_usage,
                "monthly_cost": data.monthly_cost,
                "period": data.period,
                "unit_price": data.unit_price,
                "owe_money": data.owe_money,
                "last_record": data.last_record,
                "qty_meter_balance": data.qty_meter_balance,
                "purch_times": data.purch_times,
                "last_record_time": data.last_record_time,
                "meter_no": data.meter_no,
                "meter_form_name": data.meter_form_name,
                "card_no": data.card_no,
                "comp_name": data.comp_name,
                "cust_status": data.cust_status,
                "annual_usage": data.annual_usage,
                "current_tier": data.current_tier,
                "current_tier_price": data.current_tier_price,
                "tier_cycle_start": data.tier_cycle_start,
                "monthly_stats_count": len(data.monthly_stats),
                "yearly_stats_count": len(data.yearly_stats),
            }

    return diagnostics
