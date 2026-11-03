# 中燃在线 - Home Assistant 集成（双数据源合并版）

[![HACS Custom][hacs-shield]][hacs]
[![GitHub Release][release-shield]][release]

Home Assistant 自定义集成，从**中燃在线**平台（`zrds.95007.com`）获取燃气余额、用量和费用数据。

本版本（v2.0.0）合并了原先的两个半成品集成 `zr-gas-ha` 与 `zr-gas`，将它们对应的**两个不同小程序数据来源**统一到一个集成中，归一化成同一套传感器。

## 功能特性

- **余额监控** — 实时燃气余额（元），余额不足自动提醒（HA 修复中心）
- **月度用量/费用** — 当月累计用气量（m³）与费用（元）
- **阶梯气价** — 年度累计用量 + 三档阶梯 + 当前档位/单价（档位与单价可配置）
- **月度/年度统计** — `monthly_stats` / `yearly_stats` 属性，历史用量按月/年汇总
- **表具信息** — 表读数、气量余额、购气次数、最后抄表日期 + 设备属性（表号/型号/卡号/通气日期/安装位置等）
- **新增传感器** — 燃气单价、赠送金额、最大购气量（数据源提供时）
- **多账户** — 自动发现绑定的所有燃气账户，每个账户独立设备
- **多来源并存** — 在线端与缴费端可同时配置，互不冲突（实体 ID 带来源前缀区分）
- **Token 过期自动提醒** — 修复中心引导重新认证（在线端支持短信重认证）
- **前端卡片** — `zr-gas-card` 自定义卡片，展示余额/用量/阶梯/表具信息

## 安装

### HACS（推荐）

1. HACS → **⋮** → **自定义仓库** → 填入 `https://github.com/yahooor/zr-gas-ha`，类别 **Integration**
2. 搜索 **"中燃在线"** 安装 → 重启 Home Assistant

### 手动安装

将 `custom_components/zr_gas/` 复制到 HA 配置目录的 `custom_components/` 下，重启 HA。

> 从 v1.x（旧 zr-gas-ha）升级：配置条目自动迁移，实体 ID 不变；从旧 zr-gas 仓库安装的用户请先卸载旧版（同域名会冲突）。

## 本地开发

```bash
pip install -r requirements-dev.txt   # 测试与 lint 依赖
pytest -q && ruff check .
```

AI 会话请先读 [AGENTS.md](AGENTS.md)——里面有发版流程、架构要点与红线。

## 配置

### 在线端 · 短信登录（推荐，免抓包）

1. **设置** → **设备与服务** → **添加集成** → 搜索 **"中燃在线"**
2. 数据来源选 **在线端**，登录方式选 **短信验证码登录**，输入手机号
3. 点击页面链接打开验证码图片 → 识别填入 → 提交（发送短信）
4. 输入收到的短信验证码 → 登录 → 自动发现账户

### 在线端 · Token 导入（高级）

适用于已通过抓包等方式获取凭据的用户：填入 `accessToken` + `userId`（`x-mas-app-info` 选填）。

### 缴费端 · Token 导入

从缴费小程序抓包获取 `accessToken` + `userId` 后导入。缴费端的额外字段（单价/最大购气量/表具富化）在 Token 有效时可用。

### 可选配置（选项）

| 选项 | 默认值 | 说明 |
|------|--------|------|
| 刷新间隔 | 21600 秒 (6小时) | 最小 300 秒 |
| 余额预警阈值 | 50 元 | 低于触发提醒 |
| 账单查询年数 | 2 | 1-5 年 |
| 第二/三档起始量 | 400 / 1680 m³ | 阶梯气价 |
| 三档单价 | 2.99 / 3.44 / 4.34 元 | 示例默认值（请按当地资费调整） |
| 阶梯周期起始 | 01-01 | MM-DD |

## 传感器

| 传感器 | 单位 | 在线端 | 缴费端 | 说明 |
|--------|------|:---:|:---:|------|
| 余额 | CNY | ✅ | ✅ | 在线端取 countMoney，缴费端取 qtyBalance |
| 月用量 / 月费用 | m³ / CNY | ✅ | ✅ | 来自账单接口 |
| 欠费金额 | CNY | ✅ | ✅ | 附带 new_owe_money 属性（缴费端） |
| 赠送金额 | CNY | ✅ | ✅ | awardMoney |
| 燃气单价 | 元/m³ | ✅* | ✅ | *在线端取当月账单单价 |
| 最大购气量 | m³ | — | ✅ | maxGas |
| 表读数 / 气量余额 | m³ | ✅ | ✅ | |
| 购气次数 / 最后抄表日期 | — | ✅ | ✅ | |
| 年度累计用量 | m³ | ✅ | ✅ | 附阶梯档位/单价/月度年度统计 |

