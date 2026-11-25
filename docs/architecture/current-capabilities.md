# 当前候选能力矩阵、历史边界与收敛责任索引

本文件对应 `codex/ultimate-047c0f18` 候选分支的当前代码与离线/辅助设备证据。仓库中保留的 `2026102134`（`2acdba8`）、`2026102135`（`35b9d61`）、`2026102136`（`42a3729`）、`2026102155`（`r18-device-acceptance.md`）与线上已签发 `CE2184`（`2026102184`）均为**明确历史版本记录**，保留其原始通过、失败、负控与回执摘要，不冒充本候选的真机全量结果。

## 1. 能力分层与外部参考边界

每项来源与播放能力严格区分六个证据层级，不因界面存在按钮或静态路由可达而宣称全链支持：

| 能力维度 | 本代已验证代码与契约范围 | 明确边界 / 未证实或 `BLOCKED` 项 |
| --- | --- | --- |
| 账号与来源登记 | `Registry`（`libraries.sqlite3`）管理来源凭据与随机配置 `generation`；相同保存不换代，删除重加或 `A -> B -> A` 换代并使旧票据/会话失效。 | 不建立万能统一凭据库；115 OAuth/分享与媒体服令牌分属各自受控存储。 |
| 目录浏览与分页索引 | Emby 在线目录单出口 `endOfDirectory`、模态期间挂起刷新与提交后确认；T4 原生分类/筛选目录、200 集有界详情分页与自足 `play` 票据；云盘/本地扫描 `MediaIndex` `v3` 持久化跨页 `proof` 与统一 `RESUMABLE_SCAN_REASONS`（恢复轮次保持 `partial`，单轮完整枚举才撤回消失文件）。 | 路径型来源（SMB/NFS/WebDAV）不伪造 inode 或内容哈希，维持 `start-only`。 |
| 字节流读取与重定向 | `bounded_http` 单地址切片超时回退不污染全局 `AttemptHandle`；Stremio/Nuvio 共用 `http_policy` 安全重定向关闭、响应大小上限与截止时间且禁静默降级 `http://`；`source_media_http` + `SourceStreams` 在探测与后续 `Range` 每跳连接前校验 `(source_id, generation)` 同源或电视显式批准，跨源剥离敏感头；支持 `Protocol == 'File'` 直连与 `Protocol == 'Http'` 受控网关子集（弱会话身份强制零起点）。 | 必须服务端动态转码的 HLS/DASH 会话、任意脚本/网页解析与未批准跨站流仍拒绝。 |
| 播放实例权威与续集 | `PlaybackAuthority` 统一管理播放选择与 `authorize_next` / `reserve_child` 3 秒续播窗口；`PlaybackControlServer` 复用 `playback_completion.terminal_end`（毫秒位置、5 秒新鲜度、同实例校核）与同实例时钟采样，早退流降级为 `ERROR`；`Host.owned_next`（`OwnedNextCoordinator`）统一纳管摘要预取与续集探测并支持取消/排空回执；`NextResolution` 区分末集完结、页上限、多版本待选、鉴权失败与网络错误。 | `standard` 播放器无 `native` 原子实例收据，仅在受检事件窗口内提供观察级近似，不宣称原子级切换。 |
| 远端会话回报与双端冲突 | `EmbyInvalidationHub` 非重入锁纯投影 + 完整有界 RFC 6455 客户端帧流（校验 `101`/`Sec-WebSocket-Accept`、客户端掩码、分片重组上限、`Ping`/`Pong`/`Close`）+ 摘要轮询回退；`EmbySessionReporter` 持久化已证实服务器基线 `UserData`，离线期间外部客户端改写（如改到更小的 `200s`、重置未看或标记已看）时拒绝旧 `900s` 覆盖，同实例回退拖动（`900s -> 600s`）如实写回；`Host.close()` 中止在途请求并在线程未退出前保留 `runtime.lease`。 | **Infuse Direct / EmbyCon 仅作交互语义与服务器 `UserData`/会话状态参考**；不复制任何闭源同步实现，不承诺固定毫秒/秒级推送时延。 |
| 实机遥控与音画解码 | CoreELEC / Kodi 21（Python `3.11+`，捆绑及声明下限对齐 `requests >= 2.34.2`、`urllib3 >= 2.8.0`）宿主导入、组件原子快照解包（`REL-02`）已验证；Windows 旧 `python3.8.dll` 宿主非本轮发行目标（`PLAT-01`）。 | **实体手机 Yatse + ADB UI 全量 152 场景**在缺连接手机/`adb` 时如实记为 `BLOCKED`（绝不用 Kodi JSON-RPC `Input.*` 冒充 `real_yatse` PASS）；**Dolby Vision Profile 7 FEL** 须具备授权双层 BL+EL+RPU 样片与解码/显示链实证，缺样片与采集链时记为 `BLOCKED`，绝不凭文件名、`DV` 徽标或 `P7` 标签宣称支持。 |

