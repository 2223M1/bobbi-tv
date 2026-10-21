# PR #3 安装、恢复与宿主生命周期独立审查

审查固定为 `2223M1/bobbi-tv`，base `ee65742bfcbaf08831f70306faed11bd1f8d6cc6`，head `c8de17ae9dabbe0f37753e1751b1d88107311316`（CE2014）。本分域确认 **1 项 P1：已 enabled 但宿主未运行的恢复分支使用裸路径 RunScript，失去 Kodi addon 身份及受管 service 生命周期**。另保留 1 项 P3 停机加固建议，不作为阻断 finding。

旧 R01、R02、R03 的原始反例已经通过本次固定源码复核。新的 P1 是 `ensure_running` 新增恢复分支的问题，不能写成旧安装门禁、进程残留 marker 或状态快照修复无效。

## 已完成的验证

| 范围 | 结果 | 证据 |
|---|---:|---|
| 当前适配的安装契约 | 10 / 10 通过 | `installer-contracts-head.json` |
| 现有关键安装与宿主测试 | 92 通过，0 失败，14.41 秒 | `focused-installer-tests.xml` |
| 新增 RunScript 生命周期反例 | 2 反例失败，2 正控通过 | `RESULT.json` |
| 标准 history worker 关闭诊断 | 1 诊断反例失败，1 正控通过；非阻断 | `standard-shutdown-head.json` |
| 同组原生 monitor 发现交叉复跑 | 2 反例失败，3 正控通过 | `native-monitor-crosscheck.json`，由播放分域单独计数 |

现有测试覆盖 `test_ce_general_installer.py`、`test_ce_install_recovery.py`、`test_ce2012_recovery_ui.py`、`test_runtime.py`、`test_runtime_host.py` 和 `test_ce2012_runtime_boundary.py`。这里没有把仓库全量 CI 数字算成本分域新跑的结果。

当前 10 项契约执行的是候选真实 installer、KodiHost、`service.py`、boot gate 和 Runtime；仅 Kodi IO、调度与等待边界受控。实际 `os._exit` 的残留注册恢复、活动 OS lease 排斥、未知 addon 状态中止快照、已启用后进程丢失、旧 restored 兼容以及未验证代次拒绝启动均通过。

## INSTALL-F01 — P1 — 恢复服务的身份与停止所有权丢失

