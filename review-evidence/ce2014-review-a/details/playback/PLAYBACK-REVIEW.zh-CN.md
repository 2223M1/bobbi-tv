# PR #3 播放链独立复核

## 结论与版本

本次播放范围确认 **1 项 P2 遗留缺陷**：原生播放监控把“读取暂不可用”及“同实例终态已到达”都压成 `False`，随后误判为用户换片并提前返回；这会绕过本 PR 新增的终态读取修复。两种触发路径属于同一个控制流问题，不能重复记作两项缺陷。

前轮 R04（慢字幕耗尽标准续播窗口）与 R05（无效进度刷新 EOF 证据）在原独立复现契约下已关闭。本次原生问题在 base 与 head 都可复现，应记为**本次完整审查发现的继承问题**，不能表述为 PR #3 新引入的回归。

| 项目 | 固定值 |
| --- | --- |
| 仓库 / PR | `2223M1/bobbi-tv` / [PR #3](https://github.com/2223M1/bobbi-tv/pull/3) |
| PR 状态 | 审查时 open、draft |
| Base | `ee65742bfcbaf08831f70306faed11bd1f8d6cc6` |
| Head | `c8de17ae9dabbe0f37753e1751b1d88107311316` |
| 审查方式 | 固定源码静态检查、实际策略模块及明确 I/O 替身的确定性回放 |
| 实机范围 | 本独立回放没有连接电视、部署服务或控制播放器 |

## P2：原生 monitor 提前退出，跳过同实例终态收尾

**主位置：** [native_player.py L708–L712](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/native_player.py#L708-L712)。

`monitor()` 在 `while self.isPlayingVideo()` 内，任一 `_owns_playback_session()` 或 `_matches_requested_playback()` 返回假值，就设置 `_was_superseded=True` 并 `return`。这两个谓词并不只表示“明确用户换片”：前者在 IPC 读取失败时也返回假值，后者在同实例已经产生终态、`observed` 被收回时也返回假值。于是 [L739–L746](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/native_player.py#L739-L746) 的终态读取、自然 EOF 续播边界、停止历史收尾都被绕过。

### 路径 A：一次有界 IPC 读取耗尽重试，随后恢复

前提是该请求已经得到真实 AVStart，当前 `desired`、`observed` 和 native instance 都没有改变。实际 `owned_state()` 连续读取 3 次均发生 `OSError`，耗尽它已有的单轮重试；回放中每次耗时 0.2 秒，加上两次 0.05 秒间隔，共 0.7 秒。随后紧接着的读取恢复正常，仍返回同一请求和同一实例。

当前行为是：`_owns_playback_session()` 把这次不可用返回为假；monitor 立即退出并设置本地 cancel。恢复后的实际 `owned_state()` 确认该请求仍然拥有权限，播放器仍然播放，但监控已结束，无法继续上报进度、进入 EOF 协调或停止历史收尾。`finally` 还能在恢复后的快照下执行当前请求的本地清理，进一步说明这不是服务已经选择了另一请求。

这里不是“一个失败数据包必然退出”的断言。实际 [owned_state L189–L203](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/script.module.bobbi.core/lib/bobbi_core/playback_request.py#L189-L203) 有 3 次有界重试；问题是耗尽这一次读取预算后，调用方将未知状态解释成了明确换片。[native_player.py L149–L159](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/native_player.py#L149-L159)

### 路径 B：同实例自然 EOF 恰好发生在两个快照之间

无需任何 I/O 错误，合法事件顺序如下：

1. `isPlayingVideo()` 刚返回真，monitor 进入循环。
2. `_owns_playback_session()` 读取到仍然有效的当前请求。
3. 同一个 native instance 此时发生 `NATURAL_EOF`。
4. 实际 `PlaybackOwner.observe_terminal()` 保存匹配终态并把 `observed` 设为 `None`；当前 `desired` 保持不变且未取消。
5. `_matches_requested_playback()` 第二次读取快照，看到 `observed=None`，返回假。
6. monitor 误标为 superseded，跳过新的 `wait_cinema_terminal()`。

第 4 步直接调用真实 [PlaybackOwner.observe_terminal L264–L279](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/script.module.bobbi.core/lib/bobbi_core/playback_owner.py#L264-L279)，没有人工拼出异常快照。第 5 步来自真实 [匹配谓词 L657–L671](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/native_player.py#L657-L671)。最终权威终态为 `NATURAL_EOF`，本地终态仍为 `UNKNOWN`，当前请求仍有效，但没有进入续播和停止收尾边界。

这是事件调度窗口，不代表所有 EOF 都失败。正常时序正控能够通过；本次仓库记录的成功 EOF 也不被这个反例否定。新 [terminal_state L206–L229](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/script.module.bobbi.core/lib/bobbi_core/playback_request.py#L206-L229) 及 [wait_cinema_terminal L2333–L2353](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/native_player.py#L2333-L2353) 正确增加了不可变终态读取；当前遗漏在到达它之前的 monitor 分支。

### 影响与严重性

影响已经开始播放的原生路径：短暂本地 IPC 抖动可使本次监控提前结束；片尾竞态可使准确的自然 EOF 丢失本地收尾，进而失去自动续播机会，或缺少应由停止路径记录的最终进度、完成状态与终态 UI。回放证明的是这些真实边界没有被调用，没有声称已经在电视上重现数据库损坏、停播或每次都续播失败。

建议 P2：有明确、局部、可修复的功能影响，但目前没有故障发生率或全设备必现证据；不因设备未知而加设硬件准入门槛。

## 复现范围、结果与继承关系

`reproduce_native_monitor.py` 是无网络、无设备的独立执行脚本。它导入完整的真实 `bobbi_core.playback_request` 与 `PlaybackOwner`，以真实 select/bind/claim/AVStart/terminal 操作构建状态；通过 AST 原样提取候选文件中的 `_owns_playback_session`、`_matches_requested_playback`、`monitor`、`wait_cinema_terminal` 执行。未改写上述函数的产品逻辑。

明确替身包括 Kodi 的播放布尔状态、IPC 传输、确定性时钟、已验证 AV 之后的测试起点，以及与本次控制流无关的字幕/远端历史等辅助工作。续播边界、停止收尾和 UI 清理函数使用调用记录替身，因此结果描述为“到达/跳过调用边界”，不等同于验证后继实际提交或真实历史库写入。正常 EOF 正控确实执行了真实 `wait_cinema_terminal()`。

| 用例 | Head | Base | 它证明的边界 |
| --- | --- | --- | --- |
| `transient_ipc_recovers` | 失败 | 失败 | 一次有界读取失败后恢复，不应无证据结束未改变的播放监控 |
| `eof_after_player_check` | 失败 | 失败 | 同实例 EOF 到达应进入匹配终态协调 |
| `continuously_current` | 通过 | 通过 | 正常 EOF 时序能够到达真实终态协调与收尾边界 |
| `explicit_replacement` | 通过 | 通过 | 明确换片必须结束旧监控，不清理新 owner UI、不续播 |
| `explicit_cancel` | 通过 | 通过 | 明确取消必须结束旧监控，不复活后继 |

两个版本均为 **5 项、3 通过、2 失败、0 harness 异常**。脚本按预期退出码 1 表示发现失败契约，不能把它记成测试脚本运行异常。安装审查代理也独立执行相同脚本，得到相同结果，交叉输出位于其 `native-monitor-crosscheck.json`。

`native-monitor-provenance.json` 比较方法 AST，确认 `monitor`、两个谓词、`owned_state`、`PlaybackOwner.observe_terminal` 与 `consume_next` 在 base/head 等价；`wait_cinema_terminal` 改动、`terminal_state` 新增。这与 base/head 各自回放结果相互印证：问题是遗留控制流未随新终态读法一并闭合。

JSON 同时记录真实被执行的源文件字节数、Git blob SHA-1 与 SHA-256；head 的 `native_player.py` 是 132296 字节，blob 为 `ad17c8b8c1d84fbc07b52376632b05558c703733`。对应 XML 是原始 JSON 的 JUnit 表达，没有追加或重复统计测试次数。

## 既有修复的独立确认

| 范围 | 本次证据 | 结论 |
| --- | --- | --- |
| 前轮 R04 慢字幕阻断 | 原审查脚本原样重跑；`next_with_subtitle()` 最多预算 2 秒，临近 EOF 截止时缩为剩余时间减 1 秒 | 原反例关闭；20 秒绝对窗口没有被延长 |
| 前轮 R05 无效进度刷新 | 原审查脚本原样重跑；有效进度时刻独立为 `progress_observed`，0/0 不刷新 | 原反例关闭；陈旧片尾样本不能借无效读数恢复新鲜度 |
| 标准正常续播 / 无候选 | 同一旧脚本中的两个正控 | 都通过；准确后继至多一次、无候选不捏造 |
| 当前标准与本次播放回归 | 4 个当前测试文件，共 52 项 | 全部通过，0 失败、0 异常 |

四项旧契约结果保存在 `previous-playback-contracts.xml`。52 项当前回归结果保存在 `focused-regression.xml`，来源为 `test_standard_session.py`、`test_standard_product.py`、`test_ce2012_continuation.py`、`test_ce2014_four_three_release.py`。

修复位置分别为 [标准 session L80–L137](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/script.module.bobbi.platform/lib/bobbi_platform/standard_session.py#L80-L137) 和 [标准字幕预算与晚到候选 L164–L201](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/services/standard_playback.py#L164-L201)。晚到字幕只发布可选候选，不做无作用域的 `setSubtitles`，保留用户手动 Off 的意图。标准账号代际、外部改播、停止及现有续播门槛仍应留在既有回归集合中。

## Codex 修复与验收要求

详见同目录 `CODEX-PLAYBACK-TASK.zh-CN.md`。关键约束是把“明确换片/取消”“仍有本次活动实例”“已收到匹配终态”“本次读取未知”分开处理。

明确取消、身份变更、服务重启或账号代际变更必须使旧监控停止；未知读取应在固定预算内暂停产生控制副作用并重新观察，同实例终态应进入已有不可变终态协调。禁止使用缓存快照授予控制权，禁止删除身份校验，禁止从播放器消失或近片尾进度推断原生自然 EOF。

不能无限重试、扩大已有终态 3 秒预算或标准 EOF 20 秒绝对窗口来制造通过；每次控制/后继提交仍须使用当前有效授权并保持至多一次。本回放 5 项全绿后，再运行已有相关回归即可，设备实测按项目既有通用 CE 流程另行记录。

## 本目录可交付证据

- `reproduce_native_monitor.py`：可独立执行的回放脚本。
- `native-monitor-head.json`、`native-monitor-base.json`：5 项各自完整事件、断言与源文件哈希。
- `native-monitor-head.xml`、`native-monitor-base.xml`：以上 JSON 的 JUnit 表达。
- `native-monitor-provenance.json`：base/head 方法 AST 与行号对照。
- `previous-playback-contracts.xml`、`focused-regression.xml`：4 项旧契约、52 项当前测试的原始 JUnit 输出。
- `PLAYBACK-FINDINGS.json`：便于总交付包合并的一项 finding 与测试统计。
- `CODEX-PLAYBACK-TASK.zh-CN.md`：限定范围、行为验收和复跑命令。

`fetched/` 只是独立读取时使用的产品源码临时副本，不属于报告交付证据，也不应并入执行包。
