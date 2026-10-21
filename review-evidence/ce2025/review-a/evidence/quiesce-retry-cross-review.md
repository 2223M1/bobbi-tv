# CE2024 维护重试：独立复核

冻结版本：`2223M1/bobbi-tv@c4e0baca6acefa58f031979bff71e7cd1028efdf`。本复核只读既有源码与 `source_closure/quiesce-retry-probe.json`，未运行整套测试、未访问设备、未修改产品仓库。

## 结论

**问题成立，建议 P1，范围为安装/恢复异常路径的停止顺序失守。** 首次协作停止已经开始、runtime marker 已删除，但旧 owner 仍在排空并持有 OS lease 时，首次 `quiesce()` 的等待可能超时。`Installer.apply()` 会自动调用第二次 `quiesce()`；第二次因 marker 不存在，跳过协作路径，先同步调用 Kodi 的 disable，再等待同一把仍被旧 owner 持有的锁。

这不是用户必须自行连续点击两次才能到达的路径：一次正常 `Installer.apply()` 的异常处理即可触发。建议在下一次维护真机验收前修复，因为它绕回代码明确要避免的“工作尚未排空就由 Kodi 停服务”的顺序。**现有材料证明的是此顺序与持锁时 disable 的可达性，不是已在 CE2024 真机上复现永久死锁、文件损坏或观看记录丢失。**

P1 的依据是主要安装/维护链中错误处理本应保护的失败边界被破坏，而且 disable 使用同步 Kodi RPC，15 秒的 lease 截止时间不能约束该 RPC 自身的阻塞时间。不能将其描述成所有安装都会失败，也不能把尚未复现的下游死锁写成既成事实。

## 精确到达条件

1. 已安装 provider 仍为 enabled，且起始无播放；协作协议返回 `quiesce_protocol=1` 并接受停止。
2. `Host.close()` 关闭 Runtime 后，后续 playback/history/subtitle/辅助线程或其他消费者仍需排空；这些 drain 没有统一的“小于 15 秒”完成保证。也可能某个 close 失败而故意保留 lease。
3. Runtime marker 已被删除，但旧 owner 的 lease 在首次 installer 等待截止后仍被持有。
4. 首次 `quiesce()` 抛出 `CINEMA_SERVICE_NOT_STOPPED`。`Installer.apply()` 捕获并写入 `restoring`，随即调用第二次 `quiesce()`。第二次仍无活动播放、provider enabled，因 marker 已无而直接到 disable。

源码说明：

| 证据 | 冻结 SHA 下的路径与行号 | 含义 |
|---|---|---|
| 真正的自动第二次调用 | `addons/script.module.bobbi.platform/lib/bobbi_platform/ce_installer.py:180–202` | 首次调用在 try 内；任何 `BaseException` 都进入写 `restoring` 后的第二次调用。 |
| marker 提前于整体 host 关闭消失 | `addons/script.module.bobbi.platform/lib/bobbi_platform/runtime.py:151–177` | Runtime 排空自身 HTTP 请求后，删除自身 token 对应 marker；`release_lease=False` 只阻止释放 lease，不阻止删 marker。 |
| marker 消失后仍有排空工作 | `addons/script.module.bobbi.platform/lib/bobbi_platform/host.py:393–416` | 先 `runtime.close(release_lease=False)`，后 playback、图片、准备、stream、engine 与 worker join；失败保留 lease，全部成功才释放。 |
| 分支与超时 | `addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py:112–161` | 只有 marker 存在且协议被识别时才先等 lease；其他路径在 133–135 行先 disable，139 行才等 lease；超时抛错。 |
| disable 自身不受 lease 循环截止控制 | `addons/script.module.bobbi.platform/lib/bobbi_platform/kodi.py:5–12` | `rpc()` 同步调用 `xbmc.executeJSONRPC`；没有与 `until` 相连的取消/超时。 |
| 后续等待没有统一 15 秒完成保证 | `addons/plugin.video.bobbi/lib/services/standard_playback.py:40–43,294–315`；`addons/plugin.video.bobbi/lib/services/background_service.py:308–329` | 接受的 history/subtitle/辅助工作必须 join；这些 join 本身不带 15 秒完成保证。 |

Runtime 自己的 HTTP drain 发生在 marker 删除之前，因此不能笼统写“所有 Runtime 请求在 marker 删除以后才排空”。本问题对应的是 Runtime 自身 drain 之后仍在进行的 Host 消费者 drain，或关闭失败保留 lease。即使 marker 未删、但停止过程中的 status 已不可达，代码也会走 legacy fallback；当前复现不需要依赖这个更宽泛的变体。

## 复现是否省略了足以使结论无效的保护

