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
from homeassistant.helpers.aiohttp_client import async_get_clientsession, async_create_clientsession

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
import os

_LOGGER = logging.getLogger(__name__)

# Directory to store temporary captcha images served via HA's /local/ path
_CAPTCHA_DIR = "www/zr_gas_captcha"


def _get_captcha_local_url(hass: HomeAssistant, mobile: str) -> str:
    """Get the /local/ URL for the captcha image.

    The captcha is fetched by HA's aiohttp session (same as send_sms_code),
    saved to www/zr_gas_captcha/, and served via HA's built-in static file server.

    Returns:
        Relative URL path like /local/zr_gas_captcha/18574472432.png
    """
    import time
    ts = str(int(time.time() * 1000))
    return f"/local/zr_gas_captcha/{mobile}.png?tn={ts}"


async def _fetch_and_save_captcha(
    hass: HomeAssistant, api: ZrGasAPI, mobile: str
) -> str | None:
    """Fetch captcha image via HA session and save to www/ for serving.

    This ensures the SAME aiohttp session that will later call send_sms_code
    also makes the captcha GET request, so JSESSIONID cookie is consistent.

    Returns:
        The /local/ URL for the saved image, or None on failure.
    """
    import time

    # Ensure www/zr_gas_captcha/ directory exists
    captcha_dir = os.path.join(hass.config.config_dir, _CAPTCHA_DIR)
    os.makedirs(captcha_dir, exist_ok=True)

    # Fetch captcha image using the SAME session as send_sms_code
    captcha_url = api.get_captcha_url(mobile)
    headers = {
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://servicewechat.com/wx19c4e29f3ef6b4a0/91/page-frame.html",
    }

    try:
        # Use the login session (with real CookieJar) so that cookies
        # from this GET request persist for send_sms_code / login_with_sms
        login_session = api._get_login_session()
        async with login_session.get(captcha_url, headers=headers) as resp:
            resp.raise_for_status()
            image_data = await resp.read()
        # Debug: log cookies
        cookie_info = ""
        for c in login_session.cookie_jar:
            cookie_info += f"{c.key}={c.value}(path={c['path']}) "
        _LOGGER.debug(
            "_fetch_and_save_captcha: %d bytes, cookies=[%s]",
            len(image_data), cookie_info,
        )
    except Exception as err:
        _LOGGER.warning("Failed to fetch captcha image: %s", err)
        return None

    # Save to www/zr_gas_captcha/{mobile}.png
    filepath = os.path.join(captcha_dir, f"{mobile}.png")
    try:
        def _write_file(path: str, data: bytes) -> None:
            with open(path, "wb") as f:
                f.write(data)

        await hass.async_add_executor_job(_write_file, filepath, image_data)
    except Exception as err:
        _LOGGER.warning("Failed to save captcha image: %s", err)
        return None

    ts = str(int(time.time() * 1000))
    return f"/local/zr_gas_captcha/{mobile}.png?tn={ts}"


class ZrGasConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for 中燃在线.

    Flow: user (mobile) → captcha (link + code + send) → sms_code (login) → discover → entry
    """

    VERSION = 1
    MINOR_VERSION = 4

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._mobile: str = ""
        self._api: ZrGasAPI | None = None
        self._discovered_customers: list[dict[str, str]] = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1: Choose authentication method.

        Args:
            user_input: User-provided form data, or None to show the form.

        Returns:
            FlowResult for the next step or form with errors.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            auth_method = user_input.get("auth_method", "sms")
            if auth_method == "token":
                return await self.async_step_token()

            mobile = user_input.get(CONF_MOBILE, "").strip()

            # Basic validation: must be 11 digits
            if not mobile.isdigit() or len(mobile) != 11:
                errors["base"] = "invalid_mobile"
            else:
                self._mobile = mobile
                session = async_get_clientsession(self.hass)
                self._api = ZrGasAPI(session)
                # Create an independent session with a REAL CookieJar for the
                # login flow. HA's shared session uses DummyCookieJar which
                # drops cookies — but the login flow (captcha → sendsms → login)
                # requires JSESSIONID to persist across all three requests.
                import aiohttp as _aiohttp
                login_session = async_create_clientsession(
                    self.hass,
                    cookie_jar=_aiohttp.CookieJar(unsafe=True),
                )
                self._api.set_login_session(login_session)
                return await self.async_step_captcha()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required("auth_method", default="sms"): vol.In(
                        {"sms": "sms", "token": "token"}
                    ),
                    vol.Optional(CONF_MOBILE): str,
                }
            ),
            errors=errors,
        )

    async def async_step_token(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 1b: Import pre-obtained token directly.

        Allows users to skip SMS verification by pasting a token
        obtained from another source (e.g., API call or packet capture).

        Args:
            user_input: User-provided form data, or None to show the form.

        Returns:
            FlowResult to proceed to discovery or show errors.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            access_token = user_input.get(CONF_ACCESS_TOKEN, "").strip()
            user_id = user_input.get(CONF_USER_ID, "").strip()
            x_mas_app_info = user_input.get(CONF_X_MAS_APP_INFO, "").strip()
            mobile = user_input.get(CONF_MOBILE, "").strip()

            if not access_token or not user_id:
                errors["base"] = "token_required"
            else:
                session = async_get_clientsession(self.hass)
                self._api = ZrGasAPI(
                    session,
                    access_token=access_token,
                    user_id=user_id,
                    x_mas_app_info=x_mas_app_info,
                )
                self._mobile = mobile

                # Validate token via check_token
                try:
                    await self._api.check_token()
                    # Token is valid, proceed to discovery
                    return await self.async_step_discover()
                except ZrGasAuthError as err:
                    _LOGGER.warning("Token validation failed: %s", err)
                    errors["base"] = "invalid_token"
                except Exception as err:
                    _LOGGER.error("Token import error: %s", err)
                    errors["base"] = "connection_error"

        return self.async_show_form(
            step_id="token",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ACCESS_TOKEN): str,
                    vol.Required(CONF_USER_ID): str,
                    vol.Optional(CONF_X_MAS_APP_INFO): str,
                    vol.Optional(CONF_MOBILE): str,
                }
            ),
            errors=errors,
        )

    async def async_step_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Step 2: View captcha image, enter captcha code, send SMS.

        The captcha image is fetched by HA's aiohttp session (same one
        used for send_sms_code), saved to www/zr_gas_captcha/, and
        served via HA's built-in /local/ static file path.
        This ensures JSESSIONID cookie consistency.

        Args:
            user_input: User-provided form data, or None to show the form.

        Returns:
            FlowResult for the next step or form with errors.
        """
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        # Handle form submission
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
                    # Refresh captcha on failure
                    captcha_local_url = await _fetch_and_save_captcha(
                        self.hass, self._api, self._mobile
                    )
                    if captcha_local_url:
                        description_placeholders["link_left"] = (
                            f'<a href="{captcha_local_url}" target="_blank">'
                        )
                        description_placeholders["link_right"] = "</a>"
                except Exception as err:
                    _LOGGER.error("Unexpected error sending SMS: %s", err)
                    errors["base"] = "connection_error"

        # Fetch captcha and build link (only when no link yet,
        # i.e. first display or after failed submission refresh)
        if not description_placeholders.get("link_left") and self._api:
            captcha_local_url = await _fetch_and_save_captcha(
                self.hass, self._api, self._mobile
            )
            if captcha_local_url:
                description_placeholders["link_left"] = (
                    f'<a href="{captcha_local_url}" target="_blank">'
                )
                description_placeholders["link_right"] = "</a>"
            else:
                captcha_url = self._api.get_captcha_url(self._mobile)
                description_placeholders["link_left"] = (
                    f'<a href="{captcha_url}" target="_blank">'
                )
                description_placeholders["link_right"] = "</a>"

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
        except Exception:
            _LOGGER.warning("Init request failed, continuing to discovery")
        try:
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
        self._abort_if_unique_id_configured()

        # Close the independent login session
        if self._api:
            await self._api.close_login_session()

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
        # Create an independent session with a REAL CookieJar for the
        # login flow (same reason as async_step_user)
        import aiohttp as _aiohttp
        login_session = async_create_clientsession(
            self.hass,
            cookie_jar=_aiohttp.CookieJar(unsafe=True),
        )
        self._api.set_login_session(login_session)
        return await self.async_step_reauth_captcha()

    async def async_step_reauth_captcha(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Reauth step 1: View captcha image, enter code, send SMS.

        Args:
            user_input: User-provided form data, or None to show the form.

        Returns:
            FlowResult to proceed to SMS code step or show errors.
        """
        errors: dict[str, str] = {}
        description_placeholders: dict[str, str] = {}

        # Always set mobile placeholder
        description_placeholders["mobile"] = (
            f"{self._mobile[:3]}****{self._mobile[-4:]}"
            if len(self._mobile) == 11
            else self._mobile
        )

        if not self._api:
            errors["base"] = "connection_error"

        # Handle form submission first
        if user_input is not None and self._api:
            captcha_code = user_input.get("captcha_code", "").strip()

            if not captcha_code or len(captcha_code) < 4:
                errors["base"] = "captcha_required"
            else:
                try:
                    await self._api.send_sms_code(self._mobile, captcha_code)
                    # SMS sent — proceed to SMS code input
                    return await self.async_step_reauth_sms_code()
                except ZrGasSmsError as err:
                    _LOGGER.warning("SMS send failed: %s", err)
                    errors["base"] = "sms_send_failed"
                    # Refresh captcha on failure
                    captcha_local_url = await _fetch_and_save_captcha(
                        self.hass, self._api, self._mobile
                    )
                    if captcha_local_url:
                        description_placeholders["link_left"] = (
                            f'<a href="{captcha_local_url}" target="_blank">'
                        )
                        description_placeholders["link_right"] = "</a>"
                except Exception as err:
                    _LOGGER.error("Unexpected error sending SMS: %s", err)
                    errors["base"] = "connection_error"

        # Fetch captcha and build link (first display or after failure refresh)
        if not description_placeholders.get("link_left") and self._api:
            captcha_local_url = await _fetch_and_save_captcha(
                self.hass, self._api, self._mobile
            )
            if captcha_local_url:
                description_placeholders["link_left"] = (
                    f'<a href="{captcha_local_url}" target="_blank">'
                )
                description_placeholders["link_right"] = "</a>"
            else:
                captcha_url = self._api.get_captcha_url(self._mobile)
                description_placeholders["link_left"] = (
                    f'<a href="{captcha_url}" target="_blank">'
                )
                description_placeholders["link_right"] = "</a>"

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
                    # Close the independent login session
                    if self._api:
                        await self._api.close_login_session()
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
