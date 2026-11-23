# Bobbi Architecture Convergence

最新离线候选冻结为 `42a3729` / sequence `2026102136`，见 [validation-42a3729.json](validation-42a3729.json)。已提交启动事实的原范围有限重读、管理菜单动作入口、共享安装／回退容量保护，以及不触发解压恢复的只读诊断。保留当前首页和选源；native未改、未重建。

三组主回归精确去重 11287 项，Windows 11264 通过、22 普通跳过、1项既有预期失败；Linux 435 次执行全部与主回归重叠，并逐项补齐所有普通跳过。Android另有72项打包检查通过，不代表编译、链接或真机。22组件与两次独立source-check经核验；带冻结所有权清单的图为2381文件、160824分类边，其中88964边仍未解析。唯一配置的静态导入边界规则无命中，不能外推为所有架构缺口已消除。

2136尚未上传或部署。精确新签包的只读空间预算需要745897984字节、可用563466240字节，缺约174 MiB；等待用户确认是否仅清理两份已核验可重建解压缓存。本切片未删除文件、停服或播放。设备仍是下面的2135，不能把候选离线通过写成新菜单、启动事实、精确历史或115性能已在真机验收。原110场景和历史证据不改，整体计划仍未完成。

最新已部署产品为 commit `35b9d61ebb9429f5b15e3b882efbfc9c022bd6ad`、tree `1bb4ba7c7a683a177bba9821035ed534ebc169b4`、sequence `2026102135`，见 [validation-35b9d61.json](validation-35b9d61.json)。失败弹框前清理、固定下载错误提示和115私盘下载／媒体请求的 Chrome 上下文已部署。一次真实私盘原文件播放到达同实例 AV_STARTED，11个短时采样点走时45.870→56.798秒且未观察到缓存等待；但启动媒体事实读取报 FACTS_ABSENT，精确停止历史未证实，停后健康保留两条真正的 error 级目录错误。整体计划和产品验收仍未完成。之后的媒体事实重读、容量预检等源码不能继承2135证明。

2135定向回归470通过，没有重跑全套。两组source-check各63文件相同，三组构建和22组件签包经独立校验。第一次升级返回OSError并恢复2134的1262个owned文件；当时仅约97 MiB可用，但未保留errno，不能断言已证明ENOSPC。仅清理四份已验证、可由保留原包重建的bootstrap解压程序副本，共764472469字节；回退备份、原包和用户数据均保留。新run部署同一2135签包成功，1262个owned文件匹配、八项升级哨兵相同；native未改未重建。原Stop命令已applied且不得重发，历史hash变化不能替代精确落盘证明。

以下全套、分享卡顿和旧私盘失败均属于2134历史记录，见 [validation-2acdba8.json](validation-2acdba8.json)，不改写为新版结果。

三个主回归精确去重11116项，Windows 11094通过、21普通跳过、1既有预期失败，无失败或错误。Linux补充1274次执行全部与Windows精确ID重叠，21个Windows跳过均有同case Linux通过；不重复计覆盖。两组source-check各63文件逐字节相同，22组件签名包和0.2.99入口通过校验；设备1262个owned程序文件匹配。升级前后八项哨兵相同，native未改未重建；升级后native PID15321、service PID15313，在分享播放停止后均未重启。哨兵一致不代表所有数据或当前profile绑定已验收。

2134分享源115的1Hz启动诊断再次复现卡顿：41点中2点无native、7点OPEN、32点AV_STARTED，39个绑定点身份一致、无读取失败；首次AV观测为Select后9.007306秒。时钟3.407秒、speed1、Caching=true连续18.002140秒，期间解码计数141→238，后段计数亦不变，随后走时恢复。这不是普通trace验收或5冷5暖，也不能只归因高频探针。原Stop取得applied回执，未重发；健康仍为attention_required，2条宽泛error匹配均为INFO来源查询日志，不能删除原查询失败。attempt1的选择执行不确认、页面代际变化，以及attempt2的启动/首次cards失败均保留。

115私盘真实UI已走通根目录→电影目录→现有MKV→“播放原文件”；一次选择后出现失败弹框，未进入原生播放。关闭一次弹框后原请求cancelled=true，未发全局Stop。目录可用不等于原文件播放或媒体事实落盘通过。独立只读解析在目录和元数据一致后，于获取下载地址时报PAN_REDIRECT_REJECTED；后续一次分类观察为302、HTTPS绝对地址、非已登记API路径，未跟随跳转。reference app 0.81的原始接口与当前代码相同，不能据此猜改接口。两次独立观察均不反推原UI已丢失的错误。

