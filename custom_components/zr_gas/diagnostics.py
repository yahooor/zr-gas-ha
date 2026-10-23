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
    """
    entry_data = hass.data[DOMAIN].get(entry.entry_id, {})
    coordinators: dict[str, ZrGasDataUpdateCoordinator] = entry_data.get("coordinators", {})

    # Find the coordinator matching this device.
    # Device keys: 在线端 = cust_code; 缴费端 = "pay_{cust_code}"
    device_id = next(iter(device.get("identifiers", set())))[1] if device.get("identifiers") else ""
    coordinator = coordinators.get(device_id)
    if coordinator is None and device_id.startswith("pay_"):
        coordinator = coordinators.get(device_id[4:])

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
            "source": coordinator.source,
            "last_update_success": coordinator.last_update_success,
            "update_interval": str(coordinator.update_interval),
            "cust_code": coordinator.cust_code,
            "cust_name": coordinator.cust_name,
        }
        if data:
            diagnostics["data"] = {
                "source": data.source,
                "balance": data.balance,
                "cust_code": data.cust_code,
                "cust_name": data.cust_name,
                "cust_address": data.cust_address,
                "monthly_usage": data.monthly_usage,
                "monthly_cost": data.monthly_cost,
                "period": data.period,
                "unit_price": data.unit_price,
                "owe_money": data.owe_money,
                "new_owe_money": data.new_owe_money,
                "award_money": data.award_money,
                "gas_price": data.gas_price,
                "max_gas": data.max_gas,
                "cust_type": data.cust_type,
                "last_record": data.last_record,
                "qty_meter_balance": data.qty_meter_balance,
                "purch_times": data.purch_times,
                "last_record_time": data.last_record_time,
                "meter_no": data.meter_no,
                "meter_form_name": data.meter_form_name,
                "card_no": data.card_no,
                "card_type": data.card_type,
                "vent_date": data.vent_date,
                "bar_code": data.bar_code,
                "meter_loc": data.meter_loc,
                "comp_name": data.comp_name,
                "cust_status": data.cust_status,
                "last_payment": data.last_payment,
                "last_payment_time": data.last_payment_time,
                "payment_history_count": len(data.payment_history),
                "annual_usage": data.annual_usage,
                "current_tier": data.current_tier,
                "current_tier_price": data.current_tier_price,
                "tier_cycle_start": data.tier_cycle_start,
                "monthly_stats_count": len(data.monthly_stats),
                "yearly_stats_count": len(data.yearly_stats),
            }

    return diagnostics
