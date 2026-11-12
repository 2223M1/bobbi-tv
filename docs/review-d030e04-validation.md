# d030e04 审查轮实施与验收

本记录区分实现、模拟/本地测试、构建产物及单台设备验收。尚在进行的设备用例与修复保留明确状态，不把一项成功扩展成全部平台、网盘或格式通过。原审查包是指导和历史证据，其候选 tree 不等于本轮实际实施 tree。

## 身份与证据位置

- 最新已完成全量回归的代码提交为 `62c820e97ac0c416291e89ea99989383dcbd8b75`，tree `0a1e4eac26995702c3c03037d8fdd2f5a49d84dc`；`full-03` 全程源码未变、前后工作树干净。后续仅验收文档提交不冒充该回归 tree。
- 最终部署组件序号为 `2026102116`，plugin `0.1.59` / core `0.1.60` / platform `0.1.67`；native SHA256 `591fa655fa6a507145c7fd90163a18eee91266b98fe89315268e1a5bd32be032`。已真实完成原生启用→回退至 4177→重新启用 591f。2115→2114 的程序回退是此前独立验收，随后再通过正常签名升级到 2116，不手改高水位。
- 前代 `full-02` 对应 `1a3539e35da8154ef69ee611e16594aafd516108` / tree `98884bbd500a6d75983a74349692ca99aafa0c75` / 2115；`full-01` 对应 `39555a47bef1a8f2bda405261a453295513c6bd8` / tree `ac25000f38649ef57f111ea3638b331d7ddf40a8` / 2114。旧设备结果保留原代际。
- 包外证据根 `E = D:/AM6B-Project/AM6B/tmp/bobbi-review-d030e04-20261112/results`。
- 原生构建/设备证据根 `N = D:/AM6B-Project/ce-native-completion-20261112`；这些目录不写回原审查包。
- 2115 安装文件回执 `review-evidence/ce2023/installed-files-1794455490705497400.json` 核对 1223 个文件全部匹配、零不匹配。`E/health-installed2115.json` 保留 326 个 typed objects、SQLite `quick_check=ok`，无待完成升级事务。
- CPU/RSS 回执分别核对 7 个采样源码文件及 13 个组件清单与各自适用 tree 的 Git blob，并匹配 native、组件序号及进程身份；2114/2115 不混用。这项采样核对与完整安装文件核对是独立证据。
- `E/final-evidence-index-02.json` 是 84 项证据的不可覆盖快照，记录路径、SHA256、源码适用范围及窄结论；稍后产生的 fixed EOF 等回执须单独列出，不宣称已包含在该快照内。
- `E/final-2116-checks.json` 独立核对本代 full-03、安装包、五份升级/原生回退健康回执及首页刷新切片；不把之后的片尾与最终健康结果提前写成通过。

## R00–R07 替换、删除与兼容

