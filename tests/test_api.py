"""Tests for zr_gas.api — signature, status normalization, dual-source
field mapping, meter parsing and bill parsing."""

import hashlib

import pytest
from zr_gas.api import (
    ZrGasApiError,
    ZrGasAuthError,
    ZrGasBaseApi,
    ZrGasMpApi,
    ZrGasPayApi,
    _parse_bill_items,
)
from zr_gas.const import SIGN_SALT, SOURCE_MP, SOURCE_PAY

# ── Test doubles ──────────────────────────────────────────────────────


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.status = 200

    def raise_for_status(self):
        pass

    async def json(self):
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False


class _FakeSession:
    """Records post() calls and replays canned JSON payloads in order."""

    def __init__(self, payloads):
        # payloads: single dict or list (replayed in order, last one repeats)
        self._payloads = payloads if isinstance(payloads, list) else [payloads]
        self._i = 0
        self.calls: list[tuple[str, dict]] = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        payload = self._payloads[min(self._i, len(self._payloads) - 1)]
        self._i += 1
        return _FakeResponse(payload)


# ── Signature generation ──────────────────────────────────────────────


class TestGenerateSignature:
    """Tests for ZrGasBaseApi._generate_signature(param, timestamp)."""

    def _md5(self, raw: str) -> str:
        return hashlib.md5(raw.encode("utf-8")).hexdigest()

    def test_known_values(self):
        api = ZrGasMpApi(None)
        param = "test"
        timestamp = "1234567890"
        result = api._generate_signature(param, timestamp)
        expected = self._md5(f"{param}{SIGN_SALT}{timestamp}")
        assert result == expected
        # Also verify the raw string
        assert f"{param}{SIGN_SALT}{timestamp}" == "testyph12345678901234567890"

    def test_empty_param(self):
        api = ZrGasMpApi(None)
        result = api._generate_signature("", "9999999999")
        expected = self._md5("yph12345678909999999999")
        assert result == expected

    def test_salt_value(self):
        assert SIGN_SALT == "yph1234567890"

    def test_chinese_param(self):
        api = ZrGasMpApi(None)
        param = "用户123"
        ts = "1700000000000"
        result = api._generate_signature(param, ts)
        assert result == self._md5(f"{param}{SIGN_SALT}{ts}")

    def test_different_params_different_signatures(self):
        api = ZrGasMpApi(None)
        ts = "1234567890"
        assert api._generate_signature("param1", ts) != api._generate_signature("param2", ts)

    def test_different_timestamps_different_signatures(self):
        api = ZrGasMpApi(None)
        assert api._generate_signature("test", "1000") != api._generate_signature("test", "2000")

    def test_signature_is_32_chars_hex(self):
        api = ZrGasMpApi(None)
        sig = api._generate_signature("test", "12345")
        assert len(sig) == 32
        assert all(c in "0123456789abcdef" for c in sig)

    def test_shared_by_both_sources(self):
        """Both source clients share the base signature implementation."""
        mp = ZrGasMpApi(None)
        pay = ZrGasPayApi(None)
        assert mp._generate_signature("abc", "111") == pay._generate_signature("abc", "111")


# ── Response status normalization (verified live 2026-10) ────────────


