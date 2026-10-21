# Bobbi TV CE2024 后续修复：Codex 执行包

将本文件连同整个 BobbiTV-CE2024-Independent-Review-20261021 目录交给 Codex。先读本文件、主报告和 FINDINGS.json，再执行。此任务书沿用已有会话授权和仓库 AGENTS.md，不为已授权的可逆代码/本地检查重复询问；它本身不代表已经执行过设备操作、推送或发布。

## 一、任务目标与现状

你要以已经独立核验的 CE2024 为基线，修复四个确定问题，再定位仍失败的真实播放链并生成可审阅的新候选。完成已授权的工作，保持原始失败证据，不以扩大超时、降低画质、更换成功作品或修改断言来替代修复。

固定基线：

- 仓库：2223M1/bobbi-tv。
- 分支：codex/ce2024-reviewed-delivery-20261021。
- handoff HEAD：c4e0baca6acefa58f031979bff71e7cd1028efdf。
- handoff tree：bb4256d63465fefb9c5820f3ce1ec9cca33ff546。
- 产品 commit：d2fffa570fe59b90cd1d33499efcf7c6684b2647。
- 产品 tree：380b4493b2eafcaa46efe63e0ebd8c5cd1686dc3。
- 当前签名代次：2026102024，coreelec / private-candidate。
- 入口路径：review-packages/ce2024/script.bobbi.start-0.2.15-ce2024.zip。
- 入口 SHA-256：cb355eb2a80b3974e985a9bc404fb74a8be1c98ab1319d30e4399eb503c06e9c。
- payload SHA-256：d53bc3b6ad0c4dc905a831d1906575a7c53ad15c0e6a6d6d7b12188e0d33c096。

已经确认的成绩：

- 当前 CI run 39537767479：2804 passed / 5 skipped / 0 failed / 0 errors。
- 两次 source-check 各 22 组件；63 个输出文件相同。
- 实际入口 22 组件、1349 Git 文件全部与固定 tree 一致；另 1 个明确的应用配置输入。
- D01/D02 可关闭；D03 代码和真实 RSA/ZIP 夹具可关闭，原始 CE2021 outer 丢失的生产正例缺口仍存在。
- F01/F02/F03 对应代码缺陷已修复并复核；G01 只有标准播放/历史等子域关闭。
- 作者回执显示设备已装 CE2024。没有产品变更需求时，不为“重跑一次”重复安装。

本轮四项发现：

| 编号 | 优先级 | 任务 |
|---|---|---|
| R24-01 | P2 | 字幕弱集号推断排除其他季/特别篇冲突 |
| R24-02 | P2 | 将 progressive producer 纳入服务最终排空与 lease 屏障 |
| R24-03 | P2 | 测试回执绑定实际 execution_root，记录前后身份 |
| R24-04 | P2 | 多 decoder 通道独立采样，保留身份、时间及不可比较状态 |

R24-01/R24-03 属新增问题；R24-02/R24-04 属前版已存在、当前仍遗漏的问题。不要把四项统称为 CE2024 新引入的回归。

## 二、执行边界

保持 CoreELEC/Kodi 21/Python 3.8+ 的产品兼容性。维护测试可以在项目固定测试环境执行，不把现代测试宿主版本误写成设备版本。

继续遵守现有文档清理政策；不恢复已删除的独立说明文档作为构建前提。保留原有上游标识、代码内署名及运行资产的精确 inventory。不要把精确 inventory 改成宽松目录扫描。

保持原画质、同源/同版文件选择、原音与中文字幕目标，以及 request/native instance/账户代际/手动意图保护。不要重写播放器或字幕系统来解决局部身份缺口。

保持固件、SYSTEM/eMMC、CD2、挂载、Yatse、服务器/newapi/代理现状。测试不整库替换账户、登录或观看历史，不手改 journal、高水位或包 sequence。已有授权允许的动作直接继续；若某项必需外部写入没有授权，先完成具体候选、回执和可审阅执行步骤，再说明那一项需要什么授权，其他代码工作照常完成。

## 三、T00：建立可追溯工作基线

