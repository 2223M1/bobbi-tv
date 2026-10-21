# Bobbi TV CE2014 审查后的 Codex 执行任务

本文件与 checks、run_review.py、FINDINGS.json、ACCEPTANCE.json 组成同一执行包。完整证据和判断依据在 [REVIEW.zh-CN.md](REVIEW.zh-CN.md)。受审 head 为 c8de17ae9dabbe0f37753e1751b1d88107311316，base 为 ee65742bfcbaf08831f70306faed11bd1f8d6cc6。

## 可直接交给 Codex 的任务正文

请在 Bobbi TV 当前授权的开发工作区完成 PR #3 CE2014 后续修复。先读取仓库 AGENTS.md、这份执行说明、审查报告及原始复现结果，确认实际 HEAD、tree、工作区状态与远端 PR。保护已有未提交工作；需要时使用隔离分支或 worktree。

本轮主任务是修复 F01、F02、F03 三项问题。前轮 R01–R06 的原始契约已全部通过，保留这些修复。新的 14 项主契约在原 head 应得到 8 通过、6 失败、0 执行异常；失败分别来自 F01 两条、F02 两条、F03 两条路径。先确认基线，再改产品源码。将每项修复与其新增正反例集中在可独立审查的提交中。

完成源码修复、相关测试和构建证据，交付下一候选的代码差异、准确 commit/tree、测试回执、已授权范围内的设备结果及仍开放事项。保持私库审查候选和 Draft 状态；本执行包本身没有执行部署或对外发布。已有会话明确授权的操作按原范围继续，不因本包重复索要授权；未授权的设备操作或发布只准备具体可审查步骤。

### 必须保留的产品约束

- 通用 CoreELEC；未知型号仍可按既有朋友测试流程安装。不加入型号白名单、F9/native hash 安装门槛、额外未知硬件确认或第二台设备准入要求。
- 保留精确手动选源、准确同版下一集、原始画质／码率／语言／音轨；分享失效不得通过换版、降画质、转码或全局重试掩盖。
- 保留字幕手动 Off、账号 scope／代际隔离、取消／外部接管优先、后继提交至多一次。
- 保留 journal 状态、整个 managed enabled 向量、稳定 OS lease 身份、反回退 high-watermark、恢复菜单的重试／回退／退出。
- 保留账号／profile／观看历史、CD2 1.0.19、现有挂载、Yatse、VPS／代理配置、固件及 SYSTEM／eMMC。
- 产品运行兼容 Kodi 21／Python 3.8+；本审查脚本的开发解释器为 Python 3.12，不因此提高产品运行门槛。
- 保持私有分发、原有上游标识和 notices、显式 source inventory；安装包及诊断不包含账号状态、设备备份或签名私钥。

## 任务 A 修复恢复服务的身份与管理所有权

**F01，P1；先做。** 主要入口为 addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py 的 ensure_running／activate／restore，关联真实 addon service 入口、runtime、host、boot_gate 和恢复测试。

### 当前可复现行为

addon enabled、宿主不存在、owner snapshot 不可达且 OS lease 空闲时，fallback 调用裸路径 RunScript(service.py)。原生导入链因默认 addon id 缺失无法启动；标准分支虽然 ready，但没有受管理服务 handle，下一次 quiesce 无法停止该宿主。

### 实施要求

选择真正产生 addon 上下文且受 Kodi 服务管理器管理的恢复方式。若以 disabled→enabled 的真实状态转换触发服务管理器，要保护整体 enabled 向量、正确服务启动顺序、journal 及当前 lease，正确处理查询失败、过渡期和服务仍在初始化的情况。一次 enabled=true 的 no-op 不证明服务已启动。

readiness 仍须得到当前 owner 的实际回复；成功恢复的服务必须能在随后的正常安装停机路径中释放所有权。仅改为 RunScript(addon_id) 不足以证明 service handle 已被管理；不能用提前 complete、假 ready 或删除 gate／lease 制造成功。

### 验收

