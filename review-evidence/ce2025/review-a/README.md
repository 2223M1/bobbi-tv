# Bobbi TV CE2024 审查交付包

审查对象：`2223M1/bobbi-tv` 的 `codex/ce2024-reviewed-delivery-20261021`。  
冻结提交：`c4e0baca6acefa58f031979bff71e7cd1028efdf`。  
日期：2026-10-21（北京时间）。

**结论：上轮 D01–D04 原缺陷可关闭；本轮新增 1 项 P1、2 项 P2。CE2024 可保留为个人内测候选，尚未完成稳定交付和全部观看验收。**

## 交给下一轮 Codex

将整个包作为附件，并要求先阅读 `02-CODEX-NEXT-TASK.md`。先修维护重试的 R01，R02/R03 可并行窄修；随后在实际授权范围内完成同代构建和必要验收。不要只把本包当成需要抄入仓库的新报告。

| 文件 | 用途 |
|---|---|
| 01-REVIEW.md | 完整审查、事实、缺陷、边界、规划与固定来源 |
| 02-CODEX-NEXT-TASK.md | 可直接执行的后续任务书及产品/操作约束 |
| 03-ACCEPTANCE-MATRIX.md | 当前状态、关闭条件和下一代验收要求 |
| FINDINGS.json | 三项新问题的机器可读索引 |
| evidence/EVIDENCE-INDEX.md | 独立探针、CI 回执、设备来源及范围说明 |
| evidence/review-facts.json | 冻结身份、清单、CI、产品包与原始回执事实 |
| evidence/CI-push-39537767479.zip | 实际取得的 GitHub JUnit 回执，含三份 XML |
| evidence/ci-job-119018276236.log | 该工作流任务原始日志 |
| probes/ | 四个读取本地源码的受控诊断脚本 |
| SHA256SUMS.txt | 包内其余文件的 SHA-256 校验表 |

本包用于审查与整改，没有产品源码快照、修复补丁、生产签名密钥或新的 Kodi 安装包。CI ZIP 是测试回执。CE2024 真实约 96 MB 产品入口尚未被本次独立取得和验签。

## 运行有限复现

使用自己的已授权源码检出，先确认 commit 与工作区状态。下列命令中的路径必须替换为真实绝对路径；输出重定向位置应在源码树外。建议 Python 3.12；入口构建探针另需 `cryptography`。这些脚本不会连接 GitHub 或盒子，不会修改源码树；临时目录与夹具只服务于受控复现。

```bash
python probes/probe_quiesce_retry.py --repo /absolute/path/to/bobbi-tv
python probes/probe_subtitle_episode.py --repo /absolute/path/to/bobbi-tv
python probes/probe_history_report_failure.py --repo /absolute/path/to/bobbi-tv
python probes/standalone-probe-entry.py --repo /absolute/path/to/bobbi-tv
```

| 探针 | 本次结果 | 验证范围 |
|---|---|---|
| probe_quiesce_retry.py | 退出 1，缺陷复现 | 实际 KodiHost + 真实 OS lease，替身 RPC / 协作应答 / 逻辑时钟；两次 quiesce，不是完整 Installer 事务 |
| probe_subtitle_episode.py | 退出 1，4 个歧义例被接受；22 个控制通过 | 实际纯定义/候选 rank，合成文件名及元数据；未下载字幕或操作播放 |
| probe_history_report_failure.py | 退出 1，已接纳队列未排空而 close 成功 | 实际 HistoryWriter，受控存储与 report 故障；未修改真实观看记录 |
| standalone-probe-entry.py | 退出 0，旧 LICENSE 依赖关闭 | 两组件临时签名夹具；实际 builder / audit 和隔离导入；非产品二进制认证 |

通用退出约定：**1 = 指定缺陷被复现；0 = 指定缺陷在该探针有限条件下未复现，不代表全部控制通过或问题已关闭；2 = 探针检测到输入、依赖、接口等不适配或其他执行条件错误。** 具体控制是否通过须查看 JSON；部分探针会将控制失败归为 2。退出 2 不是修复成功。前三项在本次已审查源码上退出 1 是预期证据，不能包装为“本轮官方 CI 失败”。

入口探针在内存中生成临时测试密钥，仅改变临时夹具的信任配置，不触及生产信任根。源码变化可能使探针不再适配，应将行为契约迁移到仓库测试，不能只改脚本预期。

`--source-ref` 仅在停机/历史两个探针中可选，它是调用者标签，不验证 Git commit。两者输出实际文件 SHA-256；`evidence/source-manifest.json` 另将本次取回文件与冻结 Git blob 做了逐项匹配。字幕探针直接输出 blob 比较。跨版本复现必须重新记录真实源码身份。

## 校验包

解压后进入 `CE2024-Review-Pack`，在有 `sha256sum` 的环境运行：

```bash
sha256sum -c SHA256SUMS.txt
```

校验用于确认交付文件未改变，不是产品信任签名。原始 CI artifact 的 SHA-256 单独记录在 `evidence/ci-artifact-summary.json`。
