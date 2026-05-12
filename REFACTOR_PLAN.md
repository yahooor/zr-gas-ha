# zr-gas-ha 仓库整理方案

> 审查人：高见远（Gao）· 架构师
> 审查日期：2026-05-11
> 仓库版本：v0.10.2

---

## 问题总览

| # | 类别 | 严重度 | 问题摘要 |
|---|------|--------|----------|
| 1 | manifest.json | 高 | 缺少 `integration_type`、`loggers` 等必要字段 |
| 2 | hacs.json | 中 | `filename` 字段硬编码版本号，应使用版本无关命名 |
| 3 | 根目录 zip 文件 | 高 | 三个 zip 文件不应存在于仓库中，应通过 Release Assets 分发 |
| 4 | .gitignore | 中 | `*.zip` 规则与已跟踪的 zip 文件冲突 |
| 5 | quality_scale.yaml | 低 | 内容过简，建议删除或填充完整的 quality scale 自评 |
| 6 | 前端卡片 | 中 | `www/zr_gas_card/` 不应放在集成仓库内，应独立为 HACS Frontend 仓库 |
| 7 | icons.json | 低 | 仅定义 3 个传感器图标，未覆盖全部 9 个传感器 |
| 8 | CI/CD | 低 | CI 工作流基本规范，但有少量优化空间 |
| 9 | 代码结构 | 低 | 整体良好，无 `services.yaml` 属正常（集成不暴露服务） |
| 10 | translations | 低 | zh-Hans.json 与 strings.json 完全一致（冗余），可保留或清理 |

---

## 问题 1：manifest.json 缺少必要字段

### 问题描述

当前 `manifest.json` 缺少以下 HA 规范推荐/要求的字段：

- **`integration_type`**（HA 2024.2+ 要求）：标识集成类型，如 `device`、`service`、`hub`。对云轮询类集成，应为 `"device"`。
- **`loggers`**：声明集成使用的 Python logger 名称，使 HA 能在日志配置界面显示该集成的日志选项。当前代码使用 `logging.getLogger(__name__)`，对应 logger 名为 `custom_components.zr_gas`。
- **`iot_class` 已弃用**：`iot_class` 字段在 HA 核心中已弃用（移至 `manifest.json` 仅用于旧版兼容），HACS 要求在 `hacs.json` 中声明即可。但从向后兼容角度可保留。

### 修改方案

在 `manifest.json` 中新增 `integration_type` 和 `loggers` 字段，并更新版本号。

### 修改后的完整文件

```json
{
  "domain": "zr_gas",
  "name": "中燃在线",
  "codeowners": ["yahooor"],
  "config_flow": true,
  "documentation": "https://github.com/yahooor/zr-gas-ha",
  "integration_type": "device",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/yahooor/zr-gas-ha/issues",
  "loggers": ["custom_components.zr_gas"],
  "requirements": [],
  "version": "0.11.0"
}
```

---

## 问题 2：hacs.json 规范优化

### 问题描述

1. **`filename` 硬编码版本号**：当前 `filename` 为 `zr_gas_0102.zip`，每次发版都需手动更新此字段，容易遗漏。HACS 推荐使用版本无关的文件名（如 `zr_gas.zip`），在 Release 中统一命名。
2. **`iot_class` 字段**：HACS 1.34+ 已将 `iot_class` 从 `hacs.json` 移除（改为自动从 `manifest.json` 读取）。保留不会报错，但属于冗余。

### 修改方案

将 `filename` 改为 `zr_gas.zip`，后续每次 Release 统一上传名为 `zr_gas.zip` 的文件。移除 `iot_class`。

### 修改后的完整文件

```json
{
  "name": "中燃在线",
  "content_in_root": false,
  "country": ["CN"],
  "homeassistant": "2024.1.0",
  "render_readme": true,
  "zip_release": true,
  "filename": "zr_gas.zip"
}
```

---

## 问题 3：根目录 zip 文件应移除

### 问题描述

仓库根目录包含三个历史版本 zip 文件：

```
zr_gas_0100.zip
zr_gas_0101.zip
zr_gas_0102.zip
```

**问题**：
- HACS 通过 GitHub **Release Assets** 分发 zip 文件，不应将 zip 存储在仓库中
- 这些文件增加仓库体积，且 `.gitignore` 中的 `*.zip` 规则导致 git 状态混乱
- 每次发版累积的 zip 文件会造成仓库膨胀

### 修改方案

1. 删除根目录下所有 zip 文件
2. 确保 HACS Release 流程正确：每次发布 GitHub Release 时，将 `custom_components/zr_gas/` 目录打包为 `zr_gas.zip` 并上传为 Release Asset
3. 可通过 GitHub Actions 自动化此流程（见问题 8 的 CI 改进）