## 2. 历史私有配置复核结论（`my_ext.json`）

针对用户原始私有输入（`20,660` 字节，SHA256 `b64b7501ff79cf34b349d61a360bc139d195908f9df19af7c9139a44a37acbac`）：

- 生产解析器与 `tools/check_t4_bridge.py` 实测结构为：**`0` 个可用 `type: 4` 点播站、`50` 个 `type: 3` Spider（JAR/CSP）定义、`7` 个 `lives` 直播订阅入口**。
- 预览明确提示需外部 T4 桥接运行时，**`Registry` 零半写**；手机配对 6 分片（5×`4096B` + `180B`）上传整包哈希一致且不保存不支持源。
- `7` 个 `lives` 仅为订阅入口条数，不宣称为 `7` 个可用直播频道；仅把原文件 `type: 3` 改为 `type: 4` 会被指出 CSP/运行时依赖，`--probe-live` 在 0 可用或任一阶段失败/超时/空样本时均返回非零退出码。
- 因外部真实 Spider 桥接运行时、相对 `./spider.jar` 基址及站点凭据未随环境提供，50 站点逐站真实桥接验证保持 `BLOCKED`（不以合成 T4 桩代替真实逐站证明）。

## 3. `R00`–`R19` 与本轮 `U00`–`U21` 状态对照

| 轮次 / 编号 | 主题 | 当前候选状态与证据说明 |
| --- | --- | --- |
| `R00` (`U00`, `U19`) | 预检、双顺序准备与全量门禁 | **离线通过**：`verify_package`、`preflight`、`run_checks.py`（`full` + `native`）、`R00-01..03` 正负控与历史 schema 参数化正负控均已核验。 |
| `R01` (`U10`, `U11`) | 手机配对鉴权与作用域撤销 | **离线通过**：配对令牌、CSRF/Origin、关闭二维码仅撤网络授权而保留同 profile 已提交导入 handoff 已验证。 |
| `R02` (`U10`, `U19`) | 前端纯文本渲染与分页交互 | **离线通过**：`manage.js`/`manage.html` 零动态 HTML 拼接，`68` 项 Node 前端回归通过。 |
| `R03` / `R11` (`U06`) | 云盘分页完整性与断点续扫 | **离线通过**：`MediaIndex` `v3` 持久化分页 `proof`、统一恢复原因码、10 万条有界扫描与 `SIGKILL` 恢复通过。 |
| `R04` / `R05` (`U12`, `U13`) | 搜索失败保留与 Trakt 状态分离 | **离线通过**：Prowlarr 等失败保留已有结果并可重试；Trakt `401`/未知返回 `None` 不清空旧缓存，`200 []` 原子事务清空目标桶。 |
| `R06` (`U08`, `U15`) | 有界 HTTP、TLS 与运行库下限 | **离线通过**：`connect_tcp` 单切片回退、禁 `https->http` 降级、流式上限与 `requests 2.34.2` / `urllib3 2.8.0` 下限一致。 |
| `R07` / `R08` (`U02`, `U03`, `U17`) | 播放完成权威、同实例时钟与续集准入 | **离线通过**：早退流不误判完播，跨实例不串读时钟，`authorize_next` + `reserve_child` 3 秒内精确一次续播，摘要预取不建远端会话。 |
| `R09` / `R10` (`U01`, `U04`, `U05`) | Emby 失效刷新、队列合并、冲突保护与排空 | **离线通过**：非重入锁纯投影、RFC 6455 帧流、SQLite busy 恢复、1:1 进度标记、离线外部改写保护与 `Host.close()` 真实排空通过。 |
| `R12` / `R13` (`U14`) | Emby 单次目录完成、模态延迟刷新与首页单源生成 | **离线通过**：`execute_home_rail`/`execute` 唯一 `finally` 完成出口，取消不落盘，`home_rails.json` 同时生成 XML 与 `home_rails_meta.py`。 |
| `R14` / `R15` (`U07`, `U09`) | T4 自足票据、有界分页与媒体逐跳同源网关 | **离线通过**：`T4TokenStore` `v2` 自足 `play` 记录、原生分类筛选目录、逐跳连接前同源检查与 Emby `Http` 网关子集通过。 |
| `R16` (`U18`) | 诊断隐私 schema 与真实本地 Workers/D1 | **离线通过**：默认 Node 测试与真实本地 Wrangler `4.167.0` + D1 SQLite 去重行计数（`receipt_count=1, daily_delta=1`）均已核验。 |
| `R17` (`U15`, `U17`, `U19`) | 可复现构建、原子解包与发布门负控 | **离线通过**：两次 `source-check` 逐字节一致，`stage-components.py` 单快照校验解包，历史重打包编排安全负控已迁入当前门禁。 |
| `R18` (`U17`, `U20`, `U21`) | 架构图、能力矩阵与实机冷暖启动/恢复 | **离线通过 + AM6B+ 辅助校验（实体手机 Yatse 为 `BLOCKED`）**：架构图确定性重生成且零反向依赖；AM6B+ 实机辅助校验与回退恢复至 `CE2184` 单独记录，缺 Android 手机/`adb` 的 `real_yatse` 场景保持 `BLOCKED`。 |
| `R19` (`U10`, `U11`, `U20`) | 私有 JSON 复核、分片上传与桥接五阶段 | **私有输入与分片契约通过，真实外部 Spider 桥接为 `BLOCKED`**：原 `my_ext.json` 复核与 6 分片上传通过；缺外部桥接运行时与站点凭据的逐站实测保持 `BLOCKED`。 |

