# CE2021 后续 Codex 执行任务书

本文件可直接作为下一轮 Codex 任务输入。先阅读 `CE2021-REVIEW.zh-CN.md` 和 `FINDINGS.json`，按下面的依赖顺序执行。目标是恢复可审计、可构建、与真实安装资产相符的候选，再处理明确播放缺口。

## 一、固定上下文

- 仓库：`2223M1/bobbi-tv`。
- 审查分支：`codex/ce2021-clean-delivery-20261021`。
- 固定受审 head：`b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2`；tree：`bbe592e62a7a6790c62725738b63dae9b9f9405a`。
- 重写后的 CE2014 父提交：`f6ef6a7e3c5868a2ab8ed8e600a592d51ba97167`；上轮实际受审提交：`c8de17ae9dabbe0f37753e1751b1d88107311316`。
- 报告中的原始已测代次：2026102021；清理重签代次：2026102022；Draft Release ID：419038503。
- 本轮 Git 只新增报告、回执和清理工具；产品保留文件仍与旧 CE2014 相同。不得从报告的成功数字推定修复已进入这个 checkout。
- 真实当前 CI：2679 passed / 5 failed / 5 skipped / 0 errors；两次 source-check 都失败。详见 `evidence/ci/`。
- 本轮 17 项独立反例：11 passed / 6 failed / 0 errors。它们是精确范围的验证，不是完整实机认证。

先检查远端和工作区；若 head 已移动，记录新旧身份，审清新增差异后再落修改。保留维护者现有未提交内容，使用隔离 checkout/worktree；不要强推或改写旧审查基准。

## 二、执行边界

保持新 UI、原画原码流、原声优先、手动选源、手动字幕 Off、准确同版续播与通用 CoreELEC。密钥、账号状态、缓存凭据不进入代码、日志或安装包。修复沿用原 trust，不新增设备白名单、专机前提或第二账号准入门槛。

源码修复、只读核验和本地测试先完成。设备安装、GitHub 写入、发布和消息发送只在执行会话已有相应授权时进行；缺少授权时交出完成的可审查结果和精确待执行动作，不要把等待授权当作已通过。

本任务不授权修改固件、SYSTEM、eMMC，也不要求改变私人分发边界。用户在当前会话已明确的授权和清理目标优先；报告里转述的历史操作只作为历史证据，不扩张本次权限。

## 三、任务与依赖

| ID | 任务 | 前置 | 完成标准 |
| --- | --- | --- | --- |
| T01 | 恢复真实 CE2021 修复源码与证据来源 | 无 | 固定 commit/tree；原包/清理包/补丁/运行文件映射；原始证据可读取 |
| T02 | 统一清理、inventory、构建、entry audit 契约 | 明确清理范围；与 T01 合并时核对冲突 | 完整源码构建与审计表达同一文件政策，有针对性正负例 |
| T03 | 修复重签器精确输入约束与 provenance | 可与 T01 独立推进 | 正确原件接受；旧合法代次拒绝；输入身份真实记账 |
| T04 | 验证 F01–F03、G01 和夹具适配 | T01 | 行为断言保留，正负对照通过；完整 owner-loop 补证 |
| T05 | 固定候选 CI、双构建、真实包审计 | T01–T04 | 当前测试/双构建/实际资产证明齐全，摘要可复核 |
| T06 | BT metadata 与中文字幕两个专项 | T01；实机须 T05 与既有设备授权 | 分阶段根因、最小修复、按作品独立状态与回执 |
| T07 | 交付下一轮可审查结果 | 已完成任务 | commit、diff、测试、包、证据索引、未完成项齐全 |

### T01：恢复真实已测实现，避免在旧代码上盲目重写

1. 用已有授权渠道读取作者保留的 CE2021 工作区、完整 patch、原交付合集及 Draft 资产。先对原件记 SHA-256、bytes、取得时间，只读保存。
2. 核对本包 `evidence/release/ASSET-METADATA-COMPARISON.json` 中的实际资产身份。GitHub digest 是核对输入，不代替下载后自己计算。
3. 找出 F01 受管恢复、认证协作停机、G01 drain/lease、F02 排队选择补偿、F03 单次 snapshot 分类、base_cache 复用路径等实际代码及测试。记录来源，不能按报告文字补一个近似实现后称“原修复恢复”。
4. 在隔离分支应用真实修复，审查与当前历史清理的冲突；保留 old c8de17a → rewritten f6ef6a7 的来源映射。包内运行文件可作为恢复线索，不能替代完整构建输入和源码。
5. 建立 `SOURCE-ARTIFACT-MAP.json`：每个关键路径的 Git blob/SHA-256、原包组件路径/hash、清理包组件路径/hash、相同或不同及原因。覆盖所有运行时组件，不能只用四个版本号代替。
6. 把报告 26 个链接对应的原始回执落到可访问、固定版本的位置。每份登记 producer commit/tree、工具 SHA、包 SHA/sequence、attempt、时间和证据类型。若只能取到历史结果，明确标为历史。