### 操作步骤

```bash
git rm zr_gas_0100.zip zr_gas_0101.zip zr_gas_0102.zip
```

---

## 问题 4：.gitignore 规则冲突

### 问题描述

当前 `.gitignore`：

```
zr_gas.zip
*.zip
```

存在两个问题：
1. `zr_gas.zip` 规则被下一行的 `*.zip` 完全覆盖，属于冗余
2. `*.zip` 规则与仓库中实际跟踪的 `zr_gas_0100.zip` 等文件产生逻辑矛盾（文件已被 git 跟踪，`.gitignore` 不影响已跟踪文件）
3. 删除 zip 文件后（问题 3），`*.zip` 仍然有用，可防止误提交

### 修改方案

清理冗余的 `zr_gas.zip` 行，保留 `*.zip`。添加其他常见 HA 集成开发中应忽略的模式。

### 修改后的完整文件

```gitignore
__pycache__/
*.pyc
*.pyo
.DS_Store
.pytest_cache/
reference/
docs/
*.zip
*.egg-info/
dist/
build/
.venv/
venv/
.idea/
.vscode/
```

---

## 问题 5：quality_scale.yaml 处理

### 问题描述

当前 `quality_scale.yaml` 内容：

```yaml
custom_components:
  zr_gas:
    quality_scale: custom
```

这是 HA 官方核心集成用于追踪代码质量自评（Silver/Gold/Platinum）的文件。对于自定义集成，此文件无实际功能意义，`custom` 级别是最低/默认级别。

### 修改方案

**方案 A（推荐）：删除此文件**。自定义集成不需要 quality_scale.yaml，保留反而给审查者造成困惑。

**方案 B：保留但填充完整的自评**。如果想保留，应按照 https://developers.home-assistant.io/docs/core/integration-quality-scale/ 的规范逐项填写各规则（如 `has_entity_name`、`config_flow_test`、`integration_type` 等）。这是一个较大的工作量，对自定义集成意义不大。

> 推荐方案 A，直接删除。

### 操作步骤

```bash
git rm custom_components/zr_gas/quality_scale.yaml
```

---

## 问题 6：前端卡片应独立管理

### 问题描述

`www/zr_gas_card/zr-gas-card.js` 是一个 HA 前端自定义卡片，放在集成仓库内存在以下问题：

1. **HACS 类别冲突**：HACS 要求一个仓库只能属于一个类别（`Integration` 或 `Frontend`）。当前仓库作为 Integration 注册，HACS 不会自动安装 `www/` 目录下的前端资源。
2. **版本管理困难**：卡片和集成耦合在同一仓库，但卡片的更新节奏可能与集成不同。
3. **用户安装体验差**：用户必须手动复制 JS 文件到 `www/` 目录并注册资源。

### 修改方案

**方案 A（推荐）：将前端卡片迁移到独立仓库**

1. 创建新仓库 `yahooor/zr-gas-card`（或类似名称）
2. 将 `www/zr_gas_card/zr-gas-card.js` 迁移过去
3. 在新仓库添加 `hacs.json`（类别为 `Frontend`）
4. 用户通过 HACS 安装卡片，自动部署到 `www/` 目录
5. 从本仓库中删除 `www/` 目录

新仓库的 `hacs.json`：

```json
{
  "name": "中燃在线燃气卡片",
  "content_in_root": false,
  "country": ["CN"],
  "filename": "zr-gas-card.js"
}
```

新仓库的文件结构：

```
hacs.json
README.md
dist/zr-gas-card.js
```

**方案 B（轻量替代）：在本仓库中保留但添加说明**

如果不想创建独立仓库，至少需要：
1. 在 README 中明确说明卡片需要手动安装
2. 考虑将 JS 文件移到根目录的 `dist/` 下，避免与集成代码混淆

> 推荐方案 A，长期来看更规范。

---

## 问题 7：icons.json 图标覆盖不完整

### 问题描述

当前 `icons.json` 仅有 3 个传感器图标：

```json
{
  "entity": {
    "sensor": {
      "balance": "mdi:cash",
      "monthly_usage": "mdi:fire",
      "monthly_cost": "mdi:currency-cny"
    }
  }
}
```

但集成共有 9 个传感器 + 1 个按钮，其余 6 个传感器和按钮的图标仅在 Python 代码中通过 `icon` 参数定义。虽然功能上没有问题（Python 中的 icon 参数优先级更高），但 `icons.json` 的最佳实践是为所有实体定义图标，这样 HA 前端可以在不加载 Python 代码的情况下展示图标（如设备注册表、实体列表预览等场景）。

### 修改方案

补全所有传感器和按钮的图标定义。

