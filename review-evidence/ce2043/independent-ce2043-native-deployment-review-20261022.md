# CE2043 原生部署边界与受监督音轨输入独立复审

结论：以下固定版本的本地部署准入审查通过，无新阻断。允许 root 按既有受控流程继续，
不等于已部署、实机 rollback 成功或 BT→云接力已验收。独审仅读源码/冻结制品和保存
回执；外部测试全部本地 fixture，无 SSH、systemctl、设备、云端或播放器动作。

## 固定审查输入

- tools/ce_native_update.py：`e53195a2de2aff909d6dd80749fbda843a7127d0a5c0c87b8cc433d171f1db8b`
- bobbi_core/runtime_paths.py：`1ea350ea8d49dad04771ab76a1152aa6394f376f529c3672eed417a010db227d`
- tools/ce_attended_player_action.py 修后：`25c973c75561153a5f80a2f91f834df17975a8ad23ef821e7af175e94f3f9070`

schema2043 固定最终 native ba0327、完整新 build-result 30e1e300、完整 verifier db04c3a3；
即刻前代是 8bb2，前代 build-result 固定 0c6069fe；原始 896 build/relink proof 保留
fa83d57a 链。完整 native 制品独审见 `independent-ce2042-native-schema-review-20261022.md`。

## 三层 provenance 不是 subset

独立实读三代冻结回执得到：896 inputs=269，8bb2 inputs=272，新 schema inputs=278。
正确关系严格为：

1. 固定 8bb2.baseline_inputs 等于固定 896.inputs。
2. 新 report.baseline_inputs 等于固定 8bb2.inputs，而不是跳回 896.inputs。
3. 新 inputs 严格等于 baseline_inputs 与 additional_inputs 的无重叠并集。

checked_build 对以上作字典精确相等比较，并在结构检查之前固定整个 report 字节 hash；
再核对前代路径、前代实际 binary、前代重链接 hash、前代未变标记、仅 JSONRPC.cpp
重编清单、完整 verifier pin 与 rpc_methods_exact=true。没有降为 subset 或允许任意
额外输入。初版实际 staged_files 的 BASELINE_INPUTS_CHANGED 是 root 保留的历史失败；
本独审不伪称已重放旧代码，当前实物三层正控已经通过。

独立新增 fixture 刻意令三代输入数为 2/3/4，避免作者早期 fixture 中前代/祖代相等而
漏掉真实边界。跳过即刻前代、改变/增加 baseline、前代 baseline 非精确、额外未列
输入、overlap、缺少 additional、错误 relink/重编 TU/前代 reference/未变标记、缺少
schema 验证等均拒绝。Fixture 的重新固定 hash 只用于触达结构检查，不修改真实 pins。

## 真实本地 staged_files 正控

使用实际冻结 new build-result 和 `ce2043-native-predecessor8bb2.json`，只调用本地
staged_files，不调用 CLI 或连接 transport，返回恰好三份 bytes：

| 文件 | 字节数 | SHA256 |
| --- | ---: | --- |
| kodi.bin | 23728864 | ba03279546193a8a5e6299b257e1321833dbf5b7b3ecc087ba67ed7dd2eb1991 |
| launch.py | 1728 | 8ef01e1eb6882f550e229b2791e285459fcfecafe0a13a0bfb4813afa976f42d |
| next.conf | 240 | 0501d0f0c6dbdc71c0ebcaa0082a3f23aac696a92d6a913a352fbda850127191 |

launcher 是已固定 8bb2 launcher 原字节，仅一次替换 FIX native hash；新 conf 仅指向
新的 `/storage/.local/share/bobbi-native/2026102043`。旧 2038 binary/launcher/conf 和
rollback 路径保持独立；没有覆盖前代或固件。真实 layout 的运行实例数量/hash、前代
binary、launcher hash/source、drop-in 任一变坏都会拒绝进入 transport。

原 apply/rollback/reapply 事务未为新 profile 改写。初次 apply 必须先有完整 CE2043
entry generation：phase complete、host_pending 空、high_watermark 精确等于 sequence、
有效 tx；明确拒绝 CE2042 或提前漂移到 CE2044，且在服务变更前拒绝。另仍检查 idle、
实际运行前代 hash、旧文件和 conf，安装 core 必须识别 new native；替换前再次检查
program generation。rollback 保留 receipt 历史与前代文件，不降低 entry generation。

runtime_paths 仅增加已审 ba0327 精确 hash，保留既有 subtitle ABI 根；未知 hash 或无
native contract 仍不获 ABI。它不是允许任意 native，也不改变字幕目录策略。

## audio-index：ACK 与实读恢复严格分开

本次代码阅读发现修前（hash f1ed0c56）SetAudioStream 获 ACK 后仅 same-instance 后读
成功就返回 observed_after_action，未比较目标音轨。这个状态只证明有后观察，不能
拿它称指定音轨已恢复。该问题由 root 修复；独审没有伪造修前 pytest 失败回执。

当前回执对 after.currentaudiostream.index 不等目标或缺失返回
action_acknowledged_pending，CLI 非零，不重发。独立执行真实 remote 逻辑，但移除
所有 RPC/import IO、用纯本地响应验证：正确 index、延迟未切换、缺失 after index、
中途 native 变化、回执丢失、重复 index、recheck 变化，以及 pending 的 CLI 退出码。
仍明确 atomic_instance_bound=false、attended_human_equivalent_input；before/recheck/after
不是 CAS，也不能给生产自动接力使用。Root 旧现场恢复结论需以其真实 after 的 jpn0
为依据，不以 ACK 代替；独审不操作该现场。

## 回执

- `test_independent_ce2043_native_deployment.py`：25 passed，
  `independent-ce2043-native-deployment-v1.xml`。
- 另 `test_independent_ce2043_attended_audio.py` 为 8 项独立用例。
- 两份独立用例与作者 native schema/successor/handoff/reapply/maintenance safety/
  entry generation、attended audio/stop 回归合跑 144 passed：
  `independent-ce2043-deploy-audio-v2.xml`。

未替 root 执行部署或验收设备。部署后仍应核实际运行映像 hash、introspect 的完整
BobiControl schema，以及真实同源 capture→stop→child AV/restored 的偏好恢复回执。
