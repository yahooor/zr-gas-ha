"""Config flow for the 中燃在线 (ZR Gas) integration.

Provides a user-friendly SMS login flow:
  1. User enters mobile phone number
  2. User views captcha image, enters captcha code, and sends SMS
  3. User enters SMS verification code to complete login

Captcha image display strategy:
  The remote captcha URL cannot be loaded directly in the HA frontend
  (CORS / session cookie issues), and base64 data URIs are stripped by
  HA's DOMPurify sanitizer. Instead, we fetch the captcha image server-side,
  store it in hass.data, and serve it via a custom HTTP endpoint
  (/api/zr_gas/captcha/{token}). This ensures same-origin access.

Also includes:
  - OptionsFlow for adjusting refresh interval and balance threshold
  - ReauthFlow that re-uses the SMS login when the token expires
"""

from __future__ import annotations

import logging
import uuid
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
from .views import ZrGasCaptchaView

_LOGGER = logging.getLogger(__name__)


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""


def _register_captcha_view(hass) -> None:
    """Register the captcha HTTP view if not already registered."""
    hass.data.setdefault(DOMAIN, {})
    if not hass.data[DOMAIN].get("captcha_view_registered"):
        hass.http.register_view(ZrGasCaptchaView())
        hass.data[DOMAIN]["captcha_view_registered"] = True
        _LOGGER.debug("Registered ZrGasCaptchaView")


def _store_captcha_image(hass, image_bytes: bytes) -> str:
    """Store a captcha image and return a URL token.

    Returns:
        URL path for the captcha image, e.g. /api/zr_gas/captcha/{uuid}
    """
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault("captcha_images", {})

    token = str(uuid.uuid4())
    hass.data[DOMAIN]["captcha_images"][token] = image_bytes
    captcha_url = f"/api/zr_gas/captcha/{token}"
    _LOGGER.debug("Stored captcha image with token %s", token[:8])
    return captcha_url


class ZrGasConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 中燃在线.

    Flow: user (mobile) → captcha (image + code + send) → sms_code (verify) → discover → entry
    """

    VERSION = 1
    MINOR_VERSION = 4

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._mobile: str = ""
        self._api: ZrGasAPI | None = None
        self._captcha_url: str = ""
        self._discovered_customers: list[dict[str, str]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Enter mobile phone number."""
        errors: dict[str, str] = {}

        if user_input is not None:
            mobile = user_input[CONF_MOBILE].strip()
            if not mobile.isdigit() or len(mobile) != 11:
                errors["base"] = "invalid_mobile"
            else:
                self._mobile = mobile
                session = async_get_clientsession(self.hass)
                self._api = ZrGasAPI(session)

                # Register the captcha HTTP view (idempotent)
                _register_captcha_view(self.hass)

                return await self.async_step_captcha()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_MOBILE): str}),
            errors=errors,
        )

    async def async_step_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: View captcha image, enter captcha code, and send SMS."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        # Always fetch a fresh captcha image when showing this step
        if self._api:
            try:
                captcha_bytes = await self._api.fetch_captcha_image(self._mobile)
                self._captcha_url = _store_captcha_image(self.hass, captcha_bytes)
                description_placeholders["captcha_url"] = self._captcha_url
            except ZrGasApiError as err:
                _LOGGER.error("Failed to fetch captcha image: %s", err)
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
                    # SMS sent successfully, move to the next step
                    return await self.async_step_sms_code()
                except ZrGasSmsError as err:
                    _LOGGER.warning("SMS send failed: %s", err)
                    errors["base"] = "sms_send_failed"
                    # Re-fetch captcha on failure (it may have expired)
                    try:
                        captcha_bytes = await self._api.fetch_captcha_image(self._mobile)
                        self._captcha_url = _store_captcha_image(self.hass, captcha_bytes)
                        description_placeholders["captcha_url"] = self._captcha_url
                    except ZrGasApiError:
                        pass
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
        """Step 3: Enter SMS verification code to complete login."""
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
        """Step 4: Discover bound gas accounts and create entry."""
        errors: dict[str, str] = {}

        if not self._api:
            errors["base"] = "connection_error"
            return self.async_show_form(step_id="discover", errors=errors, description_placeholders={"count": "0"})

        try:
            await self._api.init_request(self._api.user_id)
            customers = await self._api.get_bind_gas_cust_list(self._api.user_id)
        except ZrGasAuthError as err:
            _LOGGER.error("Auth error during discovery: %s", err)
            errors["base"] = "invalid_token"
            return self.async_show_form(step_id="discover", errors=errors, description_placeholders={"count": "0"})
        except Exception as err:
            _LOGGER.error("API error during discovery: %s", err)
            errors["base"] = "connection_error"
            return self.async_show_form(step_id="discover", errors=errors, description_placeholders={"count": "0"})

        if not customers:
            errors["base"] = "no_accounts"
            return self.async_show_form(step_id="discover", errors=errors, description_placeholders={"count": "0"})

        self._discovered_customers = [
            {"cust_code": c.cust_code, "cust_name": c.cust_name} for c in customers
        ]
        primary_name = customers[0].cust_name or "中燃在线"
        user_id = self._api.user_id or self._mobile

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

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> FlowResult:
        """Handle reauthorization when the token expires."""
        self._mobile = entry_data.get(CONF_MOBILE, "")
        session = async_get_clientsession(self.hass)
        self._api = ZrGasAPI(session)

        # Register the captcha HTTP view (idempotent)
        _register_captcha_view(self.hass)

        return await self.async_step_reauth_captcha()

    async def async_step_reauth_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Reauth step 1: View captcha, enter code, send SMS."""
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        # Always fetch a fresh captcha image
        if self._api:
            try:
                captcha_bytes = await self._api.fetch_captcha_image(self._mobile)
                self._captcha_url = _store_captcha_image(self.hass, captcha_bytes)
                description_placeholders["captcha_url"] = self._captcha_url
            except ZrGasApiError as err:
                _LOGGER.error("Failed to fetch captcha image: %s", err)
                errors["base"] = "connection_error"
            description_placeholders["mobile"] = (
                f"{self._mobile[:3]}****{self._mobile[-4:]}" if len(self._mobile) == 11 else self._mobile
            )

        if user_input is not None:
            captcha_code = user_input.get("captcha_code", "").strip()

            if not captcha_code or len(captcha_code) < 4:
                errors["base"] = "captcha_required"
            elif not self._api:
                errors["base"] = "connection_error"
            else:
                try:
                    await self._api.send_sms_code(self._mobile, captcha_code)
                    # SMS sent successfully, move to SMS code step
                    return await self.async_step_reauth_sms_code()
                except ZrGasSmsError as err:
                    _LOGGER.warning("SMS send failed: %s", err)
                    errors["base"] = "sms_send_failed"
                    # Re-fetch captcha on failure
                    try:
                        captcha_bytes = await self._api.fetch_captcha_image(self._mobile)
                        self._captcha_url = _store_captcha_image(self.hass, captcha_bytes)
                        description_placeholders["captcha_url"] = self._captcha_url
                    except ZrGasApiError:
                        pass
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
        """Reauth step 2: Enter SMS verification code."""
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
                    entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
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
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> ZrGasOptionsFlow:
        """Get the options flow for this handler."""
        return ZrGasOptionsFlow(config_entry)


class ZrGasOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for 中燃在线 integration."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self._config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_UPDATE_INTERVAL, default=self._config_entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)): vol.All(int, vol.Range(min=300)),
                    vol.Optional(CONF_BALANCE_THRESHOLD, default=self._config_entry.options.get(CONF_BALANCE_THRESHOLD, DEFAULT_BALANCE_THRESHOLD)): vol.All(float, vol.Range(min=0)),
                }
            ),
        )
