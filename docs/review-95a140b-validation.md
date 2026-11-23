# 95a140b 审查轮

本轮依据 `BobbiTV-Codex-Execution-Pack-95a140b-20261112.zip`，承接其候选修复后继续开发 B01–B06。包内指令作为审查建议，不扩大设备、账号或分发权限。旧轮设备回执保留原身份，不计作本轮候选通过。以下 2120 运行候选冻结于 commit `0941b74e6399c749541d689aadaede313cb9dfbb` / tree `9ec7eb8a99530f6ad4b2beabd611c174ac0a3941`；后续文档更新不改写这些回执的源码身份。

## 实施与归并

| 项目 | 本轮变更 | 边界 |
| --- | --- | --- |
| B00 | 统一扫描/点播发布锁顺序；历史预留与真实观察分开；季集 content、来源筛选下钻、单页 EpisodeProjection 复用；点复核保护在途旧扫描；completion helper 纳入 generic gate | 已承接补丁的实际提交 `b692de3`，tree 与包内候选 `c5b03f4f28c9248d62bca36f5e8869ec3212614a` 相同；未新增持久 schema |
| B01 | 文件版本备注、原名、大小、来源与文件进度；私人详情“选择文件版本”；TV/手机字段同步 | 32 项、15000 字节；MountedRef 仍从头播放，元数据不授权播放或 next |
| B02 | 统一未匹配、身份不明确、待确认建议、已忽略列表；删除旧 `_items` 分页；TV 原提交回执查询与显式可信来源选择 | 继续复用 review/CAS/receipt、一个手机 runPlan，不重新发送结果未知的写入 |
| B03 | 无变化扫描不推进目录 revision；来源统一最近任务、已观察范围、离线/待复核与显式重扫 | 单 worker，OS 阻塞调用不可抢占；取消请求与确认终态分开 |
| B04 | 两套 CE builder 共用工具 helper；既有日志与 trial 收集器补精确 next 关联 | 不改 canonical 原生算法、历史 proof 或回退器；缺任一因果边界不算通过 |
| B05 | 旧性能采样和多套固定路径汇总归入 `ce_playback_trial.py metrics/summarize`；显式 run-id/回执路径 | 无新 transport/常驻缓存/调度器；只按实测完整区间汇总，不调整缺少证据支持的默认预算 |
| B06 | 统一版本、最小依赖、来源清单；新候选全量回归、部署与带数据回退检查 | 私有本地候选；未请求推送或正式 Release |

本轮保留现有 core/platform/plugin 分工。删除的是重复根入口、旧 TV 列表及重复构建模板，不按文件数合并权限、生命周期不同的责任。

界面收尾修复：未确认类型的作品显示“原文件 / 查看原文件”，不再冒充电影或季集。详情的文件夹、文件版本与关系入口共用捕获目标→关闭当前弹窗→导航动作；已有 Videos 窗口更新目录并保留返回历史。片库搜索改为一次性操作，结果 URL 保存关键词；整理导致旧分组为空时只提供同账号/来源的返回作品与继续整理入口，不自动跨范围跳转。TV 整理预览以中文显示原描述、修改后描述、季集、版本备注及状态，不改变实际命令。

本次界面修复的组件版本为 plugin `0.1.62`、platform `0.1.70`、skin `0.1.16`，对应最低依赖同步。无源码变更的 core `0.1.62`、library `0.1.7` 保留原版本；来源清单按实际字节更新。以上实现描述不等于本代真机验收通过。

扫描与播放重叠试验后另修复来源 Registry：完整合法 v1 库的构造只读 schema，不再每次重复 DDL、设置 user_version 和提交。真实 SQLite 对照表明，旧构造在其他连接持有共享读锁或保留写锁时会失败，而普通 SELECT 可读；修复后均可读。首次建库、v0 初始化和旧 v1 可选目录表扩展仍在写事务内重新校验；坏 schema、未知版本拒绝，不自动重建。新增 49 项、相关集共 169 项通过。仅 platform 升至 `0.1.71`，不引入缓存或更改 Index 生命周期；不能据此断言旧真机任务查询失败的根因已经确证。

## 验证入口

新证据目录为 `D:/AM6B-Project/AM6B/tmp/bobbi-review-95a140b-20261112/results`，原包不改写。

