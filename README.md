# 中燃在线 - Home Assistant 集成

[![HACS Custom][hacs-shield]][hacs]
[![GitHub Release][release-shield]][release]

Home Assistant 自定义集成，用于从**中燃在线**平台获取燃气余额、月度用量和费用数据。

## 功能特性

- **余额监控** — 实时查看燃气账户余额（元）
- **月度用量** — 显示当月累计用气量（m³）
- **月度费用** — 显示当月累计费用（元）
- **多账户支持** — 自动发现绑定的所有燃气账户
- **定时刷新** — 默认每 6 小时自动更新（可配置）
- **Token 过期提醒** — 自动检测并引导重新认证
- **Energy Dashboard** — 用量数据支持接入 HA 能源面板

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

## 传感器

每个燃气账户会创建以下传感器：

| 传感器 | 类型 | 单位 | 说明 |
|--------|------|------|------|
| 余额 | monetary | CNY | 当前账户余额 |
| 月用量 | gas | m³ | 当月累计用气量 |
| 月费用 | monetary | CNY | 当月累计费用 |

## 技术细节

- **API 签名**: `md5(param + salt + timestamp)`
- **请求格式**: `application/x-www-form-urlencoded`
- **零外部依赖**: 仅使用 HA 内置库（aiohttp、hashlib）
- **最低 HA 版本**: 2024.1.0

## 更新日志

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