只读设置查询确认普通文件缓存为mode4、256 MiB、5倍读取因子和512 KiB块；不等于实际文件已使用缓存或达到该吞吐。ISO另走原生页缓存。设备的forwardprefetchpages=0来自11月10日的全局ISO临时措施，文件哈希保持一致，原测试走Bobbi分享传输而非CD2，亦不是外部默认。当前未调整参数；CD2 ISO和半小时暂停仍需独立对照，不能用普通MKV结果代替。

历史回执保留原身份与失败记录，见 [a5155c0](validation-a5155c0.json)、[629597c](validation-629597c.json)、[1eb2e58](validation-1eb2e58.json)、[e58718b](validation-e58718b.json)、[ff0422c](validation-ff0422c.json)、[319e398](validation-319e398.json)、[55b4f9b](validation-55b4f9b.json)、[2b263bb](validation-2b263bb.json)、[a725b84](validation-a725b84.json) 和 [ba4c238](validation-ba4c238.json)。旧代窄OSD通过不回标为2133完整验收；5冷+5暖、110系统场景、ISO、完整回退恢复和Android仍未完成，不宣称已修复、最快或可靠P95。

## 产品边界与唯一入口

Bobbi 是使用 Kodi 原生播放的统一影院客户端。保留 Bobbi 首页、季集和选源习惯；公共元数据、网盘、本地目录与媒体服务器沿同一索引、审核和播放合同接入。服务器提供转码，Bobbi 不自建第二套转码服务。缺少同源下一集时进入选源，不静默跨源。

```text
TV / 手机 / 皮肤
  ├─ 公共详情、人物、合集 → 同一有界请求/卡片投影
  ├─ 来源/作品/季/集/文件 → Host → CatalogService → MediaIndex
  │                                 └─ 同一扫描生命周期 → 来源协议适配器
  ├─ 整理预览/提交/撤销   → 同一审核事务与回执 → MediaIndex
  └─ 播放/音字幕/章节     → 播放实例权威 → native 或 standard 适配器
                                      └─ 捕获 profile 的历史 writer → PickleDatabase

Registry 负责来源与视图；MediaIndex 负责文件观察/描述/审核；历史负责精确观看记录。
三者共享身份与明确接口，不合成巨型数据库或万能服务。
```

播放查询只读。`command_id + expected` 固定于原播放，丢响应只查原回执。手机授权内的恢复提示不是第二回执权威。native 与 standard 明确能力差异；原生协议缺失不能偷偷降级成全局播放器命令。

同路径替换保留逻辑文件和人工整理；撤销旧文件观察、票据与自动续播资格。作品、剪辑、逻辑文件、文件观察、来源、账号、profile 和播放实例不得混用。片段、音字幕、进度不能仅凭同作品名继承。

## 审计基线和附件对账

- 基线 commit `6cd23ee627977139e16ee7b37440665f436393cb`，tree `3aff431f1aec01e2e7a7110b7a0b5fd4cc113a94`，2227 个 tracked 文件。
- Grand-Convergence ZIP SHA256 `cd13d5e281a7e7ab36082458a3b1fcced7d8eea99ee873dd7556069777be11b5`。
- 6cd23ee execution ZIP SHA256 `017bb6e38fb551d17e41418b60e3b5bfeaf7e0b9f0c68bc4b1441c7e94cf22dc`。
- 候选补丁 SHA256 `e758576a5e4f5334e6228c2a9fd0fb324fb75c68aed30b9cc4d03e12eefe860c`。核对后承接修复，不承接旧 source-inventory，也不把候选的原测试结果算成本轮结果。
- 附件的110个场景逐项保存在 `interaction-coverage.json`；其中同路径换ID、无安全游标的断点续扫等叙述以用户确认的合同修正。映射存在不等于场景通过。
- G0–G9均保留在实施路线中。G0图工具、G2公共详情、G4控制、G6历史、G8回退/构建已有代码切片；G1性能、G3完整版本事实/偏好、G5完整片段策略、G7服务器/115私盘、G9最终评分仍未验收，不能将这些大项整体标为完成。

## 图的证据等级

