# 私库提交前边界审计 — 2026-10-19

本记录是**只读、未暂存的候选快照审查，不是最终 staged 认证**。后续新增证据或改动须由 root 在最终暂存后重新检查。

本轮交付范围已缩为 CoreELEC，计划最终 CE 1907；Android、Windows 暂停。扫描已有 Windows 证据仅为检查提交内容，不代表继续多端构建、测试或发布。

## 范围与结果

- 当时 Git 候选为 1,821 文件、272,516,312 字节，包括 13 个 repository ZIP、145 份 review-evidence JSON；不含本次新增的两份审计记录。
- 对 9 个候选目录及 39 个 native/根级文件执行 Gitleaks 脱敏扫描，ZIP 检查深入一层。另检查凭据字段、ZIP 成员、目录边界及 workflow。
- 未见真实账号、session/token、签名私钥、密钥库或测试 profile 混入。候选禁入路径和 tracked-but-ignored 交集均为 0。
- `.private/`、`native/.work/`、`native/build/`、`native/downloads/`、`dist/` 未进入候选；未扫描这些忽略树，也未读取私钥内容。

## 扫描命中复核

共 22 项 `generic-api-key` 命中，均判定为非秘密；不记录任何命中值。

| 路径 | 判定 |
|---|---|
| `review-evidence/windows-fullscreen-retirement-20261019.md:13` | UI 片源 `source_key` 摘要，与选源卡片证据对应，不是认证密钥 |
| `tools/deploy_ce_candidate.py:26` | 固定公钥指纹，不是私钥 |
| `release/kodi-vendors.json`、`release/source-inventory.json` | 源文件 SHA-256 清单 |
| `addons/plugin.video.bobbi.torrent/SOURCE-PROVENANCE.json:8` | 上游源文件 SHA-256 |
| tmdbv3api 两份许可证据及对应 repository ZIP 成员 | Python 包名误报 |

精确路径、行号、规则与扫描限制见同名 JSON。资源 SQLite 仅观察到授权目录的五张表；`shares.password` 表示分享提取码，不是账号登录密码。本次只读 schema 检查不等于对所有数据库页的认证。

## 发布边界

唯一 workflow `.github/workflows/verify.yml` 使用 `contents: read`，只执行测试和可复现构建；未见 release/publish 或 artifact upload 动作，与私有发行策略一致。

审计期间没有修改用户 dirty 树、stage、commit、删除文件或操作设备。本记录不授予最终提交、CE 包、播放或升级回退验收通过。
