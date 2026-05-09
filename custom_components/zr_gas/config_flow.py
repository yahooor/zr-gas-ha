"""Config flow for the 中燃在线 (ZR Gas) integration.

Provides a user-friendly SMS login flow:
  1. User enters mobile phone number
  2. User opens captcha link, reads code, enters it → sends SMS
  3. User enters SMS verification code → login → discover accounts

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


class ZrGasConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 中燃在线.

    Flow: user (mobile) → captcha (link + code + send) → sms_code (login) → discover → entry
    """

    VERSION = 1
    MINOR_VERSION = 3

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._mobile: str = ""
        self._api: ZrGasAPI | None = None
        self._discovered_customers: list[dict[str, str]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Enter mobile phone number.

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
                return await self.async_step_captcha()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_MOBILE): str}),
            errors=errors,
        )

    async def async_step_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: Open captcha link, enter captcha code, send SMS.

        The captcha image URL is provided as a clickable link in the
        description. The user clicks the link to open the image in a
        new browser tab, reads the code, enters it, and submits to
        trigger the SMS send.

        Args:
            user_input: User-provided form data, or None to show the form.

        Returns:
            FlowResult for the next step or form with errors.
        """
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        # Build clickable link using link_left/link_right pattern (same as Xiaomi ha_xiaomi_home)
        if self._api:
            captcha_url = self._api.get_captcha_url(self._mobile)
            description_placeholders["link_left"] = (
                f'<a href="{captcha_url}" target="_blank">'
            )
            description_placeholders["link_right"] = "</a>"

        if user_input is not None:
            captcha_code = user_input.get("captcha_code", "").strip()

            if not captcha_code or len(captcha_code) < 4:
                errors["base"] = "captcha_required"
            elif not self._api:
                errors["base"] = "connection_error"
            else:
                try:
                    await self._api.send_sms_code(self._mobile, captcha_code)
                    # SMS sent successfully — proceed to SMS code input
                    return await self.async_step_sms_code()
                except ZrGasSmsError as err:
                    _LOGGER.warning("SMS send failed: %s", err)
                    errors["base"] = "sms_send_failed"
                    # Refresh captcha URL on failure
                    captcha_url = self._api.get_captcha_url(self._mobile)
                    description_placeholders["link_left"] = (
                        f'<a href="{captcha_url}" target="_blank">'
                    )
                    description_placeholders["link_right"] = "</a>"
                except Exception as err:
                    _LOGGER.error("Unexpected error sending SMS: %s", err)
                    errors["base"] = "connection_error"

        return self.async_show_form(
            step_id="captcha",
            data_schema=vol.Schema(
                {
                    vol.Required("captcha_code"): str,
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_sms_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 3: Enter SMS verification code to login.

        Args:
            user_input: User-provided form data, or None to show the form.

        Returns:
            FlowResult for the next step or form with errors.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            sms_code = user_input.get("sms_code", "").strip()

            if not sms_code:
                errors["base"] = "sms_code_required"
            elif not self._api:
                errors["base"] = "connection_error"
            else:
                try:
                    await self._api.login_with_sms(self._mobile, sms_code)
                    # Login successful — proceed to account discovery
                    return await self.async_step_discover()
                except ZrGasAuthError as err:
                    _LOGGER.warning("SMS login failed: %s", err)
                    errors["base"] = "invalid_sms_code"
                except Exception as err:
                    _LOGGER.error("Unexpected error during login: %s", err)
                    errors["base"] = "connection_error"

        return self.async_show_form(
            step_id="sms_code",
            data_schema=vol.Schema(
                {
                    vol.Required("sms_code"): str,
                }
            ),
            errors=errors,
        )

    async def async_step_discover(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 4: Discover bound gas accounts and create entry.

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

        Re-uses the SMS login flow — user enters captcha + SMS code again.

        Args:
            entry_data: Data from the existing config entry.

        Returns:
            FlowResult for the reauth captcha input form.
        """
        # Pre-fill mobile from existing entry
        self._mobile = entry_data.get(CONF_MOBILE, "")
        session = async_get_clientsession(self.hass)
        self._api = ZrGasAPI(session)
        return await self.async_step_reauth_captcha()

    async def async_step_reauth_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Reauth step 1: Open captcha link, enter code, send SMS.

        Args:
            user_input: User-provided form data, or None to show the form.

        Returns:
            FlowResult to proceed to SMS code step or show errors.
        """
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        if self._api:
            captcha_url = self._api.get_captcha_url(self._mobile)
            description_placeholders["link_left"] = (
                f'<a href="{captcha_url}" target="_blank">'
            )
            description_placeholders["link_right"] = "</a>"
            description_placeholders["mobile"] = (
                f"{self._mobile[:3]}****{self._mobile[-4:]}"
                if len(self._mobile) == 11
                else self._mobile
            )
        else:
            errors["base"] = "connection_error"

        if user_input is not None:
            captcha_code = user_input.get("captcha_code", "").strip()

            if not captcha_code or len(captcha_code) < 4:
                errors["base"] = "captcha_required"
            elif not self._api:
                errors["base"] = "connection_error"
            else:
                try:
                    await self._api.send_sms_code(self._mobile, captcha_code)
                    # SMS sent — proceed to SMS code input
                    return await self.async_step_reauth_sms_code()
                except ZrGasSmsError as err:
                    _LOGGER.warning("SMS send failed: %s", err)
                    errors["base"] = "sms_send_failed"
                    # Refresh captcha URL on failure
                    captcha_url = self._api.get_captcha_url(self._mobile)
                    description_placeholders["link_left"] = (
                        f'<a href="{captcha_url}" target="_blank">'
                    )
                    description_placeholders["link_right"] = "</a>"
                except Exception as err:
                    _LOGGER.error("Unexpected error sending SMS: %s", err)
                    errors["base"] = "connection_error"

        return self.async_show_form(
            step_id="reauth_captcha",
            data_schema=vol.Schema(
                {
                    vol.Required("captcha_code"): str,
                }
            ),
            errors=errors,
            description_placeholders=description_placeholders,
        )

    async def async_step_reauth_sms_code(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Reauth step 2: Enter SMS verification code to get a new token.

        Args:
            user_input: User-provided form data, or None to show the form.

        Returns:
            FlowResult to update the existing entry or show errors.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            sms_code = user_input.get("sms_code", "").strip()

            if not sms_code:
                errors["base"] = "sms_code_required"
            elif not self._api:
                errors["base"] = "connection_error"
            else:
                try:
                    await self._api.login_with_sms(self._mobile, sms_code)

                    # Update the existing entry with new credentials
                    entry_id = self.context.get("entry_id")
                    entry = (
                        self.hass.config_entries.async_get_entry(entry_id)
                        if entry_id
                        else None
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

        return self.async_show_form(
            step_id="reauth_sms_code",
            data_schema=vol.Schema(
                {
                    vol.Required("sms_code"): str,
                }
            ),
            errors=errors,
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