若原源码或资产无法取得，完成可做的元数据、清理器和构建修复，准确列出阻塞对象；不得编造来源映射、原始日志或把已知旧代码冒充实测 CE2021。T01 未完成时保留 D01 开放。

### T02：把文件政策写进同一套构建和审计契约

受影响位置：`release/source-inventory.json`、`release/preview-inputs.json`、`tools/build_release.py`、`tools/build_preview.py`、`tools/build_ce_entry.py`、`tools/audit_ce_entry.py`、`tools/package_ce2021_github.py` 及失败测试。

先按已确认的清理目标明确源码仓库、构建输入、分发 ZIP 三者范围，再决定应保留哪些输入或调整哪些文档断言。逐项解释清理差异，不把未经审查的删除全部机械写入 inventory。保持 code/assets 的 exact inventory 和签名/隔离导入等检查。

将 `bootstrap/LICENSE` 的当前冲突作为最小回归用例：真实 cleaner 的输出必须与入口 builder/audit 的政策一致。文档规则变化可以调整针对文档的断言，不能跳过整个 entry audit 或令验签、同代 bootstrap、隔离导入形同虚设。

输出 `REMOVAL-MANIFEST.json`：每项 removed path、所在 archive 层级、原 hash、命中规则及批准的清理类别。过滤的 patch blocks 单独列路径/数量；不要用 removed_entries 一个总数代替审计。

### T03：修复输入代次和原始来源记录

当前专用 CE2021 工具只接受经过验证的 `sequence == 2026102021` 原件；用受控参数/配置钉住原始 outer delivery SHA、内嵌 payload SHA 和预期组件身份。先验证原始 manifest 的类型、完整成员和签名，再修改它。outer 与 entry 内嵌载荷必须一致。

`original_sequence` 从已验证的原 manifest 派生，不从文件名或固定常量伪造。来源摘要也来自实际读取字节。输出 sequence 要与当前发布登记核对后分配唯一值，不复用 2026102022，不臆定“下一个数字一定空闲”。

保留并验证：正确 CE2021 接受；合法旧代次拒绝；相同/更大输入代次拒绝；错误 profile/channel/key 拒绝；组件损坏、成员不符和 entry/payload 不一致拒绝；清理后非排除字节保持；输出真实验签通过。

本包反例用临时 RSA fixture，不能替代最终真实资产验签。若把工具改为通用重签器，须明确改契约、如实记录任何原代次，且增加调用者显式期望输入身份；不能仅删掉旧代次负例。

### T04：关闭真实行为问题，审查适配差异

**F01 / G01：**

- enabled 但 owner 已死：原生导入保留 addon 身份；标准恢复后再次 quiesce 能关闭同一受管服务；不得仅将路径 RunScript 字符串换成 addon ID 便结案。
- 存活 owner：认证请求由 owner 执行空闲检查；音频、视频或未知状态拒绝安装停机；旧代次的兼容路径明确且有界。
- 停止接纳工作后取消或排空 next/subtitle/history；真实任务未结束时 lease 不转交。close 或日志回调抛错仍继续其他清理，未完成状态可重试。
- 验证原有总等待预算，不用逐层叠加 timeout 掩盖死锁。最终 old owner/辅助任务结束，enabled 向量与皮肤恢复，new owner 实际 ready。

**F02：**

- 非首卡已选，native bind 延迟和提前派发两个顺序均保持稳定 source key；现有 ListItem 身份保留。
- 1080p 已选、新增 4K 标签，控件选中项和实际筛选都保持。
- 结构变化后的必要补偿排在 bind 之后；纯字段变化不重绑、不 reset、不抢焦点。
- 首卡、手动切换、原选项真正消失分别给出明确正控。

**F03：**

- 一次新鲜权威 snapshot 分类 ACTIVE、匹配 TERMINAL、确有证据的 SUPERSEDED 与 UNKNOWN。
- 临时 IPC 失败后仍是原实例时继续有界观察；同实例 EOF 竞态进入一次终态对账；未知超预算有界退出，不触发成功副作用。
- 明确取消、新请求、错实例 EOF、重复或迟到 EOF 不复活旧任务，不清理新 owner，不重复续播。
- 在完整 native owner-loop + 真实 request adapter 组合补证；方法摘取反例不是最终集成验收。

夹具可以迁移到真实新接口，但保存旧脚本、适配副本、diff、改动理由与适配前结果。EOF 注入点迁移到 snapshot、结构变化后一次选择补偿、慢 IO 独立释放、真实 HTTP 不用虚拟时钟压缩预算，可以有合理原因；原行为断言不能被改成允许错误。适配后的 14/14 或 48/48 必须由当前候选实际运行取得。

G03 维持条件性加固：若实现明确清空 seeders/peers，给出可达对象更新用例；没有真实路径证据时不把它升级为日常故障。旧 history 风险也不夸大成已证实数据损坏。

### T05：当前候选与真实资产的最终门禁

在完整 checkout、独立虚拟环境中安装项目 `requirements-test.txt`；三套 pytest 按仓库 CI 隔离。以下参数属于当前仓库既有命令：

