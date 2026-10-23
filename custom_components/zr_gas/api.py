"""API clients for the 中燃在线 (ZR Gas) integration.

同一后端 (https://zrds.95007.com) 的两个小程序数据来源：

**在线端 (:class:`ZrGasMpApi`)** — 原 zr-gas-ha 集成，来自 uniapp 小程序
(Referer appid: wx19c4e29f3ef6b4a0)。2026-10 实测存活：
- GET  /controller/merchant/authCode.do → 真实验证码图片 ✅
- POST /user/sendsms3.do → status=-1 "图形验证码不正确"（业务层）✅
- POST /user/xcxMobileUserLogin → status=2 "请重新获取验证码"（业务层）✅

关键协议（逆向自网页 JS index.fd387e5a.js）：
- Salt: "yph1234567890"，签名 md5(param + salt + timeStamp)
- 登录返回 masToken + sid → 头部 x-mas-app-info: "aaahg10001/" + sid
- 表单编码（checkMasInfo 除外，用 JSON）

**缴费端 (:class:`ZrGasPayApi`)** — 原 zr-gas 集成，来自缴费小程序
(Referer appid: wx2082cbdc25b3b8e6, accessFrom: yphpaymp)。
2026-10 实测：登录端点 sendSmsCode/verifySmsCode 被网关在认证层
拦截（status=255，带完整小程序头也一样），**短信登录不可用**，
仅支持 Token 导入（accessToken + userId 抓包获取）。数据端点
（findCustInfo 的 qtyBalance 字段族 / getMeterInfo / queryBillHistory）
需有效 Token 后调用，字段映射基于原抓包数据。
"""

from __future__ import annotations

import datetime
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
    ENDPOINT_PAY_BILL_HISTORY,
    ENDPOINT_PAY_METER_INFO,
    ENDPOINT_PAYMENT_LOG,
    ENDPOINT_SEND_SMS,
    PAY_EXTRA_HEADERS,
    SIGN_SALT,
    SOURCE_MP,
    SOURCE_PAY,
    X_MAS_SID_PREFIX,
)
from .models import (
    ZrGasBill,
    ZrGasCustomer,
    ZrGasCustomerDetail,
    ZrGasMeterInfo,
    ZrGasPayment,
)

_LOGGER = logging.getLogger(__name__)


class ZrGasApiError(Exception):
    """Base exception for ZR Gas API errors."""


class ZrGasAuthError(ZrGasApiError):
    """Authentication error — token invalid or expired."""


class ZrGasSmsError(ZrGasApiError):
    """Error during SMS verification code flow."""


