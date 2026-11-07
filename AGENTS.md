# AGENTS.md — zr-gas-ha（主仓）

> 给 AI 会话与新协作者的项目约定。状态类信息看 README，本文件只记「怎么干活」。

## 一句话

Home Assistant 自定义集成，抓中燃在线（zrds.95007.com）两个小程序的数据：
**在线端**（mp，余额/表读数）+ **缴费端**（pay，账单/缴费记录）。当前 v2.2.4。

## 跑测试

```bash
pip install -r requirements-dev.txt   # pytest / pytest-asyncio / aiohttp / ruff
pytest -q                             # 期望 136 passed
ruff check .                          # 必须全绿（含 UP / B / ASYNC / RUF 规则集）
ruff format --check .                 # 必须全绿
```

## 发版（含镜像同步，**两步都不能省**）

```bash
# 1 主仓：改 version → commit → push → tag → release
git commit -am "..." && git push
git tag v2.2.N && git push origin v2.2.N
gh release create v2.2.N --title "..." --notes "..."
#    CI 会自动建 release 与 zr_gas.zip 资产；gh release create 报
#    "Release.tag_name already exists" 说明 CI 抢先了，用 gh release edit 补文案

# 2 镜像仓 yahooor/zr-gas 必须同版本同步
#    同步内容：custom_components/zr_gas/*.py、manifest.json、tests/、README、hacs.json
#    注意镜像仓行尾混合（api.py=CRLF，其余=LF），已设 core.autocrlf=false
#    提交信息沿用 "feat: v2.2.N — 与主仓库同步"

# 3 HA 侧安装 + **必须重启**（见下方「安装后必须重启 HA」）
```

## 安装后必须重启 HA（2026-11-07 实测，勿省）

HA 2026.11 用的是**内置 marketplace 组件**（不再是 HACS 集成，`haops hacs update`
已失效——`hacs/*` WS 命令全部 unknown_command）。

```bash
# marketplace profile 必须是 default（hasscn 的 api 端点 ghapi.hacs.vip 已挂）
#   改法见 memory/2026-11-07.md（options flow 对 marketplace 返回 500，
#   只能 SSH 改 /homeassistant/.storage/core.config_entries 后重启）

haops ws marketplace/repository/install '{"repository":"<repo_id>","version":"v2.2.N"}'
haops restart        # ← 这一步不能省，原因见下
```

**为什么必须重启**（受控实验验证过，v2.2.5/v2.2.6 实验版）：

| 操作后 | 磁盘上的代码 | 运行中的代码 |
|---|---|---|
| marketplace install | 新 | **旧** |
| reload config entry | 新 | **旧** |
| **重启 HA** | 新 | **新** |

根因：Python 的 `sys.modules` + HA loader 的 `Integration._cache` 双重缓存。
marketplace 组件里 `async_reload` 一次都没调用 —— 它只
`async_clear_custom_components_cache()`（清「自定义组件发现列表」，
不清 `sys.modules`）并创建 `restart_required_*` issue 提示重启。
**reload config entry 也无效**，因为已 import 的模块不会被重新 import。

顺带：marketplace install 会**先删掉整个集成目录再写入**（实测 `custom_components/zr_gas`
短暂消失约 30 秒）。这期间该集成的实体是 unavailable，属正常现象，别误判为安装失败。

## 架构要点

| 文件 | 作用 | 注意 |
|---|---|---|
| `api.py` | 两个数据源客户端（`ZrGasMpApi` / `ZrGasPayApi`） | 改解析必跑 pytest；`ZrGasBillsUnavailable` 是账单不可用的信号 |
| `const.py` | 常量 + 小程序渠道表（`SOURCE_MINIAPP` / `MP_APPID_*`） | 报错文案要指明渠道，统一走 `miniapp_label()`，别自己拼字符串 |
| `models.py` | `is_bill_derived_unavailable()` 等纯函数 | 判断「账单类实体该不该报 unknown」的单一入口 |
| `sensor.py` | 17 个传感器 | **账单类降级必须返回 `None`（显示 unknown），不能返回 `0.0`** |

**核心语义**：账单接口不可用时，8 个账单派生实体（月用量/月费用/上期用量/上期费用/
年度用量/年度费用/阶梯剩余/单价）报 `unknown`。返回 `0.0` 会被误读成「这个月没花钱」，
属于假阴性，比报错更危险。余额、表读数、气量余额、购气次数、欠费金额来自详情接口，不受影响。

**日志规范（v2.2.4）**：

- 需要用户动手处理的状态（绑定失效）**只 WARNING 一次**，之后降为 `DEBUG`。
  降频逻辑统一走 `ZrGasBaseApi._log_binding_lost()`，别在别处再写 `warning()`。
- 任何面向用户的报错文案都要**指明小程序渠道**（`miniapp_label(self.source)`）。
  实测两个来源都是**微信小程序**（`platform=mp-weixin`），只是 appid 不同。
- 缴费流水里的 `aliPayAmount` / `weChatAmount` 是**支付方式字段名**，
  **不是**「支付宝小程序」渠道 —— 没有证据就别说支付宝。

## 红线

- **不要只改主仓不改镜像**：`yahooor/zr-gas` 是只读镜像，不同步会让用户装到旧版
- 不要用 `0.0` 表达「查不到」——这是本仓历史上最大的坑
- 镜像仓已设 `core.autocrlf=false`，改动前确认行尾风格，否则产生整文件假 diff
- **安装/更新后必须重启 HA**，reload config entry 不生效（见「安装后必须重启 HA」）