class TestStatusNormalization:
    """_post must normalize int/string statuses and map 255 to auth error."""

    def _api(self, payload, source_cls=ZrGasMpApi):
        session = _FakeSession(payload)
        api = source_cls(session, access_token="t", user_id="u")
        return api, session

    @pytest.mark.asyncio
    async def test_status_int_1_success(self):
        api, _ = self._api({"status": 1, "message": "ok", "data": {}})
        result = await api._post("http://x", {})
        assert result["status"] == 1

    @pytest.mark.asyncio
    async def test_status_string_1_success(self):
        api, _ = self._api({"status": "1", "message": "ok", "data": {}})
        result = await api._post("http://x", {})
        assert result["status"] == "1"

    @pytest.mark.asyncio
    async def test_checkmas_style_code_200_success(self):
        """checkMasInfo returns {"code": 200, "success": true} without status."""
        api, _ = self._api({"code": 200, "success": True, "message": "token有效"})
        result = await api._post("http://x", {})
        assert result["message"] == "token有效"

    @pytest.mark.asyncio
    async def test_status_255_raises_auth_error(self):
        """Live-verified gateway rejection: {"status": "255", "message": "认证失败..."}"""
        api, _ = self._api({"status": "255", "message": "认证失败,请重新登录"})
        with pytest.raises(ZrGasAuthError):
            await api._post("http://x", {})

    @pytest.mark.asyncio
    async def test_other_status_raises_api_error(self):
        api, _ = self._api({"status": 5, "message": "业务错误"})
        with pytest.raises(ZrGasApiError):
            await api._post("http://x", {})

    @pytest.mark.asyncio
    async def test_pay_client_sends_extra_headers(self):
        """缴费端 requests must carry accessFrom/Referer from const."""
        api, session = self._api({"status": 1, "data": {}}, ZrGasPayApi)
        await api._post("http://x", {})
        headers = session.calls[0][1]["headers"]
        assert headers["accessFrom"] == "yphpaymp"
        assert "wx2082cbdc25b3b8e6" in headers["Referer"]

    @pytest.mark.asyncio
    async def test_mp_client_no_access_from(self):
        api, session = self._api({"status": 1, "data": {}})
        await api._post("http://x", {})
        headers = session.calls[0][1]["headers"]
        assert "accessFrom" not in headers


# ── 双源字段映射 (field mapping differs between sources) ─────────────


class TestMpCustInfoMapping:
    """在线端: balance = countMoney."""

    @pytest.mark.asyncio
    async def test_balance_from_count_money(self):
        session = _FakeSession(
            {
                "status": 1,
                "data": {
                    "custCode": "C001",
                    "custName": "张*",
                    "address": "某小区",
                    "countMoney": "88.50",
                    "oweMoney": "0",
                    "awardMoney": "5.00",
                    "lastRecord": "1234.5",
                    "qtyMeterBalance": "30",
                    "purchTimes": "12",
                    "meterNo": "M-001",
                    "compName": "中燃张家界",
                },
            }
        )
        api = ZrGasMpApi(session, access_token="t", user_id="u")
        detail = await api.get_cust_info("C001", "张*")

        assert detail.balance == 88.50
        assert detail.cust_code == "C001"
        assert detail.cust_address == "某小区"
        assert detail.award_money == 5.00
        assert detail.purch_times == 12
        assert detail.meter_no == "M-001"
        # 在线端不提供的新字段默认为空
        assert detail.gas_price == 0.0
        assert detail.max_gas == 0.0
        assert detail.new_owe_money == 0.0


class TestPayCustInfoMapping:
    """缴费端: balance = qtyBalance（与在线端的 countMoney 不同）."""

    @pytest.mark.asyncio
    async def test_balance_from_qty_balance(self):
        session = _FakeSession(
            {
                "status": 1,
                "data": {
                    "custCode": "C001",
                    "custName": "张*",
                    "address": "某小区",
                    "qtyBalance": "66.66",
                    "countMoney": "999",  # 不得误作余额
                    "newOweMoney": "1.20",
                    "price": "2.99",
                    "maxGas": "500",
                    "custType": "民用",
                },
            }
        )
        api = ZrGasPayApi(session, access_token="t", user_id="u")
        detail = await api.get_cust_info("C001", "张*")

        assert detail.balance == 66.66
        assert detail.new_owe_money == 1.20
        assert detail.gas_price == 2.99
        assert detail.max_gas == 500.0
        assert detail.cust_type == "民用"


# ── 表具富化信息 (getMeterInfo, best-effort for any source) ──────────


class TestMeterInfo:
    @pytest.mark.asyncio
    async def test_parse_meter_list(self):
        session = _FakeSession(
            {
                "status": 1,
                "data": [
                    {
                        "meterNo": "M-9",
                        "cardType": "CPU卡",
                        "cardNo": "K-1",
                        "ventDate": "2019-06-01",
                        "barCode": "B-123",
                        "meterloc": "厨房",
                    }
                ],
            }
        )
        api = ZrGasMpApi(session, access_token="t", user_id="u")
        meter = await api.get_meter_info("C001")

        assert meter is not None
        assert meter.meter_no == "M-9"
        assert meter.card_type == "CPU卡"
        assert meter.vent_date == "2019-06-01"
        assert meter.bar_code == "B-123"
        assert meter.meter_loc == "厨房"

    @pytest.mark.asyncio
    async def test_empty_meter_list_returns_none(self):
        session = _FakeSession({"status": 1, "data": []})
        api = ZrGasPayApi(session, access_token="t", user_id="u")
        assert await api.get_meter_info("C001") is None

    @pytest.mark.asyncio
    async def test_signature_includes_envir(self):
        """getMeterInfo 签名参数应为 custCode + envir("2")."""
        session = _FakeSession({"status": 1, "data": []})
        api = ZrGasPayApi(session, access_token="t", user_id="u")
        await api.get_meter_info("C001")
        _url, kwargs = session.calls[0]
        data = kwargs["data"]
        assert data["envir"] == "2"
        expected = hashlib.md5(f"C0012{SIGN_SALT}{data['timeStamp']}".encode()).hexdigest()
        assert data["signature"] == expected


