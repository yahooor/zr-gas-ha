"""Button platform for the 中燃在线 (ZR Gas) integration.

Provides a refresh button for each gas customer account,
allowing users to manually trigger a data update from the
HA UI without waiting for the scheduled refresh.
"""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import ZrGasDataUpdateCoordinator
from .const import DOMAIN, SOURCE_PAY

_LOGGER = logging.getLogger(__name__)

REFRESH_DESCRIPTION = ButtonEntityDescription(
    key="refresh",
    translation_key="refresh",
    icon="mdi:refresh",
)


class ZrGasRefreshButton(CoordinatorEntity[ZrGasDataUpdateCoordinator], ButtonEntity):
    """Button entity to manually refresh gas account data.

    Pressing this button triggers an immediate data refresh
    for the associated gas customer account.
    """

    entity_description = REFRESH_DESCRIPTION
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: ZrGasDataUpdateCoordinator,
        cust_code: str,
        source: str,
    ) -> None:
        """Initialize the refresh button.

        Args:
            coordinator: Data update coordinator for this customer.
            cust_code: Full customer code.
            source: Data source (在线端 mp / 缴费端 pay).
        """
        super().__init__(coordinator)
        self._cust_code = cust_code
        # 与传感器保持一致：缴费端加来源前缀，在线端沿用历史 ID
        id_prefix = "zr_gas_pay_" if source == SOURCE_PAY else "zr_gas_"
        self._attr_unique_id = f"{id_prefix}{cust_code}_refresh"
        device_key = f"pay_{cust_code}" if source == SOURCE_PAY else cust_code
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device_key)},
        }

    async def async_press(self) -> None:
        """Handle button press — trigger a data refresh."""
        _LOGGER.info("Manual refresh triggered for %s", self._cust_code)
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the 中燃在线 button platform.

    Creates a refresh button for each bound gas customer account.
    """
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, ZrGasDataUpdateCoordinator] = entry_data.get("coordinators", {})
    source = entry_data.get("source", entry.data.get("source", "mp"))

    entities: list[ButtonEntity] = []

    for cust_code, coordinator in coordinators.items():
        entities.append(
            ZrGasRefreshButton(
                coordinator=coordinator,
                cust_code=cust_code,
                source=source,
            )
        )

    async_add_entities(entities, update_before_add=True)
