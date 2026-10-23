"""Constants for the 中燃在线 (ZR Gas) integration.

本集成合并了两个数据来源（同一后端 zrds.95007.com 的两个不同小程序）：

- **在线端 (mp)** — 即原 zr-gas-ha 集成。来自 uniapp 编译的小程序
  (Referer appid: wx19c4e29f3ef6b4a0)。登录走图形验证码 + 短信验证码
  (sendsms3.do + xcxMobileUserLogin)，返回 masToken/sid。字段映射经过
  实机验证（余额 = countMoney）。

- **缴费端 (pay)** — 即原 zr-gas 集成。来自缴费小程序
  (Referer appid: wx2082cbdc25b3b8e6, accessFrom: yphpaymp)。登录走
  sendSmsCode + verifySmsCode，返回 accessToken/userId。字段映射基于
  抓包（余额 = qtyBalance），短信登录未完全验证，推荐 Token 导入。
"""

DOMAIN = "zr_gas"

# ── 数据来源 ──────────────────────────────────────────────────────────
SOURCE_MP = "mp"  # 在线端（原 zr-gas-ha）
SOURCE_PAY = "pay"  # 缴费端（原 zr-gas）
SOURCES = {
    SOURCE_MP: "在线端",
    SOURCE_PAY: "缴费端",
}

# Config entry keys
CONF_SOURCE = "source"
CONF_ACCESS_TOKEN = "access_token"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_BALANCE_THRESHOLD = "balance_threshold"
CONF_USER_ID = "user_id"
CONF_X_MAS_APP_INFO = "x_mas_app_info"
CONF_MOBILE = "mobile"

# 阶梯气价配置项
CONF_TIER_2_START = "yearly_step_2_start_volume"  # 第二档起始量 (m³)
CONF_TIER_3_START = "yearly_step_3_start_volume"  # 第三档起始量 (m³)
CONF_TIER_1_PRICE = "year_step_1_price"  # 第一档单价 (CNY/m³)
CONF_TIER_2_PRICE = "year_step_2_price"  # 第二档单价 (CNY/m³)
CONF_TIER_3_PRICE = "year_step_3_price"  # 第三档单价 (CNY/m³)
CONF_TIER_CYCLE_START = "tier_cycle_start_md"  # 阶梯周期起始月日 (MM-DD)

# 账单查询范围配置项
CONF_BILL_YEARS = "bill_query_years"  # 查询年数
CONF_CUSTOMERS = "customers"  # 已绑定的燃气客户列表

# Defaults
DEFAULT_UPDATE_INTERVAL = 21600  # 6 hours in seconds
DEFAULT_BALANCE_THRESHOLD = 50.0  # CNY

# 阶梯气价默认值（张家界民用天然气）
DEFAULT_TIER_2_START = 400  # m³
DEFAULT_TIER_3_START = 1680  # m³
DEFAULT_TIER_1_PRICE = 2.99  # CNY/m³
DEFAULT_TIER_2_PRICE = 3.44  # CNY/m³
DEFAULT_TIER_3_PRICE = 4.34  # CNY/m³
DEFAULT_TIER_CYCLE_START = "01-01"  # 阶梯周期从1月1日起

# 账单查询默认值
DEFAULT_BILL_YEARS = 2  # 查询2年账单

BASE_URL = "https://zrds.95007.com"

# ── 在线端 (mp) 登录端点 — from JS reverse engineering ──────────────
ENDPOINT_CAPTCHA_IMG = "/controller/merchant/authCode.do"
ENDPOINT_SEND_SMS = "/user/sendsms3.do"
ENDPOINT_LOGIN_SMS = "/user/xcxMobileUserLogin"

# ── 共享/在线端数据端点 ──────────────────────────────────────────────
ENDPOINT_INIT = "/tracking/buriedPointEvent/add"
ENDPOINT_CHECK_TOKEN = "/wisdom/auth/checkMasInfo"
ENDPOINT_GET_CUSTOMERS = "/crm_controller/user/getBindGasCustList"
ENDPOINT_GET_CUSTOMER_INFO = "/crm_controller/user/findCustInfoByCustCodeAndCustName"
ENDPOINT_GET_BILLS = "/crm_controller/payfee/getCustomerMoneyList"

# ── 缴费端 (pay) 端点 — from packet capture ─────────────────────────
ENDPOINT_PAY_SEND_SMS = "/crm_controller/user/sendSmsCode"
ENDPOINT_PAY_VERIFY_SMS = "/crm_controller/user/verifySmsCode"
ENDPOINT_PAY_METER_INFO = "/crm_controller/user/getMeterInfo"
ENDPOINT_PAY_BILL_HISTORY = "/crm_controller/gas/queryBillHistory"

# ── 缴费记录 — 借鉴 ExceptionsOccur/hazr 项目（同一后端） ────────────
ENDPOINT_PAYMENT_LOG = "/crm_controller/payfee/getPaymentLogForHsh"

# 缴费端附加请求头（基于抓包）
PAY_EXTRA_HEADERS = {
    "accessFrom": "yphpaymp",
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
        "MicroMessenger/8.0.73(0x18004927) NetType/WIFI Language/zh_CN"
    ),
    "Referer": "https://servicewechat.com/wx2082cbdc25b3b8e6/107/page-frame.html",
}

# 签名盐值 — 从在线端网页 JS 逆向获取 (index.fd387e5a.js)
# JS 源码: e.signature = md5(param + "yph1234567890" + e.timeStamp)
# 缴费端盐值未独立验证，暂沿用同一盐值（同一后端基础设施）
SIGN_SALT = "yph1234567890"

# x-mas-app-info SID 前缀 (from loginOK handler in pages-login-login.js)
# JS: e.sid && (e.sid = "aaahg10001/" + e.sid)
X_MAS_SID_PREFIX = "aaahg10001/"