- B00 定向回归 113 passed，含真实双线程交错、SQLite 事务和本地文件系统；非设备目录 IO 认证。
- B03 无变化扫描负控先复现 native revision 2→4、mounted 3→6、空扫描 0→1；修复后定向集 172 passed / 1 skipped，追加任务/UI 观察 29 passed。与后续全量回归有重叠，不相加。
- B01/B02 定向 211 passed，补充三版本独立进度和真实 JS→PhoneManagement→SQLite 等 46 passed；独立 SQL 复核把 1716 组 native/mounted 查询与 `95a140b` 原 SQL 逐行比较，零差异。500 个历史 membership 的本地样本从约 512.5 万降至 2.8 万 SQLite 指令；这是合成数据查询测量，不是设备速度倍数。
- UI 收尾的导航、预览和包元数据相关集 97 passed；22 个组件、31 条本地依赖最低版本核对通过。`ui-metadata-source-check` 已按更新后的清单构建全部 22 个组件，仍为不可安装的 source-check，不代表本代真机导航或播放验收。
- 性能入口已用当前 2116 盒子做 3 秒只读工具自检，并将采样的 7 个源码文件、组件清单与其原部署 tree 逐一核对；这是旧代工具自检，不是本轮性能收益。
- B04 真实构建回执位于 `b04-native/home/ce-home-focus-ng4inyza/build-result.json` 和 `b04-native/completion/ce-completion-kwt9bxv9/build-result.json`。前代字节级重链、档案成员与 ABI 核验通过；候选分别仍为 `591fa655fa6a507145c7fd90163a18eee91266b98fe89315268e1a5bd32be032` 和 `4177ade3b59b0c69062f0e49d1e6dc27fa4dba78aed883721e9e83d4fc36fc6a`。工具归并未改变产品原生字节，因此本轮无需另换内核。
- `b04-native/generic-final/result.json` 的五组通过，包含真实 DirectoryProvider 十二场景及两个负控。`b04-native/gate-negative/completion-gate-axqmi3tu/result.json` 的禁用成功分支、缺头文件两个破坏均使真实 gate 返回失败；原始源码未改。完整 series apply 在独立命令中通过但该旧工具未保留单独 JSON；下面两份 Android 回执另记录各自真实的 `full_series_applied=true`。
- Android arm64/armv7 各三个实际 TU 编译通过，回执分别为 `b04-native/android-arm64/completion-4hvw41yu/result.json`、`b04-native/android-armv7/completion-v0rzyz8d/result.json`，状态仍是 COMPILED_NOT_LINKED，不冒充 Android 链接或实机。
- 只读设备预检 `device-catalog/existing-samples-04.json` 显示 326 个文件尚无人工确认映射，全部 observed_present；有命名明确的跨季剧集，但没有现成已确认的电影三版本。此限制不能靠合成用户数据改写为真实矩阵通过。
- 冻结候选 `full-04/report.json` 的九个步骤全部 exit 0、源码前后不变：主集 6455 passed / 14 skipped / 1 xfailed，baseline 1315、preparation 254、Android packaging 44 passed，共 8068 passed / 14 skipped / 1 xfailed。JUnit 将 xfail 计入 15 个 skipped，不另算成功。许可证检查、首页生成检查和双次 source-check 通过，63 个分发文件逐字节可复现。`package_candidate_matches=false` 表示实际已扩展源码不等于包内原候选；`actual_source_verified=true` 核对的是上述冻结 tree，不是声称原补丁原样通过。
- `posix-regression/targeted63-2120/report.json` 在现有 WSL/venv 补测 Windows 跳过的 14 项及 Registry 49 项，63 passed、零失败/错误/跳过，前后同一冻结 tree。与全量集重叠，不累计成 8131 个独立测试；POSIX 结果不替代 Android 或 CoreELEC 真机。

## 设备验收：2120 测试，2121 恢复交付

### 安装与数据

`review-evidence/ce2023/installed-files-1794474655344397700.json`（仓库本地证据目录）确认 sequence `2026102120` 的 1223 个 owned program 文件全部匹配、无差异；其范围不含原有依赖或用户数据。健康检查与用户数据另见 `health-installed-2120.json`、`device-catalog/preserved-before-2120.json` 和 `device-catalog/preserved-installed-2120.json`。本轮未更换产品原生二进制；前述 native 构建与 Android COMPILED_NOT_LINKED 边界不变。

