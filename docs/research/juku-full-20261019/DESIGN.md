# Juku 0.80：全程序模块结构与可借鉴设计

这份结论基于全量函数导出及下列重点路径的人工静态核对。函数未列入本文不代表
未导出，也不表示其行为已被逐项验证。伪 C 的地址和原有符号用于定位证据，
不能作为可编译源码直接抄入产品。原始 Python 与资源核对另见 [ASSETS.md](ASSETS.md)。
本文的“值得借鉴”是设计建议，不自动代表已经实现；当前可定位的已吸收内容、明确不采用
的路径及仍待验证的能力，单列于 [中文交付结论](SUMMARY.zh-CN.md)。

## 全程序结构

Juku 不是仅有一个在线播放 URL 的插件：Python/Kodi 界面围绕本地 Go daemon，
daemon 同时承担网盘解析、媒体库、网页界面、图片缓存、远程控制和协议适配。
以下 7 个自有命名空间在两个架构的函数数量完全一致，计数包含 init、闭包和编译器
包装函数，不是源文件或手写方法数量。

| 命名空间 | 每架构函数数 | 观察到的职责 |
| --- | ---: | --- |
| `main` | 799 | HTTP 路由、播放入口、图片代理、导入任务、私有库/STRM、Emby、Kodi RPC、WebRTC桥、网页与语音入口 |
| `mv-daemon/provider` | 1,121 | 10种网盘能力、凭据/参数存储、媒体扫描、SQLite私有库、离线任务、115增量同步、TMDB |
| `mv-daemon/pkg/proxy` | 64 | 分块下载、读取/seek、URL续期、直通、字幕编码转换、代理会话管理 |
| `mv-daemon/matcher` | 31 | 文件名/父目录/季集识别、字幕候选与排序 |
| `mv-daemon/pkg/auth` | 31 | 设备身份、服务会话、签名与本地加密接口 |
| `mv-daemon/pkg/cfdialer` | 47 | 网络传输与目标域名/IP选择、连通性处理 |
| `mv-daemon/xiaoai` | 196 | 小爱配置/登录、意图解析、Kodi/私有库/在线分层选片、设备控制与Webhook |

来源：两架构 `modules.tsv`、`functions.tsv`。除以上 2,289 个自有函数，完整导出还
包括 Go runtime、HTTP/TLS/JSON/SQL 等标准库、`modernc.org/sqlite`/`libc`、Pion
WebRTC/ICE/DTLS/SCTP 等第三方模块。这些库的伪 C 均已保存，不在本文逐页粘贴。

`main.main` 明确调用 StartServer、等待信号、StopServer；StartServer 初始化 auth、
全局 transport、listener 和后台任务。路由由 `registerAllRoutes` 统一注册，
其中显式调用 `RegisterEmbyRoutes`。证据：AMD64
`functions/00c6/00c61060.calls.tsv`、`00ce/00ce3160.calls.tsv`、`00ce/00ce1ec0.calls.tsv`。

## 1. 最值得复用的是既有能力入口和所有权边界

10 个 provider（Aliyun、Baidu、ChinaMobile、ChinaTelecom、Cloud115、Cloud123、
Guangya、Quark、UC、Xunlei）具有重复而一致的能力名：扫码、分享列表、流式列表、
个人文件、搜索、分享播放与个人播放。`NormalizeProvider`、`DetectProviderFromURL`、
`NormalizePanMediaURL` 把入口规范化集中在 provider 层。

这支持波比采用“原插件/原服务提供解析能力，波比维持薄界面和播放衔接”的方向。
不应因为前端改名而复制全部网盘实现、后台常驻、令牌状态及代理线程池。
接口方法通过 Go interface 调用，静态直接调用图不能完整呈现每个 provider 的分派。
证据：ARM64 `functions.tsv` 中完整 provider 方法族；
`0055/0055b050.c`、`0055/0055b400.c`、`0055/0055b8c0.c`。

账号所有权仍需区分：网盘 TokenStore 的 provider→当前凭据，与 daemon 设备会话是
两种状态。现有定向证据已证明前者覆盖保存/清空，不能因此宣称所有后台任务都具备
账号代际隔离。全文导出没有消除这个语义边界；参考
[账号生命周期研究](../juku-account-protocol/README.md)。

