# 9446e59 审查轮

依据 `BobbiTV-Codex-Execution-Pack-9446e59-20261112.zip` 承接候选并扩展 C00–C08。包内内容作为审查建议，不扩大账号、设备或分发权限。本轮完成本地提交与 CoreELEC 部署，不推送 GitHub 或创建 Release。下表区分代码切片、真机验证和未完成范围，不宣称全部能力已经完成。

最终运行候选为 commit `732c8f2c22f899417a66b9b9a025ffaea59b8e54`，tree `4e90c5a164f787b8547bbbd91f5aa9792f7492c9`。本文件的后续提交只增加验收记录，不改运行源码。证据目录 E 为 `D:/AM6B-Project/AM6B/tmp/bobbi-review-9446e59-20261112/results`；部署原回执位于本地 `review-evidence`，不随源码提交。

## 实施与边界

| 项目 | 本轮交付 | 剩余范围 |
| --- | --- | --- |
| C00 | 集成版本备注保留、TV/手机筛选、原名排序与备注检索、读取投影 6、有界诊断采样 | 实际扩展 tree 不等于包内候选，分别记录验证身份 |
| C01 | 诊断绑定当前 endpoint/profile/原播放回执，读取失败保留缺口，不重发播放 | **起播卡顿未解决**；未完成全条件重复稳定性及竞品性能对照 |
| C02 | 继续观看关联原文件/其他版本，批量查询本机关系，共用 catalog_display，进度与未知事实分开 | 三真实版本的独立历史/替换/续播未验收；完整 exact-profile、偏好和可解释选版未实现 |
| C03 | 命名常用视图、更新/重命名/排序/删除、首页应用与恢复默认；人物页批量持有标记 | Extras、合集和推荐数据获取尚未全面合并；所有焦点与视图操作未逐项真机验收 |
| C04 | 单一播放展示投影；手机 read/control 分权；当前实例 seek、音轨、字幕与显隐；原生最终回执 | 真机覆盖 owner/native 切片，不等于真实手机 HTTP 操作、跨音轨切换或全部迟到字幕负控 |
| C05 | IntroDB 手动建议、章节投影；个人补充内容复用预览/CAS/回执/撤回，支持作品共有或精确父文件 | 补充关系真机交互未测；完整精确片段编辑、自动跳过、彩蛋/next 闭环和 TV 章节焦点未完成 |
| C06 | 普通本地目录接入原 Registry、LocalPort、CatalogService、索引、复核与标准交接 | 新增 115 私人片库闭环、Jellyfin/Emby/Plex 统一索引适配未实现；不代表 SMB/NFS/WebDAV 或精确跨挂载续播 |
| C07 | 固定 profile 根、观察切换后永久撤销旧绑定；延迟历史单 writer；有界人工状态导入导出 | 真实 A→B→A、跨设备导入未测；路径重映射、补充关系迁移、Trakt/Simkl 新写回策略未完成 |
| C08 | 冻结全门、CE 构建部署、数据迁移、原生回退恢复、有限真机验收及发现问题修复 | 实际程序 schema 2/3 降级往返、Android APK/实机与整套设备矩阵未完成 |

继续复用原数据库、唯一播放 owner、扫描 worker、手机 HTTP 服务与审核事务。补充内容排除正片版本计数、自动下一集和人工导出；本地/CD2 手机管理不授予无法保证的播放控制。文件名不冒充媒体探测结果，1080i 展示不再误写成 1080p。

收尾另修 Host 过期派发：profile fence 返回后，以及 can_quiesce 返回后、设置 stopping 前，在原 job.lock 内重新检查取消与截止时间。新增 12 项真实线程测试，相关集 40 项通过；只保证派发前拒绝，不保证已经进入 owner 的操作可撤销。这是具体的生命周期缺口，不是 C01 卡顿或快照超时的已证实根因。

## 冻结回归与构建

