# 证据索引与独立验证范围

冻结 handoff：`c4e0baca6acefa58f031979bff71e7cd1028efdf`。来源仓库均需要原有访问权限。

## 包内原始或直接生成的材料

| 材料 | 来源与处理 | 能证明什么 |
|---|---|---|
| final-ref-check.json | 最终只读查询 GitHub branch commit 与 run，保留必要字段 | 定稿前 HEAD 未变化；同一 HEAD 的 run 已完成且成功 |
| CI-push-39537767479.zip | GitHub artifact 12318492520 的实际字节 | 三份 JUnit XML；本次校验 ZIP CRC、大小、SHA-256 和计数 |
| ci-job-119018276236.log | GitHub 返回的原始任务日志 | 主套/继承套/准备套、两次 source-check 和 63 个输出比较 |
| ci-artifact-summary.json | 本次解析真实 artifact | 主套 tests=1843、skipped=5、failure/error=0；其他两套计数及跳过原因 |
| old-report-links-now.json | 本次将 CE2021 报告相对链接解析后与完整 Git tree 比较 | 26 个目标均存在；不是重新执行历史测试 |
| source-manifest.json | 下载的 28 个审查源文件与固定 tree blob 对照 | 28/28 原始文件字节匹配 Git blob；另列 SHA-256，不附源码 |
| quiesce-retry-probe.json | 本次运行实际 KodiHost/InstanceLock 的受控诊断 | 第二次 quiesce 在真实 lease 仍持有时请求停用 |
| quiesce-retry-cross-review.md | 第二审查者阅读实际调用链的交叉检查 | 确认自动重试可达及现存 gate/lease 保护；没有实际文件破坏结论 |
| history-report-probe.json | 本次运行完整 HistoryWriter 的故障注入与正常诊断对照 | 写失败 + report 失败会留下队列，close 仍成功返回 |
| probe-self-check.json | 两个源关闭探针的正常/缺输入运行记录 | 退出约定区分复现与环境不适配；不把 blocked 算通过 |
| subtitle-probe-results.json | 本次执行真实纯定义和候选 rank | 3 个输入 blob 匹配；22 控制通过；4 个歧义文件名仍被接受 |
| contract-results.json | 实际方法/领域对象，GUI、时钟与可选 IO 替身 | F02 bind→select 与 F03 11 类有限控制流；不是设备整集认证 |
| entry-builder-probe.json | 真实构建器与审计器、临时两组件签名夹具 | 无 LICENSE 和有文档对照均通过；临时序列 1 不是产品身份 |
| review-facts.json | 上述来源及分支原始回执的结构化摘要 | 冻结身份、清单、CI、产品包状态、设备/播放事实与限制 |

## 主要原始 GitHub 来源

所有仓库路径及 blob SHA 另列于 `review-facts.json` 的 `sources` 数组。设备回执仅摘录与本审查相关的事实，包内不重复包含大量检索结果、用户数据或全部媒体日志。

- [本代交付报告](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/docs/CE2024-DELIVERY.md)
- [过渡代次关闭记录](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/docs/CE2023-CLOSURE.md)
- [清单](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/release/source-inventory.json)
- [源码到产品映射](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce2023/product24-source-package.json)
- [原入口说明](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-packages/ce2024/README.md)
- [当前 CI](https://github.com/2223M1/bobbi-tv/actions/runs/39537767479)
- [实际任务日志入口](https://github.com/2223M1/bobbi-tv/actions/runs/39537767479/job/119018276236)
- [实际 CI artifact](https://github.com/2223M1/bobbi-tv/actions/runs/39537767479/artifacts/12318492520)
- [最终设备回执](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce2023/device-final-idle.json)
- [1143 个自有运行文件核对](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce2023/installed-files-1792551231636875800.json)
- [三轮受管恢复](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce-managed-recovery-1792551122840993800.json)
- [乒乓实际播放检查](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce-new-work-ping_pong-inspect-1792551289427135300.json)
- [4K 起播失败](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce-new-work-grand_budapest-select-1792551406474811700.json)
- [4K 缓存/解码诊断](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce2023/budapest-startup-diagnostics.json)
- [新动漫后端阶段](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce2023/further-universe-diagnostics.json)
- [新动漫实际轨道/字幕](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce-new-work-further_universe-inspect-1792551658645820500.json)

## 必须保留的区别

1. source-check 两次相同，不自动证明所有发行 ZIP 的时间戳及字节可重现。
2. Git 中存在原入口且映射一致，不等于本次取得并独立验签真实入口。
3. 临时两组件入口通过，不等于完整 22 组件产品、Kodi ZIP 浏览器或设备回退通过。
4. 历史设备回执与本次受控复现来自不同执行环境；本次未连接盒子。
5. 单项探针 0、CI 绿色、短窗 AV 或字幕标签，分别不能替代缺陷完整关闭、长时观看、原声意图或字幕同步验证。
6. 当前源码上三项新缺陷探针退出 1 是诊断结果，不改变当前官方 CI 已成功的事实。

后续应使用新的唯一代次和 attempt 目录保存结果，保留本包历史记录，不把新结果覆盖为旧提交的成绩。
