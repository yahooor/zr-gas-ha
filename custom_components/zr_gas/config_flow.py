"""Config flow for the 中燃在线 (ZR Gas) integration.

Provides a user-friendly SMS login flow:
  1. User enters mobile phone number
  2. User enters captcha + SMS verification code
  3. System logs in, discovers bound gas accounts, and creates entry

Also includes:
  - OptionsFlow for adjusting refresh interval and balance threshold
  - ReauthFlow that re-uses the SMS login when the token expires
"""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import ZrGasAPI, ZrGasApiError, ZrGasAuthError, ZrGasSmsError
from .const import (
    CONF_ACCESS_TOKEN,
    CONF_BALANCE_THRESHOLD,
    CONF_MOBILE,
    CONF_UPDATE_INTERVAL,
    CONF_USER_ID,
    CONF_X_MAS_APP_INFO,
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
    """Handle a config flow for 中燃在线.

    Flow: user (mobile) → sms (captcha + code) → discover → entry
    """

    VERSION = 1
    MINOR_VERSION = 2

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._mobile: str = ""
        self._api: ZrGasAPI | None = None
        self._discovered_customers: list[dict[str, str]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step1: Enter mobile phone number.

        Args:
            user_input: User-provided form data, or None to show the form.

        Returns:
            FlowResult for the next step or form with errors.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            mobile = user_input[CONF_MOBILE].strip()

            # Basic validation: must be 11 digits
            if not mobile.isdigit() or len(mobile) != 11:
                errors["base"] = "invalid_mobile"
            else:
                self._mobile = mobile
                session = async_get_clientsession(self.hass)
                self._api = ZrGasAPI(session)
                return await self.async_step_sms()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_MOBILE): str}),
            errors=errors,
        )

    async def async_step_sms(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step2: Enter captcha code and SMS verification code.

        The captcha image URL is generated from the API and shown as a
        clickable link in the form's description_placeholders. The user
        clicks the link to open the captcha image in a new browser tab,
        reads the code, and enters it back here.

        This step handles two actions:
        - "send_sms": Sends the SMS code (requires captcha_code)
        - "login": Logs in with the SMS code

        Args:
            user_input: User-provided form data, or None to show the form.

        Returns:
            FlowResult for the next step or form with errors.
        """
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        # Generate captcha URL for the clickable link
        if self._api:
            captcha_url = self._api.get_captcha_url(self._mobile)
            description_placeholders["captcha_url"] = captcha_url

        if user_input is not None:
            captcha_code = user_input.get("captcha_code", "").strip()
            sms_code = user_input.get("sms_code", "").strip()
            send_sms = user_input.get("send_sms", False)

            # Action: Send SMS code (takes priority when checkbox is ticked)
            if send_sms:
                if not captcha_code or len(captcha_code) < 4:
                    errors["base"] = "captcha_required"
                elif not self._api:
                    errors["base"] = "connection_error"
                else:
                    try:
                        await self._api.send_sms_code(self._mobile, captcha_code)
                        description_placeholders["sms_sent"] = "true"
                    except ZrGasSmsError as err:
                        _LOGGER.warning("SMS send failed: %s", err)
                        errors["base"] = "sms_send_failed"
                    except Exception as err:
                        _LOGGER.error("Unexpected error sending SMS: %s", err)
                        errors["base"] = "connection_error"

            # Action: Login with SMS code
            elif sms_code:
                if not self._api:
                    errors["base"] = "connection_error"
                else:
                    try:
                        result = await self._api.login_with_sms(
                            self._mobile, sms_code
                        )
                        # Login successful — proceed to account discovery
                        return await self.async_step_discover()
                    except ZrGasAuthError as err:
                        _LOGGER.warning("SMS login failed: %s", err)
                        errors["base"] = "invalid_sms_code"
                    except Exception as err:
                        _LOGGER.error("Unexpected error during login: %s", err)
                        errors["base"] = "connection_error"
            else:
                # No action: neither send_sms nor sms_code provided
                errors["base"] = "sms_code_required"

        return self.async_show_form(
            step_id="sms",
            data_schema=vol.Schema(
                {
                    vol.Required("captcha_code"): str,
                    vol.Required("sms_code"): str,
                    vol.Optional("send_sms", default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step3: Discover bound gas accounts and create entry.

        Args:
            user_input: Not used (auto-proceeds).

        Returns:
            FlowResult creating the entry or showing an error.
        """
        errors: dict[str, str] = {}

        if not self._api:
            errors["base"] = "connection_error"
            return self.async_show_form(
                step_id="discover",
                errors=errors,
                description_placeholders={"count": "0"},
            )

        try:
            await self._api.init_request(self._api.user_id)
            customers = await self._api.get_bind_gas_cust_list(
                self._api.user_id
            )
        except ZrGasAuthError as err:
            _LOGGER.error("Auth error during discovery: %s", err)
            errors["base"] = "invalid_token"
            return self.async_show_form(
                step_id="discover",
                errors=errors,
                description_placeholders={"count": "0"},
            )
        except Exception as err:
            _LOGGER.error("API error during discovery: %s", err)
            errors["base"] = "connection_error"
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

        # Store discovered customers
        self._discovered_customers = [
            {"cust_code": c.cust_code, "cust_name": c.cust_name}
            for c in customers
        ]

        primary_name = customers[0].cust_name or "中燃在线"
        user_id = self._api.user_id or self._mobile

        # Deduplicate by user_id (mobile number)
        await self.async_set_unique_id(user_id)
        self._abort_if_already_configured()

        return self.async_create_entry(
            title=primary_name,
            data={
                CONF_ACCESS_TOKEN: self._api.access_token,
                CONF_USER_ID: self._api.user_id,
                CONF_X_MAS_APP_INFO: self._api.x_mas_app_info,
                CONF_MOBILE: self._mobile,
                "customers": self._discovered_customers,
            },
            options={
                CONF_UPDATE_INTERVAL: DEFAULT_UPDATE_INTERVAL,
                CONF_BALANCE_THRESHOLD: DEFAULT_BALANCE_THRESHOLD,
            },
        )

    # ── Reauth Flow ─────────────────────────────────────────────────

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle reauthorization when the token expires.

        Re-uses the SMS login flow — user enters mobile + SMS code again.

        Args:
            entry_data: Data from the existing config entry.

        Returns:
            FlowResult for the reauth mobile input form.
        """
        # Pre-fill mobile from existing entry
        self._mobile = entry_data.get(CONF_MOBILE, "")
        session = async_get_clientsession(self.hass)
        self._api = ZrGasAPI(session)
        return await self.async_step_reauth_sms()

    async def async_step_reauth_sms(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Reauth step: enter captcha + SMS code to get a new token.

        Args:
            user_input: User-provided form data, or None to show the form.

        Returns:
            FlowResult to update the existing entry or show errors.
        """
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        # Generate captcha URL for the clickable link
        if self._api:
            captcha_url = self._api.get_captcha_url(self._mobile)
            description_placeholders["captcha_url"] = captcha_url
            description_placeholders["mobile"] = (
                f"{self._mobile[:3]}****{self._mobile[-4:]}"
                if len(self._mobile) == 11
                else self._mobile
            )
        else:
            errors["base"] = "connection_error"

        if user_input is not None:
            captcha_code = user_input.get("captcha_code", "").strip()
            sms_code = user_input.get("sms_code", "").strip()
            send_sms = user_input.get("send_sms", False)

            # Send SMS
            if send_sms:
                if not captcha_code or len(captcha_code) < 4:
                    errors["base"] = "captcha_required"
                elif not self._api:
                    errors["base"] = "connection_error"
                else:
                    try:
                        await self._api.send_sms_code(self._mobile, captcha_code)
                        description_placeholders["sms_sent"] = "true"
                    except ZrGasSmsError as err:
                        _LOGGER.warning("SMS send failed: %s", err)
                        errors["base"] = "sms_send_failed"
                    except Exception as err:
                        _LOGGER.error("Unexpected error sending SMS: %s", err)
                        errors["base"] = "connection_error"

            # Login
            elif sms_code:
                if not self._api:
                    errors["base"] = "connection_error"
                else:
                    try:
                        await self._api.login_with_sms(self._mobile, sms_code)

                        # Update the existing entry with new credentials
                        entry = self.hass.config_entries.async_get_entry(
                            self.context["entry_id"]
                        )
                        if entry:
                            self.hass.config_entries.async_update_entry(
                                entry,
                                data={
                                    **entry.data,
                                    CONF_ACCESS_TOKEN: self._api.access_token,
                                    CONF_USER_ID: self._api.user_id,
                                    CONF_X_MAS_APP_INFO: self._api.x_mas_app_info,
                                },
                            )
                        return self.async_abort(reason="reauth_successful")

                    except ZrGasAuthError as err:
                        _LOGGER.warning("Reauth login failed: %s", err)
                        errors["base"] = "invalid_sms_code"
                    except Exception as err:
                        _LOGGER.error("Unexpected error during reauth: %s", err)
                        errors["base"] = "connection_error"
            else:
                errors["base"] = "sms_code_required"

        return self.async_show_form(
            step_id="reauth_sms",
            data_schema=vol.Schema(
                {
                    vol.Required("captcha_code"): str,
                    vol.Required("sms_code"): str,
                    vol.Optional("send_sms", default=False): bool,
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    # ── Options Flow ─────────────────────────────────────────────────

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> ZrGasOptionsFlow:
        """Get the options flow for this handler."""
        return ZrGasOptionsFlow(config_entry)


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