1. 读取当前仓库 AGENTS.md、docs/CE2024-DELIVERY.md、本审查主报告及相关源文件。独立核对分支当前 SHA；若远端已前进，记录新增差异，不默默把本报告的结论套给新 HEAD。
2. 从 c4e0baca 建立独立工作分支/工作树。已有同名目录先核对，不覆盖用户修改。
3. 保留本审查包原样，测试输出写到新目录；不要原地覆盖 evidence 中已经记录的失败。
4. 记录实际执行的 repo 顶层目录、commit、tree、状态、解释器、依赖版本。完成 T03 后按新 schema 重新记录新运行，不倒改历史回执。
5. 跑本包与拟修模块直接相关的独立反例，先确认确实命中本报告行为。无需反复运行已经充分核验的无关全套测试。

建议分支名：codex/ce2024-review-followup-20261021；名字占用时用新的唯一名称。分支名不分配签名 sequence。

## 四、T01：修复字幕弱集号身份冲突

主要文件：

- addons/script.module.bobbi.core/lib/bobbi_core/subtitle_episode.py
- addons/script.module.bobbi.core/lib/bobbi_core/subtitle_candidates.py
- 必要时涉及当前字幕 scope 构造与相应测试，保持范围有限。

缺陷事实：SingleSeason 仅表示一个正规季；同作品还可能有 S0，文件也可能明确声明其他季。当前 EP01/第01話 匹配会忽略第2季、第二季、2nd Season、OVA、Specials、番外篇这些反证。实际候选发布层已复现 6 次错误放行。

实施要求：

1. 把字幕季/特别篇声明解析成明确证据，先处理冲突，再决定弱集号能否使用 SingleSeason 或包级季号授权。
2. 对明确其他季、无可靠映射的特别篇/OVA/番外，禁止自动候选通过；不要仅提高排序分数或在 UI 隐藏。
3. 规范标题可能本身含 Season/Special 等词，解析应排除标题本体，避免全局词语黑名单。对无法可靠判定的弱声明保守拒绝自动推断。
4. 保留真正的 EP01、第01話、[01]、强 S01E01、同季包级声明能力；保留错集、范围、多集冲突、错 TMDb、无 scope、越界集数拒绝。
5. 不修改视频 continuation 的授权，不把字幕单季证据借给视频文件选择。

验收：

- checks/reproduce_subtitle_scope.py 原 20 条期望全部通过，不更改六个负控期望。
- 保留 CE2024 支持的三个新增能力正控；不能以全部禁用弱集号来换取负控绿。
- 增加规范标题包含相关词、包元数据与具体文件冲突的测试。
- 跑 tests/test_ce2023_subtitle_episodes.py 和 tests/private_baseline/test_ce2023_subtitle_scope.py，测试进程隔离遵循现有架构。
- 下一阶段回到《乒乓》同源同集验证已知 EP01/第01話 能力及真实应用，不能只用候选 UI 文案算成功。

交付：小范围代码 diff、原失败/新通过 JSON、测试 XML、身份策略说明。

## 五、T02：让所有 progressive producer 受服务关闭管理

主要文件：

- addons/script.module.bobbi.core/lib/bobbi_core/share_stream.py
- addons/script.module.bobbi.platform/lib/bobbi_platform/host.py
- 相关 close/retry/stop-admission 测试。

缺陷事实：handler 的 worker.join(15) 返回不表示 producer 已退出。持续慢响应头可让 requests.get 超过 15 秒；当前 Host 会先释放 OS lease。真实默认 block 对照保留 lease，不能据此声称 progressive 也已覆盖。

实施要求：

1. 服务拥有全部 producer 的注册表/句柄，登记发生在可并发运行前，退出 finally 必须注销。
2. 关闭停止接纳、撤销请求、排空 handler 后，仍追踪 handler 创建但尚未退出的 producer。
3. 未完成或异常时返回明确状态/异常，让 Host 继续持有 OS lease；后续 close 可安全重试。
4. 不持有 worker 退出所需的锁等待，不把 semaphore 容量当所有权。
5. 请求级有界等待与服务级最终所有权分开。不得仅把 15 改大、强杀线程或忽略仍活着的 daemon。
6. 上游响应头阶段若实现取消/总 deadline，应独立说明机制，并保留未能取消时“留锁而不假完成”的兜底。

验收：

