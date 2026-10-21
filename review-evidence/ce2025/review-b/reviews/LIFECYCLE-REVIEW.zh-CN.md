# CE2024 生命周期与 GUI fence 独立审查

## 结论

F01 的受管服务恢复和 CE2024 新 GUI fence 确有实质代码修复；本轮独立运行相关窄集 **32 passed**。标准播放器的下一集、字幕、历史写入及 Host 的关闭失败重试，比前版有明确改善。

**G01 只能部分关闭。发现一个可独立复现的 P2：启用渐进交付时，ShareStream 的独立 producer 在上游响应头尚未收完时仍可能存活，而 Host 已报告关闭完成并释放 runtime OS 租约。** 该缺陷是前版已有代码中的遗漏，本次关闭协作修复没有覆盖到它。它不适用于缺省 block 模式，也不能据此归因设备上的 4K 起播失败。

本次只审查和执行本机测试；未重新连接设备、执行安装、回退、试播、推送、合并或发表评论。

## 固定身份及验证材料

| 项目 | 固定值 |
| --- | --- |
| 审查 head | c4e0baca6acefa58f031979bff71e7cd1028efdf |
| Git tree | bb4256d63465fefb9c5820f3ce1ec9cca33ff546 |
| 实际产品提交 | d2fffa570fe59b90cd1d33499efcf7c6684b2647 |
| 上轮比较基线 | b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2 |
| 实际入口 | script.bobbi.start-0.2.15-ce2024.zip |
| 入口 SHA-256 | cb355eb2a80b3974e985a9bc404fb74a8be1c98ab1319d30e4399eb503c06e9c |
| 内嵌完整包 SHA-256 | d53bc3b6ad0c4dc905a831d1906575a7c53ad15c0e6a6d6d7b12188e0d33c096 |

已对本领域 13 个关键产品文件执行实际入口 ZIP → 内嵌完整包 → 组件 ZIP → 本地审查源文件 → 固定 Git tree blob 的逐字节核对，全部相等。包括 share_stream、host、runtime、instance_lock、ce_install_ui、ce_installer、stop_monitor、standard_session、standard_playback、portable_runtime、background_service、transport_preferences 和 setup/default.py。见 `domain-package-map.json`。因此本报告的新复现没有落到旧源码或另一个本地修正版上。

## CE2024-LC01 / P2：渐进交付的独立 producer 未纳入完整停机屏障

### 定位

