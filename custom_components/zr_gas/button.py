"""Button platform for the 中燃在线 (ZR Gas) integration.

Provides a refresh button for each gas customer account,
allowing users to manually trigger a data update from the
HA UI without waiting for the scheduled refresh.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN

if TYPE_CHECKING:
    from . import ZrGasDataUpdateCoordinator

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
    ) -> None:
        """Initialize the refresh button.

        Args:
            coordinator: Data update coordinator for this customer.
            cust_code: Full customer code.
        """
        super().__init__(coordinator)
        self._cust_code = cust_code
        self._attr_unique_id = f"zr_gas_{cust_code}_refresh"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, cust_code)},
        }

    async def async_press(self) -> None:
        """Handle button press — trigger a data refresh.

        Logs the manual refresh and updates the coordinator.
        """
        _LOGGER.info("Manual refresh triggered for %s", self._cust_code)
        await self.coordinator.async_request_refresh()


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the 中燃在线 button platform.

    Creates a refresh button for each bound gas customer account.

    Args:
        hass: Home Assistant instance.
        entry: Config entry with account and coordinator data.
        async_add_entities: Callback to register new entities.
    """
    entry_data = hass.data[DOMAIN][entry.entry_id]
    coordinators: dict[str, ZrGasDataUpdateCoordinator] = entry_data.get(
        "coordinators", {}
    )

    entities: list[ButtonEntity] = []

    for cust_code, coordinator in coordinators.items():
        entities.append(
            ZrGasRefreshButton(
                coordinator=coordinator,
                cust_code=cust_code,
            )
        )

    async_add_entities(entities, update_before_add=True)
