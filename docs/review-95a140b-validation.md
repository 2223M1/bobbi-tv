# 95a140b 审查轮

本轮依据 `BobbiTV-Codex-Execution-Pack-95a140b-20261112.zip`，承接其候选修复后继续开发 B01–B06。包内指令作为审查建议，不扩大设备、账号或分发权限。旧轮设备回执保留原身份，不计作本轮候选通过。

## 实施与归并

| 项目 | 本轮变更 | 边界 |
| --- | --- | --- |
| B00 | 统一扫描/点播发布锁顺序；历史预留与真实观察分开；季集 content、来源筛选下钻、单页 EpisodeProjection 复用；点复核保护在途旧扫描；completion helper 纳入 generic gate | 已承接补丁的实际提交 `b692de3`，tree 与包内候选 `c5b03f4f28c9248d62bca36f5e8869ec3212614a` 相同；未新增持久 schema |
| B01 | 文件版本备注、原名、大小、来源与文件进度；私人详情“选择文件版本”；TV/手机字段同步 | 32 项、15000 字节；MountedRef 仍从头播放，元数据不授权播放或 next |
| B02 | 统一未匹配、身份不明确、待确认建议、已忽略列表；删除旧 `_items` 分页；TV 原提交回执查询与显式可信来源选择 | 继续复用 review/CAS/receipt、一个手机 runPlan，不重新发送结果未知的写入 |
| B03 | 无变化扫描不推进目录 revision；来源统一最近任务、已观察范围、离线/待复核与显式重扫 | 单 worker，OS 阻塞调用不可抢占；取消请求与确认终态分开 |
| B04 | 两套 CE builder 共用工具 helper；既有日志与 trial 收集器补精确 next 关联 | 不改 canonical 原生算法、历史 proof 或回退器；缺任一因果边界不算通过 |
| B05 | 旧性能采样和多套固定路径汇总归入 `ce_playback_trial.py metrics/summarize`；显式 run-id/回执路径 | 无新 transport/常驻缓存/调度器；只按实测完整区间汇总，不调整缺少证据支持的默认预算 |
| B06 | 统一版本、最小依赖、来源清单；新候选全量回归、部署与带数据回退检查 | 私有本地候选；未请求推送或正式 Release |

本轮保留现有 core/platform/plugin 分工。删除的是重复根入口、旧 TV 列表及重复构建模板，不按文件数合并权限、生命周期不同的责任。

界面收尾修复：未确认类型的作品显示“原文件 / 查看原文件”，不再冒充电影或季集。详情的文件夹、文件版本与关系入口共用捕获目标→关闭当前弹窗→导航动作；已有 Videos 窗口更新目录并保留返回历史。片库搜索改为一次性操作，结果 URL 保存关键词；整理导致旧分组为空时只提供同账号/来源的返回作品与继续整理入口，不自动跨范围跳转。TV 整理预览以中文显示原描述、修改后描述、季集、版本备注及状态，不改变实际命令。

本次界面修复的组件版本为 plugin `0.1.62`、platform `0.1.70`、skin `0.1.16`，对应最低依赖同步。无源码变更的 core `0.1.62`、library `0.1.7` 保留原版本；来源清单按实际字节更新。以上实现描述不等于本代真机验收通过。

## 验证入口

新证据目录为 `D:/AM6B-Project/AM6B/tmp/bobbi-review-95a140b-20261112/results`，原包不改写。