## 4. 已删除重复通路与消费者迁移表

| 已删除 / 退役实现 | 原消费者 | 当前唯一责任主体（Owner） | 兼容与行为验证 |
| --- | --- | --- | --- |
| `router.py` 重复动作集合与多处 `if action ==` 分发表 | `addon_router`、`_get_route_handler`、`ROUTE_GROUPS` | `router.py` 单一 `RouteSpec`（`ROUTE_SPECS` 派生 fast/matcher/dispatch 与明确 `completion` 职责） | 保留全部旧插件 URL、`bobi_* -> bobbi_*` 别名及兼容导出符号；导入期强制动作唯一性。 |
| `glass_settings.py` 手写 `HOME_RAILS` 表与 `generate_home_rails.py` 重复展开块 | `glass_settings`、`ce_install_ui`、皮肤 XML | `ui/rails/home_rails.json` -> `tools/generate_home_rails.py`（同时生成 XML 与 `home_rails_meta.py`） | 皮肤生成 XML 字节指纹不变；纯首页栏目偏好与渲染器安装职责解耦。 |
| `PlaybackControlServer._owned_next_worker` 与裸 `bobbi-native-next-summary` 线程 | `PlaybackControlServer` | `Host.owned_next`（`bobbi_platform.owned_playback.OwnedNextCoordinator`） | 摘要预取、候选扫描与子会话开启均受 `Host.close()` 取消与排空回执保护，未排空前保留 `runtime.lease`。 |
| `pan_tokens._directory_pages` 内存跨页证明与分散恢复原因列表 | `pan_providers`、`CatalogService` | `MediaIndex` `v3` 持久化分页 `proof` + `RESUMABLE_SCAN_REASONS` | 预算耗尽/重启/停止后跨进程恢复第 2 页不误报 `PAN_PAGE_EXPIRED`。 |
| `t4_ui.browse` 模态入口与依赖父项的 `play` 票据查询 | `t4_ui`、`T4TokenStore` | 原生 Kodi 分类/筛选目录 + `T4TokenStore` `v2` 自足 `play` 记录 | 插件 URL 保持不透明 32-hex 票据且参数受控；父项淘汰后已发选集仍可播放。 |
| `webserver.py` `stremio://`->`http://` 静默降级、`nuvio/addon_selection.py` 独立重定向循环、`realdebrid`/`premiumize` 重复 `_make_request` | Stremio、Nuvio、Debrid API | `bobbi_core.http_policy` + `DebridClient._make_request` | 保持 Stremio 与 Nuvio 各自命名空间与缓存隔离；`DebridClient` 统一验证 `params=None/{}` 与注入 `session`。 |
| `:8082` 独立无鉴权 `SubtitleUploadServer` 与手写死循环 multipart 解析器 | `source_select`、`subtitle_server` | `PhoneManagement` 配对上传作用域 + 有界线性 `parse_bounded_multipart` | 无结束边界样本毫秒级拒绝不挂死；普通管理 API 维持 `8192B` 上限。 |
| `tools/delivery_policy.py` 无生产消费者的 CE2021 历史重打包编排（`repackage_signed_delivery`、`stage_verified_repackage` 等 7 个函数） | 已退役 `package_ce2021_github.py` 及 `test_ce2023_delivery.py` | `SignedBundle`、`tools/ce_release_gate.py` 与 `delivery_policy` 现行构建/归档守卫 | 签名篡改、序号冲突、`EXCLUDE` 不误删运行资产及失败不发布目录负控已迁入 `test_ce2023_delivery.py`。 |
