"""Configuration validation for the 中燃在线 (ZR Gas) integration."""

from __future__ import annotations

import voluptuous as vol

from homeassistant.const import CONF_ACCESS_TOKEN

from .const import (
    CONF_BALANCE_THRESHOLD,
    CONF_UPDATE_INTERVAL,
    DEFAULT_BALANCE_THRESHOLD,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_ACCESS_TOKEN): str,
                vol.Optional(
                    CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL
                ): vol.All(int, vol.Range(min=300)),
                vol.Optional(
                    CONF_BALANCE_THRESHOLD, default=DEFAULT_BALANCE_THRESHOLD
                ): vol.All(float, vol.Range(min=0)),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)