## 2. 解析与传输分离，播放器会话要能结束

播放 handler 负责选 provider、获得媒体 URL/请求头/字幕并注册代理；Downloader
负责 `ReadAtWithContext`、seek、分块 worker、内存回收以及 URL 刷新。ProxyManager
集中持有代理实例，`CloseAll` 在锁内逐项调用 Downloader.Close 并从 map 删除。
这是比在每个界面/网盘适配器里单独维护一套下载生命周期更可复用的边界。

`checkProactiveRefresh` 依据已解析到期时间，比较“距到期少于60秒”和“距上次刷新
超过10秒”后异步刷新；实际还受关闭标记和 refresher 是否存在约束。这说明可以在
传输层续期，界面不必把过期 URL 当成一次全新选片。数字在 ARM64
`functions/005e/005ec800.c` 中可核对，刷新链见 `005e/005ec020.c`；
AMD64 对应 `00a9/00a9f240.c`、`00aa/00aa1aa0.c`。

这里值得借鉴的是会话所有者、读取取消和续期接口；不能只凭方法名宣称所有 HTTP
请求都立即可取消，也不能把本次静态检查当成大码率、seek、并发或原画播放实测。
具体传输策略与现有 Kodi 播放器之间应通过真实媒体测试决定。

## 3. 字幕与命名匹配可作为小而清晰的逻辑边界

`provider.MatchAndConvertSubtitles` 明确调用 matcher 的 `MatchSubtitleCandidates`，
随后把候选字段转换成对外字幕结构。网盘查找字幕与候选选择因此已有边界；
季/集/父目录信息的处理也集中在 matcher，而非仅靠当前海报标题猜字幕。
证据：ARM64 `functions/0055/00559760.c`、`functions.tsv` 中全部 31 个 matcher 函数。

波比可借鉴“先获取同源候选，再依据影片文件身份和季集信息排序”的流程，保留
原语言/多字幕选择。复用作者实现或已验证的契约优先；无需把所有字幕下载、代理和
页面逻辑再实现一遍。具体字符串规则的既有对照见
[字幕协议研究](../juku-subtitle-protocol/README.md)。

## 4. 缓存分层，并发请求共用一次工作

ImageProxyManager.GetImage 包含内存读取、磁盘 Stat/ReadFile、内容类型检查、
回填内存，以及未命中时的 singleflight 路径。`singleflightGroup.Do` 在 map 中按键
登记正在执行的请求，其他请求等 WaitGroup，完成后共用结果并删除进行中项。
这适合海报墙中多个控件同时请求同一图片，能够减少重复网络工作。
证据：AMD64 `functions/00c4/00c41c80.c:241`、`:302`、`:321`，
`functions/00c3/00c3e280.c`。另有 QueuePrewarm/prewarmWorker，但本次没有用实际
海报墙负载证明预热队列容量或刷新收益。

离线文件缓存另有 `OfflineCacheStore.GetValid`，能在使用时以当前凭据检查云端文件
是否存在，明确不存在才删本地记录。可以借鉴这种“验证后复用”的思路；错误结果
与“明确不存在”应区分，缓存键是否需要账号维度仍由波比自身状态模型决定。
它不是全程序统一缓存失效框架，也不能代替账号切换并发守卫。

## 5. 长任务可见、可取消，但状态表不等于完整取消保证

ImportTaskManager 和 ScanTaskManager 均有 Create/Get/UpdateProgress/Complete/
Fail/Cancel/cleanup 方法。ImportTaskManager.CreateTask 创建随机任务标识并记录时间；
CancelTask 排除 completed/failed/canceled 终态，更新取消状态和时间，并在存在回调时
调用取消回调。证据：AMD64 `functions/00c4/00c443e0.c`、`00c4/00c45260.c`。

值得复用的是把长导入从界面线程转成可观测任务，并保存终态及进度。不能因为
CancelTask 存在就声称整个云端导入原子回滚，或所有迟到回调都会被丢弃；要核对
实际任务提交点和调用者。波比已有类似任务所有者时，宜连接这个入口而不是再加一层
平行的“全局任务中心”。

## 6. 媒体身份、元数据与可播放链接分层

