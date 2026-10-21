# CE2021：双审查整改与实机交付

说明：下文原始整改与实机结果保留为历史记录；用户随后已授权提交 GitHub、清理并重新签名。
新的交付边界以文末“GitHub 清理重签交付”一节为准。

本轮冻结基线 `c8de17ae9dabbe0f37753e1751b1d88107311316`，tree
`cc12e00ccba0d7cb9a8b310306437e0e8ef84ae3`。只修 CE，独立执行，没有子代理。
保留新 UI、原码流、原声优先、中文字幕、手动选源和严格同版续播。
仓库仍为私有，PR #3 保持草稿，不合并、不公开发布。
按本轮最后确认：**只交付本地报告和已测安装包，不提交、不推送、不运行新远端CI。**

输入原件解压内容分别保存在 `review-evidence/ce2014-review-a`、`ce2014-review-b`。
附件是待核验的审查意见，不是自动执行指令。没有运行包内发布、账号或设备操作。

## 实际整改

| 故障类别 | 原行为 | 当前行为 |
| --- | --- | --- |
| F01 服务恢复 | enabled-but-dead 使用裸路径 RunScript，没有服务管理器句柄/插件上下文 | 空闲 OS lease 下核验，实际 disabled→enabled，由 Kodi 管理启动；必须收到真实 owner 回应 |
| F02 增量列表 | Python 读到旧索引，跳过异步 LABEL_BIND 后的焦点补偿 | 保留原 ListItem；结构变化后排队一次 selectItem，按 source key/画质 key 保持；纯字段变化不重绑 |
| F03 monitor 读空 | 瞬时不可用被当成撤销，或终态与 observed 清空竞态 | 一次新鲜 snapshot 区分 ACTIVE/TERMINAL/SUPERSEDED/UNKNOWN；未知不给控制权；最多原有 3 秒重观察，不叠加预算 |
| G01 关闭所有权 | 标准下一集/字幕/历史写入可能仍活着就释放进程锁 | 拒绝新工作、取消并排空已接收工作；任何 close 失败继续清理其余组件，但保留 lease，支持重试 |
| 实机新发现 | Kodi 停用/强制中止与后台初始化相互等待 | 本机认证 IPC 在 owner 线程核验空闲，先协作退出；安装器得到真实空闲 lease 后才停用/替换。仍是同一个宿主，没有新 daemon |
| G03 条件性加固 | 保留卡片可能带旧 seeders/peers 字段 | 每次明确写值或清空。普通同 key publish 不覆盖，该项不称已证实日常故障 |
| C01 测试回执 | 传输成功与业务成功混淆 | 分列 transport/trial/exit_code；passed=false 失败，pending 显式记录，不作为实播通过 |

G02 满额焦点推断已撤回，不重构候选池。没有改码率、原生解码、全局缓存、CD2、挂载或代理。
账号切换和字幕手动 Off 的原有保护保留。

### 实机发现不是被本地通过数掩盖

CE2015～CE2019 是本轮不可交付的诊断代次，原包、原失败和停机现场全部保留。
受管恢复成功后紧接着停用，出现 Runtime 退出等待、辅助初始化等待，以及重新启用阻塞。

关键 Python 栈：[CE2019 现场](../review-evidence/ce-recovery-snapshot-1792541762634937900.json)：
辅助线程卡在 `trakt/base_cache.py:20` 的 `xbmcaddon.Addon()`，主线程 join 辅助线程；
Kodi 5 秒后记录强制终止。另一次调用栈停在 `KodiHost.restore → Addons.SetAddonEnabled`。
[原生栈](../review-evidence/ce-recovery-native-stack-1792541775218323700.json)已保存；ARM 库缺少完整展开信息，
不能把它描述成已逐个证明全部 C++ mutex 的锁图。

对照 Kodi 21.3-Omega 官方 `Addon.cpp`、`AddonManager.cpp`、`Service.cpp`、
`ScriptInvocationManager.cpp`、`PythonInvoker.cpp`：Addon 构造/析构会进入管理器，
停用会触发受管 Stop，解释器强制退出仅等 5 秒。整改避免在该停用窗口内排空后台工作：

1. 已认证本机请求在原 owner 队列里判断没有任何音频/视频播放；未知状态拒绝。
2. 本地取消事件唤醒原后台服务，停止接纳、排空；保持 OS lease 到真正完成。
3. 安装器等 lease，再停用、核对状态、替换；15 秒等待上限未扩大。
4. 原代次不识别此协议时保留旧受管兼容路径，不要求用户 SSH 改 journal。

