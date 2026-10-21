# CE2024 独立审查与后续执行包

本包固定审查 c4e0baca6acefa58f031979bff71e7cd1028efdf，产品提交 d2fffa570fe59b90cd1d33499efcf7c6684b2647，实际签名代次 2026102024。

**结论：源码与真实包对应关系、构建、签名已核验；四项 P2 需要修复，完整播放/回退体验尚未验收完成。** 本包是审查和修复任务材料，未改产品，未重签新安装包。

## 建议阅读顺序

1. CE2024-REVIEW.zh-CN.md：完整结论、四项发现、旧问题关闭表、真机证据边界及后续顺序。
2. CODEX-EXECUTION-PACK.zh-CN.md：可直接交给 Codex 的执行任务；从 T00 开始。
3. FINDINGS.json：机器可读的统一编号和关闭条件。
4. checks/README.zh-CN.md：只读复核/隔离反例的命令与预期退出码。

## 文件布局

| 路径 | 内容 |
|---|---|
| reviews/ | 生命周期、播放/字幕、构建/交付、解码诊断专项原稿 |
| evidence/source/ | 固定Git tree、完整差异、产品/交付提交关系 |
| evidence/ci/ | 实际GitHub JUnit ZIP、日志、独立统计、作者本地成绩差异 |
| evidence/package/ | 真实入口双验签、22组件/1349 Git文件逐项映射、35项RSA/ZIP测试 |
| evidence/playback/ | F02/F03原反例、新字幕20项矩阵、定向测试和设备回执提取 |
| evidence/lifecycle/ | 原包依赖真实HTTP三控、32项测试、安装/恢复/GUI原始回执 |
| evidence/provenance/ | 两个真实Git仓库的回执归属反例 |
| evidence/decoder/ | 真实多通道文本、实际sample函数离线重放与来源 |
| checks/ | 可重新运行的独立验证脚本 |
| MANIFEST.json / SHA256SUMS.txt | 包内文件大小与SHA-256 |

专项原稿保留独立审查时的工作区相对路径；本包统一后的执行入口和证据路径以主报告及 checks/README.zh-CN.md 为准。不要直接照抄原稿中的旧工作区目录名。

## 使用方式

把整个解压目录和 CODEX-EXECUTION-PACK.zh-CN.md 一起提供给执行者。用完整固定源码checkout作为代码输入；95,916,922字节的真实入口仍从仓库固定路径取得，本包没有重复附带生产安装包或应用配置。

先核对本包完整性：

~~~bash
python checks/verify_review_package.py --root /absolute/BobbiTV-CE2024-Independent-Review-20261021
~~~

复现脚本会在本机建立临时Git仓库、临时字幕文件或loopback HTTP服务，不会连接电视或修改产品源码。字幕、渐进退出和回执归属脚本在未修复的CE2024上会按报告暴露失败；这不是脚本安装失败。具体预期见 checks/README.zh-CN.md。

本包没有自动安装、推送、合并、发布或发送消息的动作。所有安装和播放结论均区分“本次本机验证”与“核读作者历史设备回执”。

