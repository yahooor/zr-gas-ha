"""Sensor platform for the 中燃在线 (ZR Gas) integration.

Uses the SensorEntityDescription pattern (inspired by ha_hfcrgas) to
declaratively define all sensors. Adding a new sensor only requires
adding a new description entry — no new class needed.

Each bound gas customer account gets its own Device grouping:
- Balance sensor: Current account balance (CNY)
- Monthly usage sensor: Current month gas usage (m³)
- Monthly cost sensor: Current month cost (CNY)
- Owe money sensor: Outstanding debt (CNY)
- Meter reading sensor: Last meter reading
- Gas volume balance sensor: Remaining gas volume
- Purchase count sensor: Number of gas purchases
- Last reading date sensor: Date of last meter reading
- Annual usage sensor: Yearly accumulated gas usage with tier info (m³)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
import homeassistant.util.dt as dt_util

from . import ZrGasDataUpdateCoordinator
from .const import DOMAIN
from .models import ZrGasDeviceData


def _parse_timestamp(value: str | None) -> datetime | None:
    """Parse API date string to a timezone-aware datetime.

    The API returns dates like "2026-04-21" or "2026-04-21 10:30:00".
    HA requires a timezone-aware datetime for TIMESTAMP device_class sensors.
    """
    if not value:
        return None
    value = value.strip()
    if not value:
        return None
    try:
        # Try full datetime format first
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(value, fmt)
            except ValueError:
                continue
            # Attach local timezone (HA default for naive datetimes)
            return parsed.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
    except Exception:
        pass
    return None


@dataclass(frozen=True, kw_only=True)
class ZrGasSensorEntityDescription(SensorEntityDescription):
    """Describe 中燃在线 sensor entity.

    Inherits from HA's SensorEntityDescription and adds a value_fn
    callback to extract the sensor value from coordinator data.
    """

    value_fn: Callable[[ZrGasDeviceData], float | str | None]
    attributes_fn: Callable[[ZrGasDeviceData], dict[str, Any]] | None = None


# Shared device attributes for all sensors
def _device_attributes(data: ZrGasDeviceData) -> dict[str, Any]:
    """Return common device attributes shared across all sensors."""
    return {
        "cust_code": data.cust_code,
        "cust_name": data.cust_name,
        "cust_address": data.cust_address,
        "comp_name": data.comp_name,
        "meter_no": data.meter_no,
        "meter_form_name": data.meter_form_name,
        "card_no": data.card_no,
        "fee": data.fee,
        "cust_status": data.cust_status,
    }


def _stats_attributes(data: ZrGasDeviceData) -> dict[str, Any]:
    """Return monthly/yearly statistics attributes."""
    monthly_list = [
        {"month": ms.month, "gas_num": round(ms.gas_num, 2), "gas_cost": round(ms.gas_cost, 2)}
        for ms in data.monthly_stats
    ]
    yearly_list = [
        {"year": ys.year, "gas_num": round(ys.gas_num, 2), "gas_cost": round(ys.gas_cost, 2)}
        for ys in data.yearly_stats
    ]
    return {
        "monthly_stats": monthly_list,
        "yearly_stats": yearly_list,
    }


# ── Sensor descriptions ──────────────────────────────────────────────

SENSOR_DESCRIPTIONS: tuple[ZrGasSensorEntityDescription, ...] = (
    ZrGasSensorEntityDescription(
        key="balance",
        translation_key="balance",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
        icon="mdi:cash",
        suggested_display_precision=2,
        value_fn=lambda data: data.balance,
        attributes_fn=lambda data: _device_attributes(data),
    ),
    ZrGasSensorEntityDescription(
        key="monthly_usage",
        translation_key="monthly_usage",
        device_class=SensorDeviceClass.GAS,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:fire",
        suggested_display_precision=2,
        value_fn=lambda data: data.monthly_usage,
        attributes_fn=lambda data: {
            **_device_attributes(data),
            "period": data.period,
            "unit_price": data.unit_price,
        },
    ),
    ZrGasSensorEntityDescription(
        key="monthly_cost",
        translation_key="monthly_cost",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
        icon="mdi:currency-cny",
        suggested_display_precision=2,
        value_fn=lambda data: data.monthly_cost,
        attributes_fn=lambda data: {
            **_device_attributes(data),
            "period": data.period,
        },
    ),
    ZrGasSensorEntityDescription(
        key="owe_money",
        translation_key="owe_money",
        device_class=SensorDeviceClass.MONETARY,
        native_unit_of_measurement="CNY",
        icon="mdi:alert-circle-outline",
        suggested_display_precision=2,
        value_fn=lambda data: data.owe_money,
        attributes_fn=lambda data: _device_attributes(data),
    ),
    ZrGasSensorEntityDescription(
        key="last_record",
        translation_key="last_record",
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:gauge",
        suggested_display_precision=0,
        value_fn=lambda data: data.last_record,
        attributes_fn=lambda data: {
            **_device_attributes(data),
            "last_record_time": data.last_record_time,
        },
    ),
    ZrGasSensorEntityDescription(
        key="qty_meter_balance",
        translation_key="qty_meter_balance",
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:gas-cylinder",
        suggested_display_precision=0,
        value_fn=lambda data: data.qty_meter_balance,
        attributes_fn=lambda data: _device_attributes(data),
    ),
    ZrGasSensorEntityDescription(
        key="purch_times",
        translation_key="purch_times",
        state_class=SensorStateClass.TOTAL,
        icon="mdi:counter",
        value_fn=lambda data: data.purch_times,
        attributes_fn=lambda data: _device_attributes(data),
    ),
    ZrGasSensorEntityDescription(
        key="last_record_time",
        translation_key="last_record_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        icon="mdi:calendar-clock",
        value_fn=lambda data: _parse_timestamp(data.last_record_time),
        attributes_fn=lambda data: {
            **_device_attributes(data),
            "last_record": data.last_record,
        },
    ),
    # ── 新增：年度累计用气量传感器 ────────────────────────────
    ZrGasSensorEntityDescription(
        key="annual_usage",
        translation_key="annual_usage",
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.TOTAL,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:chart-line",
        suggested_display_precision=2,
        value_fn=lambda data: data.annual_usage,
        attributes_fn=lambda data: {
            **_device_attributes(data),
            **_stats_attributes(data),
            "current_tier": data.current_tier,
            "current_tier_price": data.current_tier_price,
            "tier_cycle_start": data.tier_cycle_start,
        },
    ),
)


class ZrGasSensorEntity(CoordinatorEntity[ZrGasDataUpdateCoordinator], SensorEntity):
    """Single sensor entity class for all 中燃在线 sensors."""

    entity_description: ZrGasSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZrGasDataUpdateCoordinator,
        description: ZrGasSensorEntityDescription,
        cust_code: str,
        cust_code_short: str,
    ) -> None:
        """Initialize the sensor entity."""
        super().__init__(coordinator)
        self.entity_description = description
        self._cust_code = cust_code
        self._attr_unique_id = f"zr_gas_{cust_code}_{description.key}"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, cust_code)},
            "name": f"中燃燃气 {cust_code_short}",
            "manufacturer": "中燃在线",
            "model": "在线账户",
        }

    @property
    def device_info(self) -> dict[str, Any]:
        """Return dynamic device info with live data from coordinator."""
        info = {
            "identifiers": {(DOMAIN, self._cust_code)},
            "name": f"中燃燃气 {self._cust_code[-4:]}",
            "manufacturer": "中燃在线",
            "model": "在线账户",
        }
        if self.coordinator.data is not None:
            data = self.coordinator.data
            if data.comp_name:
                info["manufacturer"] = data.comp_name
            if data.meter_form_name:
                info["model"] = data.meter_form_name
            if data.cust_address:
                info["name"] = f"中燃燃气 {data.cust_address[:20]}"
            if data.meter_no:
                info["sw_version"] = f"表号: {data.meter_no}"
            if data.card_no:
                info["hw_version"] = f"卡号: {data.card_no}"
        return info

    @property
    def native_value(self) -> float | str | None:
        """Return the sensor value extracted by value_fn."""
        if self.coordinator.data is None:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return additional state attributes extracted by attributes_fn."""
        if self.coordinator.data is None:
            return {}
        if self.entity_description.attributes_fn is not None:
            return self.entity_description.attributes_fn(self.coordinator.data)
        return {}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the 中燃在线 sensor platform."""
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, ZrGasDataUpdateCoordinator] = entry_data.get(
        "coordinators", {}
    )

    entities: list[SensorEntity] = []

    for cust_code, coordinator in coordinators.items():
        cust_code_short = cust_code[-4:] if len(cust_code) >= 4 else cust_code

        for description in SENSOR_DESCRIPTIONS:
            entities.append(
                ZrGasSensorEntity(
                    coordinator=coordinator,
                    description=description,
                    cust_code=cust_code,
                    cust_code_short=cust_code_short,
                )
            )

    async_add_entities(entities, update_before_add=True)