# ── 账单解析（两来源端点不同、字段归一化） ────────────────────────────


class TestParseBillItems:
    def test_mp_fields(self):
        bills = _parse_bill_items(
            [
                {"recordMonth": "202610", "curQty": "12.5", "receivable": "37.38", "price": "2.99"},
            ]
        )
        assert len(bills) == 1
        assert bills[0].period == "202610"
        assert bills[0].usage_volume == 12.5
        assert bills[0].usage_amount == 37.38
        assert bills[0].unit_price == 2.99

    def test_pay_fallback_fields(self):
        """缴费端字段名兜底: usageVolume/usageAmount/unitPrice."""
        bills = _parse_bill_items(
            [
                {"period": "2026-09", "usageVolume": "10", "usageAmount": "30", "unitPrice": "3.0"},
            ]
        )
        assert bills[0].period == "202609"  # "-" 被归一化去掉
        assert bills[0].usage_volume == 10.0
        assert bills[0].usage_amount == 30.0
        assert bills[0].unit_price == 3.0

    def test_none_returns_empty(self):
        assert _parse_bill_items(None) == []

    def test_single_dict_wrapped(self):
        bills = _parse_bill_items(
            {"recordMonth": "202610", "curQty": 1, "receivable": 3, "price": 3}
        )
        assert len(bills) == 1

    def test_invalid_numbers_become_zero(self):
        bills = _parse_bill_items([{"recordMonth": "202610", "curQty": "abc", "receivable": None}])
        assert bills[0].usage_volume == 0.0
        assert bills[0].usage_amount == 0.0


class TestPayBillHistory:
    @pytest.mark.asyncio
    async def test_year_range_queries_each_year(self):
        """YYYYMM 范围被换算为年份区间，逐年调用 queryBillHistory."""
        session = _FakeSession(
            [
                {
                    "status": 1,
                    "data": [{"recordMonth": "202510", "curQty": "5", "receivable": "15"}],
                },
                {
                    "status": 1,
                    "data": [{"recordMonth": "202610", "curQty": "8", "receivable": "24"}],
                },
            ]
        )
        api = ZrGasPayApi(session, access_token="t", user_id="u")
        bills = await api.get_customer_money_list("C001", "202510", "202610")

        assert len(session.calls) == 2
        assert "queryBillHistory" in session.calls[0][0]
        assert "queryBillHistory" in session.calls[1][0]
        assert session.calls[0][1]["data"]["year"] == "2025"
        assert session.calls[1][1]["data"]["year"] == "2026"
        assert len(bills) == 2
        assert bills[0].period == "202510"
        assert bills[1].period == "202610"


# ── 来源标识 ──────────────────────────────────────────────────────────


class TestSourceAttribute:
    def test_source_constants(self):
        assert ZrGasMpApi(None).source == SOURCE_MP
        assert ZrGasPayApi(None).source == SOURCE_PAY

    def test_base_source_empty(self):
        assert ZrGasBaseApi(None).source == ""


# ── 缴费记录（借鉴 hazr 的 getPaymentLogForHsh） ─────────────────────