| 条件 | 期望 |
| --- | --- |
| enabled 但进程丢失，原生可用分支 | 真实导入获得正确 addon 身份，owner 可以回复 |
| enabled 但进程丢失，标准分支 | 真实 Host／Runtime ready，随后 quiesce 能正常停止 |
| 正常 managed 原生／标准启动 | 原有正控继续通过 |
| 活动 owner 仍持锁 | 安装不替换其程序；超时保留恢复状态 |
| enabled 查询及后备查询均未知 | 保守失败，原 enabled 向量不被伪造 |
| staged／switching／restoring | 未验证的启动仍被 gate 拦截 |
| 可验证 activation／restore pending、旧 restored 兼容 | 可以恢复，持续失败仍可到达恢复菜单 |

交付新的受管启动正反例，至少覆盖“恢复→ready→停机→再次启动”，避免只验证一次 ready。

## 任务 B 修复原生列表绑定后的焦点回退

**F02，P2；可以与任务 C 在互不冲突的工作区并行。** 主要文件为 addons/plugin.video.bobbi/lib/gui/source_select.py、tests/private_baseline/test_source_incremental_ui.py，必要时调整 UI smoke 工具。

### 当前可复现行为

ControlList.addItems／addItem 会排入完整原生 LABEL_BIND；Python 读到旧位置时跳过补偿，下一次 GUI 调度把焦点设为 0。新增画质 tab 同样会丢掉非默认画质焦点。Base 的同一 5 项回放全通过，head 两条失败。

### 实施要求

保留按 source_key 和画质 key 表达的用户意图。保证原生 bind 与必要的焦点补偿顺序可靠，可使用与 Kodi 消息顺序一致的窄补偿；不要依赖“本次 getSelectedPosition 仍为旧位置”推断无须补偿，也不要依赖任意 sleep。新用户交互应优先于旧刷新快照。

继续保留可复用 ListItem 和增量排序。对元数据更新、加载状态完成、增加／移除画质、精确来源替代分别处理；按稳定身份验证当前选中对象，而不是只检查 Python 索引或 reset 调用次数。

### 验收

| 条件 | 期望 |
| --- | --- |
| 用户在第 2 张或更后卡片，新增结果后 bind 延后消费 | 原 source_key 保持 |
| bind 已消费后才读取位置 | 同一 source_key 保持 |
| 用户选择 1080p，随后追加 4K 标签 | 当前画质 key 保持 |
| 只有 metadata／完成状态变化 | 不产生多余的重置或错误选中 |
| 首卡／默认画质 | 正常显示与原正控继续通过 |
| 用户在刷新过程中再次移动焦点 | 以新交互为准，不被旧快照强制拉回 |
| 精确替代导致原卡删除 | 使用明确且一致的邻接策略，不改选未经用户授权的媒体并自动播放 |

保留源码支持的排队 GUI IO 模型；增加等价的原生绑定测试，不能把替身退回简单 list.extend。实机 smoke 主动选非首卡和非默认画质后再追加结果，记录选中 key、事件顺序及受测区域；70 次首卡静态 ROI 摘要不能替代这些新条件。

## 任务 C 收口原生 monitor 的未知读取与终态竞态

**F03，P2；这是遗留问题。** 主要入口为 addons/plugin.video.bobbi/lib/native_player.py 的 monitor／_owns_playback_session／_matches_requested_playback，关联 bobbi_core/playback_request.py 的 owned_state／terminal_state 与 PlaybackOwner。

### 当前可复现行为

第一条路径：owned_state 一轮 3 次读取均失败，随后下一读恢复，仍为相同 request／instance；monitor 已按 superseded 退出。第二条路径：isPlayingVideo 返回真后，同实例 EOF 到达，真实 owner 保存 terminal 并清除 observed；第二次谓词把 observed=None 当换片，绕过 wait_cinema_terminal。

### 实施要求

采用能区分至少四类结果的窄状态协调，保留其他调用者兼容性：