### 修改后的完整文件

```json
{
  "entity": {
    "sensor": {
      "balance": "mdi:cash",
      "monthly_usage": "mdi:fire",
      "monthly_cost": "mdi:currency-cny",
      "owe_money": "mdi:alert-circle-outline",
      "last_record": "mdi:gauge",
      "qty_meter_balance": "mdi:gas-cylinder",
      "purch_times": "mdi:counter",
      "last_record_time": "mdi:calendar-clock",
      "annual_usage": "mdi:chart-line"
    },
    "button": {
      "refresh": "mdi:refresh"
    }
  }
}
```

---

## 问题 8：CI/CD 工作流优化

### 问题描述

当前 CI 工作流基本规范，但有以下优化空间：

1. **缺少自动化 Release 流程**：发版需手动打包 zip 并上传
2. **pytest 依赖安装不精确**：`pip install pytest pytest-asyncio aiohttp homeassistant voluptuous` 会安装完整 HA 包（约 200+ 依赖），CI 耗时较长。当前测试使用 mock 方式绕过 HA 依赖，可以精简安装
3. **缺少 mypy 类型检查**（可选）

### 修改方案

**8a. 添加自动化 Release 工作流**

新增 `.github/workflows/release.yml`，在推送 tag 时自动打包 zip 并创建 Release：

### 修改后的完整文件：`.github/workflows/release.yml`

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  release:
    name: Build and Release
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Zip the integration
        run: |
          cd custom_components/zr_gas
          zip -r ../../zr_gas.zip .

      - name: Create Release
        uses: softprops/action-gh-release@v2
        with:
          files: zr_gas.zip
          generate_release_notes: true
```

**8b. 优化 CI 工作流**

### 修改后的完整文件：`.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    name: Lint (ruff)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install ruff
        run: pip install ruff
      - name: Run ruff check
        run: ruff check custom_components/ tests/
      - name: Run ruff format check
        run: ruff format --check custom_components/ tests/

  test:
    name: Tests (pytest)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install test dependencies
        run: pip install pytest pytest-asyncio
      - name: Run tests
        run: pytest tests/ -v