class TestPaymentLog:
    @pytest.mark.asyncio
    async def test_parse_and_sort_desc(self):
        session = _FakeSession(
            {
                "status": 1,
                "data": [
                    {
                        "payTime": "2026-03-15 10:00:00",
                        "amount": "100",
                        "payQty": "30",
                        "payType": "微信",
                    },
                    {
                        "payTime": "2026-08-01 09:00:00",
                        "amount": "200",
                        "payQty": "60",
                        "payType": "支付宝",
                    },
                ],
            }
        )
        api = ZrGasMpApi(session, access_token="t", user_id="u")
        payments = await api.get_payment_log("C001")

        assert len(payments) == 2
        # 按时间降序（最新在前）
        assert payments[0].pay_time == "2026-08-01 09:00:00"
        assert payments[0].amount == 200.0
        assert payments[0].qty == 60.0
        assert payments[1].amount == 100.0

    @pytest.mark.asyncio
    async def test_date_range_params(self):
        session = _FakeSession({"status": 1, "data": []})
        api = ZrGasPayApi(session, access_token="t", user_id="u")
        await api.get_payment_log("C001", days=180)
        _url, kwargs = session.calls[0]
        data = kwargs["data"]
        assert "getPaymentLogForHsh" in _url
        assert len(data["startTime"]) == 8  # YYYYMMDD
        assert len(data["endTime"]) == 8
        # 签名与 getCustomerMoneyList 同族（md5(custCode+salt+ts)）
        import hashlib as _h

        expected = _h.md5(f"C001{SIGN_SALT}{data['timeStamp']}".encode()).hexdigest()
        assert data["signature"] == expected

    @pytest.mark.asyncio
    async def test_empty_returns_empty_list(self):
        session = _FakeSession({"status": 1, "data": None})
        api = ZrGasMpApi(session, access_token="t", user_id="u")
        assert await api.get_payment_log("C001") == []


# ── v2.0.3: 实测原始返回结构（payGasCheckList / timeope / received） ──


class TestRealPayloadMappings:
    """基于 2026-10 实机抓包的真实返回结构。"""

    @pytest.mark.asyncio
    async def test_money_list_payload_with_pay_gas_check_list(self):
        """data 为对象、账单藏于 payGasCheckList（实测结构）。"""
        session = _FakeSession(
            {
                "status": 1,
                "data": {
                    "custCode": "C1",
                    "balance": ".48",
                    "payGasCheckList": [
                        {
                            "recordMonth": "202608",
                            "curQty": "73",
                            "receivable": "0.00",
                            "received": "300.03",
                            "gasFee": "300.03",
                        },
                        {
                            "recordMonth": "202605",
                            "curQty": "49",
                            "receivable": "0.00",
                            "received": "201.39",
                            "gasFee": "201.39",
                        },
                    ],
                },
            }
        )
        api = ZrGasMpApi(session, access_token="t", user_id="u")
        bills = await api.get_customer_money_list("C1", "202501", "202612")

        assert len(bills) == 2
        assert bills[0].period == "202608"
        assert bills[0].usage_volume == 73.0
        # 预付费账户 receivable=0 → 落到 received 实收
        assert bills[0].usage_amount == 300.03

    @pytest.mark.asyncio
    async def test_payment_log_real_field_names(self):
        """缴费记录实测字段: timeope / paytypedesc / qty=null / amount。"""
        session = _FakeSession(
            {
                "status": 1,
                "data": [
                    {
                        "qty": None,
                        "amount": "300.00",
                        "recordmonth": "202607",
                        "paytypedesc": "微信扫码支付",
                        "timeope": "2026-07-30 10:41:51",
                    }
                ],
            }
        )
        api = ZrGasMpApi(session, access_token="t", user_id="u")
        payments = await api.get_payment_log("C1")

        assert payments[0].pay_time == "2026-07-30 10:41:51"
        assert payments[0].pay_type == "微信扫码支付"
        assert payments[0].amount == 300.0

    @pytest.mark.asyncio
    async def test_mp_cust_info_max_gas(self):
        """在线端实测也返回 maxGas/custType/price。"""
        session = _FakeSession(
            {
                "status": 1,
                "data": {
                    "custCode": "C1",
                    "countMoney": "0.48",
                    "maxGas": "9999",
                    "custType": "01",
                    "price": None,
                    "awardMoney": "0",
                },
            }
        )
        api = ZrGasMpApi(session, access_token="t", user_id="u")
        detail = await api.get_cust_info("C1", "*")

        assert detail.max_gas == 9999.0
        assert detail.cust_type == "01"
        assert detail.gas_price == 0.0  # price=null → 0（未知）
        assert detail.award_money == 0.0  # 真实 0
