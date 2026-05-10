"""API client for the 中燃在线 (ZR Gas) integration.

This module implements the ZrGasAPI class that communicates with the
ZR Gas cloud API at https://zrds.95007.com.

Key findings from reverse-engineering the web app JS (index.fd387e5a.js):
- Salt: "yph1234567890"
- Signature: md5(param + salt + timeStamp)
- Param priority: specified field > autoSrvId > custCode > compcode > compCode > userId > mobile > fileName
- Content-Type: application/x-www-form-urlencoded (NOT JSON)
- Response format: {"data": {...}, "message": "...", "status": 1}

Login flow (from pages-login-login.js):
1. GET captcha image: /controller/merchant/authCode.do?flag={mobile}&tn={timestamp}
2. POST send SMS: /user/sendsms3.do  body: {codeKey, codeKeyValue, mobile}
3. POST SMS login: /user/xcxMobileUserLogin  body: {mobile, code, channelType:6}
   → returns {masToken, sid, data: {id, mobile, ...}}
   → sid needs prefix: "aaahg10001/" + sid → x-mas-app-info header
"""

from __future__ import annotations

import base64
import hashlib
import logging
import time
from typing import Any

import aiohttp

from .const import (
    BASE_URL,
    ENDPOINT_CAPTCHA_IMG,
    ENDPOINT_CHECK_TOKEN,
    ENDPOINT_GET_BILLS,
    ENDPOINT_GET_CUSTOMER_INFO,
    ENDPOINT_GET_CUSTOMERS,
    ENDPOINT_INIT,
    ENDPOINT_LOGIN_SMS,
    ENDPOINT_SEND_SMS,
    SIGN_SALT,
    X_MAS_SID_PREFIX,
)
from .models import ZrGasBill, ZrGasCustomer, ZrGasCustomerDetail

_LOGGER = logging.getLogger(__name__)


class ZrGasApiError(Exception):
    """Base exception for ZR Gas API errors."""


class ZrGasAuthError(ZrGasApiError):
    """Authentication error — token invalid or expired."""


class ZrGasSmsError(ZrGasApiError):
    """Error during SMS verification code flow."""


