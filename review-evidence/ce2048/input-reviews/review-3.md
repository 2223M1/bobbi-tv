# Bobbi TV CE2047 独立复审报告

日期：2026-10-22。对象：用户指定的 [CE2047 审查入口](https://github.com/2223M1/bobbi-tv/blob/1ce3ec9cb779be5fc3effcfe56d0422e3c5039fd/docs/CE2047-WEB-REVIEW.md)。

## 一、判断

**本轮整改有效，但 CE2047 仍应继续整改，暂不结案。** 上轮隐藏选源错误、BT HTTP 状态丢失、像素空读误判已经修到实际执行路径。main 的新 CI 通过，本次独立重跑也得到相同通过总数。与此同时，新增读重试与新增保活线程分别暴露了取消和退出边界问题；115 已确认失效资源的跨查询状态仍未闭环。

建议把 CE2047 作为下一轮开发、内测的固定起点。当前证据不支持“完整新作品播放已通过”“严格 UI 无闪动已通过”或稳定版结论。公开源码、允许分发与稳定认证是不同事项；本报告不会新增发布政策或设备门槛。

### 优先级与状态

| 编号 | 优先级 | 状态 | 本次独立结论 |
|---|---|---|---|
| R47-01 | P1 | 需修复 | 本地 Back 已置取消，但控制读取失败后恢复，BT 插件分支仍尝试一次成功移交。 |
| R47-02 | P2 | 新增缺陷，需修复 | 慢速持续 HTTP 响应可使手选保活线程在返回/确认后仍存活；`join(6)` 和 `Session.close()` 均不能证明其退出。 |
| R47-03 | P2 | 既存缺口，需收口 | 分享明确撤销后，新查询仍可能返回同一普通候选，缺少跨查询的已知失败状态。 |
| OPEN-ROLLBACK | P1 | 延续上轮，未关闭 | 缺少一份旧备份仍可能返回 `restored`，形成混合代际。整改范围保留，不自行增加校验任务。 |
| OPEN-ENTRY-AUDIT | P2 | 延续上轮，未关闭 | 现有入口审计未完整绑定外层 `default.py` 等成员；侧录不能补足该能力。整改范围保留。 |

P1 表示优先处理核心控制正确性；P2 表示可复现但触发或影响范围更窄。没有将未测设备行为、样本供数不足或文档已明确保留的限制包装为新源码故障。

## 二、固定版本与独立执行范围

| 对象 | 固定值 | 解释 |
|---|---|---|
| CE2045 对照 | `f6c9bd4e25199516451b128c7662f8ae54fedd66` | 本轮产品提交的直接父提交。 |
| CE2047 产品与证据 | `5d6a77d78a278984517f3e4af99c239054e9ba4a` | 本次源码审查及本地三套测试对象。 |
| CE2047 产品树 | `5a9d7663fb5f4612696d4645197a88af29fa6875` | 产品与证据提交的实际 Git tree。 |
| 当前审查入口 / CI 提交 | `1ce3ec9cb779be5fc3effcfe56d0422e3c5039fd` | 仅比产品提交多 `docs/CE2047-WEB-REVIEW.md`，22 行。 |
| 当前 CI | [39732748172](https://github.com/2223M1/bobbi-tv/actions/runs/39732748172) | main push，completed / success，2026-10-22 06:14:45–06:19:20 UTC。 |
| 公开 Release | [ce2045-main-f6c9bd4](https://github.com/2223M1/bobbi-tv/releases/tag/ce2045-main-f6c9bd4) | 仍是 CE2045，标记为 prerelease。 |

产品 SHA 本身没有独立 workflow run；真正的新 main CI 跑在其仅增加审查文档的子提交。已核对差异和 job 日志，因此可以用该 CI 支持 CE2047 产品代码测试结果，但记录中仍保留其真实 SHA，未借用 CE2045 的旧 CI。[提交比较](https://github.com/2223M1/bobbi-tv/compare/5d6a77d78a278984517f3e4af99c239054e9ba4a...1ce3ec9cb779be5fc3effcfe56d0422e3c5039fd)

本次实际完成：克隆固定源码；阅读改动及相关调用链；按仓库依赖独立运行三套测试；两次 source-check 构建与逐文件比较；真实本地 HTTP 慢响应反例；真实生产方法配 IO 替身的取消反例；临时签名包和真实 Installer 的回退反例；真实临时 SQLite 的失败重查反例；原始 UI 样本独立重算；核对当前 CI 原始日志与已有设备回执。未操作用户盒子、账号或远端仓库。

### 测试结果

| 套件 | 本次独立执行（Linux / Python 3.12.14） | 当前 GitHub CI（Python 3.11.17） |
|---|---:|---:|
| Primary | 3543 passed，6 skipped，1 xfailed | 3543 passed，6 skipped，1 xfailed |
| inherited Kodi harness，独立进程 | 1027 passed | 1027 passed |
| preparation regression，独立进程 | 254 passed | 254 passed |
| 合计 | **4824 passed / 6 skipped / 1 xfailed** | **4824 passed / 6 skipped / 1 xfailed** |
| 两次 source-check | 22 组件，63 文件一致 | 22 组件，63 文件一致 |

6 个 skip 分别为 5 项真实 Windows inherited-pipe API 测试和 1 项可选本地媒体/ffprobe 夹具；1 个 xfail 和 JUnit `record_property` 警告保持原状。维护者的 166 项专项与大套件重叠，未重复相加。审查反例单列，尤其回退的预期红态不混入 4824。

首轮沙箱禁止创建 socket：baseline 为 1026 passed / 1 failed，primary 出现同类环境错误后中止。已保留首轮日志；随后在允许本地 socket 的环境完整重跑 primary 和 baseline，采用上表的最终结果。没有把环境错误当产品缺陷，也没有静默删除不利记录。构建只验证 source-check 产物的一致性，不代表取得维护者签名安装包。

## 三、R47-01：本地取消在 IPC 恢复后仍被成功移交路径越过

### 可复现时序

1. 真实 `ResolverWindow.doModal()` 已接受本次选择，正在调用真实 `JacktookPLayer.run()`。
2. 播放器激活阶段第一次读取 snapshot 时触发 Back。真实 `onAction()` 设置 `user_cancelled=True` 和共享 `cancel_event`。
3. Back 中用于核对当前选择的三次读取都临时失败，因此不会写 `bobbi_cinema_cancel`。
4. 原播放器的读取随后恢复，`read_snapshot()` 返回仍未被服务取消的同一 request。
5. `_activate_playback_session()` 没有把本地取消作为拒绝继续的条件；BT plugin URL 分支继续进入 `play_video()`，最终调用一次 `setResolvedUrl(..., True, item)`。

本次回执在调用点同时记录 `local_cancel=true`、`user_cancelled=true`、`owner_cancelled=false`、取消属性为空、目标为 BT 插件。生产方法通过 AST 原样提取执行，GUI、IPC、可选跟踪功能和最终 Kodi 调度为明确的 IO 替身。

**同脚本前后对照已完成，且主审再次独立重放：**固定 CE2045 `f6c9bd4` 在相同注入时序下成功移交 0 次；固定 CE2047 `5d6a77d` 成功移交 1 次。使用完整合法的 BT 插件 query，输出提交来自各 checkout 的 `git rev-parse HEAD`。因此这一具体恢复时序属于本轮回归，而不是仅凭静态推测的新问题。回执分别为 `evidence/preav_local_cancel_root_ce2045_control.json` 和 `evidence/preav_local_cancel_root_ce2047.json`。

**因此确认的是“取消后仍尝试成功解析移交”，不宣称真实盒子已经开播、执行 BT add、产生重复播放或停止了别人的播放器。** 后置 monitor 是替身，本反例不模拟其后续收尾。

### 根因与落点

- [`resolver_window.py:143–150`](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/plugin.video.bobbi/lib/gui/resolver_window.py#L143-L150)：本地取消已发生，但远端取消提示取决于一次可成功的所有权观察。
- [`native_player.py:116–153`](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/plugin.video.bobbi/lib/native_player.py#L116-L153)：恢复读取后没有检查共享取消事件便激活会话。
- [`native_player.py:361–451`](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/plugin.video.bobbi/lib/native_player.py#L361-L451)：直接媒体会走带取消回调的 bind/claim；BT 插件移交分支缺少等价的最终本地取消判断。

### 建议

把共享取消事件作为“本请求停止产生新动作”的立即依据：在读重试恢复后、预留子请求前及最终插件成功移交前重新判断。保留 bounded snapshot 重试，保留 request/boot/epoch 的新鲜检查；不能通过删除恢复能力来回避反例。取消不是重试 `select/reserve_child/open` 的许可，也不授权对未知播放器实例执行 Stop。

现有 `tests/test_ce2046_preav.py` 覆盖了服务明确取消/替换和恢复后的 boot/epoch 变化；该覆盖不等于“本地用户已取消但取消消息尚未送达”的覆盖。需要补一个包含真实 `onAction` 和真实最终插件移交方法的回归。

## 四、R47-02：保活线程的实际退出没有被有界 join 保证

### 独立真实 IO 反例

本地 HTTP 服务在返回 200 后每 50 ms 发一个字节。只把首次保活调度从 5 秒加速至 0.01 秒；产品 HTTP 超时、`join(6)` 和生产 `Backend`/`Resolver` 保持原样。持续小字节使读取没有出现 2 秒无数据间隔，而 `iter_content(chunk_size=4096)` 尚未交出一块数据，循环中的 deadline/active 检查不能运行。

主审独立重放结果：Back 路径约 6.167 秒返回 `None`；确认路径约 6.164 秒报 `TORRENT_CONTROL_UNAVAILABLE`。两路在返回时保活线程均仍存活，随后 `backend.close()` 后也仍存活。每条路径只发出 1 次 `get`，没有 add、preload 或真实外部请求。测试最后主动结束响应并 join，未留下测试服务。

### 根因与影响

[`resolver.py:270–316`](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/resolver.py#L270-L316) 用 `done.set(); worker.join(6)` 等待；Back 分支在检查 `is_alive()` 之前返回，确认分支即使发现 alive 也只是抛错。

[`backend.py:134–184`](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/backend.py#L134-L184) 的总时限检查依赖 body iterator 交回控制；[`entry.py:164–170`](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/entry.py#L164-L170) 关闭 Session 也不能证明已占用的响应读取停止。

确认影响为取消/确认后留下超出调用方生命周期的线程和 IO，且本次取消需等待约 6 秒。没有证据表明这个线程直接持有平台全局维护 lease，因此不把它升格为已证实的全局更新死锁。

### 建议

为这一只读保活请求实现可中断且受总时限约束的读取，并在窗口返回时确认实际退出；只拥有和关闭本次请求的 IO。取消、superseded、异常和正常选择都走同一清理契约。单纯增加 join 时长、改成 daemon 或依赖 `Session.close()` 不能解决证据中的条件。

保持同一个 info-hash、原文件复查、一次 add、一次 preload 的约束；不持久化种子、不修改全局 TorrServer 超时、不重启服务。瞬时只读保活失败是否允许短暂恢复可另作有界策略讨论，不单列为已确认缺陷。

## 五、R47-03：失效分享只有撤销成功证明，没有跨查询失败状态

现有 Juku 修复正确撤销了旧 `verified` 证明；它并没有把“已确认失效”与“尚未验证”作为两个不同状态保留到新查询。QQdocs 的成功查询缓存还可能直接重放旧卡片。

本次无网络反例调用真实 catalogue `search/resolve` 与临时 SQLite，只替换远端 API、profile 和账号 IPC：

| 情形 | 实际观察 |
|---|---|
| QQdocs 搜索成功→取址 `share_revoked/4100010`→重查 | 同一张卡完整返回；新增上游搜索 0 次；成功缓存剩余约 21600 秒；没有失效字段。 |
| Juku 从未验证→取址撤销→重查 | 同卡返回，仍为未验证，没有失效字段。 |
| Juku 先有成功证明→取址撤销→重查 | 旧 `checked_at` 正确清 0、verified 正确降 false；同卡仍返回，没有失效字段。 |

[`catalog.py:238–275`](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/script.module.bobbi.catalog/lib/bobbi_catalog/catalog.py#L238-L275) 与 [`319–322`](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/script.module.bobbi.catalog/lib/bobbi_catalog/catalog.py#L319-L322) 支持 QQdocs 路径；[`juku_catalog.py:561–635`](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/script.module.bobbi.core/lib/bobbi_core/juku_catalog.py#L561-L635) 与 [`756–775`](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/script.module.bobbi.core/lib/bobbi_core/juku_catalog.py#L756-L775) 支持 Juku 的证明降级边界。

复现中的 account_status 返回固定测试 scope，share_known_failures 返回空 denied；没有声称覆盖完整 host/Kodi UI 链路。源码显示该接口只撤销仍有成功证明的候选，清除证明后不会自动成为跨查询失败记忆。

维护者 Planetes 原始设备记录支持“share_revoked 后重查仍有同一 source_key”。原始 UI 只记“115 网盘”，不能据此认定其 provider 是 QQdocs 或 Juku，也不能断言仍显示已验证徽标。**六小时是 QQdocs 成功缓存默认 TTL 与离线观察，不是 Planetes 实机持续六小时的测量。**

建议复用 typed failure、账号 scope 和精确文件 tuple，为已知永久失败提供有界记忆。卡片可以保留，但应有明确失效状态，并退出默认推荐；用户可主动重试。新成功应撤销旧失败，账号切换和旧请求迟到结果不能污染新账号/新文件。网络超时、取消、登录失效不等于分享永久撤销；不得因修复自动换版本、降低清晰度或增加目录全量预检。

## 六、上轮关闭与保留结论

| 上轮/本轮整改点 | 本次判断 | 证据边界 |
|---|---|---|
| 隐藏选源窗口只写不可见 property | 可关闭该缺陷 | 已有 notification，并取消本窗口 pump/session；相关真实方法测试通过。 |
| BT HTTP 非 200 诊断丢失 | 可关闭该缺陷 | 状态码、operation、method、substage、request/stage 时间闭合；错误字段白名单避免 URL/body 泄漏。 |
| 空/短 framebuffer 读取产生哈希并可能误判 | 可关闭该缺陷 | 有效性、字节数、几何和 pan 已检查；任何无效样本不能通过严格判断。 |
| pre-AV 单次断连被误判 superseded | 普通恢复路径有效，取消闭环仍未全关闭 | 远端取消/替换、boot/epoch 变化有测试；R47-01 是新增明确边界。 |
| 长时间人工选文件导致种子 idle 过期 | 正常等待路径改善，生命周期仍需 R47-02 | 已有同一 hash 等待约 60 秒后进入 preload 的设备记录；未支持完整 BT 播放。 |
| current-delivery 发布状态混淆 | 已改善 | 公开 CE2045 与本地已装 CE2047 分开；后续入口说明推送时间序列。 |
| 回退缺备份 | 未关闭，继续记录 P1 | 本次真实 Installer 夹具 1 pass / 1 fail；见下一节。 |
| 完整外层入口成员绑定 | 未关闭，继续记录 P2 | 本次只验证历史控制包上的现有 audit 能力，未取得 CE2047 包。 |

不要把已修的空读或旧成功证明撤销再次列为新问题。原报告“本地交付时尚未 push/无远端 CI”被后续入口明确限定了时间；本次直接读取了新 main CI，不将历史字样当成新缺陷。

### 两项旧完整性问题的独立复现

**回退：** 使用真实 Installer、临时签名夹具及假 Kodi host，安装 1.0.0，再升级 2.0.0，删除 `resource.uisounds.bobbi-modern` 的旧备份，执行 rollback。未抛异常，返回 `phase=restored`、`blocked=false`；11 组件回到旧版，声音组件仍为新版。用户历史未变化。[现有 `_restore()`](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_installer.py#L76-L113)

**入口审计：** 用 CE2047 的 audit 代码，对仓库已有 CE2024 真实签名包作控制。原包通过；只给临时副本外层 `default.py` 追加无害注释后，审计仍通过，外层与内层签名入口的 default.py 已不同。未执行入口、未篡改实际发布包。[现有审计覆盖](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/tools/audit_ce_entry.py#L20-L48)

这两项是已有问题延续，相关实现与 CE2045 没有变化。文档记载用户禁止新增校验且范围未澄清；本次未取得更具体原话，因此不自行将其写为已授权增加校验的任务，也不把未修状态改成关闭。没有为了这两项停止其他已授权工作。

## 七、设备、视觉、安装包的证据应如何表述

本轮没有独立登录或操作真实盒子。以下是对维护者已提交原始记录的复核。

| 项目 | 记录支持 | 不能由这些记录推出 |
|---|---|---|
| Made in Abyss 长手选 | 同 hash、13 文件，约 60 秒选择后进入 Torrent preload | AV_STARTED、完整 BT 观看。 |
| Paterson，新电影 | 选择/定位完成，缓冲约 8.9 MB / 32.2 MB 后超时，有可见反馈 | 新电影播放通过；所有电影都不能播。 |
| Planetes，新番 | 分享撤销 `4100010`，原生 ERROR，无 AV；重查同卡 | 115 整体不可用；某一 provider 必然是实机来源。 |
| CE2046 像素 | 基线 10/10，有效增量 50/51，1 MOVING，0 有效变化 | 严格无闪动 PASS。 |
| CE2047 像素 | 基线 10/10，有效增量 47/48，1 MOVING，0 有效变化 | 严格无闪动 PASS。 |
| 账号 smoke | 已装窗口、初始取消焦点、合成 QR、取消处理函数 | 真实扫码授权、轮询、过期、换账号或 Yatse 全链路。 |
| 收尾状态 | 序列 2026102047、事务 complete、无 host_pending、空闲首页、服务 active、NRestarts=0 | 安装文件逐字节身份、完整观看或全部退出时序。 |

两个像素回执的严格结果均为 `INCONCLUSIVE`、整体 `passed=false`，已独立重算吻合。静态采样区只是第一卡的质量/类型文字；保留相同有效哈希说明该局部有效样本未变，不等于全屏、字幕或视频平面的稳定证明。继续采样应保留无效帧及原因，不能删帧后宣称整轮通过。

CE2047 完整入口侧录大小为 95,968,803 字节、SHA256 `463b301067390e73176f058ea96bf0cf3b775f7ea66e63f1babe79ebf011d026`，索引和侧录一致。但完整 ZIP 仅在维护者本地，本次没有对这份实际字节做独立下载、验签、干净安装或升级/回退实验。产品 report 已坦诚标注这一边界。

设备来源：[整改报告](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/docs/CE2047-REMEDIATION-20261022.md)、[CE2047 回执](https://github.com/2223M1/bobbi-tv/tree/5d6a77d78a278984517f3e4af99c239054e9ba4a/review-evidence/ce2047)、[CE2047 UI 原始结果](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/review-evidence/bobbi-ui-smoke-1792648658714124400/result.json)。

## 八、下一轮执行建议

先修 R47-01 的本地取消终态，再修 R47-02 的实际线程排空。这两项都围绕已经加入 CE2047 的代码做窄修。随后处理 R47-03：把真实已知失败带到新查询，维持未知状态与瞬时网络失败的可恢复性。相互独立的任务分别提交，减少回归定位成本。

每项先重放本包红态，再按 `ACCEPTANCE.zh-CN.md` 形成正常回归断言；只读操作的恢复不得变成重复执行播放命令。产品发生变化后更新相关版本与显式 inventory，再运行仓库既有三进程测试和 source-check。仅修测试或文档时，不虚构新的产品版本。

继续原定的新电影/新番实播，明确记录选定的作品/季集/版本、实际文件、AV_STARTED、进度与退出。弱供数就保留弱供数的失败；分享撤销就保留真实错误并验证新查询展示。不能用另一部片、另一集、降画质或静默切源来替代原场景的通过。

完整观看、BT→115 完整接力、长期字幕等延期范围保持延期。更新交付记录时分别填写源码提交、测试/证据提交、实际包摘要、设备已装序列、公开 Release 与稳定状态；新一轮报告继续保留所有失败、取消、INCONCLUSIVE 和未覆盖项。

本包提供的是可执行整改范围和已运行证据，不是产品补丁或自动发布授权。