最新已核验冻结图属于 `2acdba8`，两次graph/overview导出逐字节相同，graph SHA256 `b94c68c5e19ad37b156a9436390658ccef0db7e33ba9de596866f88c4d842ce7`。2374个受版本管理文件、1795个加载文件、1488个Python文件、64044节点和159480边；125条显式所有权锚点匹配冻结源码。保留88176条unresolved边、20个SCC候选和3个模块碰撞，解析诊断和声明边界发现均为0。完整路径与hash见当前validation。core/platform已登记反向import例外清零仅证明声明的导入边界，不证明动态调用全部已解、运行时无债务或整体profile-safe。后续源码不归入这张冻结图。

历史冻结图、当时的反向依赖和后补映射保留在各自 validation 文件中，不回写为当前状态。最新源码的 ownership-manifest 与历史冻结清单可能不同；复核旧图应读取对应 commit 的 Git blob，不能对当前文件套用旧 hash。

`tools/architecture_graph.py` 从 Git 对象读取不可变输入，覆盖 Python、JS/TS、XML、HTTP、JSON-RPC/native 注册候选、插件入口和兼容别名。`ownership-manifest.json` 补充人工核对的状态、存储、生命周期和测试边；`dependency-debt.json` 与边界测试拒绝新增或隐瞒反向导入。静态候选、SCC和测试映射不代表运行时可达、死锁或验收通过，完整格式见同目录 README。

基线 `6cd23ee` 图含138603条边（6941 confirmed、31539 candidate、24000 external、76123 unresolved），1368个Python AST包含工具、测试及第三方，不等于第一方模块数。66个全仓兼容别名不等于66套重复实现。两次导出字节相同，graph SHA256 `91a93fb97c0abaec761dc20aa580a2ad8f0fb04668c4c998cfc4c1f05343bda8`。

## 已替换的活动职责

| 原路径 | 当前唯一职责 | 保留/删除理由 |
|---|---|---|
| Extras伪AI推荐第二页独立线程 | 真实推荐/相似关系卡片与有界请求 | 已删除伪AI线程及失效皮肤栏，不再将TMDb第二页称AI |
| Extras/人物/合集重复卡片和逐卡持有查询 | relationship请求、卡片投影及单批持有查询 | 详情窗口仍有展示生命周期，目录入口仍有分页，不合并成万能UI |
| platform运行时自行导入插件全局历史 | portable_runtime显式注入捕获根的FileHistory | 缺适配器明确不可用，普通播放不受可选历史失败阻断 |
| 固定profile存储导入Kodi UI/cache全局 | PickleDatabase显式根纯存储 | 仅旧前台无参构造保留Kodi路径适配；移除未使用的addon.xml定位 |
| core通过平台读取账号格式规则 | core/account_scope纯契约 | platform保留同对象重导出；活账号/凭据仍只由AccountManager授权 |
| 部署工具单独做catalog兼容检查 | 产品与运维共用catalog_compatibility | 电视安装、回退、恢复和激活同样检查所有登记profile及WAL |
| 手机页内丢响应后只防重复、不恢复编号 | 授权会话保留最多8个原命令核对提示 | reload/另页不重发；终态来自播放owner，撤权清理提示 |
| 修改上游 skinvariables 承载 Bobbi OSD 控制 | Bobbi 自有 osd.py 与 osd_streams 入口、同一 Client | managed 的 seek、音轨、字幕、章节及新增暂停/恢复/停止共用实例权威；确认框固定原scope，refresh只查原回执。新控制须匹配原生扩展，旧binary不走全局降级。上游不修改；完整设置及任意tempo/trickplay仍未统一，普通Kodi、音乐和LiveTV保留明确的非原子原生交互 |
| core 图片缓存自行寻找当前 profile | platform/artwork 在展示边界注入固定根与撤销检查 | core 不导入 Kodi/platform，无根时只返回规范公共图片 URL；不增加缓存或 worker |
| source_library/sharelib/共享失败在异步执行时发现当前账号 | 显式 Store/SourceLibrary/ShareReader/CatalogContext | search 提交前捕获，SourceSelect 到 Resolver 沿用；失败不重绑新 Host |
| prepared index/retry 与 native 字幕 lookup 重新查运行环境 | 请求级 PreparedSession 固定 profile、账号与 Host transport | lookup 在 owner 线程捕获；同 receipt 的失败、取消及旧 worker 结果不晚绑定新账号；与驻留 Session 分开 |
| 驻留 preparation 的资源/字体读取寻找当前 playback transport | Host 向 Session 注入实际 owner_call，ProtectionLane 显式接收 read | lease 检查包围读取；字体观察不持有 account CAS，只有最终 SQLite COMMIT 经过原 lease 门；关闭先排空 IO 再释放锁 |
| 播放入口、claim、重试、取消及后续入口重新捕获 transport | 独立 playback Client 传递同一 profile/Host 绑定 | Client 不拥有播放状态、不缓存选择，也不要求可选 PreparedSession 或云账号；失败捕获不重试发现新 Host |
| library Source/Item 纯校验定义放在 platform | core/library_contract | Registry 保留在适配层；原导入同对象重导出，不创建第二来源库 |
| native/local/mounted/network 扫描各自判断 profile | 同一 CatalogService 固定 profile_current + 永久撤销闩锁 | 每页返回和发布边界共同检查，回调在锁外；旧终态只排空到原数据库 |
| ProfileBinding 对同次观察重复规范化路径 | 每次 live observation 每根只 resolve 一次 | 仍实时重读 mapping 和符号链接目标；观察到切换或失败后永久撤销，不缓存“当前 profile” |
| server scope 轮询阻塞 Registry 或发布过期观察 | 同一 Accounts 使用一次只读、无 busy 等待的 Registry 观察及 serial CAS | busy/未知不伪造登出；强授权仍以新鲜配置 CAS 失败关闭。只消除 SQLite busy 等待，不保证所有磁盘、Plex/profile 回调延迟有界 |
| 导入片段与花絮另起存储或遗漏数据 | 同一人工描述 v1/v2/v3 + review 事务/回执/撤销 | 每项 savepoint 阻止半写；精确父关系重验，旧观察不续签 |