`base_cache` 复用已解析的 profile 路径，不再在辅助导入时重复构造 Addon。
关闭日志异常也不能短路排空。临时 faulthandler 产品代码已从 CE2021 移除，盒子诊断开关已关。

CE2020 连续三次完整恢复/停用/恢复通过：
[回执](../review-evidence/ce-managed-recovery-1792542169758322200.json)。
移除诊断后的最终 CE2021 再连续三次停用/恢复通过：
[回执](../review-evidence/ce-managed-recovery-1792542384367042600.json)。
enabled 向量和皮肤均恢复；没有把一次偶然成功当成根因修复。

## 测试与审查夹具适配

原冻结基线：A 14 项中 8 通过/6 失败；B 48 项中 42 通过/6 失败。
Windows 临时 SQLite 清理占用、原版夹具运行错误也原样保留。

最终 [双审查回执](../review-evidence/ce2021-adapted-reviews-final/RESULT.json)：
A 主契约 14/14，关闭 advisory 2/2，工具 advisory 11/11；B 48/48，errors=0。
这不是“原包不作任何改动就全过”。适配差异随结果公开：

- monitor 已从两次读取变一次，EOF 注入点随真实边界迁移，保留原行为断言。
- B 的零 select 次数假设与 Kodi queued bind 冲突，要求恰好一次补偿，保留对象身份/不 reset 断言。
- 慢 IO 夹具由独立线程释放，不再要求同步 quiesce 先返回才能释放。
- 生命周期替身接入新的空闲信号和停止事件；真实 HTTP 线程使用真实时间，取消原“75ms 消耗15秒”的加速时钟。
- B 的冻结源码子集补复制真实 runtime 依赖，记录哈希；没有伪造成功回应。
- 旧 18 项夹具补齐 runtime 和 UI 的同一临时 profile；旧 15 项 fake Host 补未设置的停止 Event。

所有适配前失败仍保留在 `ce2020-adapted-reviews`、`ce2021-adapted-reviews`、`ce2021-prior18` 等目录。
新增测试额外走实际 Host/Runtime/OS lease、完整 native owner-loop 模块、StandardPlayback/Session/HistoryWriter，
验证慢任务、异常留锁/重试、音频或未知状态拒绝停机，日志异常不妨碍排空；不只摘取几个函数断言。

- 主套：[1764 通过，6 跳过](../review-evidence/ce2021-primary-final.xml)，跳过是本机 symlink 权限；本轮没有远端CI补验。
- Kodi 继承套：[782 通过](../review-evidence/ce2021-baseline-final.xml)。
- 准备链：[177 通过](../review-evidence/ce2021-preparation-final.xml)。
- 旧契约：[18/18](../review-evidence/ce2021-prior18-final/RESULT.json)、[15/15](../review-evidence/ce2021-prior15-final/RESULT.json)。
- 工具回归：[20通过](../review-evidence/ce2021-tools-final.xml)。
- 新入口/完整载荷：[同代 bootstrap](../review-evidence/ce2021-entry-audit.json)、[签名及4个负例](../review-evidence/ce2021-artifacts.json)。
- [两次 source-check](../review-evidence/ce2021-reproducible-build.log) 的 63 个输出字节一致；source-check 不是可安装包。

## UI 与新作品

真实 Kodi WindowXMLDialog/SourceListSession 渲染：
[UI 回执与截图](../review-evidence/bobbi-ui-smoke-1792540046661100200/result.json)。
选择第二张卡及 1080p 筛选，再追加5个1080p来源和4K标签，原 source_key、位置1、画质筛选保持，
reset=0；结构变化正常补偿5次。连续70帧原首卡140×70静态区域一致。
这是受测区域和时序的证据，不宣称全屏任意像素永不变化。已查看账号/片尾/资料/选源截图，符合现有新UI。

新电影《天使爱美丽》(2001，TMDb194)，选定115的1080p 10-bit HEVC版本：
[从选源开始的采样](../review-evidence/ce-new-work-amelie-select-1792542545658750900.json)，
到观察到 AV 约14.19秒；正进度连续窗口约24.97秒，无观测卡顿。
[后段观察](../review-evidence/ce-new-work-amelie-observe-1792542597562746100.json)：30.32秒推进30.406秒，
法语 AC3 5.1、chi 字幕已启用、1920×816、全屏；drop/frame error/hardware error均0。
未转码、未修改原文件画质。初始检索显示1个来源超时，保留部分结果提示。