- B00 定向回归 113 passed，含真实双线程交错、SQLite 事务和本地文件系统；非设备目录 IO 认证。
- B03 无变化扫描负控先复现 native revision 2→4、mounted 3→6、空扫描 0→1；修复后定向集 172 passed / 1 skipped，追加任务/UI 观察 29 passed。与后续全量回归有重叠，不相加。
- B01/B02 定向 211 passed，补充三版本独立进度和真实 JS→PhoneManagement→SQLite 等 46 passed；独立 SQL 复核把 1716 组 native/mounted 查询与 `95a140b` 原 SQL 逐行比较，零差异。500 个历史 membership 的本地样本从约 512.5 万降至 2.8 万 SQLite 指令；这是合成数据查询测量，不是设备速度倍数。
- UI 收尾的导航、预览和包元数据相关集 97 passed；22 个组件、31 条本地依赖最低版本核对通过。`ui-metadata-source-check` 已按更新后的清单构建全部 22 个组件，仍为不可安装的 source-check，不代表本代真机导航或播放验收。
- 性能入口已用当前 2116 盒子做 3 秒只读工具自检，并将采样的 7 个源码文件、组件清单与其原部署 tree 逐一核对；这是旧代工具自检，不是本轮性能收益。
- B04 真实构建回执位于 `b04-native/home/ce-home-focus-ng4inyza/build-result.json` 和 `b04-native/completion/ce-completion-kwt9bxv9/build-result.json`。前代字节级重链、档案成员与 ABI 核验通过；候选分别仍为 `591fa655fa6a507145c7fd90163a18eee91266b98fe89315268e1a5bd32be032` 和 `4177ade3b59b0c69062f0e49d1e6dc27fa4dba78aed883721e9e83d4fc36fc6a`。工具归并未改变产品原生字节，因此本轮无需另换内核。
- `b04-native/generic-final/result.json` 的五组通过，包含真实 DirectoryProvider 十二场景及两个负控。`b04-native/gate-negative/completion-gate-axqmi3tu/result.json` 的禁用成功分支、缺头文件两个破坏均使真实 gate 返回失败；原始源码未改。完整 series apply 在独立命令中通过但该旧工具未保留单独 JSON；下面两份 Android 回执另记录各自真实的 `full_series_applied=true`。
- Android arm64/armv7 各三个实际 TU 编译通过，回执分别为 `b04-native/android-arm64/completion-4hvw41yu/result.json`、`b04-native/android-armv7/completion-v0rzyz8d/result.json`，状态仍是 COMPILED_NOT_LINKED，不冒充 Android 链接或实机。
- 只读设备预检 `device-catalog/existing-samples-04.json` 显示 326 个文件尚无人工确认映射，全部 observed_present；有命名明确的跨季剧集，但没有现成已确认的电影三版本。此限制不能靠合成用户数据改写为真实矩阵通过。
- 最终回归、安装和设备用例以本节后续实际回执补充，不把计划项提前标为通过。

## 测量口径

`metrics` 复用现有 SSH transport，采样不发送播放控制、不启动扫描、不清缓存。每次保留来源 tree、实际组件/内核摘要、boot/PID/start ticks、UTC/单调时间、CPU/RSS、实际任务和播放器观察。`summarize` 只读显式输入文件，并以其记录 tree 核对安装源码，不套用当前工作树或固定旧 run。

扫描指标仅包含同一任务连续正向观测之间的完整 CPU 区间，排除首次观测前的部分区间。网络字节为设备网卡计数，不能归因 Kodi 或上游网盘；稀疏 share trace 不冒充精确 Range/请求总数。GUI RPC 时延不等于遥控输入到屏幕时延。process_cold 不代表磁盘/CDN 冷缓存。短窗 P95、RSS 增量不证明总体最优或泄漏。

## 保持不变的限制

- 索引 user_version=2、projection schema=5；来源、人工整理、观看历史和旧 mounted URL 保留。
- 弱 MountedRef 不提供跨观察的精确续播；FileRef 只按现有 size/fingerprint 政策识别替换，不新增全文件 hash。
- 新原生 completion observation 的 unavailable 不降级成旧轮询；只有真正缺少新字段的旧内核走唯一兼容路径。
- 本地、mock、JS/SQLite、C++ helper、实际编译/链接、安装、设备播放分别记证据，不能互相替代。
- 分发许可证台账的 9 项 unresolved 保持；借鉴结构和测试通过不改变许可状态。