2120 安装后健康为 passed：服务 active、重启 0、无 pending transaction，启动 traceback/product error 均 0，挂载检查通过、探针云请求 0。八项用户数据/配置哨兵摘要与安装前相同；两份 preserved 快照除时间外全部 result 字段相同，包括 396 文件、4 个 confirmed 映射、review/保留表摘要、projection schema=5、零 active scans 和 integrity=ok。这证明本次安装前后保留；不替代本轮程序回退或账号切换验证。

### 界面与扫描

2118 的 `device-catalog/ui-59` 至 `ui-84` 回执验证稳定搜索→详情 981→两季/分集→文件 985→返回，以及未知类型详情 981 的原文件入口。它们只证明该次 TV 导航，不升级为实际手机、电影三版本独立进度、CD2 重挂或账号切换通过。

追加 `ui-85` 至 `ui-97` 验证首页同一作品详情 981→28 项季列表→Back 回原 Home/9830，以及详情 984“系列与演职作品”→7 个演员入口→Back 回原 Home/9830；未继续进入演员作品层。片库搜索键盘 10103→Back 返回视频窗 10025 的“搜索片库”入口，未提交关键词，不作搜索召回证明。这组回执本身无版本身份，时间为 2026-11-12 17:04:37–17:07:54（UTC+8），处于 2120 安装前、邻近健康记录明确为 2118；不将其重标为 2120 UI 通过。

2120 的 `device-catalog/scan-2120-{1,2,3}.json` 与 `scan-play-2120-{1,2,3}.json` 共六轮部分扫描均无错误，终态为 `canceled / CANCEL_CONFIRMED`，`scanner_stopped=true`、零 active scans、数据库 integrity=ok；同 revision 分页、无重页与错误 namespace 拒绝均通过。

| 2120 条件/轮次 | pages / scanned / discovered | 索引对象前→后 |
| --- | --- | --- |
| 扫描 1 / 2 / 3 | 83/687/390；84/689/390；149/1250/593 | 396→396；396→396；396→593 |
| 播放＋扫描 1 / 2 / 3 | 64/631/361；64/631/361；86/710/396 | 均为 593→593 |

对应六份 `host-scan[-play]-2120-*` 只读探针各 85 个请求，共 510 个 HTTP/ok/异常检查无失败；完整落在已观测 running 窗口内的请求分别为 75/75/75 与 75/72/75。host 通道单次最大时延仍达 559.787 ms，不称为零等待。这些是有限扫描和取消验证，不是整树完成或 FUSE 阻塞可抢占；396→593 只证明数量增长，未枚举旧 396 个 ID，不证明逐项全保留。

### 保留的失败与播放边界

- 2117 首次 select（`playback/ce-new-work-review2117-eof1-galactic_heroes-select-1794472003532922700.json`）仍为 `trace_passed=false`，连续 caching 11.472 秒、最长观察时钟停滞 12.461 秒。第二次 select（`review2117-repeat`）因 `STARTUP_OBSERVATION_INTERRUPTED / PLAYBACK_OWNER_UNAVAILABLE` 中断，捕获期没有 AV 样本；后续 30 秒 observe 通过不能抹掉起播失败。该代 next 虽有有效同实例 NATURAL_EOF，但缺 grant、child reservation、target 与 child OPEN/AV，因果链未通过。
- 2118 `device-catalog/scan-play-2118-2.json` 保留 `failed / CATALOG_PROBE_UNAVAILABLE`；第 1/3 轮及后续恢复取消通过，只证明各自结果，不将第 2 轮改成通过。
- 2120 select（`playback/ce-new-work-review2120-eof1-galactic_heroes-select-1794474943250154000.json`）仍为 exit 1、`STARTUP_OBSERVATION_INTERRUPTED / TimeoutError`、`trace_passed=false`；已采样连续 caching 4.994 秒。`startup-buffer-log-2120-01.json` 仅为限量日志观察，未收集 CD2 专用日志，`causal_attribution_proven=false`，不将该问题归因于单一网盘、CD2 或本次 Registry 修复。
- 2120 1x next（`playback/ce-new-work-review2120-eof1-galactic_heroes-next_watch-1794475259560963400.json`）取得合格同实例 NATURAL_EOF、grant→reservation→目标→child OPEN/AV，`causal_chain_passed=true`、missing 为空。但一次 `OWNER_SNAPSHOT_RuntimeError` 返回 unavailable（随后恢复），整体仍为 `passed=false / state=not_tested / exit 1`；因果链通过不等于采集无缺口或整体通过，最终历史需独立证据。

