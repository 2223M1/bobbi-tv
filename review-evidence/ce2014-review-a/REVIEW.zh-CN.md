# Bobbi TV PR 3 CE2014 完整独立审查

审查日期：2026 年 10 月 21 日（UTC+8）。审查对象：[PR #3](https://github.com/2223M1/bobbi-tv/pull/3)，固定 head c8de17ae9dabbe0f37753e1751b1d88107311316。

## 审查结论

**建议继续保持 Draft，先修复 F01、F02、F03，再形成下一审查候选。** 本次确认 3 项需要修复的问题：1 项 P1、2 项 P2。其中 F01、F02 属于本版新增路径／回归，F03 是本轮完整审查发现的遗留控制流问题。另列 C01、C02 两项非阻断改进。

前版 R01–R06 的原始失败契约已经逐项通过。本版的恢复状态、OS 锁、标准片尾证据、可选字幕预算及验收退出码都有实质修复。当前问题不应重新包装成“旧 6 项全部没修好”。

| 编号 | 优先级与归属 | 确认问题 | 下一步 |
| --- | --- | --- | --- |
| F01 | P1，本版新增 fallback | 已 enabled 但没有运行服务时，裸路径 RunScript 丢失 addon 身份／受管服务所有权 | 使用有正确 addon 身份、受服务管理器管理且可被同一停机流程停止的恢复路径 |
| F02 | P2，本版回归 | 原生 ControlList 追加会异步重新绑定；非首卡及非默认画质焦点可回到索引 0 | 按来源 key／画质 key 在原生更新后恢复焦点，覆盖两种 GUI 调度 |
| F03 | P2，遗留问题 | 原生 monitor 将短暂读失败及同实例 EOF 误作换片，跳过终态收尾 | 区分未知、明确退休、匹配活动实例和匹配终态 |
| C01 | P3，非阻断 | 新 standard 辅助工具的落盘 exit_code 与实际命令结果不一致 | 统一 transport、trial 和 pending 语义 |
| C02 | P3，非阻断 | 标准历史 worker 可能晚于 runtime lease 释放结束 | 把已接收后台工作纳入停机完成条件，当前不推断数据损坏 |

优先级表达的是修复顺序和用户影响，不是设备认证结果。主复现入口实际结果为 **14 项、8 通过、6 失败、0 执行异常**；6 条反例归并为上述 3 项确认问题。详见 [统一结果](evidence/integrated-head/RESULT.json)。

## 固定版本与覆盖范围

| 项目 | 核对值 |
| --- | --- |
| PR | open、draft、未合并；最终远端快照见 evidence/REMOTE-STATE.json |
| Base／审查时 main | ee65742bfcbaf08831f70306faed11bd1f8d6cc6 |
| Head | c8de17ae9dabbe0f37753e1751b1d88107311316 |
| Head tree | cc12e00ccba0d7cb9a8b310306437e0e8ef84ae3 |
| PR CI 集成提交 | f6adafd1fd5a39b58853f0d6f0d43dd758ba3062；tree 与 head 相同 |
| 差异 | 230 个文件，+18039 / −204 |
| 生产 addon／测试／工具 | 27 / 11 / 15 个变更文件 |
| 文档／发布描述／审查证据 | 1 / 2 / 174 个变更文件 |

已取得并按固定 Git tree 的 blob SHA 校验 **1,842 个文件**。本次按差异审查产品 Python、界面 XML、安装与构建工具、测试和证据生成逻辑，并追踪相关未改动的调用链。该数值表示已核验的文件来源数量，不表示 1,842 份文件都是新增代码，也不代表取得了完整二进制仓库。来源索引保存在 [SOURCE-PROVENANCE.json](SOURCE-PROVENANCE.json)。

独立验证执行实际候选 Python 方法；Kodi 扩展、GUI 消息、IPC 及部分最终数据库 IO 使用明确、可检查的替身。安装验证实际创建 Host／Runtime、本机回环和 OS lease。GUI 与服务调用模型依据官方 Kodi 21.3-Omega 源码，并经过独立反驳性复核。它们是源代码支持的边界复现，不是重新运行 Kodi 二进制或电视实测。

## 前版 6 项问题的处理情况

| 前版编号 | 原问题 | 本版核对结果 |
| --- | --- | --- |
| R01 | 安装已进入 activation pending，但启动门禁仍阻止宿主完成恢复 | 原契约通过；已验证的 activation／restore pending 可以进入启动，未验证阶段继续拦截。另有本版 fallback 的 F01 |
| R02 | 进程已退出，残留 runtime 注册仍挡住恢复 | 原契约通过；以真实 OS lease 区分死 owner 与活动 owner，稳定锁文件不被替换 |
| R03 | 读取 enabled 状态失败，被默认为可继续安装的空状态 | 原契约通过；详情查询与后备查询仍无法确认时保守失败 |
| R04 | 可选字幕等待耗尽标准续播期限，已就绪视频被丢弃 | 原契约通过；字幕预算受 2 秒及剩余 EOF 窗口约束，未扩大 20 秒绝对窗口 |
| R05 | 0/0 等无效进度刷新 EOF 证据的新鲜度 | 原契约通过；有效进度时间独立保存，无效样本不刷新 |
| R06 | 设备操作明确失败，验收 CLI 仍返回成功 | 原契约通过；原驱动分别保存 transport／trial／最终退出码，明确失败为非零 |

主审重跑的前版 **18/18** 与更早 **15/15** 均通过。前版 18 项中安装部分使用仓库保留的当前 IO 适配：加入实际 readiness stub 和严格 enabled 查询替身，原期望断言没有放宽。适配差异在 [PREVIOUS-CONTRACT-ADAPTER.diff](evidence/PREVIOUS-CONTRACT-ADAPTER.diff)，原始结果分别见 [旧 18 项](evidence/root/root-previous18/RESULT.json) 与 [旧 15 项](evidence/root/root-previous15/RESULT.json)。

这确认的是原反例及正控关闭。新的服务管理器上下文、原生消息队列及 monitor 竞态没有被这些旧替身覆盖，需单独补入本轮契约。

## F01 恢复补启动没有正确的服务身份和所有权

**P1；位置：** [ce_install_ui.py L174–L200](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py#L174-L200)，尤其 L195–L198。

触发前提是 addon 已 enabled，但宿主没有运行；例如进程丢失后的恢复。ensure_running 获取不到 owner snapshot、又确认没有活动 lease 后，使用裸路径 RunScript(special://home/addons/plugin.video.bobbi/service.py) 补启动。

官方 Kodi 对路径分支不会自动从目录推断 addon 身份；ExecuteAsync 得到空 AddonPtr，Python 初始化不会设置默认 addon id。当前原生导入链最终执行 lib/jacktook/utils.py 中的无参 xbmcaddon.Addon()，在该上下文下异常退出。恢复最终得到 CINEMA_SERVICE_NOT_READY。这里执行了真实产品导入链，只有 Kodi 扩展 IO 为替身。[RunScript 语义](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/builtins/AddonBuiltins.cpp#L239-L281)、[Python 初始化](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/python/PythonInvoker.cpp#L634-L648)、[无默认 id 的行为](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/legacy/Addon.cpp#L54-L68)。

标准分支可以启动真实 Host／Runtime 并获得 ready 回复，但这种普通脚本调用不登记在 ServiceAddonManager 的服务表里。下一次安装请求禁用 addon 时，管理器找不到该手动脚本的服务 handle；宿主仍持锁，quiesce 最终得到 CINEMA_SERVICE_NOT_STOPPED。[服务启动／停止所有权](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/addons/Service.cpp#L78-L128)。

| 用例 | 当前结果 |
| --- | --- |
| enabled 但未运行，经 fallback 补起原生导入链 | 失败，缺少默认 addon id |
| 同一原生导入链使用正常 addon 上下文 | 通过 |
| fallback 补起标准宿主，再使用真实安装停机入口 | 失败，服务无法由管理器停止 |
| 正常受管标准宿主启动，再使用相同停机入口 | 通过 |

**影响限定：** 这是恢复 fallback 的功能缺陷，正常 managed enable 正控通过；不能写成所有正常安装都会失败。readiness 也只证明 owner 能回复，不能替代服务所有权。

**修复要求：** 恢复必须同时满足“正确 addon 上下文”“受管理的服务 handle”“后续可停止”三件事。仅把路径换成 RunScript(addon_id)、提前写 complete、删除门禁或绕过锁，都不满足验收。使用真实启用状态转换时，应保留整个 managed enabled 向量、provider 最后启用、正确 journal 状态和 readiness 校验。

证据：[安装主审独立结果](evidence/root/root-installer-replay.json)、[详细审查](details/installer/INSTALLER-REVIEW.zh-CN.md)、[官方源码索引](details/installer/PRIMARY-SOURCES.json)。

## F02 增量选源会在原生绑定后丢失非默认焦点

**P2；本版回归。位置：** [source_select.py 画质更新 L249–L274](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/gui/source_select.py#L249-L274)、[卡片更新 L732–L881](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/gui/source_select.py#L732-L881)。

本版保留 Python ListItem 并调用 addItems，避免显式 reset；但 Kodi ControlList.addItems 仍把完整列表排入 GUI_MSG_LABEL_BIND。原生容器处理该消息时先 Reset，再选择消息参数指定的索引 0。getSelectedPosition 同步读取当前 GUI 位置，不会先清空已排队的绑定消息。[Control.cpp](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/legacy/Control.cpp#L1243-L1296)、[GUIBaseContainer.cpp](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/guilib/GUIBaseContainer.cpp#L484-L493)。

一个合法时序是：用户停在第 2 张卡；Python 排入新增卡片的 bind；立即读到尚未更新的第 2 张卡位置，因“位置未变”跳过补偿；GUI 下一轮消费 bind 后回到第 1 张卡。新增画质 tab 也触发绑定，当前实现没有按画质 key 恢复非默认选择。

这不是“每次追加必跳首行”的断言。GUI 若先完成绑定再被读取，当前条件补偿可以通过；首卡本身就处于索引 0，也会通过。独立核查 DelayedCallGuard、GuiLock 和 WindowXML 包装，没有发现会强制 flush 该队列的同步屏障。[交叉复核](details/release/UI-CROSSCHECK.zh-CN.md)。

| 用例 | Base | Head |
| --- | --- | --- |
| 非首卡，bind 延后消费 | 通过 | 失败 |
| 非默认画质，新增画质 tab | 通过 | 失败 |
| 首卡焦点 | 通过 | 通过 |
| 非首卡，bind 先消费 | 通过 | 通过 |
| 只有完成状态变化，没有新增卡片 | 通过 | 通过 |

**为什么已有 UI 证据没发现：** 现有 Python 替身用列表 extend 保留焦点；实机 smoke 主要选在首卡／全部画质，约 40ms 轮询首卡 140×70 静态 ROI，70 次摘要相同。这个场景有价值，但索引 0 被重选后仍是索引 0，不覆盖以上反例。不能把 Python reset=0 或保留 ListItem 身份直接当成“原生容器没有重绑”。

**修复要求：** 按稳定 source_key 和 quality key 保留用户选择，让原生绑定与补偿顺序正确；保留增量对象和手动选源语义。新增卡片、更新标题／数量、加载完成、追加／移除画质均要覆盖。后续实机脚本应主动选择非首卡和非默认画质，再注入新结果，记录完整选中 key、原生事件及局部画面。

证据：[Head 5 项](evidence/root/ui-RESULT-head.json)、[Base 5 项](evidence/root/ui-RESULT-base.json)。这是焦点丢失的源码支持复现，本轮没有独立观察到该调度下电视画面的全屏闪烁。

## F03 原生监控把未知读取和同实例终态误当换片

**P2；遗留问题。主位置：** [native_player.py L708–L712](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/native_player.py#L708-L712)，相关 owner 匹配在 L149–L159、L657–L671。

monitor 中任一权限／实例匹配谓词为假，就设置 superseded 并直接返回。但假值既可能表示明确换片，也可能表示本次 IPC 读取失败，或者原实例已经产生终态、observed 已清空。后两者都会跳过本版新增的不可变终态读取及 [L739–L746 收尾边界](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/native_player.py#L739-L746)。

**路径 A：** 一轮 owned_state 的 3 次有界读取都失败，回放中共 0.7 秒；下一次读取恢复，权威 owner 仍为同一请求／实例，播放器仍活跃。monitor 已标记 superseded、设置本地 cancel 并退出，后续进度／片尾收尾不会自动恢复。问题不是每个失败数据包都会触发，而是一次重试预算耗尽后把未知当成明确更换。[owned_state](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/script.module.bobbi.core/lib/bobbi_core/playback_request.py#L189-L203)。

**路径 B：** isPlayingVideo 刚读到真，第一次 owner 读取仍有效；同实例此时到达 NATURAL_EOF。真实 PlaybackOwner.observe_terminal 保存终态并清除 observed；第二次谓词因 observed=None 返回假，monitor 在终态协调前退出。本地仍是 UNKNOWN，尽管权威终态已明确。[真实 terminal 状态变化](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/script.module.bobbi.core/lib/bobbi_core/playback_owner.py#L264-L279)。

两条反例在 base 和 head 都失败；正常 EOF、明确换片、明确取消三个正控都通过。AST 比较确认 monitor、两个谓词和 owned_state 的相关逻辑未改；本版改的是 wait_cinema_terminal 并新增 terminal_state，因此应登记为完整审查发现的遗留缺口。

**影响限定：** 可丢失自然片尾的自动续播机会、最终进度／完成状态及终态 UI 的收尾调用。回放证明真实 monitor 跳过这些边界，没有宣称每次 EOF 都失败、所有历史记录都损坏，也不否定已有成功续播证据。

**修复要求：** 区分明确退休、匹配活动实例、匹配终态和读取未知。明确 request／instance／boot／epoch／账号代际变化或取消时，旧监控立即退休；未知读取在固定预算内暂停权限相关副作用并重新观察；同实例终态进入不可变终态协调。不得用缓存授予控制权、无限重试或扩大既有原生终态 3 秒／标准 EOF 20 秒窗口。

证据：[主审重跑](evidence/root/root-native-replay.json)、[Base／Head AST 归属](details/playback/native-monitor-provenance.json)、[播放完整分报告](details/playback/PLAYBACK-REVIEW.zh-CN.md)。

## 两项非阻断改进

### C01 辅助工具回执字段应统一

实际加载新增 [ce_standard_real.py L44–L48](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/tools/ce_standard_real.py#L44-L48)，以真实首轮失败回执输入，命令退出 1，但保存的 exit_code 为 transport 的 0。成功输入两者均为 0；running／passed=null 的 0 表示异步操作尚在进行，不是完成播放验收。

统一 transport_exit_code、trial_exit_code、最终 exit_code 和 pending 状态，避免下游只读单一字段汇总。原 ce_playback_trial.py 的 R06 已修复；额外 11 项 operation 契约全部通过。本建议不改写该事实。详见 [验收驱动结果](evidence/root/trial-driver-RESULT.json)。

### C02 标准后台工作应纳入停机完成条件

真实 portable_runtime 按 standard.close → host.close 退出。慢数据库 IO 时，HistoryWriter 的短 join 先返回，Host 随后释放 runtime lease；约 0.41 秒后安装可拿到 lease，旧 writer 仍活，解除受控 IO 后仍到达两次历史写边界。正常已排空正控通过。

经过反驳性复核，**不把它升级为当前数据损坏 finding**：最后数据库对象为替身，真实 PickleDatabase 另有跨解释器锁、原子操作合并，历史实现 base/head 相同，安装也不替换 profile。当前只证明停机 lease 覆盖范围比全部已接收工作窄。后续可把标准 worker 纳入完成屏障；不能用丢队列、固定 sleep 或超时后假称 drain 完成来处理。

这与旧 R02 的死 owner 残留注册不同。两个诊断用例单列，不混入主 14 项及其裁决。[独立交叉审查](details/playback/STANDARD-SHUTDOWN-CROSSCHECK.zh-CN.md)、[主审诊断结果](evidence/root/root-standard-shutdown.json)。

## CI 与独立执行结果

主审再次解压并解析了两套原始 CI JUnit。每套都是主测试 1746 passed／5 skipped，baseline 761 passed，preparation 177 passed，合计 **2684 passed／5 skipped／0 failures／0 errors**。5 项 skip 为 Windows inherited-pipe API binding，不应把 Linux 跳过说成 Windows 实测通过。两份日志都记录 63 个 source-check 文件的可复现构建。

| 证据组 | 结果与统计边界 |
| --- | --- |
| [Push CI 39448450410](https://github.com/2223M1/bobbi-tv/actions/runs/39448450410) | head c8de17a，2684 passed／5 skipped |
| [PR CI 39448461338](https://github.com/2223M1/bobbi-tv/actions/runs/39448461338) | 集成提交 f6adafd，相同 tree、相同数量；不是新增 2684 种覆盖 |
| 本包主反例和正控 | 14 项：8 通过、6 失败、0 异常 |
| 前版契约 | 18/18，通过；安装 IO 适配有保留差异 |
| 更早冻结契约 | 15/15，通过 |
| 当前安装／恢复／Host 重点测试 | 92 passed |
| 当前标准播放／续播／4:3 重点测试 | 52 passed |
| 主审当前 core／UI／分享重点测试 | 89 passed |
| 验收 operation 扩展 | 11/11；与前版 4 个驱动契约有重叠 |
| C02 非阻断停机诊断 | 2 项：1 通过、1 生命周期缺口 |

后面这些独立分组存在与 CI、旧契约的覆盖重叠，不相加成新的总测试规模。第一次受限环境执行中的 socket 禁止和未取到纹理资产已通过允许本机回环、取得真实 blob 后解决；正式 89 项结果没有把环境失败当作产品缺陷。

## 设备记录说明了什么

### 标准策略的真实来源片尾交接已经有证据

最终《星际牛仔》记录使用真实 Juku／115 寻源、真实标准策略与 Handoff，没有替换 next_loader。第 1 集在 1482.693／1483.523 秒附近形成自然 EOF；同 philosophy-raws／Hi10P FLAC／1440×1080 的第 2 集取得新请求并推进到 11.198 秒。4:3 尺寸识别修复与这条同版后继路径相符。[最终回执](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/review-evidence/ce-standard-real-1792509830895851000.json)、[生成工具](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/tools/ce_standard_real_remote.py)。

这条测试从 StartPercent=97 开始，临时脚本构造 controller，Accounts／view 是薄适配，history 回调写回执。它支持“真实来源的标准策略片尾交接已实测”，不能扩展为普通用户完整 UI、整集播放、真实观看历史持久化、中文字幕或其他硬件都已认证。last_handoff 也不是全部底层 RPC 调用次数的完整日志。末尾 SERVICE_STOPPED 属于清理。

### 已有影片失败记录应继续保留

| 对象 | 当前可支持的结论 |
| --- | --- |
| 《学生会也有洞》第 3 集 | 原生／影院路径已有 NATURAL_EOF、EOF_WITHOUT_VERIFIED_NEXT 记录；仍需覆盖 F03 的特定竞态 |
| 《十二怒汉》 | 同一 58,762,851,801 字节原文件取址收到上游 errno=4100010，分类为分享取消／失效；分类问题得到收口，原分享仍不可播 |
| 《罗生门》 | 首播失败保留；约 6.54 秒 caching，其中约 5.03 秒 decoder 静止，另有约 3.99 秒媒体时钟静止但 decoder 推进。不能相加写成电视画面冻结 13 秒 |
| 《罗生门》后段 | 30.319 秒墙钟推进 30.322 秒媒体时间，仅证明该观察窗口；不冲销启动失败 |
| 《四叠半》《玲音》《这个男人来自地球》 | 原启动时钟、缓冲与中文字幕等开放项继续保留，不以新片后段通过替代 |

来源为 [CE2014 交付文档](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/docs/CE-FAULT-CLOSURE-2014-20261020.md) 和本包 evidence/device-receipts 中的原始回执；精确来源映射见 [设备证据索引](details/release/DEVICE-SOURCE-PROVENANCE.json)。

### 界面与安装的证据边界

本轮实际查看并核对 blob 的是 account、metadata、sources-after 三张 PNG：账号和 TMDb 弹窗样式一致、文字及焦点可见，选源卡片样式得到展示。其二维码和卡片是测试数据，不是实际登录。terminal、sources-before 的大图未能从当前二进制接口取得，因此不声称已逐张检查。

维护部署最终 run 20261020-231800 的回退目标为 CE2013；维护路径与普通 clean ZIP 安装是不同证据。记录边界不转化成第二台设备、型号名单或 F9/hash 的安装准入门槛。

## 发布资产与后续指导

[CE2014 release](https://github.com/2223M1/bobbi-tv/releases/tag/untagged-7e586cd5524fbc914b32) 在审查时为 draft，目标等于 c8de17a。prerelease=false 不改变其尚未发布的事实。

| 资产 | 大小 | 元数据中的 SHA256 |
| --- | --- | --- |
| script.bobbi.start-0.2.6-ce2014.zip | 96,178,248 字节 | 59e133cf78faf6448475752c8e040dcdaf6146c4cd17184378b88db73aadd15d |
| bobbi-private-2026102014-coreelec.bobbi-update.zip | 96,011,740 字节 | 1658413e9d037beccfdf50161d2d4b9e959f530fb2dcc2d8ac4e9c102f3187a7 |
| BobbiTV-CE2014-c8de17a-source.zip | 214,280,820 字节 | 206aee7a5becb8ee281a4f305d29e0a64d2e9068859f27063a375250f023af2d |

大小、GitHub digest 与仓库入包报告吻合；入库报告记录 22 组件、1392 文件。本轮没有重新下载这两个约 96 MB 安装资产及 214 MB 源码包并独立验签；这些数值属于发布元数据核对，不能当成本轮真实 ZIP 重建／验签结论。下一候选需绑定新的 commit、tree、构建结果及实际资产字节，不覆盖旧候选证据。

建议工作顺序为：**先 F01 → F02 与 F03 可分开修改 → 原反例、旧契约和现有 CI → 对应实机边界 → 新候选交付。** C01 可以随测试工具整理；C02 单列后续加固，避免为未证实损害扩大本轮范围。

继续保持通用 CoreELEC 产品路线、准确同版来源、原始画质／音轨、字幕手动 Off、账号代际隔离、持久状态与 OS 锁、CD2 1.0.19 及原有挂载／Yatse／VPS 约束。未知型号仍可按既有朋友测试流程安装，不新增设备名单、第二台硬件或原生 hash 作为门槛。

完整可执行工作说明、每项正反例和最终回报模板见 [CODEX-EXECUTION.zh-CN.md](CODEX-EXECUTION.zh-CN.md)。本轮交付到审查和任务包为止，没有修改产品源码、操作真实设备、提交评论、合并或发布。