| 状态 | 处理 |
| --- | --- |
| 当前活动实例被新鲜快照确认 | 正常观察；有权限才产生控制相关副作用 |
| 同 boot／epoch／request／instance 的不可变终态 | 进入终态协调、历史收尾、终态 UI 与现有后继授权流程 |
| 明确取消／换片／instance 或 boot／epoch／账号代际变化 | 立即退休旧监控；不清理新 owner UI、不复活旧后继 |
| 本次读取未知 | 固定预算、有间隔重新观察；暂停依赖权限的副作用；预算耗尽有明确未知结果 |

未知不等于明确 superseded；缓存也不能授权当前控制。保持原生终态 3 秒与标准 EOF 20 秒绝对窗口，不增加无限循环、不通过延长时间掩盖竞态。原生 NATURAL_EOF 仍必须来自匹配终态，不能由近片尾百分比或播放器消失推断。

修复后 5 项独立回放全部通过；同时验证真实停止、用户新选择、账号变化、旧回执、迟到字幕 Off 等既有防护。需要修改接口时，在常规测试中补实际 caller 链，不只改 AST 回放的替身。

## 非阻断工作

### C01 可随本轮整理

统一 tools/ce_standard_real.py 及相关辅助工具的 transport_exit_code、trial_exit_code、最终 exit_code、state／passed 语义。已完成且 passed=false 时 CLI 非零且落盘一致；running／passed=null 清楚表示 pending，不能被汇总为播放验收通过。

保持 ce_playback_trial.py 原 4 项契约和本包 11 项 operation 正反例全绿。本包保存三组实际字段观察；新增常规测试约束修复后的字段，保留旧失败回执作对照。

### C02 单列后续停机加固

2 项诊断已证明外围 HistoryWriter 可以晚于 runtime lease 释放结束，但实际数据库锁和原子合并尚未出现本轮用户损害。该项不阻断本包主裁决，不增加 F01–F03 数量。

若安排处理，把已接收的标准后台工作纳入停机完成条件，先停止接纳，再确认完成或安全退休，最后释放替换许可。不可结束的 IO 应保留待恢复状态并拒绝程序切换；固定 sleep、丢弃历史队列、join 超时当成功不满足该后续契约。

## 可直接执行的验证命令

### 环境与身份

在完整 repository checkout 中运行。以下 /path/to/... 均为执行者自己的路径；不要用本次审查的部分源码快照替代完整发布构建。

    git status --short
    git rev-parse HEAD
    git rev-parse HEAD^{tree}
    python -m pip install -r requirements-test.txt

受审基线必须是 c8de17ae9dabbe0f37753e1751b1d88107311316。如果 PR 已前进，记录新 head，逐项检查问题是否已改，不覆盖新工作、也不宣称旧结果自动适用于新提交。必要时在独立 worktree 复现旧 head。

### 本包主契约

    python /path/to/this-package/run_review.py --repo /path/to/bobbi-tv --output /path/to/review-before
    python /path/to/this-package/run_review.py --repo /path/to/bobbi-tv --output /path/to/review-after --with-advisories

修复前主结果 14／8／6／0、exit 1；修复后主目标 14／14／0／0、exit 0。输出目录必须不同。C02 仍未处理时，advisories 单列一个失败是已知非阻断观察；advisory 的框架异常仍须明确处理。

### 保留前版契约

    python review-evidence/ce2012-web-contracts/run_review.py --repo /path/to/bobbi-tv --output /path/to/previous18-after
    python tools/replay_ce2009_candidate.py --output /path/to/previous15-after

目标分别为 18/18 与 15/15。若真实接口改变确需 IO 接线适配，保留原断言和原脚本，另交完整 adapter diff；不得以删例、xfail、放宽身份或加长绝对窗口来制造通过。

### 与当前 CI 一致的测试分组

三个 Kodi／准备链 harness 使用独立进程，避免 import 替身串扰：

    python -m pytest -q -rs tests --ignore=tests/private_baseline --ignore=tests/preparation_regression --junitxml=/path/to/results/ci-primary.xml
    python -m pytest -q -rs tests/private_baseline --junitxml=/path/to/results/ci-baseline.xml
    python -m pytest -q -rs tests/preparation_regression --junitxml=/path/to/results/ci-preparation.xml