| 任务 | 已实现的归并/替换 | 保留与删除条件 | 当前证据 |
| --- | --- | --- | --- |
| R00 | 公共 runtime 持有 Home lifecycle；一个 widget revision worker；standard 摘要异常隔离；离线任务控制；每个未发送子批 JIT preview；百度 JSON 深度明确为 64 | 删除 native 私有 Home 生命周期/重复 worker 入口、首批绕过 preview 特例与字幕死分支；不新增播放 owner | `2b7bc12`、定向用例及三代全量回归；原包基线失败不与本轮修复通过混算；标准/native 账号切换设备全矩阵未覆盖 |
| R01 | scope revision 替代全局写入导致的无关游标失效；typed/native 共享 review/CAS/receipt/undo；CD2 描述按 source+namespace 持久展示 | FileRef v1/MountedRef 稳定键不变；旧观察不能领取新票据，显式重选从头播放才建立新观察 | `bea9a87`、scope/索引负控、Linux 84 项；真实目录分页/namespace 拒绝已测，设备重挂未造景 |
| R02 | CatalogService 唯一 BFS/worker/预算/checkpoint/终态，NativePort/MountedPort 仅负责来源 IO 和权限证明 | 删除 `MountedCatalog.start/scan` 的线程与遍历；保留 `catalog_mount_*` 短 RPC 适配 | 同一提交、本地慢 IO/单飞负控；2114 两次及 2115 ISO 播放中一次部分扫描和精确取消通过 |
| R03 | TV 两类来源进入 `personal_catalog` 同一作品/季/集/原文件 renderer；共享 metadata 缓存与任务观察 | `mounted_catalog_ui` 只保留旧 URL 转译，兼容收藏/历史链接；未有迁移证明前不删别名 | `1a5eb3d`、统一视图/真实装饰器测试；首页焦点与历史分集设备切片，个人片库全层级设备闭环待补 |
| R04 | 手机 query-first/按需单条；通用批次计划归 core review；TV 单条写入统一 `review_entries`，JS 仍唯一 `runPlan`；保存后可明确进入“继续整理本剧” | 100 项显式轮次、每批最多 5 项/8192 字节；原 request_id/CAS/unknown receipt 不迁移；mounted grant 仅固定来源范围，不自动绑定同剧其他文件 | `1a5eb3d`、真实 JS→PhoneManagement→SQLite 桥；旧合成片库完成 100+5 轮，新隔离浏览器 fixture 补到同 ID 恢复及停止后保留 45/100；真实手机/账号仍未验收 |
| R05 | 同实例 native 最终位置观测沿现有 receipt/authority/request 到共用完成判定 | 删除新 host 依赖旧轮询位置的主判定；仅缺新字段的旧 native 保留单一 fallback，最低 native 能力全面覆盖后才可删 | `9317905`、canonical apply/C++ 编译、CE 链接和部署；EOF/历史/next 必须分层看下文 |
| R06 | 47 作品/14 操作统一 `ce_trial_cases.json`，CLI/remote/身份审计共用 | 删除 remote/CLI 重复清单及无调用者一次性 `import_playback_trial.py`；不新增产品缓存/调度器，也不凭本地模型调整传输默认预算 | `e053ce2`、真实解析器/生成程序负控；有限设备 CPU/RSS，配对与延迟项尚未齐备 |
| R07 | 版本/最小依赖/来源清单、原许可证台账与现有构建入口复用；本记录汇总迁移和证据 | 不新增第二套安装/回退；后续修复由整合提交重新生成清单并复验 | 2116 全量回归、双 source-check、1223 安装文件及原生回退/恢复核对完成；程序回退与剩余设备矩阵另列 |

## 已确认的测试与构建

`E/full-03/report.json` 保存每一步实际 HEAD/tree、干净状态、命令、JUnit 和日志。最新四个独立 pytest 进程合计 **7802 passed、14 skipped、1 xfailed，0 failed/error**，共 7817 个 case；分别为 primary 6208、baseline 1296、preparation 254、android-packaging 44。全部 9 步 exit 0。逐 testcase、XML suite 属性和日志末行一致。跳过主要是 Windows POSIX/符号链接限制；预期失败没有伪装成通过。前代 `full-02` 为 7776 passed、14 skipped、1 xfailed，其中 primary 6182，不合并计数。

前代 `E/full-01/report.json` 为 **7760 passed、14 skipped、1 xfailed**，其中 primary 6166。草稿 `final-evidence-index-01.md` 曾因汇总脚本固定读取 full-01 JUnit，把旧数字误用于 full-02；`final-evidence-index-02` 已更正并加入显式 run 路径及 XML/日志交叉检查，原始回执与草稿未覆盖。这是汇总错误，不是测试缓存或重新执行测试。

三代回归各自的供应依赖许可证检查及生成首页检查通过，各自两次 source-check 的 **63 文件可复现**。原包候选不同导致 `package_candidate_matches=false`；`actual_source_verified=true` 绑定的是各次实际实施代码。source-check 不是安装包、账号、设备播放或分发授权验收。