class ZrGasAPI:
    """Async API client for 中燃在线 (ZR Gas) cloud services.

    Supports two authentication modes:
    1. **SMS login** (user-friendly): mobile + captcha + SMS code → masToken
    2. **Direct token** (advanced): use a pre-obtained accessToken directly

    Usage::

        session = async_get_clientsession(hass)

        # SMS login flow
        api = ZrGasAPI(session)
        await api.send_sms_code(mobile, "1234")
        await api.login_with_sms(mobile, "654321")

        # Or use existing token
        api = ZrGasAPI(session, access_token="...", user_id="...", x_mas_app_info="...")
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str = "",
        user_id: str = "",
        x_mas_app_info: str = "",
    ) -> None:
        """Initialize the API client.

        Args:
            session: aiohttp client session for making HTTP requests.
            access_token: Access token (masToken) from login response.
            user_id: User identifier (passed as header in most API calls).
            x_mas_app_info: x-mas-app-info value from login response (sid with prefix).
        """
        self._session = session
        self._access_token = access_token
        self._user_id = user_id
        self._x_mas_app_info = x_mas_app_info
        self._salt = SIGN_SALT
        # Independent session with a REAL CookieJar for the login flow.
        # HA's shared session (async_get_clientsession) uses DummyCookieJar
        # which drops cookies. The login flow requires cookies to persist
        # across GET captcha → POST sendsms → POST login, so the caller
        # should use ``set_login_session()`` to inject a session created
        # via ``async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar(unsafe=True))``.
        self._login_session: aiohttp.ClientSession | None = None

    def set_login_session(self, session: aiohttp.ClientSession) -> None:
        """Set an independent session with a real CookieJar for login flow.

        Must be called before ``fetch_captcha_image()`` / ``send_sms_code()``
        / ``login_with_sms()`` so that JSESSIONID and other cookies persist
        across all three requests.

        Args:
            session: An ``aiohttp.ClientSession`` with a real ``CookieJar``.
        """
        self._login_session = session

    @property
    def access_token(self) -> str:
        """Return the current access token."""
        return self._access_token

    @property
    def user_id(self) -> str:
        """Return the current user ID."""
        return self._user_id

    @property
    def x_mas_app_info(self) -> str:
        """Return the current x-mas-app-info header value."""
        return self._x_mas_app_info

    def _get_login_session(self) -> aiohttp.ClientSession:
        """Get the session to use for login flow requests.

        Returns the independent login session (with real CookieJar) if set,
        otherwise falls back to HA's shared session.
        """
        if self._login_session is not None and not self._login_session.closed:
            return self._login_session
        return self._session

    async def close_login_session(self) -> None:
        """Close the independent login session after login is complete."""
        if self._login_session and not self._login_session.closed:
            await self._login_session.close()
            self._login_session = None

    def get_captcha_url(self, mobile: str) -> str:
        """Get the URL for the captcha image associated with a mobile number.

        The captcha image is fetched as a GET request and displayed to the
        user for manual entry.

        Args:
            mobile: Mobile phone number (11 digits).

        Returns:
            Full URL to the captcha image.
        """
        timestamp = str(int(time.time() * 1000))
        return f"{BASE_URL}{ENDPOINT_CAPTCHA_IMG}?flag={mobile}&tn={timestamp}"

    async def fetch_captcha_image(self, mobile: str) -> str | None:
        """Fetch the captcha image using the login session.

        Uses the independent login session (with real CookieJar) so that
        JSESSIONID cookie is preserved for subsequent send_sms_code and
        login_with_sms calls.

        Args:
            mobile: Mobile phone number (11 digits).

        Returns:
            Base64-encoded image data URI string, or None on failure.
        """
        captcha_url = self.get_captcha_url(mobile)
        headers = {
            "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Referer": "https://servicewechat.com/wx19c4e29f3ef6b4a0/91/page-frame.html",
        }

        try:
            login_session = self._get_login_session()
            async with login_session.get(
                captcha_url, headers=headers
            ) as resp:
                resp.raise_for_status()
                image_data = await resp.read()
                # Debug: log cookies after captcha GET
                cookies_after = ""
                for cookie in login_session.cookie_jar:
                    cookies_after += f"{cookie.key}={cookie.value}(path={cookie['path']}) "
                _LOGGER.debug(
                    "Captcha fetched: %d bytes, cookies=[%s]",
                    len(image_data), cookies_after,
                )
                b64 = base64.b64encode(image_data).decode("ascii")
                content_type = resp.content_type or "image/png"
                return f"data:{content_type};base64,{b64}"
        except Exception as err:
            _LOGGER.warning("Failed to fetch captcha image: %s", err)
            return None

    async def send_sms_code(self, mobile: str, captcha_code: str) -> None:
        """Send an SMS verification code to the given mobile number.

        Step2 of the login flow. The user must first solve the captcha
        image returned by ``get_captcha_url()``.

        API endpoint: ``POST /user/sendsms3.do``
        Body: ``{codeKey: mobile, codeKeyValue: captcha_code, mobile: mobile}``

        Args:
            mobile: Mobile phone number (11 digits).
            captcha_code: The captcha text the user entered from the image.

        Raises:
            ZrGasSmsError: If the SMS code could not be sent
                (wrong captcha, rate limited, etc.).
        """
        url = f"{BASE_URL}{ENDPOINT_SEND_SMS}"
        data = {
            "codeKey": mobile,
            "codeKeyValue": captcha_code,
            "mobile": mobile,
        }

        try:
            # Use login session (with real CookieJar) for cookie consistency
            login_session = self._get_login_session()

            # Debug: log session cookies
            cookie_str = ""
            for cookie in login_session.cookie_jar:
                cookie_str += f"{cookie.key}={cookie.value}(path={cookie['path']}) "
            _LOGGER.debug(
                "SMS send: mobile=%s, code=%s, session_cookies=[%s]",
                mobile, captcha_code, cookie_str,
            )

            request_headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
            async with login_session.post(
                url, headers=request_headers, data=data
            ) as resp:
                resp.raise_for_status()
                result = await resp.json()
        except Exception as err:
            raise ZrGasSmsError(f"Failed to send SMS code: {err}") from err

        status = result.get("status")
        message = result.get("message", "")
        # API status codes vary by endpoint:
        #   status=1 → success, status=0 → may also be success ("操作成功")
        #   status=2 → verification code expired
        #   status=-1 → wrong captcha / input error
        # NOTE: API may return status as string ("1") or int (1)
        if status in (2, "2"):
            raise ZrGasSmsError(f"发送验证码失败: 验证码已过期，请重新获取")
        if str(status) not in ("0", "1") and "成功" not in message:
            raise ZrGasSmsError(f"发送验证码失败: {message or '未知错误'}")

        _LOGGER.info("SMS code sent successfully to %s****%s", mobile[:3], mobile[-4:])

    async def login_with_sms(
        self, mobile: str, sms_code: str
    ) -> dict[str, Any]:
        """Login using mobile number and SMS verification code.

        Step3 of the login flow. On success, stores the returned
        masToken, userId, and x-mas-app-info internally for subsequent
        API calls.

        API endpoint: ``POST /user/xcxMobileUserLogin``
        Body: ``{mobile, code, channelType: 6, openId: "", unionId: ""}``

        Response contains:
        - ``masToken``: Access token for subsequent API calls
        - ``sid``: Session ID (needs prefix "aaahg10001/" for x-mas-app-info header)
        - ``data``: User info dict with ``id``, ``mobile``, etc.

        Args:
            mobile: Mobile phone number.
            sms_code: The 6-digit SMS verification code.

        Returns:
            Full API response dict including user data.

        Raises:
            ZrGasAuthError: If login fails (wrong code, expired, etc.).
        """
        url = f"{BASE_URL}{ENDPOINT_LOGIN_SMS}"
        data = {
            "mobile": mobile,
            "code": sms_code,
            "channelType": "6",
            "openId": "",
            "unionId": "",
        }

        try:
            login_session = self._get_login_session()
            login_headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
            async with login_session.post(
                url, headers=login_headers, data=data
            ) as resp:
                resp.raise_for_status()
                result = await resp.json()
        except Exception as err:
            raise ZrGasAuthError(f"SMS login failed: {err}") from err

        status = result.get("status")
        message = result.get("message", "")
        _LOGGER.debug("Login response: status=%s, message=%s, data_keys=%s",
                      status, message, list((result.get("data") or {}).keys()))

        # API status codes for login:
        #   status=1 → success
        #   status=0 → may also be success (some endpoints use 0 for OK)
        #   status=2 → verification code expired ("请重新获取验证码")
        #   status=-1 → wrong verification code ("验证码输入不正确")
        # NOTE: API may return status as string ("1") or int (1)
        if status in (2, "2"):
            raise ZrGasAuthError(f"登录失败: 验证码已过期，请重新获取")
        if status in (-1, "-1"):
            raise ZrGasAuthError(f"登录失败: {message or '验证码输入不正确'}")
        if str(status) not in ("0", "1") and "成功" not in message:
            raise ZrGasAuthError(f"登录失败: {message or '未知错误'}")

        # Check if we actually got a token (some responses have status=0 but no token)
        login_data = result.get("data") or {}
        mas_token = login_data.get("masToken") or result.get("masToken") or ""
        if not mas_token and str(status) not in ("0", "1"):
            raise ZrGasAuthError(f"登录失败: {message or '未获取到token'}")

        login_data = result.get("data") or {}

        # Extract and store credentials (mirrors loginOK handler in JS)
        mas_token = login_data.get("masToken") or result.get("masToken") or ""
        sid = login_data.get("sid") or result.get("sid") or ""
        user_info = login_data.get("data") or login_data
        uid = str(user_info.get("id") or "")

        if not mas_token:
            raise ZrGasAuthError("Login succeeded but no masToken returned")

        # Store credentials for subsequent API calls
        self._access_token = mas_token
        self._user_id = uid
        if sid:
            self._x_mas_app_info = f"{X_MAS_SID_PREFIX}{sid}"

        _LOGGER.info(
            "SMS login successful (user_id=%s, sid=%s)",
            uid,
            "***" if sid else "(none)",
        )

        return result

    async def _post_raw(
        self,
        url: str,
        data: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Send a POST request and return the raw JSON response.

        Unlike ``_post``, this does NOT check status codes or raise on
        business errors. Used by login endpoints that need to inspect
        the response before deciding what to do.

        Args:
            url: Full URL to POST to.
            data: Request body data (form-encoded).
            headers: Optional additional headers.

        Returns:
            Parsed JSON response dict.
        """
        request_headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        # Only include auth headers if we have them
        if self._access_token:
            request_headers["accessToken"] = self._access_token
        if self._user_id:
            request_headers["userId"] = self._user_id
        if self._x_mas_app_info:
            request_headers["x-mas-app-info"] = self._x_mas_app_info
        if headers:
            request_headers.update(headers)

        async with self._session.post(url, headers=request_headers, data=data) as resp:
            resp.raise_for_status()
            return await resp.json()

    def _generate_signature(self, param: str, timestamp: str) -> str:
        """Generate an MD5 signature for API request authentication.

        Algorithm: md5(param + salt + timestamp)
        Salt: "yph1234567890" (reverse-engineered from web JS)

        Args:
            param: The primary business parameter (userId, custCode, etc.).
            timestamp: Current millisecond timestamp string.

        Returns:
            MD5 hex digest.
        """
        raw = f"{param}{self._salt}{timestamp}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def _get_timestamp(self) -> str:
        """Return current timestamp in milliseconds.

        Returns:
            String representation of current epoch time in milliseconds.
        """
        return str(int(time.time() * 1000))

    async def _post(
        self,
        url: str,
        data: dict[str, Any],
        headers: dict[str, str] | None = None,
        as_json: bool = False,
    ) -> dict[str, Any]:
        """Send a POST request to the API and return the JSON response.

        The API uses two content types:
        - Most endpoints: application/x-www-form-urlencoded (data=)
        - checkMasInfo: application/json (json=)

        Args:
            url: Full URL to POST to.
            data: Request body data.
            headers: Optional additional headers.
            as_json: If True, send as JSON body; otherwise form-encoded.

        Returns:
            Parsed JSON response dict.

        Raises:
            ZrGasAuthError: If the API returns an authentication error.
            ZrGasApiError: If the API returns a non-success response.
            aiohttp.ClientError: On network-level errors.
        """
        content_type = "application/json" if as_json else "application/x-www-form-urlencoded"
        request_headers = {
            "Content-Type": content_type,
            "accessToken": self._access_token,
            "platform": "mp-weixin",
            "Accept": "*/*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }
        if self._user_id:
            request_headers["userId"] = self._user_id
        if self._x_mas_app_info:
            request_headers["x-mas-app-info"] = self._x_mas_app_info
        if headers:
            request_headers.update(headers)

        _LOGGER.debug("POST %s (content_type=%s)", url, content_type)

        kwargs: dict[str, Any] = {"headers": request_headers}
        if as_json:
            kwargs["json"] = data
        else:
            kwargs["data"] = data

        async with self._session.post(url, **kwargs) as resp:
            if resp.status in (401, 403):
                raise ZrGasAuthError(f"HTTP {resp.status}: authentication failed")
            resp.raise_for_status()
            result: dict[str, Any] = await resp.json()

        _LOGGER.debug(
            "Response status=%s message=%s",
            result.get("status"),
            result.get("message"),
        )

        # Check response status
        # Confirmed: API returns {"status": 1, "message": "...", "data": {...}}
        # NOTE: checkMasInfo returns {"code": 200, "success": true, "message": "token有效"}
        #       without a "status" field — so also check code/success.
        # NOTE: API sometimes returns status as string "1" instead of int 1
        status = result.get("status")
        code = result.get("code")
        success = result.get("success")
        message = result.get("message", "")

        if status in (1, "1") or code in (200, "200") or success is True:
            return result

        # Token invalid/expired based on response message
        # IMPORTANT: "token有效" means token IS valid, must NOT be treated as error
        if message and "token" in message.lower() and "有效" not in message:
            raise ZrGasAuthError(f"Auth failed: {message}")
        if "登录" in message and "成功" not in message:
            raise ZrGasAuthError(f"Auth failed: {message}")

        raise ZrGasApiError(f"API error (status={status}): {message}")

    async def init_request(self, user_id: str) -> bool:
        """Send an initialization / buried-point event request.

        This is required before other API calls — it registers the session.
        The request body is a URL-encoded string:
        "appUseType=0&clickType=3&eventType=1&channelType=0&userId={userId}"

        Args:
            user_id: User identifier for the session.

        Returns:
            True if initialization was successful.
        """
        url = f"{BASE_URL}{ENDPOINT_INIT}"
        data = {
            "appUseType": "0",
            "clickType": "3",
            "eventType": "1",
            "channelType": "0",
            "userId": user_id,
        }

        try:
            result = await self._post(url, data)
            return result.get("status") == 1
        except Exception:
            _LOGGER.warning("Init request failed, continuing anyway")
            return False

    async def check_token(self) -> dict[str, Any]:
        """Validate the access token and retrieve user information.

        POST to /wisdom/auth/checkMasInfo with JSON body {}.
        Confirmed response: {"message": "token有效", "status": 1, ...}

        Returns:
            API response containing userId and other account info.

        Raises:
            ZrGasAuthError: If the token is invalid or expired.
        """
        url = f"{BASE_URL}{ENDPOINT_CHECK_TOKEN}"
        data = {}

        result = await self._post(url, data, as_json=True)

        # Confirmed: response has message "token有效" when valid
        if result.get("message") == "token有效" or result.get("status") in (1, "1"):
            return result

        raise ZrGasAuthError(f"Token validation failed: {result.get('message', 'unknown')}")

    async def get_bind_gas_cust_list(self, user_id: str) -> list[ZrGasCustomer]:
        """Get list of gas customer accounts bound to the user.

        Signature: md5(userId + salt + timeStamp)

        Args:
            user_id: User identifier obtained from check_token / headers.

        Returns:
            List of ZrGasCustomer instances.

        Raises:
            ZrGasApiError: On API errors.
        """
        url = f"{BASE_URL}{ENDPOINT_GET_CUSTOMERS}"
        timestamp = self._get_timestamp()
        signature = self._generate_signature(user_id, timestamp)

        data = {
            "userId": user_id,
            "timeStamp": timestamp,
            "signature": signature,
        }
        headers = {
            "userId": user_id,
        }

        result = await self._post(url, data, headers=headers)

        items = result.get("data") or []
        if isinstance(items, dict):
            items = [items]

        customers: list[ZrGasCustomer] = []
        for item in items:
            customers.append(
                ZrGasCustomer(
                    cust_code=item.get("custCode", ""),
                    cust_name=item.get("custName", ""),
                )
            )

        return customers

    async def get_cust_info(
        self, cust_code: str, cust_name: str
    ) -> ZrGasCustomerDetail:
        """Query detailed information for a specific gas customer.

        Signature: md5(custCode + salt + timeStamp)

        Confirmed response fields from packet capture:
        - countMoney: 余额 (account balance)
        - newCountMoney: 新余额
        - address: 用气地址
        - custCode: 燃气编号
        - custName: 客户姓名 (masked, e.g. "***")
        - oweMoney: 欠费金额
        - awardMoney: 赠送金额

        Args:
            cust_code: Customer code (燃气编号).
            cust_name: Customer name with mask (e.g. "张*").

        Returns:
            ZrGasCustomerDetail with address and balance info.

        Raises:
            ZrGasApiError: On API errors.
        """
        url = f"{BASE_URL}{ENDPOINT_GET_CUSTOMER_INFO}"
        timestamp = self._get_timestamp()
        signature = self._generate_signature(cust_code, timestamp)

        data = {
            "custCode": cust_code,
            "custName": cust_name,
            "timeStamp": timestamp,
            "signature": signature,
        }

        result = await self._post(url, data)

        info = result.get("data") or {}

        # Confirmed: balance is in "countMoney" field
        balance_str = (
            info.get("countMoney")
            or info.get("newCountMoney")
            or info.get("balance")
            or "0"
        )
        try:
            balance = float(balance_str)
        except (ValueError, TypeError):
            balance = 0.0

        # Extract additional fields from API response
        def _float(val, default=0.0):
            try:
                return float(val) if val is not None else default
            except (ValueError, TypeError):
                return default

        def _int(val, default=0):
            try:
                return int(float(val)) if val is not None else default
            except (ValueError, TypeError):
                return default

        return ZrGasCustomerDetail(
            cust_code=info.get("custCode", cust_code),
            cust_name=info.get("custName", cust_name),
            cust_address=info.get("address", ""),
            balance=balance,
            owe_money=_float(info.get("oweMoney")),
            last_record=_float(info.get("lastRecord")),
            qty_meter_balance=_float(info.get("qtyMeterBalance")),
            purch_times=_int(info.get("purchTimes")),
            last_record_time=info.get("lastRecordTime", ""),
            meter_no=info.get("meterNo", ""),
            meter_form_name=info.get("meterFormName", ""),
            card_no=info.get("cardNo", ""),
            comp_name=info.get("compName", ""),
            cust_status=info.get("custStatus", ""),
            fee=info.get("fee", ""),
        )

    async def get_customer_money_list(
        self,
        cust_code: str,
        start_time: str,
        end_time: str,
    ) -> list[ZrGasBill]:
        """Query billing/payment records for a customer within a time range.

        Signature: md5(custCode + salt + timeStamp)

        Args:
            cust_code: Customer code.
            start_time: Start period in YYYYMM format.
            end_time: End period in YYYYMM format.

        Returns:
            List of ZrGasBill instances.

        Raises:
            ZrGasApiError: On API errors.
        """
        url = f"{BASE_URL}{ENDPOINT_GET_BILLS}"
        timestamp = self._get_timestamp()
        signature = self._generate_signature(cust_code, timestamp)

        data = {
            "custCode": cust_code,
            "timeStamp": timestamp,
            "signature": signature,
            "startTime": start_time,
            "endTime": end_time,
        }

        result = await self._post(url, data)

        items = result.get("data") or []
        if isinstance(items, dict):
            # May be a single record
            items = [items]

        bills: list[ZrGasBill] = []
        for item in items:
            # Fields from the older API reference (zrhsh.com):
            # recordMonth, curQty (用量), receivable (应收), received (已收)
            try:
                usage_volume = float(
                    item.get("curQty")
                    or item.get("usageVolume")
                    or item.get("gasVolume")
                    or 0
                )
            except (ValueError, TypeError):
                usage_volume = 0.0

            try:
                usage_amount = float(
                    item.get("receivable")
                    or item.get("usageAmount")
                    or item.get("payFee")
                    or 0
                )
            except (ValueError, TypeError):
                usage_amount = 0.0

            try:
                unit_price = float(
                    item.get("price")
                    or item.get("unitPrice")
                    or 0
                )
            except (ValueError, TypeError):
                unit_price = 0.0

            period = (
                item.get("recordMonth")
                or item.get("period")
                or item.get("billingCycle")
                or ""
            )

            bills.append(
                ZrGasBill(
                    period=period,
                    usage_volume=usage_volume,
                    usage_amount=usage_amount,
                    unit_price=unit_price,
                )
            )

        return bills
