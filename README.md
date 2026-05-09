# 中燃在线 - Home Assistant 集成

[![HACS Custom][hacs-shield]][hacs]
[![GitHub Release][release-shield]][release]

Home Assistant 自定义集成，用于从**中燃在线**（中国燃气）获取燃气余额、月度用量和费用数据。

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
2. 填入仓库地址：`https://github.com/YOUR_USERNAME/zr-gas-ha`
3. 类别选择 **Integration**
4. 点击 **添加** → 搜索 **"中燃在线"** → 安装
5. 重启 Home Assistant

### 方式二：手动安装

1. 下载本仓库的 `custom_components/zr_gas/` 目录
2. 复制到 HA 配置目录的 `custom_components/zr_gas/`
3. 重启 Home Assistant

## 配置

### 前置准备

你需要从微信小程序获取以下信息：

1. **accessToken** — 通过抓包工具（如 Charles、Fiddler）从小程序请求中获取
2. 在 **"中燃在线"** 微信小程序中登录你的燃气账户

### 配置步骤

1. 进入 **设置** → **设备与服务** → **添加集成**
2. 搜索 **"中燃在线"**
3. 输入从小程序抓包获取的 **accessToken**
4. 系统自动验证 Token 并发现绑定的燃气账户
5. 配置完成！

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

## 获取 AccessToken

1. 在手机上安装抓包工具（推荐 Stream / Charles）
2. 打开微信小程序 **"中燃在线"**
3. 在抓包工具中找到请求头中的 `accessToken` 字段
4. 复制该值用于集成配置

> **注意**: accessToken 有效期未知，过期后需要重新抓包获取。集成会自动检测过期并提示重新配置。

## 致谢

- [alickglyn](https://bbs.hassbian.com/thread-30786-1-1.html) — 原始 API 逆向分析
- [gao19970120](https://bbs.hassbian.com/thread-31008-1-1.html) — Node-RED + MQTT 方案参考
- [ha_hfcrgas](https://github.com/Cyborg2017/ha_hfcrgas) — SensorEntityDescription 模式参考
- [hztowngas](https://github.com/palafin02back/hztowngas) — Coordinator 和 Session 管理参考

## 免责声明

本项目仅供学习和研究使用。API 接口通过逆向工程获取，非官方公开接口，可能随时变更。使用者需自行承担相关风险。

[hacs-shield]: https://img.shields.io/badge/HACS-Custom-41BDF5.svg
[hacs]: https://hacs.xyz/docs/setup/download#add-custom-repository
[release-shield]: https://img.shields.io/github/v/release/YOUR_USERNAME/zr-gas-ha
[release]: https://github.com/YOUR_USERNAME/zr-gas-ha/releases