`E/linux-r01-r02` 的 Ubuntu 真实文件系统/SQLite 补测为 **84 passed、0 skipped**，含符号链接逃逸、改根、同名替换、scope/CAS/事务和扫描单飞。挂载记录是合成 fixture，不冒充真实 CD2 卸载/重挂。

R05 canonical 新补丁为 `native/patches/0006-bobbi-completion-observation.patch`，SHA256 `c7647dcbb94a4f2bc6e19f4deff3f3677e835a95b8a6771d10aa42860244fe2a`。generic 锁定 checkout 完整 series apply、3 个 ARM64 布局消费者编译与 C++ helper 正负控完成，状态 `COMPILED_NOT_LINKED`；不能称为已链接 Android APK。CE 完整链接回执为 `N/ce-completion-lw79f6_2/build-result.json`，构建时 `BUILT_NOT_DEPLOYED` 是历史状态，后续真实部署由 `E/native/ce-native2114-apply-1794453861407637100.json` 和 `E/health-installed2114.json` 证明，不覆盖旧回执。

早期 `E/r04/browser-fixtures-final-receipt.json` 记录桌面浏览器连接隔离 localhost 合成片库：100+5 轮确认了 105 个不同文件。其故障 fixture 确认一次真实写入后丢响应，但未观察到浏览器 receipt 查询，当次恢复及取消未验收；该批次与旧文件原样保留，不以新结果覆盖。

独立新批次 `E/r04/browser-fixture-_a3f4rno-final-receipt.json` 使用仓库实际 manage.html/js、HTTP handler、PhoneManagement、CatalogService 和 SQLite；前端文件哈希匹配 `1a3539e`，新会话未复用旧凭据。真实 IAB 页面补测结果为：

- 丢响应后点击“核对原提交”，页面恢复为已保存 1/1。前后 trace 唯一新增 RPC 是同 request_id 的 `catalog_receipt`，新增 apply 为 0；原请求/回执各一行，四张整理表的行数、逐行内容和 canonical SHA256 全部不变。
- 100 项计划运行中点击“停止后续批次”，页面从已保存 40、待核对 5 变为已保存 45、待核对 0、未开始 55。在途最后 5 项保留；9 次 group apply 每次 5 项，之前均有 5 项 ready 的 JIT preview。至少 64.847 秒后无新增 preview/apply，trace 和四张表保持；这 45 项不与此前独立批次的 105 项混算。
- 已独立核对前后及关闭后的五份快照哈希/逐行内容、原始 trace、只读 SQLite `quick_check` 和表计数。点击及页面显示来自执行者浏览器回执，未冒称由此离线核验再次操作 UI；确认对话框呈现未独立验收。
- 执行回执确认通过页面撤销会话、关闭 IAB 测试页并停止精确核对的临时服务，端口无监听，关闭后数据保持、文件未删除。Chrome 新建的 about:blank 页未访问 fixture，其关闭 API 重试仍报 `timeoutMs` 内部错误，**不声称该空白页已关闭**；其他预先存在的页未动。

该新批次发生过点击 CDP 超时和一次内核恢复；未盲目重复提交，以上保留结果由真实 RPC/SQLite 支撑。它验证桌面浏览器的两个合成故障场景，不验证实际手机网络、网盘登录、真实账号或 TV 播放。

## 已确认的单台设备切片

