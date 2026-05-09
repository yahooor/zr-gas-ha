"""Constants for the 中燃在线 (ZR Gas) integration."""

DOMAIN = "zr_gas"

# Config entry keys
CONF_ACCESS_TOKEN = "access_token"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_BALANCE_THRESHOLD = "balance_threshold"
CONF_USER_ID = "user_id"
CONF_X_MAS_APP_INFO = "x_mas_app_info"
CONF_MOBILE = "mobile"

# Defaults
DEFAULT_UPDATE_INTERVAL = 21600  # 6 hours in seconds
DEFAULT_BALANCE_THRESHOLD = 50.0  # CNY

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
