# d030e04 审查轮实施与验收

本记录区分实现、模拟/本地测试、构建产物及单台设备验收。尚在进行的设备用例与修复保留明确状态，不把一项成功扩展成全部平台、网盘或格式通过。原审查包是指导和历史证据，其候选 tree 不等于本轮实际实施 tree。

## 身份与证据位置

- 已完成全量回归的提交 `39555a47bef1a8f2bda405261a453295513c6bd8`，tree `ac25000f38649ef57f111ea3638b331d7ddf40a8`；回归前后工作树干净。其后修复须另记提交和复验，不能继承此全量结果。
- 已部署组件序号 `2026102114`，native SHA256 `4177ade3b59b0c69062f0e49d1e6dc27fa4dba78aed883721e9e83d4fc36fc6a`。
- 包外证据根 `E = D:/AM6B-Project/AM6B/tmp/bobbi-review-d030e04-20261112/results`。
- 原生构建/设备证据根 `N = D:/AM6B-Project/ce-native-completion-20261112`；这些目录不写回原审查包。
- CPU/RSS 回执核对了 7 个采样源码文件及 13 个组件清单与上述 tree 的 Git blob 完全一致；同时匹配实际 native、组件序号、PID、boot 与启动 tick。这不是全部安装文件的逐字节审计。

## R00–R07 替换、删除与兼容

| 任务 | 已实现的归并/替换 | 保留与删除条件 | 当前证据 |
| --- | --- | --- | --- |
| R00 | 公共 runtime 持有 Home lifecycle；一个 widget revision worker；standard 摘要异常隔离；离线任务控制；每个未发送子批 JIT preview；百度 JSON 深度明确为 64 | 删除 native 私有 Home 生命周期/重复 worker 入口、首批绕过 preview 特例与字幕死分支；不新增播放 owner | `2b7bc12`、定向用例及 `E/full-01`；标准/native 账号切换设备全矩阵未覆盖 |
| R01 | scope revision 替代全局写入导致的无关游标失效；typed/native 共享 review/CAS/receipt/undo；CD2 描述按 source+namespace 持久展示 | FileRef v1/MountedRef 稳定键不变；旧观察不能领取新票据，显式重选从头播放才建立新观察 | `bea9a87`、scope/索引负控、Linux 84 项；真实目录分页/namespace 拒绝已测，设备重挂未造景 |
| R02 | CatalogService 唯一 BFS/worker/预算/checkpoint/终态，NativePort/MountedPort 仅负责来源 IO 和权限证明 | 删除 `MountedCatalog.start/scan` 的线程与遍历；保留 `catalog_mount_*` 短 RPC 适配 | 同一提交、本地慢 IO/单飞负控；真机一次扫描和精确取消通过 |
| R03 | TV 两类来源进入 `personal_catalog` 同一作品/季/集/原文件 renderer；共享 metadata 缓存与任务观察 | `mounted_catalog_ui` 只保留旧 URL 转译，兼容收藏/历史链接；未有迁移证明前不删别名 | `1a5eb3d`、统一视图/真实装饰器测试；首页焦点与历史分集设备切片，个人片库全层级设备闭环待补 |
| R04 | 手机 query-first/按需单条；通用批次计划归 core review；TV 单条写入统一 `review_entries`，JS 仍唯一 `runPlan` | 100 项显式轮次、每批最多 5 项/8192 字节；原 request_id/CAS/unknown receipt 不迁移；mounted grant 仅固定来源范围 | `1a5eb3d`、真实 JS→PhoneManagement→SQLite 桥；真实手机/真实账号批量验收未声明 |
| R05 | 同实例 native 最终位置观测沿现有 receipt/authority/request 到共用完成判定 | 删除新 host 依赖旧轮询位置的主判定；仅缺新字段的旧 native 保留单一 fallback，最低 native 能力全面覆盖后才可删 | `9317905`、canonical apply/C++ 编译、CE 链接和部署；EOF/历史/next 必须分层看下文 |
| R06 | 47 作品/14 操作统一 `ce_trial_cases.json`，CLI/remote/身份审计共用 | 删除 remote/CLI 重复清单及无调用者一次性 `import_playback_trial.py`；不新增产品缓存/调度器，也不凭本地模型调整传输默认预算 | `e053ce2`、真实解析器/生成程序负控；有限设备 CPU/RSS，配对与延迟项尚未齐备 |
| R07 | 版本/最小依赖/来源清单、原许可证台账与现有构建入口复用；本记录汇总迁移和证据 | 不新增第二套安装/回退；后续修复由整合提交重新生成清单并复验 | 全量基线与双 source-check 已完成；最终修复回归、设备剩余矩阵与交付提交待整合 |