主要位置：[share_stream.py 862–870](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/share_stream.py#L862-L870)。HTTP handler 清理时调用 `worker.join(15)`，超时后没有检查线程仍存活，也没有把这个 producer 继续交给服务级关闭流程所有。

关联位置：[ShareStream.close 530–543](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/share_stream.py#L530-L543) 只等待 HTTP server 线程及服务监听线程；[Host.close 397–416](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.platform/lib/bobbi_platform/host.py#L397-L416) 随后把关闭标记为完成并关闭 OS lease。HTTP 子请求线程已经退出，不代表该线程另行创建的 `share-stream-prefix` 已退出。

### 触发条件

1. 用户在真实设置入口选择「渐进交付」，下次 Kodi 启动后生效；入口见 [setup/default.py 196–204](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.bobbi.setup/default.py#L196-L204)。配置为 `share-transport.json` 中 schema=1、mode=progressive；配置缺失时明确采用 block，见 [transport_preferences.py 6–17](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.platform/lib/bobbi_platform/transport_preferences.py#L6-L17)。[Host 89–103](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.platform/lib/bobbi_platform/host.py#L89-L103) 将该模式传给实际 ShareStream。
2. 一个已获准的上游读取正在等待 HTTP 响应头。上游持续小幅发送头部字节，因此连接没有触发 10 秒的单次 socket-read 超时，却可以让整个响应头阶段超过 15 秒。
3. 下游取消或服务关闭时，producer 尚未从 `requests.Session.get(..., stream=True, timeout=(3.05,10))` 返回。该读取在 [share_stream.py 911–915](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/share_stream.py#L911-L915)；body 的 read1 取消改进尚无法执行，因为尚未取得 response。

这是普通持续慢响应头，不依赖畸形 HTTP、假时钟、缩短 join、伪造 transport 或 DNS monkeypatch。

### 本轮实际复现

复现使用真实本机上游/下游 HTTP、实际 Host、Runtime、ShareStream、InstanceLock 和交付 ZIP 内原版 Python 依赖。上游在 HTTP 响应头尚未结束时，每 50 ms 发送一个头字段值字节；本测试实际使用 206 且大小为 1 字节。所有对外地址都是 127.0.0.1；没有真实账号、CDN、设备操作。

原包中 requests=2.31.0、urllib3=2.2.3；certifi/chardet/idna 也从相同入口包提取。五个组件 ZIP 的 SHA-256 与提取记录见 `actual-dependencies-provenance.json`。测试全过程沿用真实 15 秒 join。

| 场景 | 关闭期间观察 | 替代进程能否获得租约 | 结论 |
| --- | --- | --- | --- |
| progressive，约 0.3 秒后放行响应头 | 0.312 秒时关闭完成，旧 producer 已退出 | 可以 | 正控通过，无重叠 |
| progressive，响应头持续未结束 | 15.098 秒时关闭完成，`_shutdown_complete=True`，旧 producer 仍活着 | 可以 | **所有权屏障失败** |
| block，相同慢响应头 | 16.801 秒时关闭仍未返回 | 不可以 | 阴性对照通过，放行后正常退出 |

原包依赖三控结果：**2 passed / 1 failed**，失败项就是生命周期不变量断言。`progressive-shutdown.log`、`progressive-shutdown.xml` 和三份场景 JSON 保存本轮原始结果。先前使用 review-deps 的 requests=2.34.2、urllib3=2.8.0 得到同样结果，存于 `newer-dependency-first-run/`；它是同一三控的补充确认，不重复累计为新的产品测试项。

慢头的原包依赖时间序列，以场景开始计：0.028907 秒开始响应头；0.030294 秒调用 Host.close；0.331132 秒替代租约仍被拒绝；15.126317 秒 Host.close 返回；15.127753 秒替代租约获得成功；15.127762 秒测试才放行头部；15.130346 秒旧 producer 排空。也就是先拿到了新租约，之后旧上游工作才真正结束。所有测试线程最后均被清理，没有遗留测试服务。

### 影响与限定

实证证明的是 **Host 级别“全部已接纳工作排空后才能释放 OS lease”的约束被破坏**。这会让服务恢复/替换流程取得错误的安静信号；只靠 producer semaphore 保留一个配额并不能维持跨代所有权。

本测试没有执行 Kodi 中的实际文件替换，不能把结果扩大为已证明用户数据库损坏、实际覆盖了运行代码或设备上已发生同一竞态。安装器另有 15 秒拒绝边界，Kodi 插件管理也有自己的停机行为；这些必须在修复后的设备验收中继续验证。本次未取得设备当前 share-transport 模式的独立凭据，也没有证据将此问题关联到本轮真实 4K 起播卡顿。

### 最小修复及验收

建议由 ShareStream 管理独立 producer 的完整清单：创建前登记，完成时发布状态，确认线程真正结束后才清理可 join 的句柄；关闭先停止接纳、撤销请求，排空 HTTP handler 后，仍须等待全部已登记 producer 真正结束，或明确失败并让 Host 保留 OS lease。不要只把 `join(15)` 改成另一个数字，也不要把 semaphore 配额等同于所有权。加入 registry 时，不要持有 producer 退出所需的锁等待它。

正常客户端断开场景可以保留请求级有界等待；服务级关闭必须继续拥有未退出 producer。应保留安装器独立的 15 秒拒绝规则，待排空完成再允许恢复。不能通过加长全局超时、禁用断言或声称默认 block 就已修复所有模式来关闭本项。

验收至少包括本报告三控；再加“下游早已断开、原 handler 已退出后才关闭 Host”的 producer 仍受追踪场景，以及关闭异常重试、并发停止接纳场景。正确结果是：只要任意旧 producer 仍活着，替代 InstanceLock 必须取得失败；producer 排空后方可取得成功。

## F01 与 G01 的关闭账本

| 项目 | 本轮独立判断 | 依据及边界 |
| --- | --- | --- |
| F01 裸路径 RunScript 恢复服务 | 源码与现有窄集可关闭 | [ce_install_ui.py 210–249](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py#L210-L249) 在持有临时 OS lease 时确认关闭 provider，随后通过 Kodi 受管 enable 启动，并等真实 owner snapshot；不是 enabled 标志即成功。 |
| 协作 quiesce 顺序 | 窄集通过 | [ce_install_ui.py 112–161](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py#L112-L161) 先要求 owner 判断 idle，等待 OS lease，再调用 Kodi disable；ACK 不是排空证明。 |
| G01 standard next/subtitle/history | 已修复且窄集通过 | StandardSession/StandardPlayback/HistoryWriter 真实排空、停止接纳；Host 统一拥有最后 lease；注入后续 close 错误仍继续排其他消费者、失败保留 lease、允许重试。 |
| G01 全部已接纳消费者 | **仍开放 CE2024-LC01** | 独立渐进 producer 不在现有 service 全量排空范围；上面三控可复现。 |
| StopMonitor 的本地停止 | 实现与窄集通过 | 辅助服务等待最多切分为 0.1 秒；本地停止可唤醒长等待；避免把 Kodi 的 waitForAbort(0) 当成非阻塞轮询。 |

`test_ce2024_gui_fence.py`、`test_ce2020_cooperative_stop.py`、`test_ce2015_shutdown.py`、`test_ce2012_recovery_ui.py` 本轮合计 **32 passed in 8.70s**。首次受限沙箱禁止创建 loopback socket，结果是 16 passed / 16 PermissionError；原始日志保留为 `domain-tests.log`，不能据此判产品失败。自动审核允许本地 loopback 后，同一集完整通过，见 `domain-tests-permitted.log/xml`。

## CE2024 GUI fence：机制成立，实机成绩仍按原始回执记账

[ce_install_ui.refresh 51–69](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py#L51-L69) 先异步排队 UpdateLocalAddons，再在相同队列追加独一属性标记；通过 Monitor.waitForAbort(.05) 让出 Python 锁等待，15 秒未见标记或取消均拒绝完成。新 UUID 可隔离上一次迟到标记。依赖安装同样异步，但用实际版本及 enabled 回读确认。

独立读取 Kodi 官方 21.3-Omega 源码，确认这套推理有实现依据：

- [ModuleXbmc.cpp 90–123](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/legacy/ModuleXbmc.cpp#L90-L123)：同步调用 SendMsg，异步调用 PostMsg；该 executebuiltin 函数内没有 DelayedCallGuard。
- [ApplicationMessenger.cpp 201–225](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/messaging/ApplicationMessenger.cpp#L201-L225)：队列按 front/pop 取消息并完成 ProcessMessage。
- [AddonBuiltins.cpp 382–386](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/builtins/AddonBuiltins.cpp#L382-L386) 与 [AddonManager.cpp 702–737](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/addons/AddonManager.cpp#L702-L737)：UpdateLocalAddons 的 FindAddons 在返回前同步扫描、写入安装集合并刷新缓存；不是只启动一个另行登记的后台 job。因此紧随其后的 fence 在该路径上有完成含义。
- [Monitor.cpp 39–59](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/legacy/Monitor.cpp#L39-L59) 使用 DelayedCallGuard；[Python LanguageHook 43–52](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/python/LanguageHook.cpp#L43-L52) 明确 releaseGil/acquireGil。

上述文件的 Git blob 身份和 URL 留存在 `kodi-source-provenance.json`。这证明已报告锁反转路径的修复方向合理，不是所有设备/fork/GUI 模态组合的通用认证。

已独立取回两条 CE2023 native stack，均能见到 LanguageInvoker 停在 executebuiltin→SendMsg；后一条还包含 ScriptInvocationManager::Process 的主线程栈内符号。多处 backtrace 本身不完整，故不把原始栈夸大为所有锁持有关系的完备证明。文件保存在 `device/review-evidence/ce2023/`，Git blob 与当前固定 tree 一致。

## 设备回执：历史核对与本轮执行严格分开

下列是本轮从固定 head 独立下载并校验 Git blob 的**历史交付回执**；本审查没有重新执行这些设备操作。

| 原始回执 | 可支持的事实 | 不支持的扩张 |
| --- | --- | --- |
| ce-managed-recovery-1792551122840993800.json | cooperative_stop=true，3 cycles，恢复前后 owner boot_id 变化，enabled vector/skin restored，passed=true | 不等于 CE2024 完整程序安装后真实 rollback 循环；不覆盖所有慢任务故障。 |
| ce-managed-recovery-1792550770569415500.json | 旧 StopScript 夹具错误 OLD_SERVICE_DID_NOT_STOP，trial_exit_code=1，恢复现场成功 | 不可计作成功；后面的协作方案成功不抹去旧失败。 |
| entry-device-choose-1792550723819640700.json | sequence/high_watermark=2026102024，phase=complete | 不单独证明 Kodi ZIP 浏览器导入全过程。 |
| installed-files-1792551231636875800.json | 回执声明自有文件1143项 matched=true/mismatches=[] | 本审查没有重新从设备读取1143文件；原始回执是汇总记录，不是本轮逐文件设备哈希表。 |
| device-final-idle.json | 空 player 列表、首页、安装 complete、关键版本0.2.15/0.1.18/0.1.17/0.1.16 | 另一维护 updater 的 state.json 仍2026102021，回执也如实保留；不是可任意手改的同一 journal。 |
| bobbi-ui-smoke-1792551057134188800/result.json | 真实安装 UI、假二维码/合成卡片、无登录交换或播放；passed=true | 不是账号登录认证、自然 EOF实播或视频平面认证。 |
| bobbi-ui-smoke-1792550777540431100/result.json | 外层exit_code=0但内层passed=false/error=UI_SMOKE_TIMEOUT | 必须计失败；不能拿transport成功码掩盖业务失败。 |

CE2024-DELIVERY 对热态 UI 失败、完整安装后回退、Kodi ZIP 导入、长时与整集同版续播未认证已作明确保留。建议下一轮把这些作为单独设备验收行，保留输入代次、动作、前后 journal、owner/lease、账号与历史不变证据；不要用已有 UI 假数据回执或 CE2023 失败事务恢复去替代。

## 复现及修复交接

见 `CODEX-LIFECYCLE.md` 的最小执行任务及命令。交付测试支持 BOBBI_REVIEW_ROOT 指向产品 checkout，BOBBI_REVIEW_OUTPUT 指向场景 JSON 输出目录。此配置改动仅替换路径，不改变本轮三控断言或产品逻辑。测试运行需要 pytest 以及本地 loopback socket 权限；没有外部网络要求。
