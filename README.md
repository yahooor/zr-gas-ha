# 中燃在线 - Home Assistant 集成

[![HACS Custom][hacs-shield]][hacs]
[![GitHub Release][release-shield]][release]

Home Assistant 自定义集成，用于从**中燃在线**平台获取燃气余额、月度用量和费用数据。

## 功能特性

- **余额监控** — 实时查看燃气账户余额（元）
- **月度用量** — 显示当月累计用气量（m³）
- **月度费用** — 显示当月累计费用（元）
- **欠费提醒** — 显示账户欠费金额
- **表读数** — 显示累计表读数和气量余额
- **购气统计** — 显示累计购气次数和最后抄表日期
- **阶梯气价** — 年度累计用量 + 三档阶梯计价 + 当前阶梯信息
- **月度/年度统计** — 历史用气量和费用按月/年汇总
- **多账户支持** — 自动发现绑定的所有燃气账户
- **定时刷新** — 默认每 6 小时自动更新（可配置）
- **Token 过期提醒** — 自动检测并引导重新认证
- **Energy Dashboard** — 用量数据支持接入 HA 能源面板
- **前端卡片** — 自定义燃气卡片，直观展示所有数据

## 安装

### 方式一：HACS 自定义仓库（推荐）

1. 在 HACS 中点击 **⋮** → **自定义仓库**
2. 填入仓库地址：`https://github.com/yahooor/zr-gas-ha`
3. 类别选择 **Integration**
4. 点击 **添加** → 搜索 **"中燃在线"** → 安装
5. 重启 Home Assistant

### 方式二：手动安装

