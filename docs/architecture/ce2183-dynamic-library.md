# CE2183 之后的动态片库（开发分支）

「我的片库 → Emby」是 Kodi 插件目录。媒体库列表来自当前 Emby 用户的 Views，进入文件夹、季集、最近新增、继续观看或搜索时再请求当前页。重新进入即重新读取。选择特定版本时重新验证用户、条目和 MediaSource；播放能力查询不启动 Emby 播放会话。

| 数据或操作 | 所有者及边界 |
| --- | --- |
| 登录与多连接 | Registry 保存连接和用户令牌，不保存登录密码；同服不同用户可登记。切换需要确认，旧页面不能切回旧账号。 |
| 名称、简介、季集、播放状态 | 只投影为当前页的 Kodi ListItem。关闭页面不保存列表；不写 Kodi 视频库、Bobbi 整理索引或服务器进度。服务器“继续观看”不是不同剪辑间精确续播的证明。 |
| 海报 | 按需读取，不进入 Bobbi 磁盘图片缓存。每个 profile 复用一个私有签名密钥；同一账号代际和图片标签不变时，后台正常重启不会产生新的 Kodi 缩略图。账号撤权使旧签名无法再取图，但不删除 Kodi 已经缓存的图。 |
| 播放 | 核实所选版本允许原片、可按字节读取后，调用 Kodi 的 setResolvedUrl。动态库不接管播放器、不走 115、不转码。探测只读一个字节。 |
| 私服原片 | 匿名请求被拒时，仅对登记服务器上选定版本的静态原片自动使用当前账号重新验证，并用 Kodi HTTP 请求头交接，不逐片询问。Emby 请求的查询串和 Bobbi 的控制回执不含令牌；Kodi 持有凭据，其调试日志和遥控接口可以读到令牌。建议用普通用户账号和 HTTPS，不要公开原始日志。禁止重定向，不转发媒体或开放分享。 |

取舍参考：[EmbyCon](https://github.com/faush01/plugin.video.embycon/blob/fb45b67e40216bbc3ce64f4520b58812e5b86069/plugin.video.embycon/resources/lib/utils.py#L94-L134) 区分用户明确允许的可访问共享路径和服务器流；[Emby Next Gen](https://github.com/MediaBrowser/plugin.video.emby/blob/plugin.service.emby-next-gen_11.1.27/hooks/webservice.py#L382-L400) 可用本机 307 跳转到含账号令牌的流地址；[Jellyfin for Kodi](https://github.com/jellyfin/jellyfin-kodi/blob/7d74d62ec0c19d4cd311419f20162049df0c559b/jellyfin_kodi/helper/playutils.py#L319-L334) 的静态流绑定 MediaSourceId。这里只借鉴按版本交接，没有复制令牌查询串或新建视频代理。不会把服务器文件路径猜成盒子上的 NAS 路径，必须转码、跨站跳转等来源仍不支持。

实测官方 Emby Server 4.10.2.0，使用隔离环境和临时普通账号，未使用个人媒体。服务器元数据、搜索、版本核验及认证图片正常；同一静态原片带用户令牌返回 206，匿名和 HTTP Basic 均为 401。真实 Windows Kodi 21.3 验证了原生目录、按需展示、后台正常重启后同图新增 0 B；静态原片夹具验证了带认证头的原生播放、30 秒跳转及拒绝跨站 302。以上不是 AM6B+ 实机或正式版验收。