```bash
python -m pytest -q -rs tests --ignore=tests/private_baseline --ignore=tests/preparation_regression --junitxml=review-evidence/ce-next-primary.xml
python -m pytest -q -rs tests/private_baseline --junitxml=review-evidence/ce-next-baseline.xml
python -m pytest -q -rs tests/preparation_regression --junitxml=review-evidence/ce-next-preparation.xml
python tools/build_release.py --source-check --output dist/ce-next-check-one
python tools/build_release.py --source-check --output dist/ce-next-check-two
python tools/check_repository.py dist/ce-next-check-one dist/ce-next-check-two
```

使用新的空输出目录，逐命令记录返回码；某一步失败时不能把后一步未执行记为成功。构建目录已存在时另选唯一目录，保护旧证据。仓库后续确有 CLI 变化则同步更新命令和说明。

本包独立检查可逐项执行，明确反例在受审旧 head 上预期退出 1：

```bash
python -B checks/reproduce_native_list_focus.py --repo /absolute/path/to/candidate --output /absolute/path/to/results/ui.json
python -B checks/reproduce_native_monitor.py --repo /absolute/path/to/candidate --output /absolute/path/to/results/native.json
python -B checks/reproduce_clean_entry_audit.py --repo /absolute/path/to/candidate --output /absolute/path/to/results/entry-contract.json
python -B checks/reproduce_input_generation.py --repo /absolute/path/to/candidate --output /absolute/path/to/results/input-generation.json
```

结果中的 review_reference_commit 仅表示审查基准；实际被测身份由当前 commit/tree、dirty diff 与文件摘要决定。UI/native 原脚本保留本次原始契约，接口变化时按 T04 审查适配，不用 import error 代替产品失败。

最后对**最终真实用户入口**执行：

```bash
python tools/audit_ce_entry.py /absolute/path/to/final-entry.zip --report /absolute/path/to/results/final-entry-audit.json
```

另核对：最终独立 payload 与内嵌 payload 相同；全部组件 manifest/hash/size；原 trust；真实签名正负控；同代 bootstrap；账号状态未混入；源码与包内文件对应；删除清单完整。清理脚本自己的 passed flags 不能替代这些独立检查。固定 release 目标 commit，并保存源码+构建环境+工具摘要，不只指向可移动分支。

### T06：两项播放专项及有限设备复验

详细步骤见 `reviews/NEXT-PLAYBACK-GUIDANCE.zh-CN.md`。两个专项可以分工，但用同一可追溯候选及各自明确 attempt。

**《元气囝仔》metadata_timeout：** 固定 TMDb 67048 / S1E1 / 诸神 1080p 原 BT 身份；记录 backend 状态、add 确认、metadata poll/elapsed、文件数量、取消及结束原因。用同 backend 已知可用来源作有限对照，区分后端、特定资源与状态解释。原资源成功必须有 metadata 文件表、严格集数选择和实际 AV。没有 metadata 时按既有预算失败并保留用户返回选源；不通过换版本或全局加长重试消去失败记录。

**《乒乓》中文：** 固定 TMDb 60811 / S1E1 / 115 Vodes 原视频文件；分别检查内嵌轨、provider 鉴权/限流/超时、候选、中文文本、作品/集数/版本、时间轴、加载、实际当前字幕轨。利用既有错误状态投影。真正匹配中文出现、可读且多位置同步才通过；英语、错集、仅下载未绑定不能通过。手动选择和 Off 不被迟到自动结果覆盖。

**续播：** 父 request/instance/file → 同实例自然 EOF → 一次 SAME_VERSION_HANDOFF → 严格匹配的下一集 → 新 request/instance → 真实 AV/正进度，完整有序证据保留。StartPercent 98.8 是尾段边界回归，不能记成整集观看。

设备操作遵从当前会话已有授权，先确认空闲与可回退，记录实际安装包 hash/sequence。源码或包身份未闭环时不以新实机数字替代交付问题。无需为这轮引入新的机型、第二设备或第二账号准入门槛。

### T07：必须交回的结果

1. 固定源码 commit/tree、清晰 diff 与本次变化原因；T01 恢复来源及历史映射。
2. D01–D03、F01–F03、G01/G03 状态逐项记录：修复、未修、未验证及对应证据，不用一个总 passed。
3. 所有实际命令、exit code、原始 JSON/XML/日志、适配 diff 与未执行项。
4. 完整包摘要、signature sequence、组件清单、源码映射、删除清单、真实入口 audit。
5. 每个设备/作品 attempt 的固定对象、阶段与限定窗口；原声/中文/AV/进度/EOF/同版续播分列。
6. `transport_ok`、`trial_passed`、`exit_code`、`pending` 分列；未知保留 unknown，不伪装通过。
7. 下一轮未完成项及最小复现。保留旧失败和历史报告，新结果新增版本，不覆盖原证据。

推荐最终文件名：`NEXT-CLOSURE.md`、`SOURCE-ARTIFACT-MAP.json`、`REMOVAL-MANIFEST.json`、`GATE-RESULTS.json`、`EVIDENCE-INDEX.json` 与实际原始回执。缺失原件或授权时明确写出对象和影响，但先完成所有不受阻的工作。