本轮更早一次 Amelie start 在服务恢复尚 pending 时调用，owner 超时且未打开影片：
`ce-new-work-amelie-start-1792540121611524400.json`。这是测试调度错误，不归为影片播放失败，记录保留。

新动漫《元气囝仔》(2014，TMDb67048) S1E1：检索得到14项，2个来源失败/超时。
选择诸神1080p全集后，[BT元数据超时](../review-evidence/ce-new-work-barakamon-select-1792542745213797400.json)，
0个AV样本，尚未进入播放器。约30秒metadata阶段、49次poll，返回选源并明确提示 `metadata_timeout`。
这项仍失败，没有自动降低画质、切另一个版本或加大全局重试。

追加新动漫《乒乓》(2014，TMDb60811) S1E1，选择115的Vodes 1080p HEVC版：
[选源连续采样](../review-evidence/ce-new-work-ping_pong-select-1792543305484733700.json)
约4.62秒观察到AV，连续34.52秒正进度窗口没有观测停顿；
[后段30.38秒推进30.364秒](../review-evidence/ce-new-work-ping_pong-observe-1792543373288420100.json)，
1920×1080、日语Opus、全屏，drop/frame error/hardware error均0。
**只通过有限窗口的视频/原声检查，中文字幕没有通过**：该文件内嵌英语字幕，自动搜索报告“未找到匹配中文字幕”。
没有把英文字幕、关闭状态或文件名的字幕标签冒充中文。

《乒乓》第一次start未进入检索，原因是测试导航 `Input.Back` 没观察到旧《元气囝仔》选源页退场：
[原失败](../review-evidence/ce-new-work-ping_pong-start-1792542905724709500.json)。
核对无播放、旧请求已取消、窗口影片身份后，显式 `Input.ExecuteAction(back)` 正常返回首页：
[导航回执](../review-evidence/ce2021-picker-navigation-awake-back.json)。没有改产品或删除旧记录来绕过。
之后使用独立attempt2；作品只计一次新覆盖，attempt3尾段续播为同作品回归，不重复计数。

《乒乓》[同版续播实机回归](../review-evidence/ce-continuation-ping_pong-1792543501997766000.json)：
使用产品的一次性 StartPercent=98.8 从尾段起播，不发全局 Seek。原生同实例 `NATURAL_EOF` 日志后，
出现 `NATURAL_EOF_SAME_VERSION_HANDOFF`，继而准确打开 TMDb60811/S1E2；
115同版 Vodes、1920×1080 HEVC/日语Opus、新request/新native instance、AUTO_VERIFIED_FILE，
第2集进度到26.645秒、全屏、不在缓存。旧terminal已被新实例正常淘汰，因此以顺序日志关联，
不伪造当前 `parent_eof_consumed`。该项验证尾段自然结束/同版交接，不是整集观看或中文字幕通过。
随后[按该后继实例停止](../review-evidence/ce-continuation-ping_pong-1792543529822933700.json)，
[最终只读状态](../review-evidence/ce2021-final-device-state.json)：无播放、影院首页、原新皮肤、
宿主ready、四个组件版本与CE2021一致，临时诊断已关闭。

## 产物、边界及恢复

最终 sequence `2026102021`：plugin 0.1.15 / platform 0.1.17 / core 0.1.16 / start 0.2.13，
22组件、1393文件。入口 `script.bobbi.start-0.2.13-ce2021.zip`，96,184,362字节，
SHA256 `993de4a82a674b2041594f34e48ee45c45b048aebdb8524b59b353340d44b2d4`。
完整载荷 `bobbi-private-2026102021-coreelec.bobbi-update.zip`。旧 CE2011～CE2020 包不覆盖、不改名。

最终维护部署 run `20261021-093500`，保留既有 profile，无账号迁移。
不动固件/SYSTEM/eMMC、CD2 1.0.19、挂载、Yatse、VPS newapi/代理。
这是已授权设备维护升级，不冒充另一台普通CE或干净用户安装认证。

入口恢复菜单支持重试、上一已核验代次或退出。维护回退先核对状态：