### 同版本倍率终态与停止负控

三个独立会话都由普通选源选择同一 S1E1、同一 source_key 与 selection identity；可见的稳定 transport 身份一致，临时播放 URL 随会话变化，不用 URL 哈希相同冒充文件内容校验。`D:/AM6B-Project/ce-native-completion-20261112/` 中的 `completion-b2120eof1-eof-1794475239507980900.json`、`completion-b2120eof8-eof-1794475465244325100.json`、`completion-b2120eof32b-eof-1794476038272809200.json` 分别有 71/64/73 个实际 speed=1/8/32 样本及推进位置。三份精确原生 NATURAL_EOF 均为 position 1444729 / duration 1444945 ms，age 分别 113625/17045/33056 us；同 request 的 S1E1 历史均 completed=true、progress=100、terminal_reason=NATURAL_EOF。

这是同文件版本的倍率终态验证，不是同尾段性能比较或整段采集无错误：1x/8x 保留 read_failed_no_further_control，32b 保留 different_instance_no_further_control。首轮 32x `completion-b2120eof32-eof-1794475639556419800.json` 虽有实际倍率与合格 EOF，未收齐历史更新，仍记历史证据不足。复跑仅在外部探针副本中允许已收到精确 terminal 的换实例结果进入既有两秒磁盘历史观察，不再发送 RPC/播放控制，也不改原状态；13 项离线边界检查通过。

独立停止负控为 `completion-b2120stop-stop-1794475891930331700.json` 与 `playback/ce-new-work-review2120-stop-galactic_heroes-next_watch-1794475906922980800.json`：同一 S1E1 request/native 收到 STOP，历史 completed=false、progress=3%、terminal_reason=STOP，最终 idle；30 秒观察窗无采集错误、无 continuation grant/reservation 或子 OPEN。next_watch 的 EOF 正向判据仍返回 false，负控按这些原始字段验证，不改写为正向通过；这不是近片尾停止测试。自动播放的四次 E2 均另行精确捕获并停止，未被记为完成。

首段补充日志 `playback/startup-buffer-log-2120-03.json` 将共享读取记录与实际 transport 哈希关联：早先读取在尾部探测后以 socket_error / SHARE_STOPPED 取消，随后另一次顺读继续；不能把这条 OSError 直接认定为上游网盘失败。同期有 CINEMA-OWNER SNAPSHOT_UNAVAILABLE / TimeoutError，仍不能确定采集器本次 Timeout 的具体通道或缓冲根因。本轮未改媒体读取、CD2/115 resolver、preloader、缓存设置或原生补丁；不以未经验证的缓存调整掩盖失败。

### 带数据回退、恢复与测试整理撤销

本轮使用原部署事务正常回退至 2118 程序字节，再以递增 sequence `2026102121` 恢复冻结候选。2120 与 2121 包的 22 个组件载荷逐项 SHA-256 相同；仅发布序号及其签名元数据更新，部署源码仍是 `0941b74`，不冒称后续文档提交已重新部署。安装核验如下，均只覆盖自有程序文件：

| 阶段 | 本地安装回执（`review-evidence/ce2023/`） | 结果 |
| --- | --- | --- |
| 2120 安装 | `installed-files-1794474655344397700.json` | 1223 文件匹配 |
| 回退至 2118 字节 | `installed-files-1794476169747214000.json` | 1223 文件与 2118 包匹配 |
| 恢复 2121 | `installed-files-1794476293294193800.json` | 1223 文件匹配 |

`health-before-rollback-2120.json`、`health-rollback-2120.json`、`health-restored-2121.json` 独立记录高水位 `2120→2120→2121`，回退没有降低防降级序号；platform 为 `0.1.71→0.1.70→0.1.71`，其余列示版本和 native SHA 不变。三份健康均 passed、无 pending、服务 active、重启数为 0。八项配置/历史哨兵、十项保存登录态（115、百度为已登录）均一致。这不等于重新扫码或各云端账号/播放验收；百度目录健康查询成功但返回零项。