当前原始 CI 基线为 1746 + 761 + 177 = 2684 passed、5 个 Windows API skips。修复后新增有意义的用例时总数可以增加；交实际 JUnit、skip 原因、fail/error 和运行平台，不只交一句“全绿”。

### 可复现 source-check

    python tools/build_release.py --source-check --output /path/to/source-check-first
    python tools/build_release.py --source-check --output /path/to/source-check-second
    python tools/check_repository.py /path/to/source-check-first /path/to/source-check-second

原 CI 是 63 个输出文件字节一致。source-check 不含正式应用密钥／签名材料，也不是可安装完整用户包；有新增组件／清单时先更新显式 inventory，再如实报告新的数量。

### 下一真实资产

按仓库现有私有构建流程产生新的代次与版本，不覆盖 CE2014 和更早资产。实际用户入口必须再次执行：

    python tools/audit_ce_entry.py /path/to/new-user-entry.zip --report /path/to/new-entry-audit.json

同时运行仓库已有完整载荷、签名、篡改负例及完整性审计，记录新 ZIP 的大小、SHA256、组件／文件数、commit/tree、同代 bootstrap。只使用既有受控签名流程；没有实际包字节时明确交付为源码候选，不能把 source-check 替代真实安装验签。

## 设备验收的最小补充

在已有明确授权的设备和测试范围内，补与改动直接相关的场景；仍按通用 CE 产品路线工作。

1. 安装恢复：正常受管启动、enabled 但宿主缺失后的恢复、恢复后再次停机／升级。记录实际 addon 身份、受管生命周期、owner ready 与 lease；不要用每次重启 Kodi 的手段掩盖无法停机。
2. UI：选中非首卡、非默认画质后追加结果；覆盖原生绑定前后两种观测顺序、完成状态及必要的精确替代，验证 source_key／quality key 与视觉焦点一致。
3. 原生片尾：同实例 EOF、明确用户停止／换片、短暂 IPC 抖动恢复；确认匹配终态收尾、未知预算和旧 owner 副作用隔离。
4. 标准片尾回归：真实同版来源后继仍可交接，可复用已有作品作为回归；如从 97% 起播，继续把证据限定为片尾交接。实际普通用户 UI／历史持久化若未测试，分别保留未验证状态。

原《罗生门》启动失败、《十二怒汉》上游分享失效，以及《四叠半》《玲音》《这个男人来自地球》的既有开放项保留。新片后段通过不冲销旧失败；同一作品重播属于回归，不重复算新增作品覆盖。

## 最终交付模板

下一轮返回以下内容，并把全部日志／机器结果留在独立结果目录：

| 项目 | 必填内容 |
| --- | --- |
| 代码身份 | base、head、tree、分支、工作区状态、相对受审 head 的真实 diff |
| 问题映射 | F01–F03 各自改动、原因、行为变化；C01/C02 的处理或保留理由 |
| 新契约 | 主 14 项逐项结果、框架异常 0、修改前后原始 JSON/JUnit、脚本及产品 SHA |
| 保留契约 | 18/18、15/15；必要 IO 接线差异单独附上 |
| 常规回归 | 三套实际 JUnit、运行平台、总数及每个 skip 原因 |
| 构建与实际资产 | 两次 source-check 比较；若构建完整包，附真实字节摘要、验签及入口审计 |
| 设备回执 | 实際入口、来源、时序、终态、选中 key、数据写入范围及测试清理分别记录 |
| 开放项 | 尚未解决的影片／安装／视觉／工具问题及下一步，不删除原始失败 |
| 候选状态 | 私库 Draft；所有外部操作按当前会话授权范围执行 |

验收关注正确行为和可追溯证据。最小目标是保留本版已经恢复的行为，关闭新的三项确认问题，并使下一次审查能直接复跑。
