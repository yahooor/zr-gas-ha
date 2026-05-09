"""API client for the 中燃在线 (ZR Gas) integration.

This module implements the ZrGasAPI class that communicates with the
ZR Gas cloud API at https://zrds.95007.com.

Key findings from reverse-engineering the web app JS (index.fd387e5a.js):
- Salt: "yph1234567890"
- Signature: md5(param + salt + timeStamp)
- Param priority: specified field > autoSrvId > custCode > compcode > compCode > userId > mobile > fileName
- Content-Type: application/x-www-form-urlencoded (NOT JSON)
- Response format: {"data": {...}, "message": "...", "status": 1}

API response fields confirmed from user packet capture:
- findCustInfoByCustCodeAndCustName returns:
  countMoney (余额), custCode, custName, address, newCountMoney,
  oweMoney, newOweMoney, awardMoney, newAwardMoney, agentMoney,
  newAgentMoney, custType, custStatus, compName, etc.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import Any

import aiohttp

from .const import (
    BASE_URL,
    ENDPOINT_CHECK_TOKEN,
    ENDPOINT_GET_BILLS,
    ENDPOINT_GET_CUSTOMER_INFO,
    ENDPOINT_GET_CUSTOMERS,
    ENDPOINT_INIT,
    SIGN_SALT,
)
from .models import ZrGasBill, ZrGasCustomer, ZrGasCustomerDetail

_LOGGER = logging.getLogger(__name__)


class ZrGasApiError(Exception):
    """Base exception for ZR Gas API errors."""


class ZrGasAuthError(ZrGasApiError):
    """Authentication error — token invalid or expired."""


class ZrGasAPI:
    """Async API client for 中燃在线 (ZR Gas) cloud services.

    Communicates with the ZR Gas API using form-encoded POST requests
    with MD5-based request signing.

    Usage::

        async with aiohttp.ClientSession() as session:
            api = ZrGasAPI(session, access_token="...")
            user_info = await api.check_token()
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        access_token: str,
        user_id: str = "",
    ) -> None:
        """Initialize the API client.

        Args:
            session: aiohttp client session for making HTTP requests.
            access_token: Access token obtained from the WeChat mini-program.
            user_id: User identifier (passed as header in most API calls).
        """
        self._session = session
        self._access_token = access_token
        self._user_id = user_id
        self._salt = SIGN_SALT

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

        _LOGGER.debug("Response status=%s message=%s", result.get("status"), result.get("message"))

        # Check response status
        # Confirmed: API returns {"status": 1, "message": "...", "data": {...}}
        status = result.get("status")
        message = result.get("message", "")

        if status == 1:
            return result

        # Token invalid/expired based on response message
        if "token" in message.lower() or "登录" in message:
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
        except ZrGasApiError:
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
        if result.get("message") == "token有效" or result.get("status") == 1:
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

        return ZrGasCustomerDetail(
            cust_code=info.get("custCode", cust_code),
            cust_name=info.get("custName", cust_name),
            cust_address=info.get("address", ""),
            balance=balance,
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