- 2114 完成组件/native 部署，2115 在同一 native 上完成组件更新与安装文件核对，旧账号/本地数据未据此重置。2115 更新回执为 `review-evidence/ce-20261112-115000-upgrade.json`，冻结输入为 `review-evidence/ce-deploy-runs/20261112-115000.json`。只证明这一台设备，不外推 arm64/Android 或全部账号能力。
- `E/r01-r02-device/02-scan.json`：真实挂载来源扫描 54 页/485 项，保留 312 个本地视频索引；精确 task 取消后 `canceled / CANCEL_CONFIRMED`，活动扫描数 0。连续两页同 revision、无重项，错误 namespace 拒绝，SQLite `quick_check=ok`。这是取消的部分扫描，不是整树完成。
- 取消请求至观察终态约 0.093 秒；计划观察 15 秒，末次状态查询变慢使总计 18.443 秒。不能写成硬 15 秒上限，更不能声称可抢占阻塞 FUSE 系统调用。
- 2114 第二次 `E/r01-r02-device/03-scan-paired.json`：56 页/525 项/326 个视频，`canceled / CANCEL_CONFIRMED`，活动扫描数 0，SQLite 正常。取消请求至终态 0.115 秒、扫描请求至终态 15.346 秒；仍是取消的部分扫描。
- 2115 的 `E/r01-r02-device/04-iso-scan.json` 在 ISO 播放期间扫描 42 页/363 项，已有 326 个索引对象不变；`canceled / CANCEL_CONFIRMED`、活动扫描归零、SQLite 正常。取消请求至终态 0.120 秒、扫描请求至终态 15.369 秒；这是新增的本代际切片，不改写前两次结果。
- `E/ui-home-nav-full2114.json` 记录首页逐行上下移动；继续观看的全剧入口与分集进度分别留在 `E/ui-all-episodes-ready.json`、`E/ui-episode-progress.json`。这些成功切片不能替代空首行、删除当前项、账号切换、标准/native 全组合。

## R03 真机追加发现：首页迟到刷新

2115 的 `E/ui-mounted-begin2115.json`、`E/ui-mounted-down2115.json`、`E/ui-mounted-row2115.json` 记录 ISO 停止后已从首页导航到继续观看行；相隔 27.434 秒的两次快照中，焦点由 9810 变为 9711，后一探针在发键前因 `FOCUS_CHANGED` 停止。稀疏快照没有定位故障帧，也不能独立排除期间其他输入。源码分析及确定性 C++ 负控复现了可导致该现象的原生机制：`CDirectoryProvider::Update` 在 DONE 帧跳过新条目的 `UpdateVisibility`，首次 Fetch 返回暂时空列表，`CGUIBaseContainer::CanFocus` 随之为假，窗口可退回默认控件。已审查的 Python 刷新路径只发布 revision，没有重建首页或主动 SetFocus；真机修复表现须另行观察。

独立审查还确定性复现了后台 `OnJobComplete` 在 Update/Fetch 两次持锁之间替换条目的交错：只修改 Update 时会先发布 0 行，下帧才出现 1 行。`native/patches/0007-bobbi-directory-visibility.patch` 因而在 Fetch 原有锁内对实际即将发布的每个条目先计算可见性，再输出；Update 保留原有检测路径。没有新增焦点轮询、缓存、线程或账户例外，也没有在后台回调线程执行 GUI 可见性求值。

最终 12 项 C++ 用例覆盖真实 production 回调、provider/Fetch/容器的 DONE、路径重排、空结果、账户撤销与完成交错；原始逻辑和 Update-only 两个负控分别在预期点失败。Generic 完整 series 应用与相关编译通过，但不冒充 Android 实机。CE 完整链接回执为 `D:/AM6B-Project/ce-native-home-focus-20261112/ce-home-focus-hc5i_mgb/build-result.json`，SHA256 `e67b4d8b108157428286a93a74bb0407a0133621753785681257133d0829f90f`；候选为 591f，仅重编 DirectoryProvider，前代 4177 字节级重链、四份完成判定相关档案、ABI 与协议均未改变。早期 6a755 候选只修正常 DONE tick，从未部署；历史回执保留。

实际新原生部署后，正常 ISO 播放→Stop→首页加载中只发送一次 Down，此后 40 秒只读观察。`E/ui-home-refresh-2116-01.json` 有 42 个样本，观察到 loading→finished，焦点保持 9810、路径保持，结果 `FOCUS_PRESERVED_ACROSS_REFRESH`。它不覆盖所有空行/删项/账号切换组合，也不能排除两次采样间的瞬态；探针未内嵌二进制哈希，代际由前后维护/健康回执限定，不与 C++ 单帧测试混为一种证据。

## R05 片尾、历史与 next 分层证据