`device-catalog/preserved-before-rollback-2120.json`、`preserved-rollback-2120.json`、`preserved-restored-2121.json` 的 result 除观察时间外完全一致：593 文件、4 个确认映射、4 条 review_changes 和 4 条 review_receipts，review_digest 为 `b8466914c521c1e619daaf3d45a629d66220d014336ad01a765609e2d0c67d1a`；零活动扫描、integrity=ok、projection=5。它们证明本机这次回退/恢复的数据保留，不覆盖全部历史 schema 或 arm64。

恢复后经产品 API 正常撤销四条 The Boondocks 测试整理映射，未直接修改 SQLite。`device-catalog/trial-undo-plan-01.json` 预览核对四项 expected_revision=1；`trial-undo-01.json` 使用固定原计划的 undo request，四项均 applied、revision=2、state=proposed、mapping=null，原提交回执可查，state=undo_verified。原确认中只有 S1E1 经过 TV 操作，其余三项及撤销是产品 API 验证，不称四项 TV 全流程。撤销保留审计，不回滚版本号、不删原文件。

恢复后的 TV 回执 `device-catalog/ui-100` 至 `ui-128` 记录 Home→CD2→输入 The Boondocks 搜索→乡下人→两季列表；在此正常撤销后，选择旧 S01 入口得到空分集的两个恢复按钮。`ui-120-stale-season.json`、`ui-124-review-settled.json`、`ui-127-empty-return-open.json` 分别核对空页、继续整理后的五项管理入口、返回来源作品，source/namespace/scope 均保持不变。UI 回执本身没有版本字段，2121 身份由其前后的安装与健康记录界定，不将旧 2118 UI 证据改名。未补测实际手机、三版本独立进度或 CD2 重挂/账号切换。

最终 `health-final-2121.json` 与 `device-catalog/preserved-final-2121.json` 确认无播放、Home 空闲、无 pending、零活动扫描、593 文件仍在、数据库正常，八项哨兵及保存登录态仍一致。review_changes/review_receipts 各增至 8，四项已恢复原 proposed/null 状态；这是正常撤销新增的审计记录，不是数据丢失。设备最终保留 2121，首段缓冲与 next 采集缺口仍按上文记录为未解决边界。

## 测量口径

`metrics` 复用现有 SSH transport，采样不发送播放控制、不启动扫描、不清缓存。每次保留来源 tree、实际组件/内核摘要、boot/PID/start ticks、UTC/单调时间、CPU/RSS、实际任务和播放器观察。`summarize` 只读显式输入文件，并以其记录 tree 核对安装源码，不套用当前工作树或固定旧 run。

扫描指标仅包含同一任务连续正向观测之间的完整 CPU 区间，排除首次观测前的部分区间。网络字节为设备网卡计数，不能归因 Kodi 或上游网盘；稀疏 share trace 不冒充精确 Range/请求总数。GUI RPC 时延不等于遥控输入到屏幕时延。process_cold 不代表磁盘/CDN 冷缓存。短窗 P95、RSS 增量不证明总体最优或泄漏。

2120 的显式 12 份汇总为 `metrics/ce-metrics-summary-1794475222845880900.json`：空闲、扫描、播放、播放＋扫描各三轮，均为 page_warm，同 boot/PID `31035` / start_ticks `188986778`。七个抽样源码和 Bobbi 组件 manifest 与冻结 tree 匹配；这不替代上述 1223 文件安装核验。扫描完整观测交集为 7.000283/9.999945/11.000140 秒，播放＋扫描为 10.000246/9.999604/10.000404 秒；第一轮纯扫描有两个扫描状态缺失点，未纳入对应交集。六份播放样本为同文件、同实例、1x，采样位置持续递增，但不是连续渲染或整片无卡顿证明。精确首帧、按键到屏幕、Range 次数及上游总字节仍 unavailable；不把吞吐、CPU 或 RSS 的轮间差异归因于本次修复。

## 保持不变的限制

- 索引 user_version=2、projection schema=5；来源、人工整理、观看历史和旧 mounted URL 保留。
- 弱 MountedRef 不提供跨观察的精确续播；FileRef 只按现有 size/fingerprint 政策识别替换，不新增全文件 hash。
- 新原生 completion observation 的 unavailable 不降级成旧轮询；只有真正缺少新字段的旧内核走唯一兼容路径。
- 本地、mock、JS/SQLite、C++ helper、实际编译/链接、安装、设备播放分别记证据，不能互相替代。
- 分发许可证台账的 9 项 unresolved 保持；借鉴结构和测试通过不改变许可状态。