`E/full-03/report.json` 九步全部 exit 0，前后均为上述干净 commit/tree，`source_unchanged=true`、`actual_source_verified=true`。

- 主套 6853 passed / 14 skipped / 1 xfailed；baseline 1390、preparation 254、Android 包装结构 44 passed，共 8541 passed。JUnit skipped=15 包含该 xfail；既有搜索真人/动画证据不足的预期失败保留。
- 许可证检查、首页轨道生成检查、两次 source-check 与 63 个产物文件可复现检查通过。许可证检查不等于解决全部许可问题，既有 9 项 unresolved 不变。
- `E/posix-frozen-732c8f2/receipt.json` 与 JUnit 为同一冻结源码，259 passed，零失败/错误/跳过，覆盖全部 14 个 Windows skip 和新增截止检查；与主套有交叉，不直接相加。
- `E/deadline-python-device-1.json` 在盒子独立 Python 进程校验部署 Host 哈希后执行 6 例超时/正向测试，全部通过；仅内存 Host 与 stub owner，无运行中 Host 联系、native 命令或设备文件写入，不计作 live Host E2E。
- 前一 `full-02` 在 838ab56 上九步全过；`full-01` 的 29 个旧 fixture 失败、早期失败和所有设备未确认尝试均保留，不以定向重跑抹去。`package_candidate_matches=false` 表示功能扩展后不同于原包 tree，不是当前源码门失败。

CE 新 native 完成六个受影响 TU、双 schema consumer、完整链接、前代字节级重链和 ABI/依赖核对；19/19 actor 测试来自真实分支抽取与 stub，不是真 decoder 验收。Android 两 ABI 各三个 TU 编译通过，但未完成 schema TU、完整链接、APK、安装或实机；44 项包装结构测试不能替代这些步骤。

## 部署与数据

2122 安装包来自 c4fc5bd；到 838ab56 仅变更四个测试文件，生产源码相同。最终 2123 安装包来自 732c8f2，包含 Host 窄修：plugin/core `0.1.64`、platform `0.1.74`、skin `0.1.17`、library `0.1.7`、start `0.2.89`。source-check 不包含本地 TMDb 项目配置，不能声称其 ZIP 与可安装包逐字节相同。

本地 `review-evidence/ce-20261112-235200-{stage,upgrade}.json` 确认 sequence `2026102123` 升级成功；`E/installed-files-2123-v3.json` 将 1235 个项目自有程序文件与安装包逐个核对，缺失、额外、差异和不安全路径均为零。不包括保留的上游插件或用户数据。前两次读取探针失败保留，第三次只修诊断传输/读取预算，没有重新安装。

索引权威 schema 2→3 已实际迁移。`E/schema3-live-upgrade.json` 核对迁移前既有 14 张表的行数和内容 SHA 全部一致，593 个 typed objects/reviews 和 8 个 review receipts 保留；迁移备份与升级前一致副本的 SHA 均为 `3a0e0500d9fb3e4a7d853541b2d215ea217633179b8514f6f209931ca12f1a7c`。独立副本测试确认旧 schema2 程序拒读 3、恢复 2 后可打开并再迁移。**这不证明设备实际程序 2/3 降级往返**；部署器对不兼容程序回退明确拒绝，不能直接用旧程序打开 schema3。

`E/native-deployment` 的 apply→rollback→reapply 均 confirmed。最终 native 为 `7e88830c9cb24ef22a64a521a035a5ba411d17aeb57af2ba9db874fd9689294c`，回退测试用前代 `591fa655fa6a507145c7fd90163a18eee91266b98fe89315268e1a5bd32be032`。旧 native 仍可打开普通视频，新控制返回 unavailable，不降级成全局控制。原生二进制回退不等于程序/数据库降级。

