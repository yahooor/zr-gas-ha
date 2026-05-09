"""Config flow for the 中燃在线 (ZR Gas) integration.

Provides a 3-step configuration flow:
  1. User enters accessToken
  2. System validates token and discovers bound gas accounts
  3. Entry is created for the account(s)

Also includes:
  - OptionsFlow for adjusting refresh interval and balance threshold
  - ReauthFlow for token renewal when the existing token expires
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_ACCESS_TOKEN
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZrGasAPI, ZrGasApiError, ZrGasAuthError
from .const import (
    CONF_BALANCE_THRESHOLD,
    CONF_UPDATE_INTERVAL,
    CONF_USER_ID,
    DEFAULT_BALANCE_THRESHOLD,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


class ZrGasConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 中燃在线."""

    VERSION = 1
    MINOR_VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._access_token: str = ""
        self._user_id: str = ""
        self._discovered_customers: list[dict[str, str]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step: user provides accessToken.

        Args:
            user_input: User-provided form data, or None to show the form.

        Returns:
            FlowResult for the next step or form with errors.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            self._access_token = user_input[CONF_ACCESS_TOKEN]

            try:
                info = await self._validate_token(self._access_token)
            except CannotConnect:
                errors["base"] = "connection_error"
            except InvalidAuth:
                errors["base"] = "invalid_token"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "api_error"
            else:
                # Store userId for account discovery
                # 需实际验证: userId 字段名
                self._user_id = (
                    info.get("userId")
                    or info.get("user_id")
                    or info.get("data", {}).get("userId")
                    or ""
                )
                return await self.async_step_discover()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_ACCESS_TOKEN): str}),
            errors=errors,
        )

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the discovery step: find bound gas customer accounts.

        Validates the token, then queries the API for bound gas accounts.
        If accounts are found, creates a config entry.

        Args:
            user_input: Not used in this step (auto-proceeds).

        Returns:
            FlowResult creating the entry or showing an error.
        """
        errors: dict[str, str] = {}

        try:
            customers = await self._discover_accounts(
                self._access_token, self._user_id
            )
        except CannotConnect:
            errors["base"] = "connection_error"
            return self.async_show_form(
                step_id="discover",
                errors=errors,
                description_placeholders={"count": "0"},
            )
        except InvalidAuth:
            errors["base"] = "invalid_token"
            return self.async_show_form(
                step_id="discover",
                errors=errors,
                description_placeholders={"count": "0"},
            )
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception during discovery")
            errors["base"] = "api_error"
            return self.async_show_form(
                step_id="discover",
                errors=errors,
                description_placeholders={"count": "0"},
            )

        if not customers:
            errors["base"] = "no_accounts"
            return self.async_show_form(
                step_id="discover",
                errors=errors,
                description_placeholders={"count": "0"},
            )

        # Store discovered customers for potential future multi-account support
        self._discovered_customers = [
            {"cust_code": c.cust_code, "cust_name": c.cust_name}
            for c in customers
        ]

        # Use first customer as the primary account name
        # 需实际验证: 如果有多个账户，可能需要循环创建多个 entry
        primary_name = customers[0].cust_name or "中燃在线"

        # Check if already configured
        await self.async_set_unique_id(self._user_id)
        self._abort_if_already_configured()

        return self.async_create_entry(
            title=primary_name,
            data={
                CONF_ACCESS_TOKEN: self._access_token,
                CONF_USER_ID: self._user_id,
                "customers": self._discovered_customers,
            },
            options={
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_BALANCE_THRESHOLD: DEFAULT_BALANCE_THRESHOLD,
            },
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle reauthorization when the token expires.

        Triggered by ConfigEntryAuthFailed raised in the coordinator.

        Args:
            entry_data: Data from the existing config entry.

        Returns:
            FlowResult for the reauth confirmation form.
        """
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauthorization confirmation: enter new accessToken.

        Args:
            user_input: User-provided form data with new token.

        Returns:
            FlowResult to update the existing entry or show errors.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            new_token = user_input[CONF_ACCESS_TOKEN]

            try:
                info = await self._validate_token(new_token)
            except CannotConnect:
                errors["base"] = "connection_error"
            except InvalidAuth:
                errors["base"] = "invalid_token"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during reauth")
                errors["base"] = "api_error"
            else:
                new_user_id = (
                    info.get("userId")
                    or info.get("user_id")
                    or info.get("data", {}).get("userId")
                    or ""
                )

                # Update the existing entry with new token
                entry = self.hass.config_entries.async_get_entry(
                    self.context["entry_id"]
                )
                if entry:
                    self.hass.config_entries.async_update_entry(
                        entry,
                        data={
                            **entry.data,
                            CONF_ACCESS_TOKEN: new_token,
                            CONF_USER_ID: new_user_id,
                        },
                    )
                return self.async_abort(reason="reauth_successful")

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_ACCESS_TOKEN): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ZrGasOptionsFlow:
        """Get the options flow for this handler."""
        return ZrGasOptionsFlow(config_entry)

    async def _validate_token(self, access_token: str) -> dict[str, Any]:
        """Validate the access token against the API.

        Args:
            access_token: Token to validate.

        Returns:
            API response dict with user info.

        Raises:
            InvalidAuth: If token is invalid or expired.
            CannotConnect: If the API cannot be reached.
        """
        session = async_get_clientsession(self.hass)
        api = ZrGasAPI(session, access_token)
        try:
            result = await api.check_token()
        except ZrGasAuthError as err:
            raise InvalidAuth from err
        except Exception as err:
            raise CannotConnect from err
        return result

    async def _discover_accounts(
        self, access_token: str, user_id: str
    ) -> list:
        """Discover bound gas customer accounts.

        Args:
            access_token: Valid access token.
            user_id: User ID from token validation.

        Returns:
            List of ZrGasCustomer instances.

        Raises:
            InvalidAuth: If authentication fails.
            CannotConnect: If the API cannot be reached.
        """
        session = async_get_clientsession(self.hass)
        api = ZrGasAPI(session, access_token)
        try:
            customers = await api.get_bind_gas_cust_list(user_id)
        except ZrGasAuthError as err:
            raise InvalidAuth from err
        except Exception as err:
            _LOGGER.error("API error during discovery: %s", err)
            raise CannotConnect from err
        return customers


class ZrGasOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for 中燃在线 integration.

    Allows users to update:
    - Data refresh interval (seconds)
    - Balance alert threshold (CNY)
    """

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self._config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options.

        Args:
            user_input: User-provided form data, or None to show the form.

        Returns:
            FlowResult to update options or show the form.
        """
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_UPDATE_INTERVAL,
                        default=self._config_entry.options.get(
                            CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL
                        ),
                    ): vol.All(int, vol.Range(min=300)),
                    vol.Optional(
                        CONF_BALANCE_THRESHOLD,
                        default=self._config_entry.options.get(
                            CONF_BALANCE_THRESHOLD, DEFAULT_BALANCE_THRESHOLD
                        ),
                    ): vol.All(float, vol.Range(min=0)),
                }
            ),
        )