## 已确认的测试与构建

`E/full-01/report.json` 保存每一步实际 HEAD/tree、干净状态、命令、JUNIT 和日志。四个独立 pytest 进程合计 **7760 passed、14 skipped、1 xfailed，0 failed/error**，分别为 primary 6166、baseline 1296、preparation 254、android-packaging 44。跳过主要是 Windows POSIX/符号链接限制；预期失败没有伪装成通过。

供应依赖许可证检查及生成首页检查通过，两次 source-check 的 **63 文件可复现**。原包候选不同导致 `package_candidate_matches=false`；`actual_source_verified=true` 绑定的是实际实施代码。source-check 不是安装包、账号、设备播放或分发授权验收。

`E/linux-r01-r02` 的 Ubuntu 真实文件系统/SQLite 补测为 **84 passed、0 skipped**，含符号链接逃逸、改根、同名替换、scope/CAS/事务和扫描单飞。挂载记录是合成 fixture，不冒充真实 CD2 卸载/重挂。

R05 canonical 新补丁为 `native/patches/0006-bobbi-completion-observation.patch`，SHA256 `c7647dcbb94a4f2bc6e19f4deff3f3677e835a95b8a6771d10aa42860244fe2a`。generic 锁定 checkout 完整 series apply、3 个 ARM64 布局消费者编译与 C++ helper 正负控完成，状态 `COMPILED_NOT_LINKED`；不能称为已链接 Android APK。CE 完整链接回执为 `N/ce-completion-lw79f6_2/build-result.json`，构建时 `BUILT_NOT_DEPLOYED` 是历史状态，后续真实部署由 `E/native/ce-native2114-apply-1794453861407637100.json` 和 `E/health-installed2114.json` 证明，不覆盖旧回执。

## 已确认的单台设备切片

- 2114 组件和 4177 前缀 native 完成部署及 health，旧账号/本地数据未据此重置。只证明这一台设备，不外推 arm64/Android 或全部账号能力。
- `E/r01-r02-device/02-scan.json`：真实挂载来源扫描 54 页/485 项，保留 312 个本地视频索引；精确 task 取消后 `canceled / CANCEL_CONFIRMED`，活动扫描数 0。连续两页同 revision、无重项，错误 namespace 拒绝，SQLite `quick_check=ok`。这是取消的部分扫描，不是整树完成。
- 取消请求至观察终态约 0.093 秒；计划观察 15 秒，末次状态查询变慢使总计 18.443 秒。不能写成硬 15 秒上限，更不能声称可抢占阻塞 FUSE 系统调用。
- `E/ui-home-nav-full2114.json` 记录首页逐行上下移动；继续观看的全剧入口与分集进度分别留在 `E/ui-all-episodes-ready.json`、`E/ui-episode-progress.json`。这些成功切片不能替代空首行、删除当前项、账号切换、标准/native 全组合。
- R05 正控目前已有 1×/8× native 同实例 `NATURAL_EOF` 有效观测；主代理报告 8× history 完成标记为真，但百分比过冲 103.6% 已暴露并正在修复。1× history/next 完整归属、修复后的 8×、32×及负控须以最终回执收尾，不能先写全部通过。