2114 的 8× 正控暴露 history progress 过冲 103.6%；该原始结果保留。修复提交 `1a3539e` 随 2115 部署后，已有以下同 request/native 实例证据：

| 回执（位于 N） | 可确认结果 | 不能扩大的结论 |
| --- | --- | --- |
| `completion-fixed8-eof-1794455782140910900.json` | 真实速度 8；有效 NATURAL_EOF；exact history 从未完成变为完成，current/total 为 1444.729/1444.945 秒，progress=100.0 | next 日志仅 `capture_interval_only`，不是独立精确归属证明 |
| `completion-fixed32b-eof-1794456189424735400.json` | 真实速度 32；有效 NATURAL_EOF；exact history 从未完成变为完成，current/total 为 1444.929/1445.144 秒，progress=100.0 | next 同样仅区间归属，不声称所有下一集路径通过 |
| `completion-fixed1-eof-1794455913532775900.json` | 真实速度 1；有效 NATURAL_EOF | 抓取以 `read_failed_no_further_control` 结束，history_after 仍是未完成读数；只见 reconciliation begin，历史/next 未收齐 |
| `completion-fixed32-eof-1794455830483088800.json` 及 `completion-fixed32-observe-1794455853589035300.json` | 早一轮 32× native_event 有有效 NATURAL_EOF | 后读历史槽已被下一 request 替换，不能由新槽反推旧实例最终历史；不以 fixed32b 覆盖这次不足 |

上述 8×、早一轮 32×、1×、32×复测分别为同系列第 1、2、3、4 集，不能称同一文件速率配对。两次成功历史切片确认了过冲修复，尚不等于完整 EOF/history/next 矩阵通过。

2116 追加 `N/completion-final1-eof-1794459283770350300.json`：通过首页继续观看→选源起播第 5 集，在 1× 尾段收到同 request/native 实例的 `NATURAL_EOF`，观测 `valid=true`、age=117779 μs、position/duration=1446564/1446779 ms（距尾 215 ms）；exact history 从未完成变为完成，current/total=1446.564/1446.779 秒、progress=100.0。探针随后遇到 RPC 读取失效而停止控制，状态仍保留 `read_failed_no_further_control`；已收取的精确 native 事件与历史读取支持这一窄结论，不把探针全流程改记无错误。next 日志仍只有 `capture_interval_only`，不声称已验证精确 owner handoff。

`N/completion-finalnext-snapshot-1794459306659102700.json` 观察到新的 request/native 已播放；新捕获确认是第 6 集。`N/completion-finalstop-stop-1794459336906543600.json` 对新实例执行 Stop，TCP 事件及 authority 均为 STOP，history 保持 completed=false、progress=1.6，结束为 `terminal_idle`；这是正常 Stop 负控，不称近尾 Stop、账号撤销或全部负控矩阵通过。旧 trial 辅助器复用历史会话时返回 `USER_CHANGED_SELECTION`，选源数量更新时一次 UI 探针返回 `FOCUS_CHANGED`，以及起播后只读 UI 探针拒绝 `PLAYBACK_ACTIVE` 的回执也保留，不把这些守卫退出冒充功能测试成功。

2114 的 `completion-paused-pause-1794454967462834400.json` 在 53 个速度 0 样本中未观察到终态/next，history 保持未完成。`completion-stopped-stop-1794454996633813200.json` 与后读 `completion-stopped-observe-1794455010861485100.json` 确认 exact STOP、history 未完成，不能重标为 2115 全负控。Seek/反向、换源、账号撤销、迟到旧实例、输入 read_error/提前 EOF 等仍须各自证据。

## R06 有限性能证据

