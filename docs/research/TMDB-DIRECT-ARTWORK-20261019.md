# TMDb 直连图片缓存与失败阶段闭环

本次仅实现、离线回归及本机 loopback 验证；没有借用其他插件的 TMDb Key，
没有申请或发布应用凭据，没有把 API 请求交给第三方图片中转，也没有作盒子
画面/公网可达率已通过的声明。

## 实现

- `bobbi_core.metadata_transport` 只允许 `api.themoviedb.org`、
  `image.tmdb.org` 的正常 HTTPS。优先系统 DNS 直连；网络层失败时可使用
  固定的 RFC8484 DoH 解析，再直接连接官方 CDN，TLS 始终核对原始域名/SNI。
  TLS 验证失败不触发绕过，不跟随重定向。DoH 只收到 DNS 主机名，绝不收到
  API path、query、Key、账号 Cookie。解析成功仅缓存 DNS 响应的有效 TTL，
  最长 300 秒；候选地址全部失败则清除此 DNS 缓存。
- `bobbi_core.image_cache.image_url` 是统一图片构造 helper。它只读取数百
  字节的本机注册信息，不在构建卡片/GUI 线程同步联网。海报、剧照、头像、
  logo、季卡、新番和详情窗口的原构造点均已接入。服务未就绪则保留正常
  HTTPS 官方 URL；不改变非 TMDb artwork 来源。
- `Host` 启动独立的 read-only loopback 图片服务，单独最多 4 个请求线程，
  不占账号/播放 `/control` 的线程池；`owner.tick` 不下载图片。
  本机随机能力码与控制令牌不同，只能读图片，不能执行任何控制命令。
- Endpoint 严格限定 `/t/p/<尺寸>/<文件名>.<jpg|jpeg|png|webp>`，无任意 URL
  参数、API query、路径穿越或个人文件读写。必须精确 loopback Host 和能力码；
  不监听 LAN/公网，不开放远端服务器端口。
- 只有成功 HTTP 200、有界完整传输及可识别完整 JPEG/PNG/WebP 外壳的原始
  字节才能原子发布本机缓存；不转码、不缩小原图、不改变用户尺寸档位。
  每张最多 8 MiB；成功缓存最多 128 MiB/2048 张；只淘汰自有哈希命名缓存。
  同图并发合并一次下载，失败有 30 秒内存冷却，失败页/HTML/截断数据不入缓存。
  TMDb 文件名是内容标识，成功图本地可离线复用；缓存命中不再发网络请求。

注册文件为 platform profile 下的 `image-runtime.json`，缓存是同级 `images/`。
能力码只用于本机只读图片，不含 TMDb Key 或云盘凭据。退出按本实例 token
核对后才移除注册；保留已成功图片供下次使用。

## 错误阶段

网络错误有限枚举 `DNS / CONNECT / HEADERS / BODY / TLS / TIMEOUT / CANCELLED`
及长度、格式、HTTP 等阶段。`requests.ConnectionError.metadata_stage` 会传到
`TMDbException.metadata_stage`，诊断消息不保留 Key-bearing URL。
TLS、取消、已耗尽总预算、错误来源及禁用代理等不会再做一轮盲目外层重试。

图片请求继承 10 秒 deadline，分块读取每次检查总预算并更新 socket 超时。
系统 DNS 与建连仍属于 OS 的可合作取消能力，不承诺能硬中断 libc；关闭或
deadline 后的迟到结果不再原子发布。最多 4 个服务线程，不会无限堆积 worker。

## 门禁

新增 `tests/test_image_cache.py` 和扩展 `tests/test_metadata_transport.py`：

- helper 不联网、严格路径/域名/无 Key query；
- 真实 loopback GET/鉴权/Host/非法路径拒绝与离线重复读取；
- single-flight、只清理自有缓存、配额、失败冷却、失败不缓存；
- 关闭后不发布、旧实例不删除新实例注册；
- TLS 原始域名、禁止 relay、短读/总大小、DNS 回复身份与 TTL；
- 安全错误阶段跨 requests → TMDb 边界保留，不把 body 中断谎报 DNS；
- 空配置 Host 仍不导入可选 native engine/CD2/requests/ctypes。

联合执行图片/网络、Host、Juku 协议/目录和分享字幕八组门禁：**213 passed**。
这是本机 fixture 和静态实现证据，不代替干净安装、真实 TMDb 权限、Kodi
texture loader 展示或平台二进制兼容验收。