**定位：** [`ce_install_ui.py` 195–198 行](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py#L195-L198)。停止调用链为同文件 89–123 行；启动路径经 `service.py` 到 `portable_runtime.main`。

**已复现前提：** Kodi 仍报告 provider 为 enabled，但此前 service 解释器已经退出，也没有实际 Runtime 持有 lease。`ensure_running` 的 owner snapshot 失败，随后取得临时 lease 并发送 `RunScript(special://home/addons/plugin.video.bobbi/service.py)`。

此命令没有建立正常 Kodi 服务调用的两个条件：

1. **原生分支缺少解释器 addon 身份。** Kodi 21.3 的 RunScript 对参数做 addon ID 查找；路径分支只把路径交给 ExecuteAsync，AddonPtr 为空。PythonInvoker 因而不设置 `__xbmcaddonid__`；LanguageHook 也不从目录补救。候选实际 `background_service` 导入链到 `jacktook/utils.py:11` 的裸 `xbmcaddon.Addon()` 后报错，恢复最终为 `CINEMA_SERVICE_NOT_READY`。相同真实导入链带正常 provider 身份时通过。
2. **标准分支没有受管 service handle。** 实际 Host/Runtime 可以就绪并响应 owner snapshot，但手动 RunScript 的 handle 不在 `CServiceAddonManager.m_services` 中。下一次真实 `KodiHost.quiesce` 禁用 addon 时，ServiceManager 只停止已登记的 service handle，不能找到手动启动的这一份。反例中 enabled 已为 false，手动宿主仍运行并持有 OS lease，最终返回 `CINEMA_SERVICE_NOT_STOPPED`。正常受管启动的标准宿主可以正常停机，是独立正控。

本结论限定于已经执行该 fallback 的情况。正常 managed enable 的正控通过；没有把所有普通安装写成必然失败，也没有把未实测的调度竞争追加成另一个缺陷。Kodi 重启或正确的受管重启可以改变条件，这不是“永久无法恢复”的结论。

### 证据及方法边界

`reproduce_install_lifecycle.py` 导入候选实际 Python 模块。原生导入使用隔离子进程，只替换 Kodi 扩展 API，未替换候选业务依赖。标准路径使用真实 Host、Runtime、loopback HTTP owner 请求和 OS 文件锁；Kodi 的 managed/unmanaged handle 行为由官方 C++ 源码约束的 IO 模型表示。它不是一台 Kodi/CE 实机，也不是硬件认证。

官方固定来源集中在 `PRIMARY-SOURCES.json`，保留 Kodi **21.3-Omega** tag、每个 Git blob SHA、行号和含义：

- [AddonBuiltins.cpp 224–285](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/builtins/AddonBuiltins.cpp#L224-L285)：路径不会生成 AddonPtr。
- [PythonInvoker.cpp 634–650](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/python/PythonInvoker.cpp#L634-L650)、[LanguageHook.cpp 119–138](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/python/LanguageHook.cpp#L119-L138)、[Addon.cpp 54–68](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/legacy/Addon.cpp#L54-L68)：缺少默认身份的实际拒绝链。
- [Service.cpp 69–130](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/addons/Service.cpp#L69-L130)：只有服务管理器启动路径登记、按登记 handle 停机。

仓库自己的 `tools/ce_standard_real_remote.py:23–26` 也对临时路径 RunScript 手动补过默认 addon ID。这是旁证；本发现不依赖这段注释，也不把同样补 ID 当作完整修复，因为它仍不能登记受管 service handle。

### 后续执行要求

恢复“已 enabled 但没有服务”的状态时，应使用 Kodi 支持的受管 service 生命周期，或实现同样明确、可停止且带退出确认的机制。最终方案必须同时解决身份、正确 service entrypoint、所有权登记和停止确认；简单把路径换成 `RunScript(addon_id)` 不保证执行 service extension，给 `Addon()` 填默认 ID 也只解决其中一半。

保留真实 owner readiness、服务 boot gate、稳定 runtime lock inode、enabled 向量 readback、恢复代次与 high-watermark 规则。增加真实 native import 身份检查，以及“恢复启动标准宿主 → 再次安装 quiesce”的闭环检查。当前新增 `test_enabled_without_host_restarts_actual_service_once` 的 builtin 替身一收到命令就宣布 ready，无法覆盖这两条真实边界。

## 旧 R01–R03 的关闭范围

| 原问题 | 当前证据与边界 |
|---|---|
| R01：activation pending 与实际 service 门禁错位 | 真实 `service.py` 允许已校验的 `activation_pending`；staged / switching / restoring 仍被拒绝；restored + host pending 保持旧 gate 兼容；正常激活与重入通过。新 F01 单独处理 fallback 的调用身份。 |
| R02：进程丢失后 runtime marker 卡死恢复 | Runtime 与安装器使用稳定 OS lease；lock 文件保留 inode，关闭只释放 fd。实际子进程退出后 marker 可安全清理；活动 owner 持 lease 时恢复被拒绝。HTTP、engine、catalog 工作收束也有现有通过测试。 |
| R03：RPC 查询失败被误记成 disabled | 当前 strict details/fallback 要求合法 enabled/version；查询与完整 inventory 都不确定时中止，不保存伪造 disabled 向量。恢复保留完整 enabled 向量，旧版本 restored 及 high-watermark 用例通过。 |

“ready”的实际含义是：loopback 请求能到当前已绑定 owner，并得到合法 snapshot；它比单看 enabled 或 runtime.json 强。它不证明所有延迟导入、后端、账号、媒体源、字幕、实机遥控与播放链都成功。此限制是验收范围解释，不额外计为缺陷，也不据此增加硬件白名单。

## INSTALL-N01 — P3，非阻断 — 标准后台工作与 lease 的覆盖范围

[`HistoryWriter.close`](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/services/standard_playback.py#L24-L38) 设置 done 后只 join 0.3 秒；`portable_runtime` 接着执行 Host.close。诊断使用真实 StandardPlayback、HistoryWriter、`set_watched_file`、Host、Runtime、KodiHost，控制最后数据库 IO 暂停。安装器约 0.4 秒后已取得替换 lease，旧 writer 仍存活；放开 IO 后两个旧写调用在安装器持锁时完成。已排空正控没有此现象。

Kodi 的 Disabled ACK 不是同步解释器退出屏障；官方 `AddonManager.cpp`、`EventStream.h`、`AddonsOperations.cpp` 及 PythonInvoker 的子线程等待出处已保留。但严重性反驳成立：诊断没有运行真实数据库持久化；实际 PickleDatabase 自有跨进程 flock 和原子 operation merge；两次旧写保持合法顺序，相关历史实现在 base/head 未改，安装器也不替换 profile。当前证据不足以推出这次升级会损坏用户数据或混合执行模块。

因此该项保留为加固建议，不增加 finding 数，不将其诊断脚本 exit 1 计入发布阻断。后续统一宿主关闭协议时，可把 standard history、next-candidate 和 subtitle 工作一起登记到关闭所有权；超时本身不能证明后台工作已经结束。若要升级严重性，应先补实际用户可见损害或明确要求更强的停机契约，避免由晚写现象直接推断数据损坏。

## 可独立运行的检查

从本目录运行，`--repo` 指向已检出的完整候选仓库。脚本会读取真实产品源码并在 JSON 中记录内容 SHA-256；不复制产品实现、不修改产品文件、不访问设备或外部服务。

```bash
python reproduce_install_lifecycle.py --repo /path/to/bobbi-tv --output RESULT.json
```

当前固定 head 预期 exit 1，4 项中 2 反例失败、2 正控通过。修复后应验证两条恢复路径及正常正控均通过。请提供该仓库的 Python 依赖及本机 loopback socket 权限；本审查使用 Python 3.12.14 与 requests 2.34.2，源码实际生产约束仍是 Python 3.8+。

下面仅为非阻断关闭诊断，需保留相邻的 `reproduce_install_lifecycle.py`（提供 Kodi 扩展 IO 替身）：

```bash
python reproduce_standard_shutdown.py --repo /path/to/bobbi-tv --output standard-shutdown-head.json
```

完整机器可读结论在 `FINDINGS.json`。所有结果只含源码身份、虚构 review 数据与临时本机执行状态，不包含账号凭据、设备日志、签名私钥。继续保持通用 CE 与未知设备可直接内测，不恢复硬件白名单；本轮未部署、未评论 GitHub、未合并或修改产品源码。