2115 的普通视频和 ISO 控件测试使用 `D:/AM6B-Project/ce-control-20261111/probe_controls.py`，控制前固定正在播放的文件与 native 实例。ISO《让娜·迪尔曼》的 `controls-basic-1794456320953228300.json` 证明暂停短窗位置固定、恢复时钟递增，绝对前跳及恢复原位在后一个约 2 秒采样点到位。`controls-verify-speed-1794456361717034900.json` 证明电视菜单方向键/确认键能改变实际 speed；其 `checks_passed` 不检查反向时钟，不能据此声称快退已验证。`controls-transport-1794456446710072500.json` 的 2× 时钟在 2.128 秒内前进 4.006 秒，恢复 1× 后在 2.126 秒内前进 2.045 秒；反向短样本出现正向跳变、相对 Seek 的 1 秒读数未证明生效，均保留未证实状态。`controls-tracks-1794456395969618800.json` 的字幕关/开/换轨/还原通过，ISO 仅单音轨。`controls-stop-owned-1794456672246653200.json` 确认同实例停止，随后无活动播放器。这些是短段控制结果，不是整片、所有格式或暂停半小时预加载验收。

2115 真实 CD2 入口完成首页→来源→全部作品→具体原文件→重新核验并从头播放，回执为 `E/ui-mounted-*2115.json`。原文件菜单可打开“整理这个原文件”，进入“原文件与建议”后返回相同文件，未提交任何作品映射。播放《Samurai Champloo》第 4 集的 `controls-snapshot-1794456989296039000.json`、`controls-tracks-1794457042778932800.json`、`controls-stop-owned-1794457082550893100.json` 证明正常时钟、字幕切换、英/日双音轨切换并还原及停止后返回原文件列表。该路线使用既有 standard 播放 owner，native request_id 为空不是新的 cinema 会话。MountedRef 明示从头播放且不继承旧路径精确进度；它没有冒充 FileRef 的各文件进度支持。真实重挂、三版本进度和完整季集层级仍未覆盖。

2114 的 `E/r06/perf-home-summary.json`：暖态首页 30.002 秒，RSS 31 点为 524.57 MiB；CPU 完整区间 30 个，进程中位数 28.00%、P95 31.00%（单核 100%），整机中位数 4.88%、P95 5.43%。不是冷启动。

首个 `home-scan-01` 与真实任务 running 仅重叠 0.498 秒，RSS 1 点 530.34 MiB，完整 CPU 区间 0 个，median/P95 为 null；不能用整个带 scan 标签的 30 秒归因扫描负载。

2114 的 `E/r06/perf-home-scan-02-summary.json` 补到真实 observed-running 重叠 15.107 秒：RSS n15、840.098–840.254 MiB；CPU 完整区间 n14，中位数 64.490%、P95 98.005%，整机 12.075%/18.089%。n14 的 nearest-rank P95 即样本最大值，不是稳定总体分位数；任务结束后的片段不是另做的受控空闲基线，不能把早期首页与此时 RSS 差额全部归因扫描。

2114 的 `E/r06/perf-galactic-idle-summary.json`：普通视频标签短窗口 55.003 秒，RSS n56、636.375–1067.535 MiB，末值比首值高 428.332 MiB；CPU n55，中位数 114.956%、P95 173.141%（单核口径），整机 20.962%/32.035%。

2115 的独立 `E/r06/perf-galactic-idle-2115-summary.json`：55.004 秒，RSS n56、576.531–1059.691 MiB，末值比首值高 466.164 MiB；CPU n55，中位数 111.970%、P95 169.005%，整机 20.797%/30.106%。这是另一次进程采样，开始时进程已运行约 124 秒，不是冷启动；不与 2114 合并或据此声称优化提升。两次短期 RSS 上升均不能独立判泄漏，仍需可比重复会话、缓冲及停止后释放证据。

2115 启动 select 抓取 `review-evidence/ce-new-work-galactic_heroes-select-1794455580829461200.json` 返回 `PLAYBACK_OWNER_UNAVAILABLE`；稍后 `N/completion-fixed8-snapshot-1794455659222166700.json` 的同 owner AV 仅证明后来已播放，不能补出精确 first-AV 延迟。

2115 另有同 ISO 播放实例的顺序片段，见 `E/r06/perf-iso-pair-2115-summary.json`。两段 PID/boot/start tick、7 个采样源码文件、13 个组件清单和 native/序号均匹配实际 2115 runtime：

