# Bobbi TV CE2024 独立审查报告

审查日期：2026-10-21（Asia/Shanghai）。对象：codex/ce2024-reviewed-delivery-20261021。固定提交：c4e0baca6acefa58f031979bff71e7cd1028efdf。

## 1. 审查结论

**建议保留 CE2024 为下一轮修复基线；源码与安装包对应关系、构建和验签已通过本轮独立核验，完整产品验收仍需修改后继续。**

上一轮 D01「修复源码未交付」和 D02「清理破坏构建/审核契约」已具备关闭证据。D03 的输入身份及代次校验代码也已修复，35 项真实 RSA/ZIP 夹具通过；最初 CE2021 外层原包丢失的历史正例缺口继续保留。旧 F01/F02/F03 的对应代码缺陷可在已复核范围内关闭，不能把这些关闭扩大成完整升级、回退、整集续播或全部片源观看通过。

本轮确认 **4 项 P2**，其中字幕季集推断和测试回执归属属于本次新增代码问题；渐进式 producer 退出、多解码通道统计属于前版已有、这次独立证实的遗漏。没有发现新的已证实 P0/P1；这个等级说明的是本轮发现的范围，不是对所有设备和播放路径的无缺陷保证。

| 编号 | 发现 | 性质 | 当前状态 |
|---|---|---|---|
| R24-01 | 弱集号字幕忽略其他季/特别篇反证，可发布错误自动候选 | 新增 P2 | 20 项矩阵中 6 项错误放行 |
| R24-02 | progressive 上游 producer 未退出，Host 已释放实例锁 | 遗留 P2；G01 未完全关闭 | 原包依赖、真实 HTTP 三控复现 |
| R24-03 | 测试回执把执行归到记录器仓库 commit | 新增 P2；工具证据 | 两个真实 Git 仓库对照复现 |
| R24-04 | 多解码通道同名计数被最后一个通道覆盖 | 遗留 P2；诊断证据 | 真实回执文本与实际 sample 函数复现 |

作者报告明确保留了新电影起播、新动漫原音/字幕/缓冲、旧 BT、热态 UI 等失败，本轮没有把报告解读成“全通过”，也没有据新反例反推作者已造假。审查判断与交付文档大部分边界一致；需要补的是这四个可复现缺口及剩余实机闭环。

## 2. 固定身份与覆盖范围

| 对象 | 身份/范围 |
|---|---|
| 审查 head | c4e0baca6acefa58f031979bff71e7cd1028efdf |
| head tree | bb4256d63465fefb9c5820f3ce1ec9cca33ff546 |
| 产品 commit | d2fffa570fe59b90cd1d33499efcf7c6684b2647 |
| 产品 tree | 380b4493b2eafcaa46efe63e0ebd8c5cd1686dc3 |
| 上轮基线 | b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2 |
| 实际签名身份 | 2026102024 / coreelec / private-candidate |
| start / platform / core / plugin | 0.2.15 / 0.1.18 / 0.1.17 / 0.1.16 |
| 完整 recursive tree | 5,608 条，truncated=false |
| 与上一轮完整 tree 比较 | 新增 1,142；修改 48；删除 0 |
| 产品 addons 变更 | 新增 3、修改 23；third_party 无变更 |

交付前于 2026-10-21 14:28:45（Asia/Shanghai）重新读取，分支仍为上述 head，当前 CI 仍为 success；见 evidence/source/FINAL-REF-CHECK.json。

GitHub compare 返回的 files 仅 300 条，本轮使用完整 tree 计算差异，未把截断结果当全部改动。审查覆盖改动的产品实现、构建/重签/交付工具、测试适配、当前 CI、实际入口及关键原始设备回执。大量新增路径是历史和当前证据，不应把 1,142 个新增路径解释成 1,142 处产品改写。

