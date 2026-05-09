"""Constants for the 中燃在线 (ZR Gas) integration."""

DOMAIN = "zr_gas"
CONF_ACCESS_TOKEN = "access_token"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_BALANCE_THRESHOLD = "balance_threshold"
CONF_USER_ID = "user_id"

DEFAULT_UPDATE_INTERVAL = 21600  # 6 hours in seconds
DEFAULT_BALANCE_THRESHOLD = 50.0  # CNY

BASE_URL = "https://zrds.95007.com"

ENDPOINT_INIT = "/tracking/buriedPointEvent/add"
ENDPOINT_CHECK_TOKEN = "/wisdom/auth/checkMasInfo"
ENDPOINT_GET_CUSTOMERS = "/crm_controller/user/getBindGasCustList"
ENDPOINT_GET_CUSTOMER_INFO = "/crm_controller/user/findCustInfoByCustCodeAndCustName"
ENDPOINT_GET_BILLS = "/crm_controller/payfee/getCustomerMoneyList"

# 签名盐值 — 从网页 JS 逆向获取 (index.fd387e5a.js)
# JS 源码: e.signature = md5(param + "yph1234567890" + e.timeStamp)
SIGN_SALT = "yph1234567890"
