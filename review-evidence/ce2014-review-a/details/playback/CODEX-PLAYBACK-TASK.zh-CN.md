# Codex 执行任务：闭合原生 monitor 的终态与读取不确定性

## 起点与范围

对 `2223M1/bobbi-tv` PR #3 的固定 head `c8de17ae9dabbe0f37753e1751b1d88107311316` 做最小播放链修复。先核对仓库当前 `AGENTS.md` 与 head；若后续分支已推进，对照本包源文件哈希和方法证据重新确认触发路径，不机械覆盖更新。

本任务针对 `addons/plugin.video.bobbi/lib/native_player.py` 中原生 `JacktookPLayer.monitor()`，以及必要的只读 owner 观察辅助。它是 base `ee65742bfcbaf08831f70306faed11bd1f8d6cc6` 已有、PR #3 尚未闭合的问题；不要改写成 PR #3 新回归。

## 当前失败契约

已经 AVStart 的 exact 请求进入 monitor 后，以下任一路径会使 L708–L712 无证据地设置 `_was_superseded=True` 并提前返回，绕过 L739–L746 的终态与停止收尾：

1. `owned_state()` 一次有界读取中的 3 次 OSError 耗尽重试；紧接着读取恢复，同一 request/native instance 仍在播放。
2. `isPlayingVideo()` 返回真后，同 native instance 的 `NATURAL_EOF` 在两次 owner 快照之间到达。实际 owner 合法清空 `observed`，保留匹配终态；`_matches_requested_playback()` 将它返回为假。

复现脚本加载真实 owner 策略、真实 owned_state 和原样 AST monitor 方法；Kodi/IPC/时钟及终态边界记录是明确替身。现状为 5 项中 3 个正控通过、2 个失败契约，0 harness 异常。

## 必须实现的行为

- 将当前活动实例、匹配终态、明确 superseded/cancel 和读取未知分开表达。采用枚举、结构化结果或等效清晰机制均可，避免再以一个布尔值同时表示这些状态。
- 一旦有新 request、boot/epoch、账号代际或明确取消证据，立即退休旧监控。旧异步任务、晚到 EOF 及晚到候选不能复活旧播放或续播。
- 一轮读取暂不可用时，暂停依赖权限的操作，在有界且有间隔的观察中等待新证据；不能从旧快照获得控制权，不能无限重试或忙循环。
- 对已经观测到本次 native instance 的匹配终态，进入已有不可变终态协调。终态读取与控制授权继续分离；读到历史终态不自动授予播放/续播权限。
- 保留原有 3 秒终态协调预算；标准路径的 EOF 20 秒绝对截止也保持不变。不要通过放宽时间窗掩盖失败。
- 后继提交仍由现有授权与一次消费机制决定。禁止把“无视频”“进度靠近尾部”“读取失败”直接解释成原生自然 EOF。
- 保持准确同版、原始画质和音轨、通用 CE 路径、手动字幕 Off 与账号隔离。不新增特定盒子型号或硬件内测准入。

## 测试要求

从真实 monitor 调用链覆盖以下契约，并保留明确换片和取消的正控。尽量复用本包脚本和现有测试夹具，不造只测试新枚举返回值、却不经过 monitor 的镜像测试。

| 场景 | 必须结果 |
| --- | --- |
| 暂不可用后恢复，request/instance 未变 | 不误标 superseded；恢复后继续观察；随后正常 EOF 能到达收尾 |
| EOF 在播放布尔检查与 owner 快照之间到达 | 读取到本次不可变 EOF；到达一次续播授权边界及停止收尾 |
| 无抖动的正常 EOF | 保持通过 |
| 明确新选择 | 旧监控结束，不触碰新 owner UI，不自动续播 |
| 明确取消 | 旧监控结束，晚到成功不能复活 |
| 读取持续不可用 | 有界结束或有界安全退让；不提交命令、不伪造 EOF、无忙循环 |

如真实接口重构导致本包 AST 适配层失效，可以适配夹具导入方式，但必须保留当前 5 项行为断言、明确 I/O 替身和正常正控；报告适配原因。不能通过跳过失败用例、替换产品 monitor、吞掉异常或只更新黄金值来通过。

## 本地执行命令

以下假定 `REPO` 指向候选仓库、`EVIDENCE` 指向可写证据目录、`REVIEW_SCRIPT` 指向本包脚本，三个变量均由执行者明确设置。

```bash
python "$REVIEW_SCRIPT" --repo "$REPO" --output "$EVIDENCE/native-monitor-fixed.json"
```

修复前预期退出 1（3 通过、2 失败、0 异常）；修复后预期退出 0（5 通过、0 失败、0 异常）。若需要适配接口，仍须提供新的真实 monitor 级等价回放。

继续运行已有相关回归，至少包括：

```bash
python -m pytest -q \
  tests/test_standard_session.py \
  tests/test_standard_product.py \
  tests/test_ce2012_continuation.py \
  tests/test_ce2014_four_three_release.py \
  --junitxml="$EVIDENCE/playback-regression.xml"
```

本组在审查 head 为 52 通过。完整总执行包如已列出原生 owner/终态相关 gate，也须执行；只有具体剩余风险或仓库门禁需要时再扩大测试集合。

## 交付要求

交付最小产品 diff、每项行为与对应测试的映射、修复前后 JSON/JUnit、源文件版本/哈希，以及一段明确区分“本地策略回放”“仓库原有实机记录”“本次是否实机验证”的说明。不得将本地替身回放写成设备认证。

没有额外用户授权时，本任务仅准备和验证可评审修改，不连接电视、部署服务、发布新安装包、写 GitHub 评论或合并 PR。