def _to_float(val: Any, default: float = 0.0) -> float:
    """Best-effort float conversion for API values."""
    try:
        return float(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def _to_int(val: Any, default: int = 0) -> int:
    """Best-effort int conversion for API values."""
    try:
        return int(float(val)) if val is not None else default
    except (ValueError, TypeError):
        return default


class ZrGasBaseApi:
    """两个数据来源共享的请求基础：签名、时间戳、状态码归一化。

    Subclasses provide source-specific headers via ``_extra_headers``
    and their own login/data methods.
    """

    source = ""  # SOURCE_MP / SOURCE_PAY, set by subclasses

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
            access_token: Access token from login response.
            user_id: User identifier (passed as header in most API calls).
            x_mas_app_info: x-mas-app-info header value (online source only).
        """
        self._session = session
        self._access_token = access_token
        self._user_id = user_id
        self._x_mas_app_info = x_mas_app_info
        # Independent session with a REAL CookieJar for the login flow.
        # HA's shared session (async_get_clientsession) uses DummyCookieJar
        # which drops cookies. The login flow requires cookies to persist
        # across GET captcha → POST sendsms → POST login, so the caller
        # should use ``set_login_session()`` to inject a session created
        # via ``async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar(unsafe=True))``.
        self._login_session: aiohttp.ClientSession | None = None

    # ── Credentials ────────────────────────────────────────────────

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

    # ── Login session management ───────────────────────────────────

    def set_login_session(self, session: aiohttp.ClientSession) -> None:
        """Set an independent session with a real CookieJar for login flow.

        Must be called before ``fetch_captcha_image()`` / ``send_sms_code()``
        / ``login_with_sms()`` so that JSESSIONID and other cookies persist
        across all three requests (online source only).
        """
        self._login_session = session

    def _get_login_session(self) -> aiohttp.ClientSession:
        """Return the login session if set, else the shared session."""
        if self._login_session is not None and not self._login_session.closed:
            return self._login_session
        return self._session

    async def close_login_session(self) -> None:
        """Close the independent login session after login is complete."""
        if self._login_session and not self._login_session.closed:
            await self._login_session.close()
        self._login_session = None

    # ── Signature helpers ──────────────────────────────────────────

    def _generate_signature(self, param: str, timestamp: str) -> str:
        """Generate an MD5 signature: md5(param + salt + timestamp)."""
        raw = f"{param}{SIGN_SALT}{timestamp}"
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _get_timestamp() -> str:
        """Return current timestamp in milliseconds as a string."""
        return str(int(time.time() * 1000))

    # ── 缴费记录（best-effort, 借鉴 hazr 项目的端点与参数） ─────────

    async def get_payment_log(self, cust_code: str, days: int = 180) -> list[ZrGasPayment]:
        """Query recent payment/recharge history (best-effort).

        POST /crm_controller/payfee/getPaymentLogForHsh
        params: custCode + startTime/endTime (YYYYMMDD) + plain signature
        （与 getCustomerMoneyList 同路径族同签名方式，任何来源 token 可尝试）。
        排序：按 payTime 降序（最新在前）。
        """
        now = datetime.datetime.now()
        end_time = now.strftime("%Y%m%d")
        start_time = (now - datetime.timedelta(days=days)).strftime("%Y%m%d")

        url = f"{BASE_URL}{ENDPOINT_PAYMENT_LOG}"
        timestamp = self._get_timestamp()
        signature = self._generate_signature(cust_code, timestamp)

        data = {
            "custCode": cust_code,
            "startTime": start_time,
            "endTime": end_time,
            "timeStamp": timestamp,
            "signature": signature,
        }

        result = await self._post(url, data)

        items = result.get("data") or []
        if isinstance(items, dict):
            items = [items]

        payments = [
            ZrGasPayment(
                pay_time=str(
                    item.get("payTime") or item.get("createTime") or item.get("time") or ""
                ),
                amount=_to_float(item.get("amount") or item.get("payFee") or item.get("money")),
                qty=_to_float(item.get("payQty") or item.get("qty")),
                pay_type=str(item.get("payType") or item.get("payTypeName") or ""),
            )
            for item in items
        ]
        payments.sort(key=lambda p: p.pay_time, reverse=True)
        return payments

    # ── Meter enrichment (best-effort, any source) ─────────────────

    async def get_meter_info(self, cust_code: str) -> ZrGasMeterInfo | None:
        """Query meter enrichment info (best-effort for any source).

        getMeterInfo 属缴费端小程序的端点，但与 getBindGasCustList 等
        在线端已在使用的端点同属 /crm_controller/* 网关路径族、同一套
        accessToken 头 — 在线端登录的 token 大概率同样可调通。因此对
        所有来源都尝试调用；失败由 Coordinator 捕获并降级为空，不影响
        主数据。

        Signature: md5(custCode + envir + salt + ts), envir="2".
        字段: meterNo / cardType / cardNo / ventDate / barCode / meterloc.
        """
        url = f"{BASE_URL}{ENDPOINT_PAY_METER_INFO}"
        timestamp = self._get_timestamp()
        signature = self._generate_signature(f"{cust_code}2", timestamp)

        data = {
            "custCode": cust_code,
            "envir": "2",
            "timeStamp": timestamp,
            "signature": signature,
        }

        result = await self._post(url, data)

        items = result.get("data") or []
        if isinstance(items, dict):
            items = [items]
        if not items:
            return None

        info = items[0]
        return ZrGasMeterInfo(
            meter_no=info.get("meterNo", ""),
            card_type=info.get("cardType", ""),
            card_no=info.get("cardNo", ""),
            vent_date=info.get("ventDate", ""),
            bar_code=info.get("barCode", ""),
            meter_loc=info.get("meterloc", ""),
        )

    # ── Request plumbing ───────────────────────────────────────────

    def _extra_headers(self) -> dict[str, str]:
        """Source-specific extra headers, merged into every request."""
        return {}

    async def _post(
        self,
        url: str,
        data: dict[str, Any],
        headers: dict[str, str] | None = None,
        as_json: bool = False,
    ) -> dict[str, Any]:
        """Send a POST request and return the normalized JSON response.

        The API uses two content types:
        - Most endpoints: application/x-www-form-urlencoded (data=)
        - checkMasInfo: application/json (json=)

        Raises:
            ZrGasAuthError: HTTP 401/403, status=255, or token/login errors.
            ZrGasApiError: Other non-success responses.
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
        request_headers.update(self._extra_headers())
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

        # Response status normalization.
        # NOTE: status may be int (1) or string ("1"); checkMasInfo instead
        # returns {"code": 200, "success": true} without "status".
        status = result.get("status")
        code = result.get("code")
        success = result.get("success")
        message = result.get("message", "")

        if status in (1, "1") or code in (200, "200") or success is True:
            return result

        # Gateway-level auth rejection (verified live: no-token requests to
        # /crm_controller/* return {"status": "255", "message": "认证失败..."})
        if str(status) == "255":
            raise ZrGasAuthError(f"Auth failed: {message or '认证失败'}")
        # Token invalid/expired based on response message
        # IMPORTANT: "token有效" means token IS valid, must NOT be treated as error
        if message and "token" in message.lower() and "有效" not in message:
            raise ZrGasAuthError(f"Auth failed: {message}")
        if "登录" in message and "成功" not in message:
            raise ZrGasAuthError(f"Auth failed: {message}")

        raise ZrGasApiError(f"API error (status={status}): {message}")


class ZrGasMpApi(ZrGasBaseApi):
    """在线端 API 客户端（原 zr-gas-ha，经实机验证可用）。

    登录流程（验证码 → 短信 → 登录）::

        api = ZrGasMpApi(session)
        api.set_login_session(login_session_with_real_cookiejar)
        await api.send_sms_code(mobile, "1234")     # 图形验证码
        await api.login_with_sms(mobile, "654321")  # 短信验证码

    或直接使用已有 Token::

        api = ZrGasMpApi(session, access_token="...", user_id="...",
                         x_mas_app_info="...")
    """

    source = SOURCE_MP

    # ── Login flow ─────────────────────────────────────────────────

    def get_captcha_url(self, mobile: str) -> str:
        """Return the captcha image URL for a mobile number.

        Verified live: returns a real 80x26 PNG image.
        """
        timestamp = str(int(time.time() * 1000))
        return f"{BASE_URL}{ENDPOINT_CAPTCHA_IMG}?flag={mobile}&tn={timestamp}"

    async def send_sms_code(self, mobile: str, captcha_code: str) -> None:
        """Send an SMS verification code (step 2 of login).

        POST /user/sendsms3.do with {codeKey, codeKeyValue, mobile}.

        Verified live error semantics:
          status=-1 → wrong captcha ("输入的图形验证码不正确")
          status=2  → captcha expired
        """
        url = f"{BASE_URL}{ENDPOINT_SEND_SMS}"
        data = {
            "codeKey": mobile,
            "codeKeyValue": captcha_code,
            "mobile": mobile,
        }

        try:
            login_session = self._get_login_session()

            cookie_str = ""
            for cookie in login_session.cookie_jar:
                cookie_str += f"{cookie.key}={cookie.value}(path={cookie['path']}) "
            _LOGGER.debug(
                "SMS send: mobile=%s****%s, code=****, session_cookies=[%s]",
                mobile[:3],
                mobile[-4:],
                cookie_str,
            )

            request_headers = {
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "*/*",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
            async with login_session.post(url, headers=request_headers, data=data) as resp:
                resp.raise_for_status()
                result = await resp.json()
        except ZrGasApiError:
            raise
        except Exception as err:
            raise ZrGasSmsError(f"Failed to send SMS code: {err}") from err

        status = result.get("status")
        message = result.get("message", "")
        # status=2 → verification code expired
        # status=-1 → wrong captcha / input error
        # NOTE: API may return status as string ("1") or int (1)
        if status in (2, "2"):
            raise ZrGasSmsError("发送验证码失败: 验证码已过期，请重新获取")
        if str(status) not in ("0", "1") and "成功" not in message:
            raise ZrGasSmsError(f"发送验证码失败: {message or '未知错误'}")

        _LOGGER.info("SMS code sent successfully to %s****%s", mobile[:3], mobile[-4:])

    async def login_with_sms(self, mobile: str, sms_code: str) -> dict[str, Any]:
        """Login with mobile + SMS code (step 3 of login).

        POST /user/xcxMobileUserLogin with
        {mobile, code, channelType: 6, openId: "", unionId: ""}.

        On success stores masToken / userId / x-mas-app-info internally.

        Verified live error semantics:
          status=2  → code expired ("请重新获取验证码")
          status=-1 → wrong code ("验证码输入不正确")
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
            async with login_session.post(url, headers=login_headers, data=data) as resp:
                resp.raise_for_status()
                result = await resp.json()
        except ZrGasApiError:
            raise
        except Exception as err:
            raise ZrGasAuthError(f"SMS login failed: {err}") from err

        status = result.get("status")
        message = result.get("message", "")
        _LOGGER.debug(
            "Login response: status=%s, message=%s, data_keys=%s",
            status,
            message,
            list((result.get("data") or {}).keys()),
        )

        if status in (2, "2"):
            raise ZrGasAuthError("登录失败: 验证码已过期，请重新获取")
        if status in (-1, "-1"):
            raise ZrGasAuthError(f"登录失败: {message or '验证码输入不正确'}")
        if str(status) not in ("0", "1") and "成功" not in message:
            raise ZrGasAuthError(f"登录失败: {message or '未知错误'}")

        # Extract credentials from response
        login_data = result.get("data") or {}
        mas_token = login_data.get("masToken") or result.get("masToken") or ""

        if not mas_token:
            raise ZrGasAuthError("Login succeeded but no masToken returned")

        sid = login_data.get("sid") or result.get("sid") or ""
        user_info = login_data.get("data") or login_data
        uid = str(user_info.get("id") or "")

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

    # ── Session / token ────────────────────────────────────────────

    async def init_request(self, user_id: str) -> bool:
        """Send a buried-point init request (registers the session).

        参数对齐小程序真实行为（借鉴 hazr 抓包: clickType=10, channelType=6）。
        Best-effort — failure is logged and ignored.
        """
        url = f"{BASE_URL}{ENDPOINT_INIT}"
        data = {
            "appUseType": "0",
            "clickType": "10",
            "eventType": "1",
            "channelType": "6",
            "userId": user_id,
        }

        try:
            result = await self._post(url, data)
            return str(result.get("status")) in ("0", "1")
        except Exception:
            _LOGGER.warning("Init request failed, continuing anyway")
            return False

    async def check_token(self) -> dict[str, Any]:
        """Validate the access token via POST /wisdom/auth/checkMasInfo.

        Verified live: reachable; requires accessToken/userId headers.
        """
        url = f"{BASE_URL}{ENDPOINT_CHECK_TOKEN}"
        result = await self._post(url, {}, as_json=True)

        if result.get("message") == "token有效" or result.get("status") in (1, "1"):
            return result

        raise ZrGasAuthError(f"Token validation failed: {result.get('message', 'unknown')}")

    # ── Data queries ───────────────────────────────────────────────

    async def get_bind_gas_cust_list(self, user_id: str) -> list[ZrGasCustomer]:
        """Get bound gas customer accounts. Signature: md5(userId+salt+ts).

        state="1" 参数对齐小程序真实请求（借鉴 hazr 抓包）。
        """
        url = f"{BASE_URL}{ENDPOINT_GET_CUSTOMERS}"
        timestamp = self._get_timestamp()
        signature = self._generate_signature(user_id, timestamp)

        data = {
            "userId": user_id,
            "state": "1",
            "timeStamp": timestamp,
            "signature": signature,
        }
        headers = {"userId": user_id}

        result = await self._post(url, data, headers=headers)

        items = result.get("data") or []
        if isinstance(items, dict):
            items = [items]

        return [
            ZrGasCustomer(
                cust_code=item.get("custCode", ""),
                cust_name=item.get("custName", ""),
            )
            for item in items
        ]

    async def get_cust_info(self, cust_code: str, cust_name: str) -> ZrGasCustomerDetail:
        """Query customer detail. Signature: md5(custCode+salt+ts).

        在线端字段映射（实机抓包确认）:
        - countMoney/newCountMoney → 余额 balance
        - address / oweMoney / awardMoney / lastRecord / qtyMeterBalance
          / purchTimes / lastRecordTime / meterNo / meterFormName / cardNo
          / compName / custStatus / fee
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

        balance_str = (
            info.get("countMoney") or info.get("newCountMoney") or info.get("balance") or "0"
        )

        return ZrGasCustomerDetail(
            cust_code=info.get("custCode", cust_code),
            cust_name=info.get("custName", cust_name),
            cust_address=info.get("address", ""),
            balance=_to_float(balance_str),
            owe_money=_to_float(info.get("oweMoney")),
            award_money=_to_float(info.get("awardMoney")),
            last_record=_to_float(info.get("lastRecord")),
            qty_meter_balance=_to_float(info.get("qtyMeterBalance")),
            purch_times=_to_int(info.get("purchTimes")),
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
        """Query billing records in a YYYYMM range.

        Signature: md5(custCode+salt+ts). Fields: recordMonth / curQty /
        receivable / price.
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
        return _parse_bill_items(result.get("data"))


class ZrGasPayApi(ZrGasBaseApi):
    """缴费端 API 客户端（原 zr-gas，仅支持 Token 导入）。

    2026-10 实测：sendSmsCode / verifySmsCode 登录端点被网关在认证层
    拦截（status=255，带完整小程序请求头亦然），短信登录不可用。
    请从缴费小程序抓包获取 accessToken + userId 后通过 Token 导入使用。

    字段映射与在线端的差异（基于原抓包）:
    - 余额 balance = qtyBalance（在线端为 countMoney）
    - 额外字段: newOweMoney / price(单价) / maxGas / custType
    - getMeterInfo 提供表具富化: ventDate / barCode / meterloc / cardType
    - 账单走 queryBillHistory（按年查询），而非 getCustomerMoneyList
    """

    source = SOURCE_PAY

    def _extra_headers(self) -> dict[str, str]:
        """缴费端小程序附加请求头（accessFrom 等，基于抓包）。"""
        return dict(PAY_EXTRA_HEADERS)

    # ── Token ──────────────────────────────────────────────────────

    async def check_token(self) -> dict[str, Any]:
        """Validate the token via getBindGasCustList.

        The login endpoints are gateway-blocked, so a successful
        (non-255) account discovery doubles as token validation.
        Raises ZrGasAuthError when the token is rejected.
        """
        customers = await self.get_bind_gas_cust_list(self._user_id)
        return {"message": "token有效", "customers": len(customers)}

    # ── Data queries ───────────────────────────────────────────────

    async def get_bind_gas_cust_list(self, user_id: str) -> list[ZrGasCustomer]:
        """Get bound gas customer accounts (shared endpoint with mp)."""
        url = f"{BASE_URL}{ENDPOINT_GET_CUSTOMERS}"
        timestamp = self._get_timestamp()
        signature = self._generate_signature(user_id, timestamp)

        data = {
            "userId": user_id,
            "state": "1",
            "timeStamp": timestamp,
            "signature": signature,
        }
        headers = {"userId": user_id}

        result = await self._post(url, data, headers=headers)

        items = result.get("data") or []
        if isinstance(items, dict):
            items = [items]

        return [
            ZrGasCustomer(
                cust_code=item.get("custCode", ""),
                cust_name=item.get("custName", ""),
            )
            for item in items
        ]

    async def get_cust_info(self, cust_code: str, cust_name: str = "") -> ZrGasCustomerDetail:
        """Query customer detail with pay-source field mapping.

        缴费端字段映射: balance = qtyBalance（缺失时回退 countMoney）。
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

        balance_str = info.get("qtyBalance") or info.get("countMoney") or info.get("balance") or "0"

        return ZrGasCustomerDetail(
            cust_code=info.get("custCode", cust_code),
            cust_name=info.get("custName", cust_name),
            cust_address=info.get("address", ""),
            balance=_to_float(balance_str),
            owe_money=_to_float(info.get("oweMoney")),
            new_owe_money=_to_float(info.get("newOweMoney")),
            award_money=_to_float(info.get("awardMoney")),
            gas_price=_to_float(info.get("price")),
            max_gas=_to_float(info.get("maxGas")),
            cust_type=info.get("custType", ""),
            last_record=_to_float(info.get("lastRecord")),
            qty_meter_balance=_to_float(info.get("qtyMeterBalance")),
            purch_times=_to_int(info.get("purchTimes")),
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
        """Query bills via queryBillHistory (year-by-year, pay source).

        The pay source has no period-range endpoint; the YYYYMM range is
        converted to a year span and each year queried separately.
        """
        try:
            start_year = int(start_time[:4])
            end_year = int(end_time[:4])
        except (ValueError, IndexError):
            start_year = end_year = int(end_time[:4]) if end_time[:4].isdigit() else 2026

        bills: list[ZrGasBill] = []
        for year in range(start_year, end_year + 1):
            url = f"{BASE_URL}{ENDPOINT_PAY_BILL_HISTORY}"
            timestamp = self._get_timestamp()
            signature = self._generate_signature(f"{cust_code}{year}", timestamp)

            data = {
                "custCode": cust_code,
                "year": str(year),
                "timeStamp": timestamp,
                "signature": signature,
            }

            result = await self._post(url, data)
            bills.extend(_parse_bill_items(result.get("data")))

        return bills


def _parse_bill_items(items: Any) -> list[ZrGasBill]:
    """Parse a bill list payload shared by both sources.

    Field fallbacks cover both programs' captures:
    period: recordMonth / period / billingCycle
    volume: curQty / usageVolume / gasVolume
    amount: receivable / usageAmount / payFee
    price:   price / unitPrice
    """
    if not items:
        return []
    if isinstance(items, dict):
        items = [items]

    bills: list[ZrGasBill] = []
    for item in items:
        period = item.get("recordMonth") or item.get("period") or item.get("billingCycle") or ""
        # Normalize period to YYYYMM (strip separators if present)
        period = period.replace("-", "").replace("/", "")[:6]

        bills.append(
            ZrGasBill(
                period=period,
                usage_volume=_to_float(
                    item.get("curQty") or item.get("usageVolume") or item.get("gasVolume")
                ),
                usage_amount=_to_float(
                    item.get("receivable") or item.get("usageAmount") or item.get("payFee")
                ),
                unit_price=_to_float(item.get("price") or item.get("unitPrice")),
            )
        )
    return bills