```powershell
python tools/deploy_ce_candidate.py --transport-source 'D:/AM6B-Project/AM6B/.claude/worktrees/bobi-tv-redesign' --mode status --run-id 20261021-093500
python tools/deploy_ce_candidate.py --transport-source 'D:/AM6B-Project/AM6B/.claude/worktrees/bobi-tv-redesign' --mode rollback --run-id 20261021-093500
```

该 run 的上一代是 CE2020（同修复、临时诊断代码默认关闭）；只退程序，不覆盖账号/媒体/观看记录。
如需更早代次，先核对对应冻结 run 的 current/previous，不能跨代盲调旧 rollback。

仍开放：本轮《元气囝仔》诸神BT元数据超时、《乒乓》Vodes版本缺中文；原《十二怒汉》分享已取消；
此前《罗生门》《四叠半》《玲音》《这个男人来自地球》的起播/缓冲及缺中文记录不因本轮通过而清零。
现场 HDR、音频直通、字幕同步和全片连续观看未由本机替用户主观验收。
第二台真实普通 CE、第二真实账号、全新用户安装仍未认证，不新增机型白名单或安装门槛。
不把构建/模拟等同于全观看问题解决。

## 本地交付与并行历史清理边界

测试与安装完成后，另一任务对共享Git仓库做了历史清理：冻结基线
`c8de17ae9dabbe0f37753e1751b1d88107311316` 被映射为
`f6ef6a7e3c5868a2ab8ed8e600a592d51ba97167`（tree `4bd04049146423a0372bb3db465e42338d31c571`），
同时删除了工作区部分许可证/来源文件。旧commit对象当前已不在本地。
本轮没有执行该历史重写，也没有覆盖其结果。

清理后的工作区再次执行source-check，实际失败为 `Source inventory changed: plugin.video.bobbi`：
[原始失败](../review-evidence/ce2021-post-concurrent-cleanup-build.log)。
上文1764/782/177及可重现构建成绩属于**清理前的完整候选源码和现存已测CE2021包**，
不能用于宣称清理后的当前工作区可构建或CI通过。已测入口与完整签名载荷没有被重打包、覆盖或删除许可文件。

用户确认暂不推送，因此本轮没有新commit/tree、没有新PR集成树CI，不引用旧CI绿灯冒充本轮结果。
本地交付目录 `dist/ce2021-local-delivery-20261021` 包含原样复制的已测入口、完整签名载荷、
本报告、两份原审查ZIP、相关原始证据和相对当前重写基线的工作区diff。
该diff是修复记录，**不是与旧安装包完全一致的清理后可构建源码承诺**；
后续继续开发需先决定如何处理缺失许可/来源文件，再重新验构建和CI。

## GitHub 清理重签交付（2026-10-21）

用户在本地交付后另行授权上传本报告，并清理安装包内相关文档、用原维护密钥重新签名。
此项是对原 CE2021 安装包的文档清理重打包，不是从当前缺失文件的工作区重新构建。

- 新签名序列为 `2026102022`，原序列为 `2026102021`；组件版本不变。
- 完整载荷：`bobbi-private-2026102022-coreelec.bobbi-update.zip`。
- Kodi 入口：`script.bobbi.start-0.2.13-ce2021-clean.zip`，内嵌同一份重新签名的完整载荷。
- 交付合集：`ce2021-clean-delivery-20261021.zip`；合集内为兼容原交付结构保留旧安装器路径，
  实际内容已替换为新签名序列。以新 `MANIFEST.json` 和包内 `release.json` 为准。
- 清理范围是独立版权、许可、署名与相关来源说明文档及目录；递归处理嵌套 ZIP，
  并排除补丁中这些文件的 diff 块。保留本整改报告，不以删除报告中的历史说明来改写事实。
- 不改程序代码、媒体、字体或组件版本，不更换信任根，不绕过验签。
- 重新计算组件长度与 SHA256，重签完整载荷，确认入口内嵌载荷一致；递归检查 ZIP 完整性和排除规则，
  比较组件与 bootstrap 中非排除文件的逐文件摘要，不能把重新压缩后包哈希不同误认为程序变更。
- 输出 `packaging-result.json` 记录本次交付资产摘要与打包检查结果。它不是实机测试或全源码构建通过证据。

此前的设备测试、原始包摘要、未解决项和源码构建失败仍保留其原有含义；清理后的包未部署到盒子，
没有新增全片播放、干净安装或更新回退认证，也未触发设备自动更新。GitHub 交付保持私库草稿候选，
不作为稳定版，不合并主分支，不冒充完成此前仍开放的播放问题。