设备属性：燃气编号、客户名、地址、燃气公司、表号、表型号、卡号、费用编号、客户状态、数据来源；缴费端另有卡类型、通气日期、表具条码、安装位置。

## 前端卡片

```yaml
type: custom:zr-gas-card
entity: sensor.zhong_ran_ran_qi_XXXX_balance
# 可选:
# title: 我的燃气
# low_threshold: 50      # 余额预警线
# show_usage: true       # 用量/阶梯区
# show_meter: true       # 表具信息区
```

安装：`www/zr_gas_card/zr-gas-card.js` 复制到 HA 的 `www/zr_gas_card/`，资源注册 `/local/zr_gas_card/zr-gas-card.js`（JavaScript Module）。

## 接入能源面板

年度累计用量传感器（`annual_usage`）带 `total` state_class 与 m³ 单位，可直接加入 HA 能源面板的燃气统计：

1. **设置** → **仪表盘** → **能源** → **燃气**
2. 选择「年度累计用量」实体（建议选 tracker 为「不使用统计」+ 按实体记录）
3. 单价可手动填当地阶梯价（或用「燃气单价」传感器做动态价）

月用量/月费用传感器为账单快照（账期滞后），不适合作为能源统计源；历史明细见 `annual_usage` 的 `monthly_stats` 属性。

## API 连通性验证

仓库附带独立验证脚本（无需 HA 环境）：

```bash
# 无凭据探测端点存活（不会发送真实短信）
python scripts/verify_api.py

# 用有效 token 验证数据链路
python scripts/verify_api.py --token <accessToken> --user-id <userId>

# 交互式短信登录，打印可用凭据
python scripts/verify_api.py --sms --mobile <手机号>
```

## 技术细节

- **签名**: 请求带 MD5 签名（算法与盐值见源码 `api.py`，逆向自小程序前端）
- **请求**: `application/x-www-form-urlencoded`（checkMasInfo 用 JSON）
- **零外部依赖**（aiohttp/hashlib 均为 HA 内置）；最低 HA 2024.1.0

## 更新日志

### v2.2.3 — 账单降级显示修正（0.0 → 未知）

- **修复**: 账单接口不可用（账号绑定失效、网络失败等）时，账单派生传感器此前沿用默认值 **`0.0`**，会被误读为「这个月没花钱 / 没有欠费」。现改为返回 `None`，HA 显示为 **`unknown`（未知）**，与「真的是 0」区分开
- **影响字段**（7 个）: 月用量、月费用、上期用量、上期费用、年度累计用量、年度累计费用、当前阶梯剩余额度
- **单价单独处理**: `gas_price` 有 api 直供与账单推算两个来源，仅当来源为 `derived`（或缺失）时降级；api 直供的单价仍可信
- **不受影响**: 余额、表读数、气量余额、购气次数、欠费金额、赠送金额（均来自详情接口，与账单无关）
- **实现**: 新增 `ZrGasBillsUnavailable` 异常——绑定失效由「静默返回空列表」改为显式上抛；分年查询若一条账单都没拿到也上抛（部分成功则照常返回）；`ZrGasDeviceData` 新增 `bills_degraded` 标记；判定逻辑抽为 `models.is_bill_derived_unavailable()` 纯函数便于单测
- **附带效果**: 同时补上了 v2.2.2 的绑定失效短路（此前线上仍是 v2.2.1，每轮刷新产生 6 条重复告警，现已降为 0）
- **测试**: 117 → 124（新增降级判定 6 个用例 + 整段/分年全失败上抛 2 个用例；原「返回空列表」用例按新语义改写）

### v2.2.2 — 绑定失效错误短路优化

