# CE2024 独立审查、整改建议与交付评估

审查日期：2026-10-21（北京时间）  
仓库：2223M1/bobbi-tv  
审查分支：codex/ce2024-reviewed-delivery-20261021  
冻结 handoff：`c4e0baca6acefa58f031979bff71e7cd1028efdf`  
冻结 tree：`bb4256d63465fefb9c5820f3ce1ec9cca33ff546`  
产品源码：`d2fffa570fe59b90cd1d33499efcf7c6684b2647`  
产品 tree：`380b4493b2eafcaa46efe63e0ebd8c5cd1686dc3`

## 一、结论与处理顺序

**CE2024 已经实质解决上轮 D01–D04 的源码和交付链问题，可以作为继续个人内测的修复候选保留；本次不建议将其关闭为稳定交付或所有观看问题已解决。**

上轮缺失的产品修复已进入 Git；实际 CI 通过；清单和真实入口构建修通；26 条历史证据链接全部恢复。不能再把 CE2021 的“只提交三个文件”“当前 CI 红”“入口必须读取已删除 LICENSE”等结论套到本版本。

本次新增三项有受控复现的问题：

| ID | 级别 | 问题 | 处置 |
|---|---|---|---|
| CE24-R01 | P1 | 协作退出超时后的自动重试，会因 runtime 标记已消失而先停用仍持锁的 owner | 优先修复维护失败恢复路径，再关闭安装维护验收 |
| CE24-R02 | P2 | EP01,02、EP01、02 等多集/歧义字幕名被认成精确单集 | 收紧歧义识别，保留合法 EP01 / 第01話 的单季修复 |
| CE24-R03 | P2 | HistoryWriter 的失败日志再抛异常会杀死 writer，close 却成功返回 | 保护诊断回调，检测实际排空完成，保留异常结果 |

另有已在本代实机报告中诚实保留的开放问题：4K REMUX 起播停顿与 decoder timeout、新动漫 BT 缓冲/原声/中文字幕、旧 BT 原资源失败、热态 UI 超时，以及普通 Kodi ZIP 导入、完整回退、长时观看和整集同版续播等未认证范围。它们和上表的新源码问题分别记账。

本次没有推送、评论、合并或部署，也没有读取盒子的实时状态。设备结论来自本分支已提交的原始回执，不是本审查重新连接盒子所得。

## 二、审查范围和证据等级

独立完成：

- 冻结提交、父提交关系、完整 Git tree（5608 项，未截断）、与上轮完整树的成员/对象比较。
- 核心恢复、关闭、列表绑定、monitor、字幕季集识别、构建/入口/bootstrap、文件策略及相关回归代码审查。
- 当前 GitHub CI 原始日志与实际下载的 JUnit ZIP；ZIP 摘要和内容已核对。
- 22 个组件、1349 个显式清单路径；1350 条已提交 source-package 映射与清单对应。
- 新问题的受控复现，以及 F02/F03、入口构建的针对性关闭验证。
- 已提交的恢复/UI/安装匹配/试播/后端阶段诊断回执，保留原失败与未覆盖状态。

边界：

1. Git 中存在已测入口 `review-packages/ce2024/script.bobbi.start-0.2.15-ce2024.zip`。标准文件接口返回其正确 blob 但内容为空；标准 blob 接口把 ZIP 按 UTF-8 解码失败。因此本次没有取得该 95,916,922 字节入口，不能声称独立验签真实产品包、重新计算其 ZIP 摘要或逐文件检查包内程序。
2. 本次取得并校验的是 GitHub CI 回执 ZIP；它与产品安装包是不同对象。
3. 本地探针使用真实相关模块或原方法，但 Kodi GUI/RPC、时钟和存储故障边界由夹具控制。它们不是设备认证，也不是全库测试重跑。
4. 本次未检查所有历史附件的内容或重做历史场景；26/26 表示相对链接目标已在当前树中恢复。