| ISO 片段 | 时间与样本数 | RSS MiB min–max | Kodi 单核 CPU median / P95 | 整机 busy median / P95 |
| --- | --- | --- | --- | --- |
| 无扫描播放 | 55.002 秒，RSS n56 / CPU n55 | 1123.219–1145.898 | 83.969% / 124.005% | 15.078% / 26.162% |
| 扫描 collector 内真实 running 交集 | 15.092 秒，RSS n15 / CPU n14 | 1126.836–1138.813 | 106.502% / 134.026% | 19.778% / 25.000% |

控制回执位于 `D:/AM6B-Project/ce-control-20261111`：`controls-capture-1794456304777613900.json` 记录 ISO 与 request/native 身份；`controls-observe-1794456558580193600.json`、`controls-observe-1794456599688119900.json`、`controls-observe-1794456641013012500.json` 各含 5 个经相同文件/native guard 的时钟点，均为 1×、caching=false 且媒体时钟递增。第一窗在无扫描 CPU 采样结束后，第二窗只有 4 点落在保守 running 交集，第三窗在扫描 collector 结束后；不是连续每秒监测，也不证明整部 ISO 无卡顿。同一实例的前后位置不同，未随机化或重复，不能把指标差异全部归因扫描。

P95 为 nearest-rank。collector 不采精确首帧/seek/遥控延迟；trace 只有稀疏事件，`fetch_end` 字节与 GET begin 不能冒充精确上游流量/Range 次数。已有同 ISO 实例顺序片段，但受控重复对照、冷/暖对照及输入延迟仍未齐，不作性能“最佳”或优化完成结论。

## 升级、回退与未覆盖门

2116 签名包 SHA256 为 `ffa43b768bfa6e655652af74128b9521865a82ca57f443cc6025b7f28eac033d`，来源为本文开头的冻结提交；生产验证器与独立公钥验签、22 组件内容核对均通过。`review-evidence/ce-20261112-124600-upgrade.json` 记录正常升级，`review-evidence/ce2023/installed-files-1794458812082057800.json` 核对 1223 个程序文件全部匹配。更新前后 7 项用户数据/config 摘要一致，未重新登录或改 CD2 挂载。

原生维护回执位于 `E/native`：`ce-native2116-apply-1794458839878144800.json`、`ce-native2116-rollback-1794458884084695500.json`、`ce-native2116-reapply-1794458926468437600.json`。三步通过原有维护状态机；`E/health-installed2116-native.json`、`E/health-2116-native-rollback.json`、`E/health-2116-native-reapply.json` 确认实际运行文件依次为 591f→4177→591f，组件代际持续 2116，7 项用户数据/config 摘要均不变；runtime ABI 描述随原生版本切换并在回退时恢复，不把该预期变化误判为用户数据丢失。

最终 `E/health-final2116.json` 与 `E/r01-r02-device/05-final2116-inspect.json` 确认首页空闲、无活动播放/扫描、服务运行、无待完成更新、326 个 typed objects 与 SQLite quick_check 正常。账号、片库、准备任务及配置摘要保持；历史摘要因上述真实测试播放正常更新，没有回灌旧数据库。最终日志归类单独记录，不以粗略的 error 字符串计数推断崩溃。

最终日志的 43 条 `bobbi`+`error` 字符串命中全部为 INFO，0 traceback。42 条是本地下游 HTTP 读取消观测，15 个请求最终均 canceled（10 个 SHARE_STOPPED、5 个 delivery_incomplete），没有 failed 终态；其中 9 条中间 response/OSError 后也都进入 SHARE_STOPPED 取消终态。另 1 条是提供商汇总的空 error 字段。脱敏逐类回执为 `D:/AM6B-Project/AM6B/tmp/bobbi-log-final2116-diagnostic-20261112/classification-04.json`；它没有揭示本轮未修产品故障，但不能仅由 socket_error 定位到某一次 Stop/seek。旧代第三方字幕网络超时回执仍保留，不因本次日志为 0 而改写。