- 使用本包提取的实际依赖，原真实 HTTP 三控保持不变。
- slow progressive 在旧 producer 存活期间替代 lease 必须拒绝；排空后成功。
- fast progressive 与 block 对照继续通过。
- 增加 handler 已断开并退出、之后才关闭 Host 的场景，证明 producer 仍被服务追踪。
- 增加并发停止接纳、重复 close、close 异常后重试。
- 相关原 32 项生命周期/GUI fence 测试保持通过。
- 不把这个修复当作 4K 起播问题的根因结论，除非后续同源实机证据证明关联。

交付：线程/lease 的时间序列、实际依赖版本、进程结束后的无遗留测试线程证明和明确失败状态。

## 六、T03：修复测试回执和交付门禁的执行身份

主要文件：

- tools/closure_gate.py
- 读取此回执的后续 handoff 工具与对应测试。

缺陷事实：命令在 root 执行，却在 ROOT 读 commit；真实双 Git 仓库已复现错归属。本轮当前 CI/实际包独立映射已经补足版本身份，修复不应篡改旧回执来伪造历史干净运行。

实施要求：

1. schema 区分 execution_root 与 recorder_root。分别记录工具来源和被测源码来源。
2. 在实际 execution_root 解析 Git 顶层、commit、tree、工作区状态，执行前后都采集。
3. 输出尽量放在被测 checkout 之外，避免写测试回执本身污染产品状态。如果使用明确的仅回执排除规则，须固定规则并记录，不能一概忽略所有 untracked。
4. 身份无法确认或执行中变化时，门禁不得只凭 exit_code=0 接受。命令的真实退出码仍原样保留。
5. 不把 dirty 固定为 true/false；记录测得值及其范围。保留对历史 schema 的只读解释，不能由缺字段推断 clean。
6. handoff gate 检查执行前后 identity/tree/status 与拟交付产品 commit 的对应关系；必要时记录维护工具 commit，而不是混进产品 commit。

验收：

- checks/test_closure_gate_identity.py 同仓库和不同执行仓库都通过实际归属断言。
- 另 worktree、独立 repo、无 Git 根、执行过程中 HEAD/工作区变化均有明确测试。
- 同一次运行不能被归给另一个 repo。读取失败不能 fallback 到记录器 HEAD。
- 产品版本已改变时，旧固定 CE2024 handoff 工具须明确拒绝或使用新版本工具；不得通过放宽 PRODUCT_CHANGED 检查继续给新产品贴旧身份。

交付：新回执 schema、兼容解释、前后身份日志、门禁负控、保存不变的旧回执索引。

## 七、T04：按解码通道采集事实，再推进 4K 诊断

主要文件：

- tools/ce_trial_remote.py
- 消费 decoder_counters 的诊断/门禁及测试。

缺陷事实：原文本 channel 0 的 drop/fra/hw=8 被后续 channel 1 的0覆盖；交换同两个块，结果变成8。前版解析 AST 一样。末尾累计8不是后30秒增量，不得用修复后的解析器倒改旧采样。

实施要求：

1. 为每个 channel 保留 ID、device 名、frame/drop/fra/hw 计数与读取时间；保留可追溯原文或其散列及原文位置。
2. 按真实活动通道/层关系解释；不能把双 decoder frame count 无条件相加。
3. 需要增量门禁时，先验证同一通道身份、无计数重置、样本时间可比较；通道消失/切换/重置要标记 unknown 或新阶段。
4. 消费方适配新结构；不要保留一个可能静默覆盖的旧字段然后继续当唯一事实。
5. 区分启动阶段、后续观察窗和累计错误。短窗进度通过不能清除同实例的启动失败。

验收：

- 单通道、两通道、相反排列、缺字段、通道新增/消失、计数重置的正式测试。
- 同一通道集合仅改变文本排列，结构化结果不得改变；两个通道的非零值都保留。
- 本包 decoder-reproduce.py 用于确认历史错误行为，修复后应建立新不变量测试，不能把其0/8历史输出固化为通过期望。
- 以后实际采样的 raw、结构化值、时间与 request/native instance 可对照。

交付：新结构、消费者适配、真实旧文本回放、窗口/累计值的明确解释。

## 八、T05：同源关闭原音、字幕和起播问题