1. 从 [Releases](https://github.com/yahooor/zr-gas-ha/releases) 下载最新版本 zip
2. 解压到 HA 配置目录的 `custom_components/` 下（确保目录结构为 `custom_components/zr_gas/`）
3. 重启 Home Assistant

## 配置

### 配置步骤

**方式一：短信验证码登录（推荐）**

1. 进入 **设置** → **设备与服务** → **添加集成**
2. 搜索 **"中燃在线"**
3. 选择认证方式：**sms**
4. 输入注册时使用的 **手机号码**
5. **图形验证码步骤**：点击页面中的链接，在新标签页打开验证码图片 → 识别后填入输入框 → 点击提交发送短信
6. **短信验证码步骤**：输入收到的短信验证码 → 提交登录
7. 系统自动发现绑定的燃气账户
8. 配置完成！

**方式二：Token 直接导入（高级）**

适用于已通过其他方式获取 accessToken 的用户（如抓包工具）。

1. 进入 **设置** → **设备与服务** → **添加集成**
2. 搜索 **"中燃在线"**
3. 选择认证方式：**token**
4. 填入 **accessToken**、**userId**（必填），**x-mas-app-info** 和 **手机号**（选填）
5. 系统验证 Token 有效性 → 自动发现绑定的燃气账户
6. 配置完成！

> **说明**: 推荐使用短信验证码登录，无需抓包工具。Token 过期后会自动提示重新验证。

### 可选配置

在集成选项中可以修改：

| 选项 | 默认值 | 说明 |
|------|--------|------|
| 刷新间隔 | 21600 秒 (6小时) | 数据更新频率，最小 300 秒 |
| 余额预警阈值 | 50 元 | 余额低于此值时触发通知 |
| 账单查询年数 | 2 | 查询历史账单的年数范围（1-5年） |
| 第二档起始量 | 400 m³ | 阶梯气价第二档年用气量起点 |
| 第三档起始量 | 1680 m³ | 阶梯气价第三档年用气量起点 |
| 第一档单价 | 2.99 元/m³ | 阶梯气价第一档单价 |
| 第二档单价 | 3.44 元/m³ | 阶梯气价第二档单价 |
| 第三档单价 | 4.34 元/m³ | 阶梯气价第三档单价 |
| 阶梯周期起始月日 | 01-01 | 阶梯气价年度周期起始日期（MM-DD） |

## 传感器

每个燃气账户会创建以下传感器：

| 传感器 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| 余额 | monetary | CNY | 当前账户余额 |
| 月用量 | gas | m³ | 当月累计用气量 |
| 月费用 | monetary | CNY | 当月累计费用 |
| 欠费金额 | monetary | CNY | 账户欠费金额 |
| 表读数 | gas | m³ | 累计表读数 |
| 气量余额 | gas | m³ | 剩余气量 |
| 购气次数 | — | 次 | 累计购气次数 |
| 最后抄表日期 | timestamp | — | 上次抄表时间 |
| 年度累计用量 | gas | m³ | 当前阶梯周期的累计用气量 |

每个传感器附带以下设备属性：燃气编号、客户名、用气地址、燃气公司、燃气表号、表型号、卡号、费用编号、客户状态

**年度累计用量传感器** 额外提供以下 attributes：
- `current_tier`: 当前阶梯档位（1/2/3）
- `current_tier_price`: 当前阶梯单价（元/m³）
- `tier_cycle_start`: 当前阶梯周期起始日期
- `monthly_stats`: 月度统计列表 `[{"month": "2026-01", "gas_num": 12.5, "gas_cost": 37.38}, ...]`
- `yearly_stats`: 年度统计列表 `[{"year": "2026", "gas_num": 150.2, "gas_cost": 449.10}, ...]`

## 前端卡片

集成附带自定义前端卡片 `zr-gas-card`，可直观展示燃气数据。

### 安装卡片

1. 将 `www/zr_gas_card/zr-gas-card.js` 复制到 HA 配置目录 `www/zr_gas_card/`
2. 进入 **设置** → **仪表板** → ⋮ → **资源** → **添加资源**
   - URL: `/local/zr_gas_card/zr-gas-card.js`
   - 类型: JavaScript Module
3. 重启 Home Assistant

### 使用卡片

在仪表板中添加自定义卡片：

```yaml
type: custom:zr-gas-card
entity: sensor.zhong_ran_ran_qi_8854_balance
show_usage: true    # 显示用量统计（默认 true）
show_meter: true    # 显示表信息（默认 true）
low_threshold: 50   # 余额预警阈值（默认 50 元）
```

## 技术细节

- **API 签名**: `md5(param + salt + timestamp)`
- **请求格式**: `application/x-www-form-urlencoded`
- **零外部依赖**: 仅使用 HA 内置库（aiohttp、hashlib）
- **最低 HA 版本**: 2024.1.0

## 更新日志

### v0.10.2 — 移除冗余 state_class + HACS 配置优化

**代码清理：**
- **移除**: `sensor.py` — monthly_usage/monthly_cost/owe_money 的 `state_class` 字段（无 state_class 时 HA 不参与长期统计，避免月度切换时的异常行为）

**改进：**
- **新增**: `hacs.json` — 添加 `zip_release: true` + `filename` 配置，HACS 自动识别 Release zip 文件

### v0.10.1 — 代码审查修复（8 项修复）

**Bug 修复：**
- **修复**: `__init__.py` — `datetime.now()` → `dt_util.now()`（时区修正）
- **修复**: `sensor.py` — balance 传感器 `state_class=TOTAL` → `MEASUREMENT`（余额非累计量）
- **修复**: `sensor.py` — monthly_usage/cost `state_class=TOTAL` → `MEASUREMENT`（月切换避免负增量）
- **修复**: `__init__.py` — `_calculate_annual_usage` 返回 4-tuple，消除 cycle_start 重复计算
- **修复**: `config_flow.py` — OptionsFlow 阶梯参数验证（tier3>tier2、MM-DD格式）
- **修复**: `api.py` — debug 日志遮蔽手机号和验证码
- **修复**: `__init__.py` — bill 列表排序保证（sort by period, reverse）
- **修复**: `const.py` — "customers" 提取为 `CONF_CUSTOMERS` 常量

### v0.10.0 — 阶梯气价 + 历史统计 + 费用反算

**新功能：**
- **新增年度累计用量传感器** — 显示当前阶梯周期的累计用气量（m³），包含当前阶梯档位和单价
- **新增阶梯气价系统** — 三档年度阶梯计价（可配置各档起始量和单价），支持可配置阶梯周期起始日
- **新增月度/年度统计** — 年度累计用量传感器附带 `monthly_stats` 和 `yearly_stats` attributes，按月/年汇总历史用气量和费用
- **新增费用反算用气量** — `TierConfig.calculate_usage_from_cost()` 方法，根据费用和当前阶梯价格反算实际用气量（处理跨阶梯场景）
- **新增账单查询范围配置** — 可配置查询 1-5 年历史账单（默认 2 年），在 Options 中设置
- **新增阶梯气价配置项** — OptionsFlow 新增 7 个配置项：三档起始量、三档单价、阶梯周期起始月日

**改进：**
- 阶梯气价默认值适配张家界民用天然气（一档 2.99 元/m³、二档 3.44 元/m³、三档 4.34 元/m³）
- 翻译文件（中/英）同步更新，包含新增传感器和配置项翻译

### v0.9.1 — 代码清理

**代码清理：**
- **移除**: `api.py` 中未使用的 `import base64`
- **移除**: `api.py` 中多余的 `self._salt` 实例变量，改用 `SIGN_SALT` 常量
- **移除**: `api.py` 中已废弃的 `fetch_captcha_image()` 方法（已由 config_flow 的 `_fetch_and_save_captcha` 替代）
- **修复**: `api.py` 中 `login_with_sms` 的 `login_data`/`mas_token` 重复赋值逻辑
- **修复**: `api.py` 中 `init_request` 状态检查从 `== 1` 改为 `str(status) in ("0", "1")`，兼容字符串/整数返回
- **移除**: `config_flow.py` 中未使用的 `_get_captcha_local_url()` 函数
- **移除**: `config_flow.py` 中所有内联 import（`import time`、`import aiohttp as _aiohttp`），统一到顶层
- **移除**: `config_flow.py` 中重复的 `import os`
- **补充**: `config_flow.py` 添加 `HomeAssistant` 类型导入

### v0.9.0 — Bug 修复 + 代码清理

**Bug 修复：**
- **修复**: 最后抄表日期传感器 (`TIMESTAMP`) 崩溃 — API 返回日期字符串 `"2026-04-21"` 需解析为带时区的 `datetime` 对象
- **修复**: sensor.py 和 button.py 的 `ZrGasDataUpdateCoordinator` 导入改用 `TYPE_CHECKING` 保护，避免潜在循环导入

**代码清理：**
- **移除**: `api.py` 中未使用的 `_post_raw` 死代码

### v0.8.0 — 5 个新传感器 + Bug 修复 + 前端卡片

**新功能：**
- **新增 5 个传感器**：欠费金额、表读数、气量余额、购气次数、最后抄表日期
- **新增设备属性**：燃气编号、客户名、地址、燃气公司、表号、表型号、卡号等 10 个属性
- **新增动态设备信息**：设备页面自动显示燃气公司名、表型号、表号、卡号
- **新增前端卡片**：`zr-gas-card` 自定义卡片，展示余额/用量/表信息

**Bug 修复：**
- **修复**: API `status` 字段兼容字符串 `"1"` 和整数 `1`，解决 `"API error (status=1): 查询成功"` 误报
- **修复**: `"token有效"` 不再被误判为认证失败
- **修复**: `CURRENCY_YUAN` 在 HA 新版本中已移除，改用 `"CNY"` 字符串
- **修复**: `_abort_if_already_configured()` 改为 `_abort_if_unique_id_configured()` 适配 HA 2024+
- **修复**: Sensor `state_class` 从 `MEASUREMENT` 改为 `TOTAL`，适配 `MONETARY`/`GAS` 设备类
- **修复**: `config_flow.py` 移除 `aiofiles` 依赖，改用 `hass.async_add_executor_job()` 写文件

### v0.7.1 — 修复 aiofiles 依赖问题

- **修复**: `config_flow.py` 移除 `aiofiles` 依赖，改用 `hass.async_add_executor_job()` 写文件，兼容 HA 默认环境
- **背景**: v0.7.0 使用了 `aiofiles`，但 HA 默认不含此库，会导致集成加载失败

### v0.7.0 — SMS 登录流程修复

- **修复**: 使用 `async_create_clientsession` + `aiohttp.CookieJar(unsafe=True)` 创建带真实 CookieJar 的独立 session
- **修复**: 确保登录三步流程（captcha → sendsms → login）共享同一 session/cookie，JSESSIONID 正确传递
- **修复**: `login_with_sms` 状态码判断 — status=2(验证码过期)、status=-1(验证码错误)、status=0/1(成功)
- **修复**: `send_sms_code` 增加 status=2 过期判断
- **修复**: Reauth 流程完成后正确关闭独立 session
- **问题根因**: HA 的 `async_get_clientsession` 使用 DummyCookieJar，所有 cookie 在请求间被丢弃

### v0.6.2 — Token 导入流程修复

- **修复**: Token 导入验证从 `init_request()` 改为 `check_token()`，更精准验证 token 有效性
- **修复**: `init_request` 异常从仅捕获 `ZrGasApiError` 改为捕获 `Exception`，避免非预期错误阻断流程
- **修复**: Discover 流程中 `init_request` 失败不再阻断后续账户发现，拆分为独立 try 块

### v0.6.1 — 代码审查修复

- **修复**: issue_registry 重复创建且 token 恢复后未清除的问题
- **修复**: Reauth 流程中 `entry_id` 缺失导致 KeyError 崩溃
- **修复**: 月度用量传感器 `state_class` 从 `TOTAL_INCREASING` 改为 `MEASUREMENT`，避免月度重置时统计异常
- **修复**: 账单数据精确匹配当前月份，避免取到历史账单
- **清理**: 移除未使用的 `fetch_captcha_image`、`encode_captcha_image` 死代码
- **清理**: 移除未使用的 `CannotConnect`、`InvalidAuth` 异常类
- **改进**: Coordinator 数据更新成功时自动清除 token 过期 issue
- **改进**: 增加数据获取成功的调试日志

### v0.5.0

- **重构**: Config Flow 拆分图形验证码与短信验证码为独立步骤
  - 步骤1: 输入手机号
  - 步骤2: 点击链接打开验证码图片 → 输入验证码 → 提交发送短信
  - 步骤3: 输入短信验证码完成登录
- **重构**: Reauth 流程同步拆分（reauth_captcha → reauth_sms_code）
- **改进**: 发送短信失败时自动刷新验证码链接
- **改进**: Config Flow MINOR_VERSION 升至 3

### v0.4.2

- **修复**: 验证码图片在 HA Config Flow 中无法显示
  - 放弃 base64 data URI 和自定义 HTTP 端点方案
  - 改为提供验证码外部链接，用户点击链接在新标签页打开图片，手动识别后填回
  - 移除 `views.py`（不再需要自定义 HTTP 端点）

### v0.4.1

- **修复**: 验证码图片仍无法显示 — 改用 HA 自定义 HTTP 端点提供验证码图片

### v0.3.0

- **修复**: Config Flow 验证码图片无法显示 — 改为服务端获取并嵌入 base64 data URI

### v0.2.0

- **新增**: 短信验证码登录流程（手机号 + 图形验证码 + 短信验证码）
- **新增**: Token 过期后 Reauth 短信重新认证

### v0.1.0

- 初始版本，支持 accessToken 直接接入

## 致谢

- [alickglyn](https://bbs.hassbian.com/thread-30786-1-1.html) — 原始 API 逆向分析
- [gao19970120](https://bbs.hassbian.com/thread-31008-1-1.html) — Node-RED + MQTT 方案参考
- [ha_hfcrgas](https://github.com/Cyborg2017/ha_hfcrgas) — SensorEntityDescription 模式参考
- [hztowngas](https://github.com/palafin02back/hztowngas) — Coordinator 和 Session 管理参考

## 免责声明

本项目仅供学习和研究使用。API 接口通过逆向工程获取，非官方公开接口，可能随时变更。使用者需自行承担相关风险。

[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs]: https://hacs.xyz/docs/setup/download#add-custom-repository
[release-shield]: https://img.shields.io/github/v/release/yahooor/zr-gas-ha
[release]: https://github.com/yahooor/zr-gas-ha/releases