收尾只改本文、片库契约与能力矩阵，没有改变 `62c820e` 的 addons/native/tools/tests/源码清单。文档相关发布、许可证与维护检查另有 `E/closeout-doc-checks.xml`，81 passed；不重复加到全量 7802。提交范围的敏感信息扫描及 `git diff --check` 另行通过，不替代分发许可。

索引仅加 scope revision/typed observation 等辅助表，user_version 仍为 2、投影 schema 为 5；原 objects/typed_objects/reviews/history 和稳定键保留。投影重建失败在事务内回滚。支持 schema 2 的旧版本可重建读取投影，不支持者拒绝写入；不得通过删除索引来假装回退成功。

真实带数据程序回退已执行：`E/rollback-preflight-2115.json` 核对 13 组件、1608 个备份文件；`review-evidence/ce-20261112-115000-rollback.json` 记录通过原维护机制回到 2114 的程序版本，同时保留 sequence=2026102115 防降级高水位。`E/health-pre-rollback2115.json` 与 `E/health-rollback2115-to2114.json` 中账号、历史、片库、准备任务、advancedsettings 与 torrent 配置摘要全部相同；115/百度的本地保存登录态仍为 authenticated，未重新向远端验票，326 个索引对象保留且 SQLite quick_check=ok。原生仍为 4177 前缀，不操作 CD2 挂载。回退后的 1223 个安装文件与原 2114 签名包逐字节匹配，见 `review-evidence/ce2023/installed-files-1794457343990921000.json`。这不替代更早 schema 1 或所有历史版本的回退矩阵。

原目录入口、旧 mounted URL、115 PreparationQueue 与账号 Registry 保留；普通旧观察不能跨挂载继承进度或播放许可。旧 native 的完成 fallback 只服务缺少新字段的兼容期；撤回消费者时回到保守完成策略，不放宽 Stop/账号撤销边界。组件及 native 回退必须走原安装/更新机制并核对目标代际，不直接覆盖用户数据库或挂载配置。

最终仍须逐项记录，未执行则保持未覆盖：

- R00/D01、D03、D04、D12：标准/native 冷启动及账号变更，真实手机大批量/冲突及真实网络中的恢复与取消，真实 FUSE 阻塞与掉线，字幕 Off/音轨/版本及各 adapter 用户操作矩阵。桌面合成 fixture 的恢复/取消与 2114 单次 Stop 均不替代全矩阵。
- R01/R03/D02、D05、D09：真实重挂/改根/同名替换；个人片库作品→季→集→多版本与各文件进度；空行/删项/窗口重建及迟到 metadata。
- R05/D06–D07：同一文件速率配对及精确归属的 next；Seek/反向、换源、账号变化、迟到旧实例、输入 read_error/提前 EOF。2116 新增的 1× exact history 和 Stop、2115 的 8×/32× history 与 2114 暂停/Stop 各保留原代际；不可用时基不列作成功正控。
- R06/D08、D10：ISO 首帧/seek/播放取消；已取得同 ISO 实例顺序空闲/扫描片段和扫描取消，但受控重复对照、冷/暖与输入延迟仍未齐，精确网络量当前不可得。
- R07/D11：2116 修复回归、安装身份及新原生回退/恢复已核对；此前 2115→2114 程序带数据回退独立保留。更早 schema 和未覆盖的数据/旧 URL 组合仍待验收。Android 实机及远端正式发布不由本地私有包签名通过自动获得。

分发授权保持独立门。`licenses/THIRD-PARTY.json` 仍有 9 项 unresolved：`script.module.jurialmunkey`、`script.module.infotagger`、`plugin.video.bobbi`、`script.module.bobbi.platform`、`script.module.bobbi.core`、`script.module.bobbi.mdsub`、`script.module.bobbi.catalog`、`skin.bobbi.cinema`、`resource.uisounds.bobbi-modern`。皮肤与逐字体哈希在 `licenses/skin-reference-evidence.json`，其状态仍是证据而非分发许可；Juku/Fuse3 结构借鉴和测试成功都不消除这些门。