先完成 T01/T04，确保身份规则与诊断数据可信。旧 CE2024 上的只读定位可先执行，明确标为旧基线诊断；若用于验收本轮产品修复，必须先完成下文 T07-A 的受测候选准备，并在已有授权范围安装、核对实际运行版本与文件身份。针对以下原对象分别开证据行，不用更容易播放的标题代替。

### A. 《比宇宙更遥远的地方》S1E1，原 Stye 1080p HEVC BT

当前事实：3个BT候选、2来源失败；40秒 trace 未观察 AV；后端 metadata=1.552秒、buffering=46.401秒、total=48.496秒；后续实际 eng 5.1、中文字幕未启用。84.78秒是后续观察上界，不能作为精确 native 首帧时延。

必须采集同一 request 的：

- TMDb original_language 与数据来源、cache locale/age、作用于此请求的 scope。
- 原声 hint 生成位置、传递到 BT/播放器的值，以及 native 最终选轨理由。
- 字幕 search/detail/下载/中文正文/季集身份/导出/native submit/确认各阶段及失败码。
- provider metadata、buffering、文件选择、请求移交、首 AV 的分段时间。

分清 hint 根本没生成、途中丢失、native 未采用，再修最小环节。en-US缓存存在不等于original_language=英语，也不能单凭“缺zh-CN缓存”宣布根因。字幕UI候选不是成功；必须对应正确文件及native确认。手动Off/选轨优先级必须保持。

### B. 《布达佩斯大饭店》，原115 4K REMUX

保留3840×2160、DTS-HD MA、原字幕策略和原片源。现有17.48秒停滞、10.5秒连续caching、CAMLCodec timeout仍是启动失败基线。

使用修正后的分通道诊断，同一request/native instance记录HTTP/上游读取方式、buffering、播放时钟、decoder变化及日志的先后关系。先识别证据能支持哪一层，再提出参数/代码改变。不要先降码率、转码、全局调大超时或盲调硬解。后续约30秒的时钟正进度观察窗单独记账，不据此证明渲染连续或解码无异常。

### C. 《元气囝仔》，原诸神1080p BT

先确认资源发现是否重新到达原候选。0候选/2来源失败只能说明未进入原metadata阶段；若资源仍不可达，保留“未覆盖”，继续完成其他任务，不把换片成功当关闭。可到达时再记录原metadata、严格文件选择、首AV及失败退出/空列表返回。

### D. 《乒乓》S1E1作为回归正控

保留原115 Vodes 1080p HEVC。核对日语原声、实际外挂文件与候选来源/正文，分别检查前中后三段同步与可读性。手动Off、切轨、播放中字体切换单独留回执，不能由 applied=true 推导所有体验已好。

## 九、T06：补齐设备闭环

基于已有授权，在合适的无播放窗口执行；先完成 T07-A 生成并核验实际候选，再确认安装后的运行版本/文件身份，不能把旧 CE2024 的运行结果归给本轮修复。完整回退等场景必须以实际已准备的候选为前提。若只继续旧基线诊断，单列状态，不假定设备仍处于旧版本。

| 场景 | 需要保留的证据 |
|---|---|
| 热态 UI timeout | 原失败前状态、同操作重放、错误/超时、owner/lease；空闲重启成功单列 |
| 空来源列表返回 | 查询失败/0候选、返回动作、窗口/焦点与错误状态，不以有结果列表代替 |
| Kodi ZIP浏览器导入 | 从真实ZIP入口到安装完成的全流程；暂存入口菜单测试另列 |
| 完整新候选回退与恢复 | 合法前后代次、journal、高水位、owned文件、owner/lease、账户/历史保护；不手工降序 |
| 自然EOF→同版下一集 | 真实整集或已有明确可接受的等价验收路径；区分EOF、STOP、取消、替换 |
| 长时播放/seek/字幕意图 | 启动与观察窗分别记录；前中后字幕、手动Off/切轨、拖动后同实例状态 |

不要把 CE2023 失败事务 recover 当作 CE2024 安装后的完整 rollback 证明。也不要把合成 QR/card 的 UI 窗口回执当真实登录或视频平面证明。无法完成的场景写清未执行、未到达还是失败，以及剩余阻塞的具体条件。

## 十、T07：候选准备与最终交付（分两次执行）

**执行依赖：T00 → T01～T04 → T07-A → T05/T06 的修复版设备验收 → T07-B。** 旧基线只读定位不受此顺序阻碍，但不能算新候选验收。