早期收敛记录为 cinema 的61个纯别名保留兼容、16个生产文件中的62个内部导入直达 core。`55b4f9b` 中纯别名为57个；`preparation_client`、`playback_ipc`、`playback_request`、`prepared_protection` 四个入口已改为显式绑定的兼容装配包装器，不再是同模块别名，也不新增业务状态权威。旧保存URL、插件导入和升级兼容需逐项证明才移除；没有静态调用也不单独构成删除许可。旧 ActorInfoWindow 及 actor_info.xml 已删除：全仓无导入/构造/XML装配入口，PeopleClient 的旧保存URL入口明确转入已有分页人物目录，执行回归验证URL兼容。旧两条独立线程不再随包分发；可从本分支基线Git恢复。

core preparation/playback IPC 的 platform fallback 已移除，缺显式注入即失败。`pan_playback.py` 已在入口捕获 transport，将固定 call/Client传至standard select/cancel及后续步骤，不再属于旧动态 `runtime.call` 债务。绑定合同与设备交互验收仍须分开，不能以native Client或本地standard测试替代standard全链实机验收。

## 来源和版本的当前边界

当前源码已移除 core `runtime_paths` 的进程全局 profile 和 Kodi/home 回退，入口显式注入字幕路径、导出能力与搜索准入。搜索复用固定 profile 的既有 SQLite/L1 后端和设置快照，关闭等待真实工作与回调排空；不再为每轮重试创建连接。配置不可读或损坏时拒绝默认写回，撤销后的缓存写入及账号锁等待后的旧提交被拒绝。原生 ABI/存储格式保持，普通结果过滤沿用同一 getter。具体所有权与剩余边界见 [运行时收敛说明](README.md#runtime-path-and-search-ownership-boundary)。这些源码不属于历史2130验收；debrid认证、部分来源质量过滤和第三方scraper内部依赖仍未统一，空依赖例外清单不能代替系统闭环。

115 私盘使用原 AccountManager 的薄适配，不新增凭据存储。目录、文件重验、Chrome 原文件地址接入既有 FileRef/PanService/CatalogService/Range/FileHistory，ISO 仅对有原文件 Range 能力的115开放。私盘账号 scope 与原分享播放 scope 明确分流，不改变已有分享 token。2134目录成功但原文件失败的记录保留；独立单变量UA诊断后，2135统一Chrome下载及媒体上下文，一次真实私盘MKV到达AV。未放开下载重定向策略或引入外部凭据；历史、事实、长播与ISO仍未验收，真实协议继续标实验。

SMB/NFS/WebDAV 使用 Kodi 的目录与原生播放协议，沿用同一索引和 worker。NetworkRef 只保留来源 ID、namespace、相对路径、尺寸、精确 lastmodified 和配置 generation，不伪造 inode、挂载证明或内容 hash。未知枚举完整性、重复路径、缺尺寸/时间、取消/超时均失败且不推断删除。路径来源当前仍 start-only，不能从文件名或相同路径自动继承时间轴。

Registry 在原 metadata 表保存随机配置代际；相同配置保存不换代，删除重加或 A→B→A 都换代。网络凭据仅在适配器私有路径交给 Kodi，不进入引用、卡片或错误文本。阻塞 VFS 不声称强制取消，关闭失败保留既有生命周期锁。

历史媒体事实只投影精确文件的实际观察，批量查询最多32项/单存储快照。已有时长、音轨/字幕数量、启动时选中轨道和字幕显隐；2134补入同实例AV_STARTED后的按需视频codec/width/height，沿原history writer保存，保留旧格式兼容。不推断HDR、渲染、输出或实际转码；standard和服务器事实未因此接通。2135私盘到达AV但观察器报FACTS_ABSENT，不能宣称真实媒体事实落盘通过；保留binding不足以停后精确核对FileRef，未按最新行猜测终态。剪辑身份、分卷策略和路径精确续播也未闭合。

Plex/Jellyfin/Emby 已接入现有来源注册、目录、扫描、重验、原文件 Range 播放和本地历史链。每种服务一条连接，可枚举多个媒体库；Plex 分卷分别保留，不自动串联。没有建立第二套索引、凭据库或 worker。scope 包含 Registry 的 source_id 和 generation，删除重加与配置 A→B→A 不复活旧授权。

`c58cd3e` 已接入三个服务器的只读描述：复用扫描原有详情响应，沿同页账号/profile/事务门写入 reviews.candidates 的嵌套候选。标题、年份、简介和外部ID保留“服务器声明”身份；selected、FileRef和人工mapping/revision不变，人工解绑/忽略/撤销后也不由刷新抢回解释权。查询投影语义标记6→7，数据库user_version仍为4；实际旧reader/writer的顺序重开7→6→7已做回归，不宣称混合版本同时打开安全。该切片随2128部署但未完成真实服务器验收。先前Windows831通过/1环境跳过、POSIX147及补充端口34通过仍是独立历史局部回执，不与ff0422完整回归相加。

三个服务器仍明确 start-only：entry/media/part ID 加大小不能证明同 ID、同尺寸内容没有替换，因此不能授予自动续播，native/standard 都显式零起点。2134的server_progress.inspect_progress在已有CatalogService/FileHistory和账号/profile范围内只读核对服务器条目进度与本地精确历史，保留冲突；无UI/IPC入口、不轮询、不改历史或远端进度。历史和描述可展示，不代表可安全恢复或已确认作品匹配。服务器花絮、片段、自动进度同步，以及实际 Direct Stream/Transcode 协商和会话生命周期尚未完成。未进行真实服务器验收，来源保持实验状态。

## 实施与验收记录

本地测试证据目录为 `D:/AM6B-Project/AM6B/tmp/bobbi-convergence-20261113/results`。最新已部署产品冻结摘要见 [validation-35b9d61.json](validation-35b9d61.json)；[2134记录](validation-2acdba8.json)、[2133记录](validation-ed645ee.json)及下面早期历史检查点原样保留，包括失败与负控。定向测试组有重叠，不能相加当全套覆盖，也不以文件名中的 final/frozen 自动授予最终资格。

- 附件完整性/标准历史定向测试通过；原生播放只读负控5失败，修复及OSD归属分类扩展后121通过。
- 本地目录手机授权链负控失败，修复后相关109通过；整页重载恢复新增6项负控失败，后续手机相关合跑89通过（含真实前端测试包装）。
- 账号纯契约/依赖边界及相关准备、字幕、交接181通过。
- 纯历史存储、明确注入、固定profile与关闭排空98通过。
- 公共详情/搜索代理早期定向98及58通过；ff0422统一回归已另行完成，旧定向计数不追加为独立覆盖。
- 产品兼容保护与Android证明/门禁代理合跑226通过、1个已有Windows符号链接skip。
- WSL真实完整补丁应用及7组C++语义门禁通过，2个EOF负控正确失败。series SHA256 `2a7fed3b11747470566f9eb69a64d3d26557db218b1975aad4d3dcdebe424345`。这不是Android链接、签包或设备证明。
- 三套早期完整回归分别为主测试6958通过/22失败/17跳过/1预期失败、继承桩1520通过、preparation254通过。主测试19个失败为缺已声明 Crypto 依赖，隔离环境安装后相关110通过；bootstrap漏装兼容保护已修、18通过；2个库存失败等待源码冻结刷新。后续改动需要重新完整验收，不能沿用这些数字作为最终全绿。
- 人工审核半写负控4项复现，savepoint 修复后相关116通过；v2片段迁移及真实设置入口通过，v3花絮关联相关109通过，设置/旧格式额外43通过。有重叠，不能相加。
- 交叉复核新增父文件可用性竞态：完成扫描仅撤销父 membership 时 ref/revision 不变；旧 apply 仍接受导入。负控1失败，事务内补可用性重验后相关67通过，保持整项回滚。
- 图片装配定向42通过、真实展示UI23通过；源库/共享失败显式绑定主相关390通过、隔离16通过、额外218通过，有重叠。
- 网络来源与统一profile闩锁新增44及5项通过，受影响两组297通过/1跳过及186通过，有重叠。真实SQLite、线程门控、HTTP与前端链仍属于本地合同测试，不是设备认证。
- 2026-11-13 15:12 只读设备基线检查：sequence 2026102123、空闲首页、Kodi active/0重启、schema3/integrity ok、594 typed objects；115和百度保存登录状态。当时尚未部署，该记录只作升级前基线；探针未发起云请求。

## 历史检查点

各代冻结、诊断、控制回执和工具修正集中保留在本文开头链接的 validation 记录中，包括原失败、回退、负控及证据哈希。旧代局部通过不继承给新代；后补观察有各自时点，不修改原冻结记录。本页只保留当前路线和边界，避免历史摘要被误读为最新能力。

### 阶段0–6跟踪

阶段0/1新增交付追踪，不重定义G0–G9，也不宣告阶段完成。阶段0保留审计附件、基线、冻结源、签包、native及设备证据的独立身份；阶段1继续核对所有权清单、反向依赖例外及未解动态边。两阶段均为部分完成，仍须逐项核对出口条件。

阶段2的公共详情与显式绑定已有切片，焦点/返回/晚到结果、profile A→B→A和延迟writer系统链待验。阶段3仍缺完整剪辑/分卷语义、技术事实与偏好解释，路径精确续播不成立，完整OSD和任意tempo也未统一。阶段4的自动片段策略、服务器片段及跨来源/账号/typed-path迁移未完成。阶段5的服务器进度同步仍缺失，Direct Stream/Transcode/HLS会话和真实115/NAS/服务器验收未闭合。阶段6已有2129→2128程序字节回退的窄证明，回退后完整健康/播放、数据恢复、中断恢复及Android clean-link/APK/实机仍待证明。110个原跨模块场景继续pending，其中83个局部执行映射、27个候选映射，SYS-081–090尚缺直接测试文件引用；本轮离线全绿不改写这些状态。

## 发布许可门

当前分发许可仍受 `licenses/THIRD-PARTY.json` 阻塞，7项 `unresolved-source` 和2项 `unresolved-full-license` 未解决。platform使用的p115rsacipher对应模块LICENSE为GPLv3、pyproject元数据声明MIT，两份冲突证据均保留，适用范围、兼容性和分发许可未确定，不推断整个平台的MIT或GPL授权。测试、可复现构建、保留声明字节和内部候选安装均不解除这一许可门，签名包也不构成公开发布获准。

## 后续完成顺序

1. 保留各代原始失败、成功和工具错误。2134低频启动诊断继续复现停滞；优先定位115私盘下载地址重定向及普通分享卡顿，不声明性能修复。错误弹框前先尝试原请求清理的修复已有2项旧源码失败负控、390项相关通过；固定下载错误分类与提示有4项失败负控、89项相关通过及独立208项通过。组间不重复计覆盖，两项修复均须另建包部署，不能归入已部署2134。
2. 标准历史队列饱和、准确落盘回执、内部服务器进度只读核对和按需视频事实已完成2134离线冻结及部署，但真实媒体事实落盘、服务器和系统交互仍未通过。服务器仍缺替换抵抗的内容身份及远端条件写合同，不启用自动续播／回写。继续按110场景验证交互，不以测试数量、升级健康或旧代局部通过代替新代码验收。
3. 对已接入同一登记、扫描、身份、重验、播放和历史的115私盘、SMB/NFS/WebDAV、Plex、Jellyfin、Emby逐个做真实协议验收；未验证协议保持实验状态，服务器和路径来源保留start-only边界。
4. 同一115红例固定起点及音字幕，5冷+5暖，保存所有失败并对齐传输/解复用/解码/时钟；不以十次样本声称可靠P95或“最快”。
5. 在2129→2128程序字节回退的窄证明之外，独立验证回退后健康/播放、数据恢复与中断，保留source/component/native/schema身份及CoreELEC/Android分账；解决许可阻塞后再判断发布资格，不能把一次升级或字节回退成功写成完整交付完成。
