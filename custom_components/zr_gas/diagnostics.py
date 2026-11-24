"""Minimal, shareable diagnostics for a gas device."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN, SOURCE_PAY

if TYPE_CHECKING:
    from homeassistant.helpers.device_registry import DeviceEntry


def _bill_month(value: str) -> str | None:
    return value if re.fullmatch(r"[0-9]{4}(?:0[1-9]|1[0-2])", value) else None


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry | Mapping[str, Any]
) -> dict[str, Any]:
    """Return refresh, billing and source metadata without account identifiers or amounts."""
    result: dict[str, Any] = {
        "entry": {"version": entry.version, "minor_version": entry.minor_version}
    }
    coordinators = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("coordinators", {})
    identifiers = (
        device.get("identifiers") if isinstance(device, Mapping) else device.identifiers
    ) or ()

    coordinator = None
    for domain, device_key in identifiers:
        if domain != DOMAIN:
            continue
        candidate = coordinators.get(device_key)
        if candidate is None and device_key.startswith("pay_"):
            pay_candidate = coordinators.get(device_key[4:])
            if pay_candidate is not None and pay_candidate.source == SOURCE_PAY:
                candidate = pay_candidate
        if candidate is not None:
            coordinator = candidate
            break

    if coordinator is None:
        return result

    result["coordinator"] = {
        "source": coordinator.source,
        "last_update_success": coordinator.last_update_success,
        "update_interval": str(coordinator.update_interval),
    }
    data = coordinator.data
    if data is not None:
        result["data"] = {
            "bills_degraded": data.bills_degraded,
            "period": _bill_month(data.period),
            "last_bill_period": _bill_month(data.last_bill_period),
            "has_meter_reading_time": bool(data.last_record_time),
            "has_payment_time": bool(data.last_payment_time),
            "monthly_stats_count": len(data.monthly_stats),
            "yearly_stats_count": len(data.yearly_stats),
            "payment_history_count": len(data.payment_history),
        }
    return result