**T07-A：受测候选准备。** 代码修复和定向反例充分验证后，先更新受影响组件版本及精确 source inventory，冻结产品 commit/tree；随后在完整源码 checkout 中执行现有三套隔离测试与两次source-check。若具备既有授权和生产签包条件，按最新登记分配新 sequence，生成并完整核验实际入口，在设备验收前确认其安装后的运行身份。无实际候选时，T05/T06只能继续旧基线定位，不能宣布修复版设备通过。

以下命令是当前工作流的结构；新目录名称应唯一，避免覆盖已有证据。

~~~bash
python -m pytest -q -rs tests --ignore=tests/private_baseline --ignore=tests/preparation_regression --junitxml=/absolute/new-evidence/primary.xml
python -m pytest -q -rs tests/private_baseline --junitxml=/absolute/new-evidence/baseline.xml
python -m pytest -q -rs tests/preparation_regression --junitxml=/absolute/new-evidence/preparation.xml
python tools/build_release.py --source-check --output /absolute/new-build/source-a
python tools/build_release.py --source-check --output /absolute/new-build/source-b
python tools/check_repository.py /absolute/new-build/source-a /absolute/new-build/source-b
~~~

注意：

1. 本包独立反例位于仓库测试树之外，CI绿不能自动覆盖它们。把修复相关不变量纳入正式测试，再保留本包独立重放结果。
2. 更新受影响组件版本和精确 source inventory，来源必须是待交付的干净固定提交；不能只改receipt里的hash。
3. 新签名sequence必须根据最新已分配登记和已有安装高水位确定，严格大于已用值且未占用。至少包含已用2026102024；本文件不预先占用2026102025。
4. 生产签包继续使用既有维护者工具和授权配置；不得用测试key/config冒充实际客户端。若本轮无生产签包条件，完整交付源码、source-check及明确待签项，不能伪造生产包成功。
5. 对实际新入口执行全签名、全组件、全inventory、全Gitblob与完整外层组合检查，覆盖default.py/addon.xml/bootstrap/payload以及唯一明确构建输入。
6. checks/verify_actual_entry.py 固定了本次CE2024原包身份，用于复核旧基线。新候选需更新独立身份输入/另建验证器并保留旧验证器，不能拿新包绕过旧pin后声称验证了旧包。
7. 当前package_ce2024_handoff.py是冻结CE2024专用工具。产品变更后应产生明确的新候选工具/参数；保留旧版拒绝跨产品变化的保护。
8. 在已有授权范围形成新私有分支/PR时，交付真实HEAD和真实CI结果；推送、合并、发布分别记账，不能互相代替。未授权外部写入时，先交付可审阅的本地提交、差异和候选材料。

**T07-B：汇集最终 handoff。** T05/T06 后整理设备回执、真实CI和剩余失败，冻结交付commit/tree。产品在设备试验后若又改变，必须重新冻结受测候选，列明哪些既有设备结论仍适用、哪些需要重验；不能只更新报告或重新签名就沿用旧产品验收。

## 十一、最终必须交付

- 修复说明：按 R24-01～R24-04 逐项给出原行为、改动、回归、不变量与当前状态。
- 固定身份：产品commit/tree、交付commit/tree、实际Git状态、构建环境、sequence登记依据。
- 测试：定向与全量分开；原始XML/JSON/log；明确skip/error/未覆盖，不累加重复复跑。
- 真实包：如果已获准并具备条件，交付实际入口/payload及其hash、全文件映射和签名核验。
- 真机结果：每作品/同源/集数/attempt/request/native instance单独列项；保留启动失败及后续观察窗，不覆盖历史。
- 后续待办：每项写清已修复、仅代码通过、设备通过、仍失败或未覆盖。
- 回退与使用指导：只依据已实测的合法产品路径，明确未认证项。
- 提供简洁自检表，说明未降低画质、未扩大超时、未删除失败断言、未改写旧回执。

**停止条件：** 四个确定问题修复且原反例满足不变量，当前源码测试/构建可复现，已执行设备门禁有原始证据；仍受外部资源或授权条件阻断的项目如实保留，同时交付全部已完成工作。不能为了得到一个“全绿”结论扩大范围或伪造成功。

