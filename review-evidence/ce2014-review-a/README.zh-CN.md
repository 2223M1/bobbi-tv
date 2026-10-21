# Bobbi TV PR 3 CE2014 独立审查交付包

审查对象：[PR #3](https://github.com/2223M1/bobbi-tv/pull/3)，固定提交 c8de17ae9dabbe0f37753e1751b1d88107311316。审查日期：2026 年 10 月 21 日（UTC+8）。

**建议继续保持 Draft，先修复 3 项确认问题：1 项 P1、2 项 P2。** 前版 6 项问题的原复现契约已分别通过。另有 2 项非阻断改进，不混入主裁决。

## 先读这些文件

| 文件 | 用途 |
| --- | --- |
| [REVIEW.zh-CN.md](REVIEW.zh-CN.md) | 完整结论、旧问题复核、新问题证据、CI 与设备记录的准确范围 |
| [CODEX-EXECUTION.zh-CN.md](CODEX-EXECUTION.zh-CN.md) | 可以直接交给 Codex 的任务、修复顺序、限制、命令和验收矩阵 |
| [FINDINGS.json](FINDINGS.json) | 3 项正式问题及 2 项改进的机器可读清单 |
| [ACCEPTANCE.json](ACCEPTANCE.json) | 下一候选必须满足的行为与结果交付 |
| [SOURCE-PROVENANCE.json](SOURCE-PROVENANCE.json) | 固定 base/head/tree、23 个复现直接来源及 1,842 个已校验文件的来源索引 |
| [evidence/integrated-head/RESULT.json](evidence/integrated-head/RESULT.json) | 本包统一入口实际运行的完整结果 |

## 复跑主反例

使用 Python 3.12 的开发环境，在包外的真实仓库 checkout 上运行。以下两个路径由执行者替换；审查输出必须是新目录。

    python -m pip install -r /path/to/this-package/requirements-review.txt
    python /path/to/this-package/run_review.py --repo /path/to/bobbi-tv --output /path/to/new-review-result

当前受审 head 的预期是 **14 项：8 通过、6 失败、0 执行异常，退出码 1**。6 条失败路径归并成 3 项问题，不能写成 6 个独立缺陷。修复后的目标是 14/14 通过。

额外观察可以一起执行：

    python /path/to/this-package/run_review.py --repo /path/to/bobbi-tv --output /path/to/another-new-result --with-advisories

额外分组包括停机生命周期 2 项（当前 1 通过、1 契约缺口）和验收驱动 11 项（当前全部通过），并保留 3 组回执字段观察。它们不改变主 14 项统计，也不因为 C02 的诊断失败自动阻断主结果。

退出码约定：0 为主契约全部通过；1 为确认的主契约失败；2 为环境、导入、超时或复现框架异常。临时目录或本机回环 socket 被环境禁止属于 2，不能当作产品缺陷。本包不会连接盒子、操作真实账号或提交 GitHub 内容。

## 证据组织

- evidence/integrated-head：统一执行器产生的主反例、正控、可选观察、JUnit 与日志。
- evidence/root：主审独立复跑的原始结果，包括旧 18 项、旧 15 项和当前 89 项相关回归。
- evidence/ci：两套实际 CI 原始 ZIP 和日志；每套均为 2684 passed / 5 skipped。
- evidence/device-receipts：仓库已有设备回执，保留原内容；本轮没有重新连接设备。
- details/installer、details/playback、details/release：分域审查、反驳性复核和官方 Kodi 来源索引。
- checks：5 个可单独运行的检查脚本；标准停机诊断依赖相邻的安装生命周期脚本。

本包是审查及执行任务交付，不含修复后的产品、完整仓库、账号材料、签名私钥或安装二进制。产品代码保持原样；本轮没有实施修复、部署、评论、合并或发布。文件完整性清单在 SHA256SUMS.txt。