独立比较产品 commit 与 handoff head 的 addons/、third_party/、release/ 三个目录，共 1,561 个 tree 条目，无差异。因此本次对 head 的运行文件核验也覆盖产品 commit；维护工具和报告另行按 handoff head 审查。

来源：[固定提交](https://github.com/2223M1/bobbi-tv/commit/c4e0baca6acefa58f031979bff71e7cd1028efdf)、[产品提交](https://github.com/2223M1/bobbi-tv/commit/d2fffa570fe59b90cd1d33499efcf7c6684b2647)、[原交付报告](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/docs/CE2024-DELIVERY.md)。独立证据：evidence/source/。

## 3. 四项发现与关闭条件

### R24-01 / P2：单季证据不能覆盖文件明确的其他季或特别篇声明

**触发条件：** 目标 S1E1，作品元数据满足新的 SingleSeason 证据，字幕文件使用 EP01 或第01話，同时明确带有“第2季”“第二季”“2nd Season”“OVA”“Specials”或“番外篇”。

当前 from_details 排除 S0 后建立“唯一正规季”授权；rank 的季号提取只覆盖 Snn 与 Season nn。弱集号 matches 又只核对授权和集号集合，没有否决上述文件反证。结果是明确声明其他季，或带有尚未可靠映射到目标季集的 OVA／特别篇标记的文件，仍能作为 S1E1 候选。

本轮使用实际 rank、AssrtCandidates.candidates、正文检查与 publish；仅 provider 网络 I/O 是确定性夹具。6 个错误文件均被写出为 state=candidate，实际中文 SRT 正文和文件导出检查没有挡住它们。相同夹具在上轮 CE2021 均被拒绝。20 项矩阵中其余 14 项通过，包括合法 EP01/第01話、显式 S01E01、明确包季号授权，以及错集、S02E01、范围、无 scope、错 TMDb、超集数、冲突集号等拒绝条件。

后续 fallback、KodiNative 和 PlaybackAuthority 会继续检查 request/native instance、账户、手动字幕意图和文件身份，但没有再次核对语义季集。满足自动外挂条件时，这些候选可以进入应用路径。本轮动态证明到候选发布；**没有声称实际《乒乓》加载了错误字幕，也没有把合成文件名说成真实 provider 曾返回的文件。**

**最小修复：** 在弱集号授权之前统一识别明确季号冲突和特别篇歧义；不能因为“一个正规季”就忽略 S0/OVA/其他季。标记解析要避开规范作品名本身，避免粗暴词语黑名单误杀合法标题。保留有效 EP01、第01話、[01]、明确包季号及原有强身份正控；不放宽视频文件或自动续播身份。

**关闭标准：** 本包 20 项矩阵全部满足原期望；增加规范标题本身含相关词、metadata 与文件互相冲突的边界；真实字幕回归继续用原作品/原集/原源，并分别确认正确正文、前中后同步和手动 Off 不被覆盖。

定位：[subtitle_episode.py 34–48](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/subtitle_episode.py#L34-L48)、[subtitle_candidates.py 122–137](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/subtitle_candidates.py#L122-L137)。

证据：evidence/playback/subtitle-scope-matrix.json；旧版对照同目录。复现：checks/reproduce_subtitle_scope.py。自动应用路径的具体定位与完整矩阵见 reviews/PLAYBACK-REVIEW.zh-CN.md。

### R24-02 / P2：渐进式流代理的 producer 未加入服务最终退出屏障

**触发条件：** 用户通过实际设置入口启用 progressive，已有上游请求持续缓慢发送响应头，服务开始关闭。缺配置时默认 block；默认路径的阴性对照没有发生提前释放。

HTTP handler 清理仅 worker.join(15)。若 producer 仍在 requests.Session.get 等待完整响应头，单次 socket-read 的 10 秒超时不等于响应头总截止时间，持续少量数据可让这段等待超过 15 秒。handler 退出后，ShareStream.close 等完 server/handler 并返回，Host 随即释放 OS lease；独立 share-stream-prefix 仍可能活着。

本轮使用真实 loopback 上游/下游 HTTP、实际 Host、ShareStream、InstanceLock，以及真实安装包中的 requests 2.31.0 / urllib3 2.2.3。没有修改时钟、transport、join 或 15 秒预算。

| 场景 | 观察 | 结果 |
|---|---|---|
| progressive，约 0.3 秒后完成响应头 | 约 0.312 秒关闭，producer 已退出，随后新 lease 可取得 | 正控通过 |
| progressive，持续慢响应头 | 15.098 秒关闭完成，旧 producer 仍活着，新 lease 已可取得 | 不变量失败 |
| block，相同慢响应头 | 16.801 秒关闭未完成，新 lease 仍被拒绝；放行后排空 | 阴性对照通过 |

精确时序确认：Host 先关闭、新 lease 先成功，测试随后才放行上游头部，旧 producer 最后退出。测试线程均已清理。它证明 Host 的“所有已接纳工作退出后才允许接管”约束存在遗漏；**没有证明已发生设备文件替换、数据库损坏，或本次 4K 起播故障由此引起。**

**最小修复：** ShareStream 统一登记、拥有并排空全部 producer；请求 handler 结束后，其仍存活的 producer 仍须归服务管理。关闭失败或未排空时 Host 保留 lease，并支持重试。避免持有 producer 退出所需的锁等待；不要只增加 join 秒数或把 semaphore 配额当跨代所有权。

**关闭标准：** 三控保持同样的真实条件；所有旧 producer 活着时新 lease 必须拒绝，全部退出后才能取得。补“handler 先退出，稍后才关闭 Host”、重复 close、close 中异常、停止接纳的竞争。保留安装器既有拒绝边界，不依靠全局延长超时通过。

定位：[share_stream.py 862–870](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/share_stream.py#L862-L870)、[ShareStream.close](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/share_stream.py#L530-L543)、[Host.close](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.platform/lib/bobbi_platform/host.py#L397-L416)。

证据：evidence/lifecycle/ 的三份场景 JSON、progressive-shutdown.xml/log 与实际依赖来源。复现：checks/test_progressive_shutdown.py。

### R24-03 / P2：执行目录和回执 commit 来源不是同一个仓库

closure_gate.run(name, command, root=...) 让 subprocess 在 root 中运行，却在记录器 ROOT 中读取 git rev-parse HEAD。调用者使用干净 worktree 运行测试时，回执可能标注另一个 checkout 的 commit。package_ce2024_handoff.local_gates 又把该字段等于 PRODUCT 作为身份门禁。

本轮建立两个内容/commit 不同的真实临时 Git 仓库。命令自己打印执行仓库的 HEAD，结果回执记录另一个仓库：同仓库对照通过，跨仓库执行反例失败；第二个独立审查者也复跑得到相同行为。没有 mock subprocess 或产品函数。

本次 clean24-primary 的原始回执确实使用了独立 cleancheck cwd，因此接口问题与现实工作流相关。但**此反例不证明当时真的测试了错误源码**；当前 GitHub CI 的固定 checkout、实际包 1,349 文件映射和产品 tree 比较已独立补足 CE2024 身份。dirty=true 是保守硬编码，不能误写为把脏目录冒称干净。

**最小修复：** 明确区分 execution_root 与 recorder_root；在实际执行根读取 Git 顶层目录、commit、tree 和状态。执行前后都采集，工作区或身份变化要使门禁失败；无法确认执行目录的 Git 身份时，不可退回记录器仓库当作默认值。记录器工具自身哈希另存，保留日志位置与身份来源。

**关闭标准：** 同仓库、另一个 worktree、不同仓库、执行中变化、无 Git 根各有明确行为；跨根执行必须归于实际执行根，错误不得生成可接受的产品通过回执。更新 handoff gate 消费新 schema。保留历史原始回执，不原地“修正”旧文件。

定位：[closure_gate.py 19–25](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/closure_gate.py#L19-L25)、[package_ce2024_handoff.py 72–85](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/package_ce2024_handoff.py#L72-L85)。

证据：evidence/provenance/；复现：checks/test_closure_gate_identity.py。

### R24-04 / P2：解码计数丢失通道身份，结果依赖通道输出顺序

ce_trial_remote.sample 把 vdec_status 全文中的 frame/drop/fra err/hw err 写入一个字典。同名字段在多通道文本中被后一个通道覆盖。

本轮《布达佩斯》observe 原始回执末尾有两个真实通道：channel 0 dvbldec 三类错误/drop 均为累计 8；channel 1 dveldec 均为 0。使用完整、未改写的当前 sample 函数，只替换设备 I/O 边界，得到：

| 输入文本 | drop / fra err / hw err |
|---|---|
| 仅真实 channel 0 块 | 8 / 8 / 8 |
| 真实原顺序全文：0 后接 1 | 0 / 0 / 0 |
| 同样两个块，仅交换顺序 | 8 / 8 / 8 |

旧 b20e972 解析 AST 与当前完全一致，因此是遗留问题。本轮证据定位明确，不应泛称结构化采样已证明“解码零错误”。

**限定：** 末尾原始快照与之前四个 sample 并非已证明同一时刻；不能把累计 8 反填到四个历史 sample，也不能说错误必然发生于后续 30 秒窗。它不是起播卡顿根因证明，作者也仍保留 startup 失败。

**最小修复：** 按通道 ID/设备名保存完整结构；原文与采样时间绑定；若使用增量判断，先确认通道身份、重置、替换及前后样本可比较。不要直接把双层 decoder 的 frame count 相加。

**关闭标准：** 单通道、多通道、块顺序变化、通道消失/新增、计数重置均不会静默丢掉非零值；无法比较时明确 unknown。本包探针是确认历史错误行为，正式回归应断言“保留各通道且顺序不影响结果”，不能把当前错误值作为永久期望。

定位：[ce_trial_remote.py 298–300](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/ce_trial_remote.py#L298-L300)。真实输入：[固定 observe 回执](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce-new-work-grand_budapest-observe-1792551462588057300.json)。

证据：evidence/decoder/；复现：checks/decoder-reproduce.py。

## 4. 上轮问题逐项复核

| 旧问题 | 本轮判断 | 关闭边界 |
|---|---|---|
| D01 修复未进入 Git | 关闭 | 当前真实产品实现已进入固定 tree，实际包与该源码一致；不代表每个修复目标都无遗漏 |
| D02 清理/构建/audit 契约冲突 | 关闭 | 统一政策、真实 CI 双构建、实际入口完整核验均通过 |
| D03 任意旧代次输入/错误来源记账 | 代码与真实 RSA/ZIP 夹具关闭 | 原 CE2021 outer 丢失，精确生产旧输入正例仍缺失 |
| F01 裸路径恢复/停机顺序 | 对应源码和窄集关闭 | 实际受管 enable、真实 owner/lease；完整新版本回退需另验 |
| F02 卡片/画质焦点回零 | 对应缺陷关闭 | 原独立脚本 5/5；真实 UI 回执为合成卡片、无播放/登录 |
| F03 UNKNOWN/EOF 监控退出竞态 | 对应缺陷关闭 | 原断言适配后 5/5；整集 EOF → 同版下一集未重做 |
| G01 所有消费者排空 | 部分关闭 | standard/history/close-retry 改进成立；R24-02 仍开放 |
| G03 可选 seeders/peers 残留 | 相关源码和回归已恢复 | 当前两字段会显式清空；不扩大为已发生真实设备数据损坏 |
| CE2023 同步 GUI 死锁 | CE2024 修复机制和定向验证成立 | 新 GUI fence/异步安装、真实历史安装 complete；热态 UI 超时仍开放 |

F03 的独立反例仅适配新的 timeout 参数及单次 snapshot 的 EOF 注入次序，原行为断言未改变。F02 旧脚本未经修改重放。生命周期窄集 32 项、播放/UI 窄集 59 个唯一用例、交付窄集 35 项均通过；这些集合分别记账，不与 CI 或重复复跑相加。

## 5. 实际安装包核验

本轮取得了分支中保存的真实入口字节，不再沿用上轮“未取得安装包”的限制。先由实际文件计算大小、SHA-256 和 Git blob，再匹配固定 tree；随后同时执行产品 SignedBundle.check_all 和独立 cryptography RSA-3072 / PKCS#1 v1.5 / SHA-256 验签。

| 项目 | 实际结果 |
|---|---|
| 入口字节数 | 95,916,922 |
| 入口 SHA-256 | cb355eb2a80b3974e985a9bc404fb74a8be1c98ab1319d30e4399eb503c06e9c |
| 内嵌 payload 字节数 | 95,817,630 |
| payload SHA-256 | d53bc3b6ad0c4dc905a831d1906575a7c53ad15c0e6a6d6d7b12188e0d33c096 |
| 签名组件 | 22 个，全部通过 |
| Git 文件 | 1,349 个，全部匹配 inventory SHA-256 与固定 Git blob |
| 文件分布 | addons 下 1,142；third_party/addons 下 207 |
| 唯一额外构建输入 | 237 字节应用配置；仅记录散列，未披露内容 |
| 实际组件文件总数 | 1,350 = 1,349 Git 文件 + 1 应用输入 |
| 自有程序文件口径 | 1,143 = 1,142 Git 文件 + 1 应用输入 |
| 外层入口 | 17 成员 = start 组件 2 + 同代 bootstrap 14 + payload 1，精确相等 |
| 未知额外/缺失成员 | 0 |
| 隔离 bootstrap 导入 | 通过 |

外层 default.py/addon.xml 同样对照签名组件，未仅依赖作者审核器的 account_state_copied=false 字段。字体、声音、图片、XML、Python 等运行文件都处在完整文件映射中。当前文档清理不再破坏 inventory 和构建；不需要恢复已确认清理的独立说明文档来解决工程问题。

这说明该实际包确实对应被审查源码；不说明包内程序已满足所有播放体验目标。实际包中的产品逻辑仍然包含 R24-01、R24-02。

[固定入口下载页面](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-packages/ce2024/script.bobbi.start-0.2.15-ce2024.zip)。完整独立逐文件结果：evidence/package/ACTUAL-ENTRY-VERIFIED.json；可复跑验证器：checks/verify_actual_entry.py。

## 6. 当前 CI 与独立检查

真实 GitHub run 39537767479、job 119018276236，checkout 为本次固定 head/tree，结论 success。已直接下载并解析原始 JUnit artifact 12318492520，47,962 字节，SHA-256 为 05f88c6c78878dee189ce76fbc101ed229746c6791fe1e1983752a2bdb98f4f8。主审再次按 testcase 元素计数，与套件属性相符。

| 当前 CI | passed | skipped | failed | errors |
|---|---:|---:|---:|---:|
| primary | 1,838 | 5 | 0 | 0 |
| baseline | 789 | 0 | 0 | 0 |
| preparation | 177 | 0 | 0 | 0 |
| 合计 | 2,804 | 5 | 0 | 0 |

当前 5 个 skip 是 Linux 环境未执行的 Windows inherited-pipe API 场景。作者 Windows 本地产品回执为 primary 1,823 passed / 6 skipped；6 个 skip 是无法创建符号链接。逐条比较确认：当前增加 14 个 handoff 测试，无旧测试被移除；6 个旧 skip 在 Linux 通过，5 个 Windows 绑定用例转为 skip，故通过数净增 15。两套成绩的时间、源码范围与环境不同，不能拼成同一次运行。

原始 CI 日志确认两次 source-check 各构建 22 个组件，63 个输出文件逐字节一致。source-check 无生产应用配置/私钥，不是 CI 重建私有签名入口的证明；私有入口身份由第五节的实际包核验单独支持。

| 独立检查 | 结果 | 含义 |
|---|---|---|
| F02 原独立探针 | 5/5 | 队列绑定后焦点补偿符合原断言 |
| F03 原独立断言，最小接口适配 | 5/5 | 暂时 IPC 缺失、EOF、替换、取消行为改善 |
| 生命周期现有测试 | 32 passed | 既有断言独立重跑 |
| 播放/UI 现有测试 | 59 个唯一用例 passed | 已剔除重复 loopback 重跑 |
| 真实 RSA/ZIP 交付测试 | 35 passed | 临时测试密钥，不是生产旧包正例 |
| 新字幕矩阵 | 14 passed / 6 反例 | R24-01 |
| 原包依赖真实 HTTP 三控 | 2 passed / 1 反例 | R24-02 |
| 两仓库回执归属 | 1 passed / 1 反例 | R24-03；第二人复跑不重复累计 |
| 多 decoder 实际 sample 探针 | 3 种文本输入证实顺序依赖 | R24-04；不是 3 个修复通过测试 |

首次因沙箱禁止 loopback socket 导致的 PermissionError 均与产品失败分开记录；获得本机 socket 权限后，相同产品窄集通过。新反例不是 import 错误或环境禁止造成的失败。

[当前 CI](https://github.com/2223M1/bobbi-tv/actions/runs/39537767479)、[固定工作流](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/.github/workflows/verify.yml)。原始 CI 与交叉统计位于 evidence/ci/。

## 7. 真机与影片证据的准确结论

本节为独立读取作者提交的固定版本原始回执，**本轮没有连接电视重跑**。包内文件匹配由本审查实际完成；设备 1,143 自有文件匹配是作者设备汇总回执，不能混称本审查重新读了电视文件。

| 项目 | 已有证据支持 | 后续仍需完成 |
|---|---|---|
| 实际 CE2024 安装 | 安装 journal complete，sequence/high_watermark 2026102024；版本与自有文件汇总吻合 | 经暂存入口再操作菜单，尚非 Kodi ZIP 浏览器导入全过程认证 |
| 受管恢复 | 协作停止后的三轮 owner/lease、启用向量、皮肤恢复 | 不等于 CE2024 完整安装后回退循环；旧 StopScript 失败仍保留 |
| 来源 UI | 非首项与 1080p 维持、reset=0；74 帧 ROI 一致的原回执 | 合成卡片/假二维码，无真实登录交换或视频；热态 UI timeout 未解释 |
| 《乒乓》S1E1 | 115 1080p；约 4.69 秒首次观察 AV，34.48 秒启动正窗口；实际 jpn 音轨，外挂 applied 且 enabled | 未取得该 applied SHA 的完整字幕正文映射；前中后同步/可读性、Off、字体、整集续播未验 |
| 《布达佩斯大饭店》4K REMUX | 原画质/英语 DTS-HD MA；起播最大观察停滞 17.48 秒、连续 caching 10.5 秒、日志 decoder timeout | 起播失败仍成立；后续 30.33 秒窗推进 30.16 秒不能覆盖。需先修分通道采样再定位 |
| 《比宇宙更遥远的地方》S1E1 | 40 秒 trace 未见 AV，后来确实开播；metadata 1.552 秒、buffering 46.401 秒、total 48.496 秒 | 英语 5.1、无启用中文字幕，原音/字幕/缓冲未过；约 84.78 秒是后续观察上界，不是精确首帧时延 |
| 《元气囝仔》原 BT | 交付文档仍保留旧 metadata 失败；这次查询 0 候选、2 来源失败 | 未重到原 metadata 阶段，旧问题不能关闭；本审查未另取其全部原始 JSON |
| 完整退出/连续观看 | 代码回归有明确改善 | 长时播放、seek、整集 EOF→同版下一集、STOP/取消/换源等组合实播仍需逐项记账 |

en-US TMDb 详情缓存存在不等于作品原声为英语，也不能单独解释原音 hint 失败。先记录同一 request 的 original_language、cache locale/age、hint 产生与传递、native 选轨理由，再决定修哪里。字幕则分别观察 detail、下载、中文正文、候选发布、导出、native 提交和确认；只显示候选不能算字幕已加载。

设备不应为了重现而改变固件、SYSTEM/eMMC、CD2、挂载、Yatse、服务器/newapi/代理，也不应替换整库账户或观看历史。完整回退只走产品已核验的合法恢复路径，不手改高水位或硬装旧代次。这里沿用当前项目边界，没有新增盒子白名单或新账号测试要求。

## 8. 后续执行顺序

| 批次 | 工作 | 完成判据 |
|---|---|---|
| A：代码与证据修复 | R24-01 字幕 scope、R24-02 producer 排空；R24-03/R24-04 可并行独立改动 | 原反例转绿，既有正控保留，执行/采样身份真实 |
| B：准备受测候选 | 先更新版本/inventory，再冻结产品 commit/tree、三套测试、双构建、新代次签包及全包核验 | 得到明确可识别的实际候选；按已有授权安装并核对运行身份 |
| C：同源定位 | 原《比宇宙》原音与字幕链、原《布达佩斯》起播；可查时回到原《元气囝仔》 | 有同一 request/source/instance 的阶段证据；未到达阶段如实标记未覆盖 |
| D：设备闭环 | 热态 UI/空列表返回、完整回退、ZIP 导入、字幕前中后与手动意图、整集交接、长看/seek | 每项独立回执，启动失败不能由后续短窗覆盖 |
| E：最终交付 | 汇集受测候选身份、设备原始回执、真实 CI 与未通过项，冻结 handoff | 产品在测试后若又改动，重新冻结候选并明确需要重验的结论 |

旧 CE2024 上可随时继续只读定位，但结果必须单列为旧基线诊断。C/D 若用于验收本轮产品修复，B 是前置条件；不能把仍运行旧 CE2024 的设备结果记给尚未安装的新修复。新代次只按最新登记确定，不预占下一数字。

不建议下一轮再以全面清理、播放器重写或更换成功片源作为主要工作。当前最有价值的推进是保留已经闭合的来源链，完成四个小范围修复，并用同一批失败作品定位剩余体验问题。完整步骤和验收约束在 CODEX-EXECUTION-PACK.zh-CN.md。

## 9. 交付包内容和使用

- CE2024-REVIEW.zh-CN.md：本主报告。
- CODEX-EXECUTION-PACK.zh-CN.md：可直接交给 Codex 的任务书，含范围、顺序、验收和交付要求。
- FINDINGS.json：统一 R24-01 至 R24-04、旧问题关闭状态与验证边界。
- checks/README.zh-CN.md：固定基线复现命令、依赖及各脚本预期结果。
- checks/：实际包验证、F02/F03、字幕、真实 HTTP 退出、Git 回执、解码诊断脚本。
- evidence/：固定 tree、完整差异、原始 CI/JUnit、实际包逐文件映射、独立反例和必要回执。
- reviews/：四个专项报告。
- MANIFEST.json、SHA256SUMS.txt：交付文件长度与散列；外层 ZIP 有独立校验文件。

这是独立审查与修复执行包，不包含新的产品修复或重新签发的安装包。原始 95 MB 安装入口仍按固定 Git 路径取得；没有把生产应用配置、签名私钥或完整仓库重复装入审查包。

审查过程中未做设备安装/回退/播放、未改产品源码、未向 GitHub 推送、合并、发布或发评论。未重新查看全部设备截图或认证视频平面、HDR 主观表现。对原始 CE2021 外包丢失、Windows 专属 API 跳过、未实测的真实回退和整集播放，均保留原有证据边界。

