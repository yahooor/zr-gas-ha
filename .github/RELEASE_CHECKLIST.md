# 发版检查清单

每次发版后请按以下清单检查，确保所有必要步骤都已完成。

## 1. 发版前准备

- [ ] 确认所有代码已合并到 main 分支
- [ ] 本地测试通过
- [ ] 检查 `manifest.json` 中的 `version` 字段已更新
- [ ] 检查 `hacs.json` 配置正确

## 2. 更新文档（重要！）

- [ ] **更新 README.md 的"更新日志"部分**
  - 格式：`### v0.12.3 — 简短描述`
  - 使用 `**修复**:`、`**新增**:`、`**改进**:` 等标记
  - 参考现有 README.md 的格式
- [ ] 更新 `CHANGELOG.md`（如有）

## 3. 创建 Release

- [ ] 推送代码到 GitHub main 分支
- [ ] 创建 Git tag：`git tag v0.12.3 && git push origin v0.12.3`
- [ ] 在 GitHub 创建 Release（附 Release Notes）

## 4. 验证安装

- [ ] 在 HACS 中验证新版本能正常显示和安装
- [ ] 测试升级流程

## 5. 发布后

- [ ] 检查 GitHub Releases 页面
- [ ] 检查 HACS 商店识别