```

> 注：当前测试使用 HA mock（`conftest.py` 中的 `_setup_ha_mocks`），不需要安装 `homeassistant` 包。移除后 CI 时间将大幅缩短。如果未来需要集成测试（使用 `homeassistant` 的 `pytest-homeassistant-custom-component`），可以单独添加一个 job。

---

## 问题 9：代码结构审查

### 审查结论：整体良好

逐项检查：

| 检查项 | 状态 | 说明 |
|--------|------|------|
| `__init__.py` | 正常 | 正确使用 `DataUpdateCoordinator`、`async_setup_entry`/`async_unload_entry` 模式 |
| `config_flow.py` | 正常 | 包含完整的多步骤 flow（user/captcha/sms_code/discover）+ reauth + options |
| `strings.json` | 正常 | 与 `config_flow.py` 中的 step_id 和 error key 完全对齐 |
| `translations/` | 正常 | en.json 和 zh-Hans.json 结构与 strings.json 一致 |
| `sensor.py` | 正常 | 使用 `SensorEntityDescription` 模式，符合 HA 最佳实践 |
| `button.py` | 正常 | 使用 `ButtonEntityDescription` 模式 |
| `models.py` | 正常 | 纯数据类，无 HA 依赖 |
| `api.py` | 正常 | 异步 API 客户端，使用 HA 的 shared session |
| `const.py` | 正常 | 常量集中管理 |
| `diagnostics.py` | 正常 | 提供 device diagnostics 支持 |
| `manifest.json` | 需改进 | 见问题 1 |
| `services.yaml` | 不需要 | 集成不暴露任何服务（button entity 本身已覆盖刷新功能） |

**无需额外修改代码结构。**

---

## 问题 10：翻译文件冗余分析

### 问题描述

`translations/zh-Hans.json` 的内容与 `strings.json` **完全一致**。

在 HA 翻译机制中：
- `strings.json` 是**默认翻译**（当用户语言无匹配翻译文件时使用）
- `translations/zh-Hans.json` 是简体中文的显式翻译

两者内容一致属于正常现象（strings.json 本身就是中文），因为目标用户主要是中文用户。如果保持 strings.json 为中文，则 zh-Hans.json 确实冗余。但这是 HA 的标准文件结构，不应删除。

### 修改方案

**无需修改。** 保持现状即可。这是 HA 集成的标准做法。

---

## 执行清单

以下按优先级排序的执行步骤：

### 第一优先级（必须执行）

1. **[manifest.json]** 添加 `integration_type`、`loggers` 字段，更新 `version`
2. **[根目录 zip]** 删除 `zr_gas_0100.zip`、`zr_gas_0101.zip`、`zr_gas_0102.zip`
3. **[hacs.json]** 修改 `filename` 为 `zr_gas.zip`，移除 `iot_class`
4. **[.gitignore]** 清理冗余规则，补充常见忽略模式

### 第二优先级（建议执行）

5. **[icons.json]** 补全所有传感器和按钮图标
6. **[CI/CD]** 添加 `release.yml` 自动化发版工作流
7. **[CI/CD]** 精简 `ci.yml` 中 pytest 的依赖安装
8. **[quality_scale.yaml]** 删除无实际意义的文件

### 第三优先级（长期优化）

9. **[前端卡片]** 将 `www/zr_gas_card/` 迁移到独立仓库，作为 HACS Frontend 项目发布
10. **[README.md]** 更新安装说明，移除手动安装 zip 的步骤，添加卡片独立仓库链接

---

## 修改文件汇总

| 文件 | 操作 | 说明 |
|------|------|------|
| `custom_components/zr_gas/manifest.json` | 修改 | 添加 `integration_type`、`loggers`，更新版本 |
| `hacs.json` | 修改 | 修改 `filename`，移除 `iot_class` |
| `.gitignore` | 修改 | 清理冗余，补充忽略模式 |
| `custom_components/zr_gas/icons.json` | 修改 | 补全所有实体图标 |
| `zr_gas_0100.zip` | 删除 | 历史发布包，应通过 Release Assets 管理 |
| `zr_gas_0101.zip` | 删除 | 同上 |
| `zr_gas_0102.zip` | 删除 | 同上 |
| `custom_components/zr_gas/quality_scale.yaml` | 删除 | 自定义集成无实际意义 |
| `.github/workflows/release.yml` | 新增 | 自动化发版工作流 |
| `.github/workflows/ci.yml` | 修改 | 精简测试依赖 |

---

## 完整修改后的文件内容

以下为所有需要修改/新增文件的完整内容，可直接使用。

### 1. `custom_components/zr_gas/manifest.json`

```json
{
  "domain": "zr_gas",
  "name": "中燃在线",
  "codeowners": ["yahooor"],
  "config_flow": true,
  "documentation": "https://github.com/yahooor/zr-gas-ha",
  "integration_type": "device",
  "iot_class": "cloud_polling",
  "issue_tracker": "https://github.com/yahooor/zr-gas-ha/issues",
  "loggers": ["custom_components.zr_gas"],
  "requirements": [],
  "version": "0.11.0"
}
```

### 2. `hacs.json`

```json
{
  "name": "中燃在线",
  "content_in_root": false,
  "country": ["CN"],
  "homeassistant": "2024.1.0",
  "render_readme": true,
  "zip_release": true,
  "filename": "zr_gas.zip"
}
```

### 3. `.gitignore`

```gitignore
__pycache__/
*.pyc
*.pyo
.DS_Store
.pytest_cache/
reference/
docs/
*.zip
*.egg-info/
dist/
build/
.venv/
venv/
.idea/
.vscode/
```

### 4. `custom_components/zr_gas/icons.json`

```json
{
  "entity": {
    "sensor": {
      "balance": "mdi:cash",
      "monthly_usage": "mdi:fire",
      "monthly_cost": "mdi:currency-cny",
      "owe_money": "mdi:alert-circle-outline",
      "last_record": "mdi:gauge",
      "qty_meter_balance": "mdi:gas-cylinder",
      "purch_times": "mdi:counter",
      "last_record_time": "mdi:calendar-clock",
      "annual_usage": "mdi:chart-line"
    },
    "button": {
      "refresh": "mdi:refresh"
    }
  }
}
```

### 5. `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint:
    name: Lint (ruff)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install ruff
        run: pip install ruff
      - name: Run ruff check
        run: ruff check custom_components/ tests/
      - name: Run ruff format check
        run: ruff format --check custom_components/ tests/

  test:
    name: Tests (pytest)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install test dependencies
        run: pip install pytest pytest-asyncio
      - name: Run tests
        run: pytest tests/ -v
```

### 6. `.github/workflows/release.yml`（新增）

```yaml
name: Release

on:
  push:
    tags:
      - "v*"

jobs:
  release:
    name: Build and Release
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Zip the integration
        run: |
          cd custom_components/zr_gas
          zip -r ../../zr_gas.zip .

      - name: Create Release
        uses: softprops/action-gh-release@v2
        with:
          files: zr_gas.zip
          generate_release_notes: true
```

### 需要删除的文件

```bash
git rm zr_gas_0100.zip zr_gas_0101.zip zr_gas_0102.zip
git rm custom_components/zr_gas/quality_scale.yaml
```