PrivateLibStore 有库、影片、链接、SHA/URL/TMDB 查询、季集、额外元数据、收藏及
播放进度方法；批量匹配流程先处理文件名和父目录，再使用既有链接/SHA/TMDB 身份
查询以及匹配结果批量写入。证据：AMD64 `functions/00c9/00c90d40.c:1492`、
`:1584`、`:1814`、`:1998`、`:5183`，以及 ARM64 `PrivateLibStore` 方法族。

对播放器前端有用的是“影片/版本身份稳定，链接可以刷新”的模型；不要把一个临时
CDN URL 当成影片主键，也不要因为解析失败静默换成另一版本。大批量导入、刮削、
私人库发布与自动同步则已经构成另一套复杂子系统。导入主函数重建伪 C 超过5,000行，
这证明能力广泛，并不证明值得把它整体复制进轻量播放器。

115 LifeSyncManager 具备事件轮询、创建/删除/重命名目录处理和回调；它代表增量
同步能力。其远端事件完整性、失败恢复、跨账号并发、发布接口授权和数据冲突策略
没有通过本次静态导出获得运行保证，不应写成已验证承诺。

## 7. 同一媒体库可接多个消费端，适配层应薄

Emby 路由、播放信息、图片、播放进度与收藏接口围绕已有媒体数据展开。
`buildEmbyMediaSources` 整理来源显示名和容器；STRM 导出则通过
`buildStrmPluginUrl` 回到插件入口，并用 `url.Values.Encode` 编码参数。
证据：AMD64 `functions/00c1/00c1a560.c`、`00cc/00cc0e00.c`、
`00cb/00cb8980.calls.tsv`。这提供了“同一身份/链接模型，多个客户端适配”的范例。

但 Juku 还包含直接修改 Kodi sources XML 和视频数据库、清理孤立库目录、批量注入
影片/剧集等代码。它们属于强耦合的宿主集成，不能仅因已有方法就照搬到不同 Kodi
版本，更不能把清理操作当成没有副作用。波比应先使用正常插件/JSON-RPC/STRM边界，
若确需数据库集成，再针对目标 Kodi 版本单独验证迁移、备份和恢复。

## 8. 遥控入口复用路由，语音选片分层

WebRTCBridge.handleRPCRequest 解码请求，构造 HTTP 请求，并交给同一个
`net/http.(*ServeMux).ServeHTTP`；返回写入内存 response writer 后回送。
这说明远程传输可适配到已有控制层，无需为远控复制业务 handlers。
证据：AMD64 `functions/00ce/00ce7000.c` 及 `.calls.tsv`。

小爱 `Resolver.ResolveAndPlay` 依次尝试 Kodi 本地库、私有库、在线来源，命中后
返回；还有候选编号选择和独立意图/关键词校验。证据：AMD64
`functions/00c0/00c03140.c`，更低层在线拼音查找方法亦在全量索引中。
可以借鉴输入解析、候选选择、播放执行的边界与本地优先策略。波比未请求小爱、
WebRTC、远端中转等功能时，不应为了“功能齐全”引入新的常驻服务或默认远端配置。

## 复用优先级

| 优先级 | 适合波比借鉴的内容 | 落地边界 |
| --- | --- | --- |
| 先做 | 使用上游插件/服务入口；保留媒体版本身份；统一播放会话；同源字幕候选 | 薄适配与现有播放器任务所有者 |
| 按实际问题做 | 图片请求合并/缓存；可取消长任务；缓存使用时验证；播放URL续期 | 先复用已有实现，再对真实卡顿/失效场景验证 |
| 有明确需求再做 | 私有库扫描、增量同步、STRM/Emby消费端、语音/远控 | 独立功能边界与目标客户端验证 |
| 不宜直接照搬 | 忽略持久化错误的部分账号路径、直接Kodi数据库注入/清理、整个daemon重复实现 | 保留现有可靠保存与状态守卫，另行审查必要集成 |

这些建议不构成对 Juku 性能、安全、所有账号并发或每个 provider 可用性的总体背书。
完整函数证据提供后续检查入口；下一步设计应由波比的真实需求和实测问题选择，
而不是把全量反编译等同于把上游的全部功能重新实现。
