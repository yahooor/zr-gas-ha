"""Constants for the 中燃在线 (ZR Gas) integration."""

DOMAIN = "zr_gas"

# Config entry keys
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

# Login flow endpoints (from JS reverse engineering: pages-login-login.js)
ENDPOINT_CAPTCHA_IMG = "/controller/merchant/authCode.do"
ENDPOINT_SEND_SMS = "/user/sendsms3.do"
ENDPOINT_LOGIN_SMS = "/user/xcxMobileUserLogin"

# Data query endpoints
ENDPOINT_INIT = "/tracking/buriedPointEvent/add"
ENDPOINT_CHECK_TOKEN = "/wisdom/auth/checkMasInfo"
ENDPOINT_GET_CUSTOMERS = "/crm_controller/user/getBindGasCustList"
ENDPOINT_GET_CUSTOMER_INFO = "/crm_controller/user/findCustInfoByCustCodeAndCustName"
ENDPOINT_GET_BILLS = "/crm_controller/payfee/getCustomerMoneyList"

# 签名盐值 — 从网页 JS 逆向获取 (index.fd387e5a.js)
# JS 源码: e.signature = md5(param + "yph1234567890" + e.timeStamp)
SIGN_SALT = "yph1234567890"

# x-mas-app-info SID 前缀 (from loginOK handler in pages-login-login.js)
# JS: e.sid && (e.sid = "aaahg10001/" + e.sid)
X_MAS_SID_PREFIX = "aaahg10001/"