- **修复**: 账号绑定失效（服务端返回 `{"msg": "请先完成燃气用户绑定，再办理燃气业务。", "status": "2"}`）时，不再触发无意义的分年降级重试（此前每轮刷新产生 6 条重复告警）。命中"绑定"关键词即短路：整段查询失败直接返回空账单；分年循环命中即 break 跳过剩余年份
- **改进**: `_post()` 错误消息提取兼容服务端 `msg` 字段（部分端点用 `msg` 而非 `message` 承载错误文案，此前只拼 raw 响应体、错误展示为空）
- **改进**: 绑定失效时输出明确指引日志——"请到「中燃在线」小程序重新绑定燃气户"，替代重复的错误告警
- **测试**: 115 → 117（新增整段命中绑定错误返回空列表不发分年请求、分年循环命中即 break 2 个用例）

### v2.2.1 — 修复账单拉取 status=2 报错

- **修复**: 在线端 getCustomerMoneyList 整段查询（跨度 2 年）被服务端静默拒绝（status=2 且 message 为空），导致账单类传感器全为 0。现先按整段查询一次，失败（非认证类错误）时自动降级为按自然年切片循环查询并合并去重（与缴费端 queryBillHistory 按年模式一致）
- **改进**: `_post()` 业务错误异常消息附带原始响应体（截断 500 字符），线上日志可直接看到服务端真实返回，便于排查
- **测试**: 109 → 113（新增降级分年/去重/单年容错/认证错误不重试 4 个用例）

### v2.0.1 — 修复登录会话关闭告警

- **修复**: 登录流程改用自建自管的 aiohttp 会话（保留真实 CookieJar），不再关闭 HA 托管会话（消除 `closes the Home Assistant aiohttp session` 日志告警）
- **改进**: 配置流程中止/取消时自动关闭登录会话，避免泄漏

### v2.0.0 — 双源合并重构

**合并**：
- 合并 `zr-gas-ha`（在线端）与 `zr-gas`（缴费端）两个集成为一个，配置时选择数据来源
- 统一 API 层：`ZrGasBaseApi` 基类 + `ZrGasMpApi` / `ZrGasPayApi`，各自保留登录流程与字段映射（余额字段 countMoney vs qtyBalance 等差异在客户端内归一化）
- 缴费端独有字段并入统一模型：燃气单价、赠送金额、最大购气量、新欠费、客户类型、表具富化（通气日期/条码/位置/卡类型）
- 表具富化 getMeterInfo 对所有来源自动尝试，失败静默降级 — 在线端短信登录即可免抓包获取额外表具字段

**实测验证 (2026-10)**：两个数据来源的连通性与登录方式均经实机验证，详见更新日志与 `scripts/verify_api.py`。

**工程**：
- Config Flow VERSION 2 + 自动迁移（v1 条目升级不断实体）
- 在线端/缴费端可并存：unique_id 与设备标识带来源前缀
- 传感器 9 → 12（新增燃气单价/赠送金额/最大购气量），增强版前端卡片（来源徽标/阶梯框/表具区，兄弟实体自动推导）
- 测试 68 → 92（新增双源字段映射/状态归一化/账单解析/表具签名等）
- 移除 quality_scale.yaml；ruff + pytest CI

### v0.12.2 及更早

见 [zr-gas-ha 历史更新日志](https://github.com/yahooor/zr-gas-ha/releases)。

## 致谢

- [alickglyn](https://bbs.hassbian.com/thread-30786-1-1.html) — 原始 API 逆向分析
- [gao19970120](https://bbs.hassbian.com/thread-31008-1-1.html) — Node-RED + MQTT 方案参考
- [ExceptionsOccur/hazr](https://github.com/ExceptionsOccur/hazr) — 缴费记录端点（getPaymentLogForHsh）、埋点参数、methodEncrypt 加密协议（appKey/sign 密钥）借鉴
- [githubdulong/Script (ChinaGas.js)](https://github.com/githubdulong/Script) — 数据接口行为参考
- [ha_hfcrgas](https://github.com/Cyborg2017/ha_hfcrgas) / [hztowngas](https://github.com/palafin02back/hztowngas) — 架构参考

## 免责声明

本项目仅供学习和研究使用。API 接口通过逆向工程获取，非官方公开接口，可能随时变更。使用者需自行承担相关风险。

[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs]: https://hacs.xyz/docs/setup/download#add-custom-repository
[release-shield]: https://img.shields.io/github/v/release/yahooor/zr-gas-ha
[release]: https://github.com/yahooor/zr-gas-ha/releases