未发现能阻止该次 disable 的现有保护。既有 probe 使用实际 `KodiHost.quiesce()` 与实际 `InstanceLock`，fake clock 仅加速两个 15 秒等待；fake `runtime.call` 的“接受后删除 marker，同时 owner 仍持 lease”与以上真实关闭顺序相容。它省略了真 Runtime/Host 的线程执行与 Kodi manager 锁，因此**不能据该 probe 宣称真机卡死已发生**，但不会推翻分支和调用顺序结论。

已检查且仍然有效的保护应在报告中保留：

- `ce_installer.py:180` 的 `staged/restoring` gate 阻止新入口运行；它不会使已经接收的后台工作瞬间完成，也不拦截 `SetAddonEnabled`。
- `installation.lock` 串行化安装事务；它不是 runtime owner 的替换 lease。
- `_acquire_runtime_lease()` 在获取失败后没有记录“已持锁”；所以第二次不会错误地因 `_runtime_lease` 存在而成功。
- `ce_install_ui.py:139` 的最终 lease 等待与 `ce_installer.py:182–190` 的调用顺序仍阻止此情形直接进入程序文件替换。**不能把本发现写成已绕过替换锁。**
- 如果第二次也超时，`_restore()` 尚未执行，journal 保持 `restoring`；后续需要恢复流程。这是可见恢复负担，但不是已确认不可恢复。
- `can_quiesce()` 检查无播放，不能证明 history、字幕、目录或辅助线程已经完成。

现有 `tests/test_ce2020_cooperative_stop.py:12–59` 证明快速排空时先取得 lease 再 disable；它在 3 秒内释放慢 close，不覆盖首次等待超时后的自动第二次调用。`tests/test_ce2015_shutdown.py` 验证关闭失败时保留 lease，也未验证之后 installer 的 disable 顺序。

## 修复方向与最小验收

需要保留协作 owner 的“已接受停止、仍在排空”身份，不能在 marker 消失或 status 临时失败后把同一 owner 降级为 legacy 然后强制停服务。最小修复可在同一 KodiHost 上记住接受状态，使重试在 disable 前继续等待 lease；完整修复还应覆盖入口进程重开/恢复时的同一状态。另一个方向是持久的 draining 标识或延后注册清理，但**只延后删 marker 不够**：当前 status 失败同样会进入 fallback。

不能简单把“先等 lease”塞到所有 legacy 路径：真正旧版 owner 可能只有 Kodi disable 才会退出，会产生新的兼容性回归。修复需明确区分活跃旧 owner、现代 owner 正在 drain、死注册，保留既有 legacy 升级通道。

建议加一个有针对性的回归：让真实 `Installer.apply()` 首次协作停止后进入“marker 已无、lease 仍持有”的阶段，并使首次等待超时；验证自动异常路径和用户后续恢复都不在旧 owner 释放 lease 前发送 disable。释放实际 OS lease 后再确认恢复能完成；另保留正常协作停止与真正旧版服务的测试。无需重跑与此问题无关的整套用例来证明这个分支。

## 证据绑定与本地文件差异

`source_closure/source` 的四个关键文件均已计算 Git blob SHA1，与完整冻结 tree 相等：

| 文件 | Git blob SHA1 |
|---|---|
| `ce_install_ui.py` | `41e5b82b4b628f7b7bcfa3ab3097574058f03af7` |
| `ce_installer.py` | `53f1c08afeb8d4cc552203a10eb525e03ade6773` |
| `host.py` | `be53fd6d68f2a5d227a17beec72a437ded8c2de8` |
| `runtime.py` | `80a37814b13d95642744a8ed3b913d77168cd91d` |

`root-source` 对应文件仅在末尾额外多一个空行，逻辑与引用行号不变；不要把该本地导出副本的原始字节 hash 当成 Git 原始文件的 hash。

## 安全入口 builder 诊断脚本

同目录提供 `standalone-probe-entry.py`，显式 `--repo ROOT`。它只读给定源码，把 18 个必要实际源文件复制到 `TemporaryDirectory`，在临时目录内生成两组件夹具、测试公钥 trust、inventory、addon.xml 和签名包。临时 RSA 私钥只在内存，不保存生产密钥、不写给定 repo、不联系设备或网络；最终清理所有临时文件。

- 退出 0：无 LICENSE 的 focused build、真实 SignedBundle 校验、实际 audit 与独立解释器 bootstrap import 通过。
- 退出 1：精确复现缺少 LICENSE 导致的 builder `KeyError`，且有文档控制组通过。
- 退出 2：环境/接口缺失，或其他失败使这一 focused probe 无法给出结论。

已且仅以 `packaging_review/source` 单次验证该安全封装，结果写入 `standalone-probe-entry-result.json`，exit 0。两个控制组都通过。夹具 sequence 固定为 1，并明确不是生产 CE2024 sequence；该结果不替代 22 组件实际交付 ZIP 的字节校验或真机安装认证。
