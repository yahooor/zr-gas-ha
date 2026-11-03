# AGENTS.md — zr-gas-ha（主仓）

> 给 AI 会话与新协作者的项目约定。状态类信息看 README，本文件只记「怎么干活」。

## 一句话

Home Assistant 自定义集成，抓中燃在线（zrds.95007.com）两个小程序的数据：
**在线端**（mp，余额/表读数）+ **缴费端**（pay，账单/缴费记录）。当前 v2.2.3。

## 跑测试

```bash
pip install -r requirements-dev.txt   # pytest / pytest-asyncio / aiohttp / ruff
pytest -q                             # 期望 124 passed
ruff check .                          # 必须全绿（含 UP / B / ASYNC / RUF 规则集）
```

## 发版（含镜像同步，**两步都不能省**）

```bash
# 1 主仓：改 version → commit → push → tag → release
git commit -am "..." && git push
git tag v2.2.N && git push origin v2.2.N
gh release create v2.2.N --title "..." --notes "..."

# 2 镜像仓 yahooor/zr-gas 必须同版本同步
#    同步内容：custom_components/zr_gas/*.py、manifest.json、tests/、README、hacs.json
#    注意镜像仓行尾混合（api.py=CRLF，其余=LF），已设 core.autocrlf=false
#    提交信息沿用 "feat: v2.2.N — 与主仓库同步"

# 3 HACS 更新
haops hacs update yahooor/zr-gas-ha --version v2.2.N
```

## 架构要点

| 文件 | 作用 | 注意 |
|---|---|---|
| `api.py` | 两个数据源客户端（`ZrGasMpApi` / `ZrGasPayApi`） | 改解析必跑 pytest；`ZrGasBillsUnavailable` 是账单不可用的信号 |
| `models.py` | `is_bill_derived_unavailable()` 等纯函数 | 判断「账单类实体该不该报 unknown」的单一入口 |
| `sensor.py` | 17 个传感器 | **账单类降级必须返回 `None`（显示 unknown），不能返回 `0.0`** |

**核心语义**：账单接口不可用时，8 个账单派生实体（月用量/月费用/上期用量/上期费用/
年度用量/年度费用/阶梯剩余/单价）报 `unknown`。返回 `0.0` 会被误读成「这个月没花钱」，
属于假阴性，比报错更危险。余额、表读数、气量余额、购气次数、欠费金额来自详情接口，不受影响。

## 红线

- **不要只改主仓不改镜像**：`yahooor/zr-gas` 是只读镜像，不同步会让用户装到旧版
- 不要用 `0.0` 表达「查不到」——这是本仓历史上最大的坑
- 镜像仓已设 `core.autocrlf=false`，改动前确认行尾风格，否则产生整文件假 diff