## R06 有限性能证据

`E/r06/perf-home-summary.json`：暖态首页 30.002 秒，RSS 31 点为 524.57 MiB；CPU 完整区间 30 个，进程中位数 28.00%、P95 31.00%（单核 100%），整机中位数 4.88%、P95 5.43%。不是冷启动。

首个 `home-scan-01` 与真实任务 running 仅重叠 0.498 秒，RSS 1 点 530.34 MiB，完整 CPU 区间 0 个，median/P95 为 null；不能用整个带 scan 标签的 30 秒归因扫描负载。

`E/r06/perf-galactic-idle-summary.json`：普通视频标签短窗口 55.003 秒，RSS 56 点为 636.375–1067.535 MiB，末值比首值高 428.332 MiB；CPU 55 个区间中位数 114.956%、P95 173.141%（单核口径），整机为 20.962%/32.035%。这不是重复稳定态基准；短期 RSS 上升不能独立判泄漏，尚需播放器时钟、缓冲状态及停止后回落证据解释。

P95 为 nearest-rank。collector 不采精确首帧/seek/遥控延迟；trace 只有稀疏事件，`fetch_end` 字节与 GET begin 不能冒充精确上游流量/Range 次数。冷/暖对照、充分重叠的同文件扫描对照未齐，不作性能“最佳”或优化完成结论。

## 升级、回退与未覆盖门

索引仅加 scope revision/typed observation 等辅助表，user_version 仍为 2、投影 schema 为 5；原 objects/typed_objects/reviews/history 和稳定键保留。投影重建失败在事务内回滚。支持 schema 2 的旧版本可重建读取投影，不支持者拒绝写入；不得通过删除索引来假装回退成功。真实设备带用户数据的回退尚未执行，不能以 fixture 替代。

原目录入口、旧 mounted URL、115 PreparationQueue 与账号 Registry 保留；普通旧观察不能跨挂载继承进度或播放许可。旧 native 的完成 fallback 只服务缺少新字段的兼容期；撤回消费者时回到保守完成策略，不放宽 Stop/账号撤销边界。组件及 native 回退必须走原安装/更新机制并核对目标代际，不直接覆盖用户数据库或挂载配置。

最终仍须逐项记录，未执行则保持未覆盖：

- R00/D01、D03、D04、D12：标准/native 冷启动及账号变更，真实手机大批量/冲突/丢响应，真实 FUSE 阻塞与掉线，字幕 Off/音轨/版本/Stop。
- R01/R03/D02、D05、D09：真实重挂/改根/同名替换；个人片库作品→季→集→多版本与各文件进度；空行/删项/窗口重建及迟到 metadata。
- R05/D06–D07：1×/8×/32×真实有效速度与同 owner history/next 一致；暂停、Seek、Stop、换源、账号变化、迟到旧实例、输入 read_error/提前 EOF；不可用时基不列作成功正控。
- R06/D08、D10：ISO 首帧/seek/取消；同文件、足够 running 重叠的扫描对照；冷/暖与输入延迟；精确网络量当前不可得。
- R07/D11：最终修复后的回归与产物身份、带数据升级/回退实机验证；Android 实机、生产签名及远端正式发布不由本地通过自动获得。

分发授权保持独立门。`licenses/THIRD-PARTY.json` 仍有 9 项 unresolved：`script.module.jurialmunkey`、`script.module.infotagger`、`plugin.video.bobbi`、`script.module.bobbi.platform`、`script.module.bobbi.core`、`script.module.bobbi.mdsub`、`script.module.bobbi.catalog`、`skin.bobbi.cinema`、`resource.uisounds.bobbi-modern`。皮肤与逐字体哈希在 `licenses/skin-reference-evidence.json`，其状态仍是证据而非分发许可；Juku/Fuse3 结构借鉴和测试成功都不消除这些门。
