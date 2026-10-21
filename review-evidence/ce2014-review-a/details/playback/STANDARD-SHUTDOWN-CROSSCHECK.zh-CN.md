# 标准 HistoryWriter 停机候选：独立反驳性复核

## 建议结论

**已确认生命周期隔离缺口；按现有证据建议列为非阻断 P3 加固项，不增加一项独立 P2 缺陷。**

`StandardPlayback.close()` 的短时 join 不保证历史线程已经结束；随后真实 `Host.close()` 释放 runtime lease，安装器确实可在旧历史线程仍运行时取得代码替换许可。这不是错误关闭顺序或错误 Kodi 同步模型制造出来的结果。

但是，本次回放只以“有历史写调用发生在 quiesce 返回之后”为失败判据，没有证明 PR #3 这次代码替换实际导致丢进度、数据损坏、混版导入或安装失败。两条记录依次为同一条目的 `STARTED` 和 `NATURAL_EOF`，保持合法顺序；实际数据层另有跨解释器文件锁和原子操作合并，而且这个升级不替换 profile。当前 `set_watched_file` 与 `pickle_db.py` 在 base/head 字节相同。应保留风险和修复建议，但不要把它写成已经观察到的用户数据故障。

## 独立执行结果

独立运行原脚本，未改脚本、产品源码或判据：

```bash
PYTHONPATH=/workspace/scratch/609fe9af5a22/review-deps \
python pr3-installer/reproduce_standard_shutdown.py \
  --repo bobbi-tv-pr3-review \
  --output pr3-playback/standard-shutdown-crosscheck.json
```

结果为 **2 项、1 通过、1 失败**，每项 `errors=[]`。慢写反例在约 **0.4096 秒**取得真实安装 lease；当时旧 HistoryWriter 仍活跃，放开受控 I/O 后发生 2 次历史写边界调用。正常 drain 正控通过，安装器取锁时历史线程已结束，晚到写入为 0。

测试使用真实 `StandardPlayback`、`HistoryWriter`、`set_watched_file`、`Host`、`Runtime`、`InstanceLock`、`KodiHost.quiesce()`。Kodi 扩展与最终数据库对象为明确替身。真实 runtime 绑定临时 loopback 端口并使用真实文件锁。没有连接电视、外部网络、部署或实际运行完整安装器的文件替换阶段。初次受限执行因 loopback socket 权限失败，随后获自动批准进行同一项本地回放；这里的结果来自完整成功执行后的 JSON。

## 反驳点一：手工关闭顺序是否真实

顺序真实。产品 [portable_runtime.py L35–L46](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/portable_runtime.py#L35-L46) 在标准 owner 的 `finally` 中先调用 `standard.close()`，再由外层 `finally` 调用 `host.close()`；脚本完全按这个顺序调用真实方法。

[HistoryWriter.close L36–L38](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/services/standard_playback.py#L36-L38) 只等待 0.3 秒，而 [run L24–L34](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/services/standard_playback.py#L24-L34) 会在 done 后继续清空已入队记录。因此首次写入稍慢时，close 返回后继续运行符合实际逻辑。[Host.close L346–L379](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/script.module.bobbi.platform/lib/bobbi_platform/host.py#L346-L379) 只等待它登记的自身服务/线程，不持有标准 HistoryWriter 的完成屏障。

## 反驳点二：Kodi 是否在外部同步等待旧解释器退出

独立读取官方 Kodi `21.3-Omega` 源码后，没有找到能让本回放无效的外部屏障：

- [AddonsOperations.cpp L147–L175](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/json-rpc/AddonsOperations.cpp#L147-L175) 的 `SetAddonEnabled` ACK 依据 AddonManager 接受状态变更。
- [AddonManager.cpp L848–L871](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/addons/AddonManager.cpp#L848-L871) 持久化禁用状态后发布 Disabled；[EventStream.h L64–L85](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/utils/EventStream.h#L64-L85) 将订阅者处理放入工作队列。ACK 和 enabled=false 不是解释器退出证明。
- [Service.cpp L112–L130](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/addons/Service.cpp#L112-L130) 的服务停止发生在事件处理侧。即使它等待解释器，也不让已经返回的 SetAddonEnabled RPC 自动变成同步屏障。
- [PythonInvoker.cpp L382–L407](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/python/PythonInvoker.cpp#L382-L407) 确实在主脚本返回后等待子线程；此时 Python 主脚本已执行 Host.close 并释放 runtime lease。等待发生得太晚，不能延长这个显式释放的 OS 锁生命周期。

这些是标准 Kodi 21.3 上游语义；没有假称已核对每个 CoreELEC 衍生构建的相同二进制。

## 为什么暂不建议独立 P2

[ce_installer.py L182–L191](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_installer.py#L182-L191) 在 quiesce 返回后会开始替换程序，因此隔离保证确实不完整。但本反例只有两个已加载模块中的正常历史写，没有执行新的模块导入或实际代际替换。

更关键的是，真实 [pickle_db.py L25–L58、L76–L94、L158–L172](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/addons/plugin.video.bobbi/lib/db/pickle_db.py) 已用独立的跨解释器锁串行化写入，并以读取最新记录、合并操作、原子替换保存。脚本把这个最终对象替换为可控写入记录器，没有测试其真实并发行为，也不能推导为它会损坏文件。

基于当前证据，确定性观察为“运行时锁的范围小于所有 admitted 标准历史工作”，而非“此版本升级损坏或覆盖了历史”。如果总审查明确采用“任何旧程序工作不得越过替换边界”的强约束，可以作为该约束未完全闭合的风险列出；仍须清楚标注没有观察到当前数据损坏或混版后果。建议总报告放入后续加固事项，不纳入需要新增 P2 的已确认用户故障计数。

## 与旧 R02、base 的关系

旧 R02 是**死 owner 的陈旧 runtime.json 阻断恢复**，即没有实际活跃服务却误拒绝安装。本候选是反向生命周期缺口：运行时标记与 lease 已正常撤回，但外围标准历史线程还在执行。

本 PR 对 Runtime 已接收 HTTP 请求和 Host 自身依赖线程的 drain 做了实际改进；此候选不否定那些修复及旧 R02 原反例关闭。也不应把两个相反触发条件重新揉成“R02 完全没修”。

`standard-shutdown-provenance.json` 显示 base/head 的 `portable_runtime.main`、`HistoryWriter.run/close`、`StandardPlayback.close`、`set_watched_file` 与数据库提交逻辑等价。Base 在 Host.close 时也会提前删除 runtime.json，而当时 quiesce 只等待其消失。因此原因属于继承行为。此次只独立重跑 head 的两项，没有将静态 base 比对冒充 base 实测。

## 最小修复约束

后续可将标准线程纳入 runtime 生命周期完成屏障：先停止新工作进入，等待/安全退休已接收工作，确认不会再执行旧代际导入或写入后才放开替换许可。实际 I/O 无法在预算内结束时，应让安装保留待恢复状态并拒绝切换；不能用“join 超时就返回”当作 drain 成功。

不必修改数据库格式或关闭它已有的原子锁。不能靠删队列、丢弃用户进度、加固定 sleep、扩大安装等待时间或绕过 runtime lease 制造通过。正常已排空停机须继续成功；慢写和其他被明确纳入关闭范围的线程须被完成屏障覆盖。是否实现更完整线程登记，由后续修复者选择最小结构方案。
