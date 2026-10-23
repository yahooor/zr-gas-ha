#!/usr/bin/env python3
"""中燃在线 API 连通性验证脚本（独立运行，无需 Home Assistant）。

用法::

    # 基础连通性检查（无需凭据，不会发送真实短信）
    python scripts/verify_api.py

    # 用有效 Token 验证数据链路（从 HA 配置条目或抓包获取）
    python scripts/verify_api.py --token <accessToken> --user-id <userId> [--x-mas <x-mas-app-info>]

    # 交互式短信登录验证（真实发送短信）
    python scripts/verify_api.py --sms --mobile <手机号>
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import time

import aiohttp

BASE_URL = "https://zrds.95007.com"
SIGN_SALT = "yph1234567890"

PASS = "\033[32m✅\033[0m"
FAIL = "\033[31m❌\033[0m"


def sig(param: str, ts: str) -> str:
    return hashlib.md5(f"{param}{SIGN_SALT}{ts}".encode()).hexdigest()


def ts_ms() -> str:
    return str(int(time.time() * 1000))


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  {PASS if ok else FAIL} {name}" + (f" — {detail}" if detail else ""))
    return ok


async def probe(session: aiohttp.ClientSession) -> None:
    """无凭据探测：端点存活 + 网关行为。"""
    print("\n[1] 在线端登录链路")
    url = f"{BASE_URL}/controller/merchant/authCode.do?flag=13800000000&tn={ts_ms()}"
    async with session.get(url) as resp:
        data = await resp.read()
        check(
            "图形验证码端点",
            resp.status == 200 and len(data) > 100,
            f"{resp.status}, {len(data)} bytes",
        )

    async with session.post(
        f"{BASE_URL}/user/sendsms3.do",
        data={"codeKey": "13800000000", "codeKeyValue": "0000", "mobile": "13800000000"},
    ) as resp:
        r = await resp.json()
        check(
            "短信发送端点 (业务层可达)",
            str(r.get("status")) == "-1",
            f"status={r.get('status')} {r.get('message')}",
        )

    async with session.post(
        f"{BASE_URL}/user/xcxMobileUserLogin",
        data={
            "mobile": "13800000000",
            "code": "000000",
            "channelType": "6",
            "openId": "",
            "unionId": "",
        },
    ) as resp:
        r = await resp.json()
        check(
            "短信登录端点 (业务层可达)",
            str(r.get("status")) == "2",
            f"status={r.get('status')} {r.get('message')}",
        )

    print("\n[2] 缴费端登录链路（预期被网关拦截 status=255）")
    pay_headers = {
        "accessFrom": "yphpaymp",
        "platform": "mp-weixin",
        "Referer": "https://servicewechat.com/wx2082cbdc25b3b8e6/107/page-frame.html",
    }
    async with session.post(
        f"{BASE_URL}/crm_controller/user/sendSmsCode",
        data={
            "mobile": "13800000000",
            "timeStamp": ts_ms(),
            "signature": sig("13800000000", ts_ms()),
            "platform": "mp-weixin",
            "appId": "wx2082cbdc25b3b8e6",
        },
        headers=pay_headers,
    ) as resp:
        r = await resp.json()
        blocked = str(r.get("status")) == "255"
        check("sendSmsCode", blocked, f"status={r.get('status')} {r.get('message')}")

    print("\n[3] 数据端点（无 token 预期 255）")
    for name, path, extra in [
        ("getBindGasCustList", "/crm_controller/user/getBindGasCustList", {"userId": "1"}),
        (
            "findCustInfo",
            "/crm_controller/user/findCustInfoByCustCodeAndCustName",
            {"custCode": "0", "custName": "*"},
        ),
        ("getMeterInfo", "/crm_controller/user/getMeterInfo", {"custCode": "0", "envir": "2"}),
        (
            "getCustomerMoneyList",
            "/crm_controller/payfee/getCustomerMoneyList",
            {"custCode": "0", "startTime": "202501", "endTime": "202612"},
        ),
        (
            "queryBillHistory",
            "/crm_controller/gas/queryBillHistory",
            {"custCode": "0", "year": "2026"},
        ),
    ]:
        t = ts_ms()
        param = extra.get("custCode") or extra.get("userId") or "0"
        if "year" in extra:
            param += extra["year"]
        if "envir" in extra:
            param += extra["envir"]
        async with session.post(
            f"{BASE_URL}{path}",
            data={**extra, "timeStamp": t, "signature": sig(param, t)},
            headers=pay_headers,
        ) as resp:
            r = await resp.json()
            check(name, str(r.get("status")) == "255", f"status={r.get('status')}")


async def verify_token(
    session: aiohttp.ClientSession, token: str, user_id: str, x_mas: str
) -> None:
    """带 token 的数据链路验证。"""
    headers = {
        "accessToken": token,
        "userId": user_id,
        "platform": "mp-weixin",
        **({"x-mas-app-info": x_mas} if x_mas else {}),
    }
    print("\n[4] Token 校验 (checkMasInfo)")
    async with session.post(
        f"{BASE_URL}/wisdom/auth/checkMasInfo", json={}, headers=headers
    ) as resp:
        r = await resp.json()
        ok = r.get("code") == 200 or r.get("message") == "token有效"
        check("token", ok, str(r.get("message")))
        if not ok:
            print("  → Token 无效/过期，请重新获取")
            return

    print("\n[5] 账户发现")
    t = ts_ms()
    async with session.post(
        f"{BASE_URL}/crm_controller/user/getBindGasCustList",
        data={"userId": user_id, "timeStamp": t, "signature": sig(user_id, t)},
        headers=headers,
    ) as resp:
        r = await resp.json()
        items = r.get("data") or []
        if isinstance(items, dict):
            items = [items]
        check("绑定账户数", isinstance(items, list), f"{len(items)} 个")
        for it in items:
            print(f"     - {it.get('custCode')} {it.get('custName')}")

        if items:
            cust = items[0].get("custCode", "")
            print("\n[6] 客户详情 + 表具富化 + 账单（在线端字段映射）")
            t = ts_ms()
            async with session.post(
                f"{BASE_URL}/crm_controller/user/findCustInfoByCustCodeAndCustName",
                data={
                    "custCode": cust,
                    "custName": items[0].get("custName", ""),
                    "timeStamp": t,
                    "signature": sig(cust, t),
                },
                headers=headers,
            ) as resp:
                r = await resp.json()
                d = r.get("data") or {}
                if r.get("status") in (1, "1"):
                    check("余额 countMoney", True, f"{d.get('countMoney')} 元")
                    check("欠费 oweMoney", True, f"{d.get('oweMoney')}")
                    check("表读数 lastRecord", True, f"{d.get('lastRecord')}")
                else:
                    check("客户详情", False, str(r.get("message")))

            t = ts_ms()
            async with session.post(
                f"{BASE_URL}/crm_controller/user/getMeterInfo",
                data={
                    "custCode": cust,
                    "envir": "2",
                    "timeStamp": t,
                    "signature": sig(f"{cust}2", t),
                },
                headers=headers,
            ) as resp:
                r = await resp.json()
                if r.get("status") in (1, "1") and r.get("data"):
                    m = (r["data"] or [{}])[0] if isinstance(r["data"], list) else r["data"]
                    check(
                        "表具富化 getMeterInfo（token 跨源可用）",
                        True,
                        f"卡类型={m.get('cardType')} 位置={m.get('meterloc')}",
                    )
                else:
                    check(
                        "表具富化 getMeterInfo（token 跨源不可用，将自动降级）",
                        False,
                        str(r.get("message")),
                    )


async def sms_login(session: aiohttp.ClientSession, mobile: str) -> None:
    """交互式短信登录（真实发送短信）。"""
    print(f"\n[短信登录] 手机号 {mobile[:3]}****{mobile[-4:]}")
    url = f"{BASE_URL}/controller/merchant/authCode.do?flag={mobile}&tn={ts_ms()}"
    with open("captcha.png", "wb") as f:
        async with session.get(url) as resp:
            f.write(await resp.read())
    print("  验证码已保存 captcha.png — 请打开识别后输入:")
    captcha = input("  图形验证码: ").strip()
    async with session.post(
        f"{BASE_URL}/user/sendsms3.do",
        data={"codeKey": mobile, "codeKeyValue": captcha, "mobile": mobile},
    ) as resp:
        r = await resp.json()
        if str(r.get("status")) not in ("0", "1"):
            print(f"  ❌ 发送失败: {r.get('message')}")
            return
    code = input("  短信验证码: ").strip()
    async with session.post(
        f"{BASE_URL}/user/xcxMobileUserLogin",
        data={"mobile": mobile, "code": code, "channelType": "6", "openId": "", "unionId": ""},
    ) as resp:
        r = await resp.json()
        d = r.get("data") or {}
        if d.get("masToken"):
            print("  ✅ 登录成功")
            print(f"     accessToken = {d.get('masToken')}")
            uid = (d.get("data") or d).get("id") or ""
            print(f"     userId      = {uid}")
            print(f"     x-mas-app-info = aaahg10001/{d.get('sid', '')}")
        else:
            print(f"  ❌ {r.get('message')}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="中燃在线 API 验证")
    parser.add_argument("--token")
    parser.add_argument("--user-id")
    parser.add_argument("--x-mas", default="")
    parser.add_argument("--sms", action="store_true")
    parser.add_argument("--mobile")
    args = parser.parse_args()

    print(f"中燃在线 API 验证 — {BASE_URL}")
    async with aiohttp.ClientSession() as session:
        await probe(session)
        if args.token and args.user_id:
            await verify_token(session, args.token, args.user_id, args.x_mas)
        elif not args.sms:
            print("\n(带 --token <accessToken> --user-id <userId> 可验证数据链路)")
        if args.sms and args.mobile:
            await sms_login(session, args.mobile)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
