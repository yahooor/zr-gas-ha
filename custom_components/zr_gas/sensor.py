"""Sensor platform for the 中燃在线 (ZR Gas) integration.

Uses the SensorEntityDescription pattern (inspired by ha_hfcrgas) to
declaratively define all sensors. Adding a new sensor only requires
adding a new description entry — no new class needed.

Each bound gas customer account gets its own Device grouping:
- Balance sensor: Current account balance (CNY)
- Monthly usage sensor: Current month gas usage (m³)
- Monthly cost sensor: Current month cost (CNY)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CURRENCY_YUAN, UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ZrGasDataUpdateCoordinator
from .const import DOMAIN
from .models import ZrGasDeviceData


@dataclass(frozen=True, kw_only=True)
class ZrGasSensorEntityDescription(SensorEntityDescription):
    """Describe 中燃在线 sensor entity.

    Inherits from HA's SensorEntityDescription and adds a value_fn
    callback to extract the sensor value from coordinator data.
    """

    value_fn: Callable[[ZrGasDeviceData], float | None]
    attributes_fn: Callable[[ZrGasDeviceData], dict[str, Any]] | None = None


# ── Sensor descriptions ──────────────────────────────────────────────
# Declarative sensor definitions. To add a new sensor, just add an entry.

SENSOR_DESCRIPTIONS: tuple[ZrGasSensorEntityDescription, ...] = (
    ZrGasSensorEntityDescription(
        key="balance",
        translation_key="balance",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CURRENCY_YUAN,
        icon="mdi:cash",
        suggested_display_precision=2,
        value_fn=lambda data: data.balance,
        attributes_fn=lambda data: {
            "cust_code": data.cust_code,
            "cust_name": data.cust_name,
            "cust_address": data.cust_address,
        },
    ),
    ZrGasSensorEntityDescription(
        key="monthly_usage",
        translation_key="monthly_usage",
        device_class=SensorDeviceClass.GAS,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfVolume.CUBIC_METERS,
        icon="mdi:fire",
        suggested_display_precision=2,
        value_fn=lambda data: data.monthly_usage,
        attributes_fn=lambda data: {
            "cust_code": data.cust_code,
            "period": data.period,
            "usage_volume": data.monthly_usage,
            "usage_amount": data.monthly_cost,
            "unit_price": data.unit_price,
        },
    ),
    ZrGasSensorEntityDescription(
        key="monthly_cost",
        translation_key="monthly_cost",
        device_class=SensorDeviceClass.MONETARY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=CURRENCY_YUAN,
        icon="mdi:currency-cny",
        suggested_display_precision=2,
        value_fn=lambda data: data.monthly_cost,
        attributes_fn=lambda data: {
            "cust_code": data.cust_code,
            "period": data.period,
        },
    ),
)


class ZrGasSensorEntity(CoordinatorEntity[ZrGasDataUpdateCoordinator], SensorEntity):
    """Single sensor entity class for all 中燃在线 sensors.

    Uses entity_description (SensorEntityDescription pattern) to
    declaratively define each sensor's behavior. This eliminates the
    need for multiple sensor subclasses.
    """

    entity_description: ZrGasSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZrGasDataUpdateCoordinator,
        description: ZrGasSensorEntityDescription,
        cust_code: str,
        cust_code_short: str,
    ) -> None:
        """Initialize the sensor entity.

        Args:
            coordinator: Data update coordinator for this customer.
            description: Entity description defining sensor behavior.
            cust_code: Full customer code.
            cust_code_short: Last 4 digits for display.
        """
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
    def native_value(self) -> float | None:
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
    """Set up the 中燃在线 sensor platform.

    Creates sensor entities for each bound gas customer account,
    using the SensorEntityDescription pattern.

    Args:
        hass: Home Assistant instance.
        entry: Config entry with account and coordinator data.
        async_add_entities: Callback to register new entities.
    """
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
