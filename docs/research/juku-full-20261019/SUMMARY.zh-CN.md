# Juku 0.80 全量研究交付结论

这次交付是 **AMD64 + ARM64 两个 ELF 的全量静态反编译**，不是只挑字幕、账号或
播放器函数。Go runtime、标准库、第三方库及 Juku 业务函数全部纳入：**38,132 个
已识别函数全部尝试，38,125 个成功输出伪 C，7 个失败保留反汇编与两次尝试记录**。
两架构各 2,289 个 Juku 自有函数全部成功；Go 函数表与 ELF 函数符号的入口遗漏均为 0。
此外保留了原始 Python、配置、图片与可定位的内嵌网页资源。详见 [覆盖与失败清单](README.md)、
[全程序设计研究](DESIGN.md)、[原代码与资产审查](ASSETS.md)。

“全量”不表示原始 Go 工程完整恢复，也不表示每个函数都经人工语义证明。7 个失败来自
runtime/标准库/第三方库；仍有 48,371 / 43,748 字节的函数 body 外 `.text` 未分类。
接口分派、内联函数、远端服务及真实运行效果不能仅由伪 C 保证。没有运行样本 daemon、
使用包内私钥或把反编译材料装进产品。

## 如何参考有价值的部分

以下“已吸收”指现有工作区可核对的实现，不声称本次收尾新增生产代码，也不替代对应
代次的真机验收。全量材料用于全面比较设计边界，并不要求复刻上游全部功能。

| 状态 | 内容与边界 |
| --- | --- |
| 已吸收：目录适配 | 主站/共享库作为目录来源，分阶段刷新、快照校验和原子发布；播放继续使用当前用户账号与选中媒体身份。见 [juku_catalog.py](../../../addons/script.module.bobbi.core/lib/bobbi_core/juku_catalog.py)、[juku_refresh.py](../../../addons/script.module.bobbi.core/lib/bobbi_core/juku_refresh.py)。 |
| 已吸收：同源字幕 | 依据两架构核对的 `sub_fid/sub_id/subtitle_id` 协议解析显式引用，再在选中分享和媒体身份内取字幕；不是泛抓所有同名字幕。见 [share_subtitles.py](../../../addons/script.module.bobbi.core/lib/bobbi_core/share_subtitles.py)。 |
| 已吸收：缓存与请求合并 | 图片读取有界、同键在途请求合并、成功结果复用；不照搬上游整个图片代理或预热后台。见 [image_cache.py](../../../addons/script.module.bobbi.core/lib/bobbi_core/image_cache.py)。 |
| 保留自身实现 | 账号代次、播放所有者、取消与迟到结果守卫沿用波比边界；不能因 Juku 有退出/取消方法就认定其具备同等并发保证。见 [account_manager.py](../../../addons/script.module.bobbi.platform/lib/bobbi_platform/account_manager.py)。 |
| 不直接采用 | 整套 daemon/provider 重写、另一套平行后台、直接注入/清理 Kodi 数据库、全局代理覆盖、把请求失败吞成空列表、无需求的默认远控/中转服务；不复制密钥和账户状态。 |
| 待实测或明确需求 | 分块读取/seek/URL 续期的真实高码率表现、跨账号并发、长任务取消终态；手机管理、STRM/Emby、语音与增量同步仍需独立需求和目标客户端验收。静态存在不等于已接入。 |

## 完整归档

收尾重新验算 ZIP 整体及 **114,454 个归档条目**，长度、manifest 和 SHA-256 全部一致。
资产只读复核也通过：46 个源文件、44 个镜像文件、883 个唯一复制路径，共 25,984,245 字节。

- [AMD64 全量静态包](https://github.com/2223M1/bobbi-tv/releases/download/audit-20261019-private-ce1909/juku-0.80-amd64-full-static.zip)：49,114,616 字节，57,341 项。SHA-256：`507afb7d91792188e285f89c2ef84b29aadea766833c0b52b405c43521bef7a9`。
- [ARM64 全量静态包](https://github.com/2223M1/bobbi-tv/releases/download/audit-20261019-private-ce1909/juku-0.80-arm64-full-static.zip)：51,980,628 字节，57,113 项。SHA-256：`20685353b7567a8eb1702881a24361a06e699a7fd7bc14c651d94cfd9dbc8100`。

归档包含该架构全部静态导出、索引、调用图、失败 journal 和逐文件清单，不包含原始
安装包、ELF、账户状态或私钥；原始输入的固定位置和哈希另记在 README。交付结论是
**全量静态证据已齐备，设计参考有明确采用边界；并非完整源码重建或全功能实机认证**。