主要来源：[冻结提交](https://github.com/2223M1/bobbi-tv/commit/c4e0baca6acefa58f031979bff71e7cd1028efdf)、[本代交付报告](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/docs/CE2024-DELIVERY.md)、[实际 CI](https://github.com/2223M1/bobbi-tv/actions/runs/39537767479)。

## 三、旧问题复核：哪些已经可以关闭

### 3.1 D01：真实修复没有提交——已关闭原缺陷

与 b20e972 的完整树比较，本分支新增 1142 个文件、修改 48 个文件、删除 0 个文件；大量新增项是历史与本代证据，产品代码及新测试也已实际进入树中。该数量来自完整树对象比较，不依赖 GitHub compare 的最多 300 文件列表。

关键组件版本已经与本代交付报告一致：

| 组件 | CE2024 |
|---|---:|
| script.bobbi.start | 0.2.15 |
| script.module.bobbi.platform | 0.1.18 |
| script.module.bobbi.core | 0.1.17 |
| plugin.video.bobbi | 0.1.16 |

产品提交 d2fffa57 与 handoff c4e0baca 虽然 SHA 不同，但三个生产目录的子树对象完全相同：

| 目录 | 共同 Git tree SHA |
|---|---|
| addons | 4f27e7a61c17832714deeb0633deadee03f30433 |
| third_party | 542b9efba1882ddb327fa43a286ffaf4a79c2c6a |
| release | b1e892c4516239b513a2fd0316799f5c3d4d46d8 |

所以不能仅凭“产品提交与交付提交不同”判定错代。handoff 增补了证据、维护工具与说明。

F01 的受管启停和协作停机、G01 的失败继续清理与留锁、F02 的异步重绑补偿、F03 的单次快照四态分类均已落地。F01/G01 仍有本次新发现的故障组合，见 R01/R03；这不意味着此前主体修复不存在。

### 3.2 D02：清单与实际文件冲突、当前 CI 失败——已关闭原缺陷

22 个组件、1349 条显式文件路径对当前 Git 树核查，缺失 0、额外生产文件 0（独立生成的应用配置另有声明）。构建仍执行实际 SHA-256、成员集合和依赖检查，没有通过关闭校验换取绿色。

`delivery_policy.py` 明确文件策略；运行代码、字体与声音不会仅因目录名或泛化排除规则被悄悄删除。无需恢复用户已经确定清理的独立文档。[构建校验](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/build_release.py#L96-L122)、[文件策略](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/delivery_policy.py)。

当前 CI 的真实结果：

| 对象 | 结果 |
|---|---|
| Workflow / run | Verify private sources / 39537767479 |
| Job / 事件 | 119018276236 / push |
| 受测源码 | c4e0baca6acefa58f031979bff71e7cd1028efdf |
| 北京时间 | 2026-10-21 11:17–11:20 |
| 主套 | 1838 passed、5 skipped、1 warning；0 failures/errors |
| 继承套 | 789 passed |
| 准备套 | 177 passed |
| 第一次、第二次 source-check | 各构建 22 组件成功 |
| 两次结果比较 | Reproducible files: 63 |

5 项 skip 是 Linux 上不可执行的 Windows inherited-pipe API 测试。报告中的本地 1823 passed / 6 symlink skips 属于 Windows 产品提交的另一组回执；两者不可混用。

已独立下载 CI artifact 12318492520，47,962 字节，SHA-256 `05f88c6c78878dee189ce76fbc101ed229746c6791fe1e1983752a2bdb98f4f8`。其中三份 XML 的计数与原始 CI 日志一致。artifact 不含安装包。

当前分支没有对应 PR。PR #3 仍是旧分支 f6ef6a7，保持 open/draft；它的历史结果不代表本代集成测试。若后续创建新 PR，再记录它实际受测的 merge tree；这次不凭空增加一个不存在的 PR 门禁。

### 3.3 旧 D03：入口依赖已删除 LICENSE——已关闭原缺陷

`build_ce_entry.py` 已删除旧无条件 LICENSE 读取；bootstrap 仍从同代签名平台组件提取。[入口构建](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/build_ce_entry.py#L24-L49)。

本次用真实构建器、SignedBundle、RSA 校验器和 audit_ce_entry，生成两组件临时签名夹具：不含 LICENSE 的输入与仅补该文档的对照，都能成功生成入口，并通过同代 bootstrap 比较和独立解释器导入。14 个 bootstrap 成员的相对依赖完整；导入 KodiHost/Installer/runtime.call/InstanceLock 时没有依赖已安装 bobbi_core 掩盖问题。

这个结果关闭的是旧入口构建缺陷，不是实际 96 MB 产品包的独立验签或 Kodi ZIP 浏览器实测。

本代报告把另一份审查的“重签器输入代次/记账”也编号为 D03。应做交叉映射，不可因重签器说明而漏掉旧入口 D03。旧 outer 原件缺失导致的重签正例仍未验证，报告已如实保留；这不是 CE2024 从源码正常构建链的新阻塞。

### 3.4 D04：26 条证据链接缺失——已关闭原缺陷

原 CE2021 报告的 26 个相对证据链接，当前树中 26 个全部存在。已有恢复、UI、播放、失败回执及适配 diff 可以直接审阅。无需继续要求“把完全缺失的证据找回来”。

建议增补一个当前代次总索引，把本代证据、恢复的历史材料、外部归档中的 DELIVERY/GITHUB-STATUS 身份分别列明，便利使用者；这是可读性增强，不再列为上轮的全量断链阻塞。

## 四、新发现 CE24-R01：协作停机失败重试先停用仍持锁的 owner

**优先级 P1；触发条件是已接受协作停机、runtime 注册已移除，而后续已接纳工作在 15 秒内仍未排空，或关闭过程出错后按保护策略继续持有 lease。**

实际调用链：

1. `Host.close()` 先执行 `runtime.close(release_lease=False)`。
2. Runtime 关闭 IPC 并删除 runtime.json，但保留真实 OS lease。
3. Host 再关闭播放、缓存、准备服务、流、engine 并 join worker；只有全部成功才释放 lease。
4. 第一次 `KodiHost.quiesce()` 已通过协议握手，等待 lease；超时后正确抛出 CINEMA_SERVICE_NOT_STOPPED。
5. `Installer.apply()` 的 except 路径无条件再次调用 quiesce。
6. 第二次因 runtime.json 不存在，跳过协议与提前等锁分支，直接执行 `Addons.SetAddonEnabled(False)`；此时 owner 仍持有 lease，之后才再次等锁。

源码：[quiesce](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py#L112-L161)、[安装失败路径](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_installer.py#L180-L203)、[Host 顺序](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.platform/lib/bobbi_platform/host.py#L393-L416)、[标记删除](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.platform/lib/bobbi_platform/runtime.py#L169-L177)。

本次受控复现使用真实 KodiHost 与 InstanceLock，以替身控制 Kodi RPC、协作应答及逻辑时钟，没有连接设备或使用网络：

| 调用 | runtime 标记 | 真实 owner 锁 | 插件 enabled | 结果 |
|---|---|---|---|---|
| 首次 quiesce | 已删除 | 持有 | true | 15 秒逻辑预算后拒绝 |
| 第二次 quiesce | 不存在 | 仍持有 | false | 先请求停用，再等待锁失败 |

这突破了“已知合作退场必须先排空、后停用”的约束，可能重新进入 Kodi 强制停止及锁等待路径。**本次没有在设备上复现死锁，也没有证明文件损坏。** 安装 gate 和后续 lease 检查仍阻止未经确认的文件替换，这些现存保护应保留。

修复要求：

- runtime.json 消失不能被解释为 owner 已退出，也不能单凭它自动降级为 legacy 强停路径。
- 只延后删除标记仍不充分：status 读取异常也可能落入同一兼容分支，必须按 owner 的真实协议身份与关闭状态处理。
- 对已知合作退场的代次，重试、异常恢复和新的维护入口都要继续尊重尚未释放的 OS lease。
- 同一 KodiHost 对象重复调用，以及新对象重入时都不能提前 disable。
- 保留真实旧版本的受控兼容；必须明确它与“新 owner 正在排空/状态未知”的区别。
- 保持原等待预算，失败后保留可恢复事务，不以增加全局超时或强杀代替修复。
- 增加实际 Installer.apply 异常路径覆盖，不能只测第一次成功 quiesce。

## 五、新发现 CE24-R02：多集/歧义字幕名被认作单集

新 EP01 / 第01話 逻辑有合理目的：仅在可信单季或明确季号条件下放行此前过度拒绝的单集字幕。该修复应保留。

但 `subtitle_episode.matches()` 对弱集数标记只汇总已识别 episode，范围检查主要识别横杠、波浪号、加号、&。逗号、顿号、分号后的裸第二集号可能被忽略。[识别代码](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/subtitle_episode.py#L28-L48)、[实际候选入口](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/subtitle_candidates.py#L121-L138)。

在合法的第 1 季第 1 集上下文中，真实识别器和候选 rank 会接受：

- Ping Pong EP01,02.ass
- Ping Pong EP01、02.ass
- Ping Pong 第01話、02話.ass
- Ping Pong EP01;02.ass

这些文件名至少有明确的多集歧义，不能自动当作“精确第 1 集”。常规 EP01 / 第01話 / [01] / S01E01 正控，以及错集、错季、横杠范围、缺少可信 scope 的负控均正常，问题局限于新放行路径的歧义识别。

本次没有证明实际《乒乓》加载的是这些文件，也没有证明视频续播受到影响；该模块的范围是字幕身份判定。建议识别完整多集表达或拒绝歧义，并保留原有精确作品、季集、版本及手动字幕意图保护。不应退回“一律拒绝所有无季号字幕”。

## 六、新发现 CE24-R03：HistoryWriter 的日志故障中断排空

`HistoryWriter.run()` 捕获写入异常后直接调用 report；如果 report 再抛异常，writer 线程退出。close 只设置 done 并 join 线程，不检查仍在队列中的已接受工作。[实现](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/plugin.video.bobbi/lib/services/standard_playback.py#L11-L43)。

生产链为 portable_runtime 的 xbmc.log 回调 → Host.report → HistoryWriter(host.report)。Host.close 自己有保护日志的包装，但并未覆盖 HistoryWriter.run 的回调。

真实完整 HistoryWriter 的受控复现：

| 条件 | 实际尝试记录 | 剩余队列 | worker 状态 | close |
|---|---|---:|---|---|
| 第一条写失败、report 正常 | 1、2 | 0 | 正常退出 | 返回 |
| 第一条写失败、report 也抛错 | 仅 1 | 1 | RuntimeError 退出 | 仍成功返回 |

这是标准播放路径的故障组合，未在 AM6B native 实机上观察到，不应描述成当前日常历史记录已经丢失。建议 P2：诊断失败不能杀死 worker；close 要能区分排空成功与 worker 提前异常退出。保存本身失败仍应按既定策略记录结果，不因“日志要安全”而把未完成工作写成成功。

## 七、原修复中已得到补证的部分

### F02/F03

本次队列夹具确认画质结构变化产生 bind→select，1080p 高亮保持；纯字段更新不重绑。过滤谓词本身由另外的原实机语义断言补证，不把高亮等同于筛选。

monitor 的实际四态方法配合真实 PlaybackOwner、原完整控制流，在 11 类边界场景符合预期：短暂空值/读取失败后恢复、同实例 EOF/STOP、新请求、取消、boot/epoch/instance 变化，以及 3 秒 UNKNOWN 观察预算。这个结果关闭上轮两次读取竞态的具体缺陷，不代替整集真实续播。

### 入口 GUI 阻塞的修复与实机回执

报告保留 CE2023 两次 switching 卡死和线程栈，CE2024 将 UpdateLocalAddons 改成异步 GUI 队列提交及唯一完成标记，InstallAddon 以版本回读完成；未收到标记不能算成功。这一改法与源码执行顺序相符，也有正常、失联、取消、迟到标记回归。

原设备回执显示入口事务 complete、sequence/high_watermark=2026102024；1143 个自有运行文件匹配，无差异。这个数量不等于完整包的 1350 条映射，前者明确排除了原有依赖及用户数据；两者范围不同。旧 updater 的另一份 state.json 仍记 CE2021，也不是本次入口的 installation.json，不能据此否认安装或强改记录。

普通 Kodi ZIP 浏览器导入和成功安装后的完整回退循环仍未认证。此次是维护工具暂存入口后运行真实菜单，不能扩写成全新安装全流程通过。

证据：[安装文件核对](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce2023/installed-files-1792551231636875800.json)、[最终设备回执](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce2023/device-final-idle.json)。

## 八、观看结果：已有进展、已知失败与未认证范围

| 场景 | 原始回执支持的结论 | 下一步 |
|---|---|---|
| 受管恢复 | 合作停机制造 owner 缺失，再真实受管恢复，3 轮 enabled/skin 恢复 | 补 R01 超时重试，不重测大量无关成功路径 |
| UI 增量 | 非首卡、1080p、source key 保持；reset=0、5 次必要焦点补偿、74 帧局部静态区域一致 | 热态超时失败仍需定位；局部帧一致不代表全屏所有时序 |
| 乒乓 Vodes 115 | 约4.69秒观测到AV；34.48秒连续正进度窗口；日语；native确认外挂文件应用且Kodi字幕启用 | 报告称中文已加载；本审查未取得该sha对应字幕正文，未验同步/Off/字体/整集续播 |
| 布达佩斯大饭店115 4K REMUX | 维持4K、英语DTS-HD MA；起播trace失败，最长观测停顿17.48秒、连续caching10.50秒；日志有CAMLCodec timeout | 同源定位输入缓存与解码事件先后；后续30秒稳定窗口不能覆盖起播失败 |
| 比宇宙更遥远的地方BT | 40秒捕获无AV，后续确实开播；后端metadata1.552秒、buffering46.401秒、total48.496秒 | 英语5.1非目标原声，实际字幕未启用，中文候选未加载；分别定位，不自动换版本 |
| 元气囝仔原诸神BT | 本轮0候选、2来源失败，未进入原metadata失败阶段 | 原问题继续开放，资源可查后回原对象验证 |

《比宇宙更遥远的地方》的后续 inspect 在84.78秒首次观测到AV，这只是有采样间隔的观察上界，不是准确启动耗时；48.496秒又是后端准备链总耗时，也不等于 native AV 事件时间。统一 request、时钟域、采样时刻后再比较。

原声问题已知有 en-US 详情缓存和前端缓存存在；不能直接说“没缓存”。应记录当前 locale、实际命中的详情键、作品身份、生成的 hint、绑定与 native 选轨结果。无需为排查这个问题重构或闪写固件。

《乒乓》回执的 subtitle_file_applied=true、sha 与 Kodi 外挂启用足以证明自动外挂落地；候选详情另有中文标签与 EP01 文件名。但当前材料未将该已应用 sha 与候选 ID/字幕正文完整绑定，本审查不宣称已逐字验证中文内容或字幕同步。建议补一条脱敏候选→下载文件sha→应用sha映射，而不是要求上传整份字幕正文。

已确认工具正确保留失败：布达佩斯 select 的 transport=0、trial/exit=1、trace_passed=false；新动漫40秒无AV为not_covered、passed=null、exit=2。没有把“无AV所以未观察到停顿”误算成功。旧 StopScript 夹具失败和热态 UI 失败仍保留，重启后成功没有覆盖原件。

播放来源：[乒乓 inspect](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce-new-work-ping_pong-inspect-1792551289427135300.json)、[布达佩斯起播](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce-new-work-grand_budapest-select-1792551406474811700.json)、[新动漫inspect](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce-new-work-further_universe-inspect-1792551658645820500.json)、[后端诊断](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-evidence/ce2023/further-universe-diagnostics.json)。

## 九、后续规划

1. **先修 R01，R02/R03 可并行窄修。** 用有正负控、真实锁和原模块的回归覆盖，不以修改本审查脚本或增加全局超时交差。
2. **复核本代有效成果。** 保留受管恢复、完整排空、异步列表和四态monitor；不要重做已撤回G02，不恢复已确认清理的文档，不关闭清单/签名检查。
3. **在干净提交上构建下一代。** 先查已占用序列及实际水位，使用新的合法序列；冻结源码、测试与完整包映射，入口与载荷同代。实际维护密钥只留在原维护环境。
4. **补同代安装与恢复边界。** 先只读确认设备现状；在已有维护授权下补普通Kodi ZIP入口、成功安装后的完整回退/恢复。此次审查不是重复安装或强制回退命令。
5. **分三条观看线定位。** 新动漫先追原声hint与字幕候选装载，4K同源追缓存/解码先后，旧BT回原资源追检索/metadata/文件选择/AV。不得自动降画质、转码或换版本制造成功。
6. **做有限且有针对性的观看验收。** 一部电影、一集动漫，正常首页手选，建议10–15分钟连续观察，再按实际条件验证同版自然续播、手动Off、seek及字体切换。未做的项记录NOT_RUN，不冒充全片认证。

继续保留通用CE方向、新UI、原始音视频、中文字幕目标、手动选源、严格同版续播、用户字幕意图和账号/历史保护。不新增机型白名单、native hash、F9、第二台设备或第二账号门槛；不触碰固件、SYSTEM/eMMC、CD2、挂载、Yatse及既有代理。

## 十、交付包使用方法

- `02-CODEX-NEXT-TASK.md`：可直接交给下一轮Codex的任务。
- `03-ACCEPTANCE-MATRIX.md`：新缺陷及必要设备/观看验收条件。
- `FINDINGS.json`：机器可读问题、级别、状态和证据索引。
- `evidence/`：本次CI原始回执、事实摘要、已关闭项检查、复现结果。
- `probes/`：读取指定本地源码树的独立诊断脚本，不包含项目源码或维护密钥。

本包没有修复补丁或新安装包。探针按其README约定区分缺陷复现、有限通过与不适配；接口变化时迁移行为契约，不把运行异常计为修复成功。