`E/health-after-addons-2123.json` 和 `health-final-2123.json` 通过：服务 active、NRestarts=0、无 pending transaction，115/百度保持登录、CD2 来源仍在，schema3 integrity=ok。升级前后八项配置/数据哨兵相同；后续试播正常更新 history 摘要，不称最终历史字节未变。最终无活动播放，停在 Home。最终日志末 1 MiB 的 bobbi+error 文本命中 8 行，分类均为 INFO；不能称 8 条 ERROR 级错误，也不据此宣称完全没有运行错误。

## 有限真机功能验收

### 视图与本地目录

2122 实测来源筛选、保存“验收临时视图2122”、重新打开原范围、应用到首页并显示真实作品。native 往返后临时视图仍可找到。随后通过普通管理入口恢复默认首页并删除该测试描述；`E/ui-cleanup-list-final.json` 显示尚无常用视图。仅删除本次创建的筛选描述，原媒体与观看记录未删除；没有宣称所有排序/重命名/焦点路径均通过。

`E/local-catalog-run-1.json` 完成本地 fixture 的登记→单次扫描→query/items→移除本次登记：1 页/1 文件、身份一致、Registry 指纹恢复、媒体 stat 不变。复用产品正常保留策略，测试索引和任务行仍在，故最终 typed objects/reviews 为 594、scans 为 16；不是零残留。没有验证该来源的播放、自建映射、补充关系或手机授权。外置探针最后补的并发登记保护仅经离线测试，不回标为此次真机已覆盖。

### 播放控制

2122 的 `c04-a-off/on/cht/chs/audio0.json` 确认字幕显隐、简繁两字幕轨和唯一音轨重选的最终 applied 及对应状态，不称跨音轨切换。最初 2 秒 seek 的 native applied 后位置未确认，`c04-a-seek.json` 保留失败；播放器时钟不能由 queued/applied 文本代替。

外置探针补最多 4 秒、9 次只读 settle，不重发控制。`c04-b-seek10.json` 第二样本 13490ms 命中目标 13533ms，并超出含余量的自然进度上界；`c04-b-reject-old.json` 确认前一 host/native 实例的旧 expected 在 owner 边界被拒绝，未进入当前 native 账本。该负控不单独证明同 boot 内迟到 native 队列拦截。最初 b-inspect 字幕 TV 投影短暂未就绪，后续样本一致，不宣称全程没有展示延迟。

最终 2123 再次验证 `c04-final-off/on/seek10.json`：字幕关闭/开启均 applied；seek 目标 39773ms，第二样本 39375ms，超出自然进度上界 35454ms，位置跳转已观察。`review9446-final2` exact-stop 对原实例 0.78 秒确认。此轮选源启动使用仓库外较宽只读预算和仅针对明确 unavailable 的有界读取重试，未重发启动/选择；不计作标准起播性能通过。所有控制证据均明确 `phone_path_tested=false`。

## 未解决问题

2122 普通 UI 的银河英雄传说 1988 S01E01、115 1080i REMUX 红例首个 AV 观察 6.807 秒，最大观测停滞 16.815 秒、3 次时钟不连续，`trace_passed=false`，没有观测缺口。旧 native 同片也有缓冲。new2/new3 的读取 TimeoutError、new2 cards 的 PICKER_REPLACED，以及 2123 final1 启动只读 unavailable 均保留为失败/未完成；后续控制成功不覆盖这些结果。

direct 诊断的三次完整 45 秒/90 点中，一次长缓冲、两次正常推进；另一次读取超时未完成。它说明该次长缓冲不以 ShareStream 为必要条件，但不足以确定上游、解码器或 owner 根因。默认 transport 保持 block；未完成的 open_range 等对照不算已比较。Host 截止修复同样不构成卡顿修复证明。

真实手机完整操作、电影三版本独立进度、真实 profile/账号切换、CD2 重挂、自然 next、补充关系交互、全格式长播与程序 schema 降级仍没有完整验收。未做同文件、硬件、网络与冷/热条件一致的 Fuse3/Juku 对照，不能宣称全部追平、最优或已经达到最快。
