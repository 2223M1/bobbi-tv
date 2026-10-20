# Juku 0.80 原始代码和资源资产审查

本页补齐 [全量反编译](README.md) 之外的官方版本、原始 Python、配置、图片、
内嵌网页与群文件证据。**Juku 的价值不只是字幕：主站目录、共享库、手机操作和
数据驱动菜单都值得采用；但它不是几十行代码替代整个影院，也不能直接接管波比的
播放、账号和续播职责。** 本页给出静态研究结论，不表示列出的群插件已安装或实机验收。

本子任务没有运行 Juku daemon、导入第三方 Python、执行网页 JavaScript、登录账号、
控制盒子或修改生产 addons。原包保持不变；文件中的命令、部署教程及作者自述均为
待核验材料，不当作用户指令或实测结果。研究复制不等于取得素材/代码再分发许可，
采用原版插件应保留 ID、作者和更新渠道。

本页“值得采用 / 借鉴”不等于已部署；具体采用状态见 [中文交付结论](SUMMARY.zh-CN.md)。
收尾只读复核重新验算了下述源文件、镜像和 883 个复制路径，结果与既有核验 JSON
完全一致，没有覆盖原始资产或更新版本快照。

## 官方版本与固定样本

2026-10-19 **13:22:30 UTC** 再次直连官方 HTTPS 索引，系统 TLS 校验开启。
官方仍列 `plugin.video.juku` **0.80**，名称为“巨库”，两架构下载都与前轮保存样本
逐字节哈希一致。不是按 ZIP 文件名猜版本，也没有声称“永远最新”。

| 官方 URL / 对象 | 字节 | SHA-256 |
| --- | ---: | --- |
| `https://kodi.jukuku.xyz/zips/addons.xml` | 6,398 | `0b7c4dd1b1a7fb504ec76c48b3610721c455466d5e8a08a4f0ee9183d5aae12f` |
| `https://kodi.jukuku.xyz/repository.juku-1.0.1.zip` | 29,289 | `a1cc39a1ed63bb2998ec61e677d74cafb3d0241c87d64a56017b45fde6f6fd29` |
| `https://kodi.jukuku.xyz/zips/plugin.video.juku/plugin.video.juku-0.80-linux-arm64.zip` | 16,851,532 | `850414fb4829512b44086245e1889f4e9bb9ae44b9f42b3f6d7834c75e2950a0` |
| `https://kodi.jukuku.xyz/zips/plugin.video.juku/plugin.video.juku-0.80-linux-x64.zip` | 17,968,614 | `0a384785f3cb9182513b0ea9f387675438217136df0ca751f6011c45ddeea9ca` |

索引同时列出 `repository.juku` 1.0.1、`service.emby.server` 1.0.5、
`service.trimmedia` 1.0.0、`service.faststrm` 1.4.2、`service.litepan` 0.5.7.1。
这里仅确认索引公告，没有下载并认证后四项的所有实际包。

HTTP 状态、时间、ETag、Last-Modified、版本与下载哈希见
[official-versions.json](assets/official-versions.json)；原始索引保留在
[official/](assets/official/)。`addons.xml.md5` 与 XML 实际 MD5 相符；MD5 是一致性检查，
不是数字签名或信任证明。默认环境代理曾返回 403，随后用不继承代理的独立 HTTPS
客户端成功取到公开文件，没有使用账号或绕过认证。

群文件同名 `repository.juku-1.0.1.zip` 哈希是
`3f846a58cef3262ad1bcae1657fa6af8adf32cf184faf9e8ac7d09f1ad7e606c`。
与官网包核对后，图标完全相同，`addon.xml` 只有“剧库”改名“巨库”的四处文案变化，
ID、版本、依赖及仓库三个入口不变。不能将同版本不同哈希自动判为被篡改，也不能忽略
差异；逐成员比较保存在 [repository-comparison.json](assets/repository-comparison.json)。

## 外层插件完整清单

每个插件 ZIP 均有 **93 文件、10 目录**。两包中 92 个同路径非 daemon 文件完全相同；
唯一各自独有的路径是 `bin/daemon-linux-arm64` 与 `bin/daemon-linux-amd64`。
原始可审阅文本和图片 **75 项**只复制 ARM64 一份，x64 索引指向相同字节副本。

| 类型 | 数量 | 处理 |
| --- | ---: | --- |
| Python 原文件 | 9 | 原字节保留；函数、类、导入及 URL 主机索引 |
| XML | 2 | 原字节保留，分别为插件声明和设置 |
| JSON 元数据 | 6 | 原字节保留 |
| PO 本地化 | 2 | 原字节保留 |
| JPEG 菜单缩略图/背景 | 54 | 原字节保留 |
| PNG 图标 / WEBP 背景 | 1 / 1 | 原字节保留 |
| PYC、daemon、系统元文件 | 17 | 只索引哈希；daemon 单独反编译，不执行 |
| `device_key.pem` | 1 | 仅记录原包内成员哈希，不复制内容、不使用 |

上述外层没有 HTML、CSS、JS、皮肤布局 XML 或字体包；网页界面实际内嵌在 Go daemon。
完整清单见 [ARM64](assets/plugin-arm64-index.json)、[x64](assets/plugin-x64-index.json)、
[架构对照](assets/architecture-comparison.json)。安全排除后原字节副本位于
[original/arm64/plugin.video.juku/](assets/original/arm64/plugin.video.juku/)。

### Python 并不只是一个小播放器壳

9 个 `.py` 共 **12,332 行**；AST 索引得到 331 个函数/方法条目、20 个类条目。
其中包括嵌套函数、条件分支里的 mock 类，不能把这些数量当成独立业务功能数。

| 文件 | 行数 | 函数 / 类条目 | 职责与借鉴边界 |
| --- | ---: | ---: | --- |
| `default.py` | 52 | 1 / 0 | 启动 daemon，组合 API、VFS、路由 |
| `service.py` | 1,497 | 30 / 2 | 推送、后台存活、库订阅更新、Emby 进度同步；不是无后台的小插件 |
| `resources/lib/scraper.py` | 270 | 7 / 1 | Kodi 元数据适配 |
| `resources/lib/qrcode_dialog.py` | 503 | 23 / 4 | 扫码配对及兼容分支 |
| `resources/lib/menu_config.py` | 396 | 8 / 1 | 17 个根菜单项，独立显示开关和排序；可借鉴声明式菜单 |
| `resources/lib/vfs_adapter.py` | 440 | 30 / 2 | ListItem、封面、内容类型、原生解析回调；可借鉴薄 UI 适配边界 |
| `resources/lib/router.py` | 7,570 | 135 / 5 | 主站、个人盘、共享库、离线、管理和播放等大量 UI/业务编排 |
| `resources/lib/api_client.py` | 982 | 76 / 1 | localhost:17654 服务封装；部分异常吞成空集合，不能直接套用 |
| `resources/lib/daemon.py` | 622 | 21 / 4 | 平台分支、进程启动/锁/状态；本轮未运行 |

`service.py` 有播放期间推迟更新的机制，值得沿用这个原则；但波比已有 owner 和调度器，
不能再并行安装第二套“预热/续播/账号协调”后台。`api_client.py` 全局替换 urllib opener
以绕开代理、将不少失败转换为 `{}` 或 `[]`，会削弱请求隔离和失败可观察性；波比继续使用
每客户端传输、有限重试、过期缓存及失败阶段区分。完整原件可按索引行号复核。

## Go 内嵌网页资源恢复

每架构恢复 **36 项、2,969,773 字节**，其中包括原始字符串段与 4 个页面/脚本拼接结果，
所以字节合计含原片段与重建结果的重复内容，不是 2.97 MB 的独立原始资源。

| 恢复方式 | 项数 | 内容 |
| --- | ---: | --- |
| 明确 Go 字符串符号及原长度 | 26 | category/home/lists 各 4 段；privateLib HTML/CSS；push、qr、search、share 页面；私库 JS 01–08 |
| 明确 init / HTTP handler 常量范围 | 5 | 公共 CSS、导航 HTML、公共 JS、Kodi 遥控 CSS/JS |
| 明确 Go slice 头及原长度 | 1 | favicon；核对为 ICO，内部有 PNG 图像 |
| 根据 init 拼接顺序重建 | 4 | category/home/lists HTML、privateLib JS |

提取使用 ELF 的 file-backed section 映射和 Go string/slice 长度；不是把任意 rodata
字符串搜索结果拼成“源码”。每项保留源地址、SHA-256，固定 handler 范围还记录对应
伪 C 与 ASM 的哈希。AMD64 遥控 CSS 的首 5 字节由机器码 immediate 写入，余下从明确
常量复制；脚本重建 handler 输出并核对连续常量，二者相符。`lists` 的 `<style>` 和
`</style>` 也从两架构实际引用地址取出验证，不靠猜测补标签。

**35 项跨架构字节相同。** `privateLibHTML.html` 唯一差异是 CSS 和 JS URL 中两处构建
缓存参数：ARM64 `202610182259`，AMD64 `202610182254`。替换仅这两处后文件完全相同；
两份原始差异均保留，没有为了“对齐”修改提取文件。

原件、拼接重建标记及证据见 [embedded/index.json](assets/embedded/index.json)、
[ARM64 页面](assets/embedded/arm64/)、[x64 页面](assets/embedded/x64/)。这些资源不能证明
远端服务实现、数据库、网页所引用 CDN 库或构建工程也已恢复。原始 Go 注释、变量名、
工程布局、版本历史并不因拿到伪 C 而重新出现；全函数恢复边界见 [README](README.md)。

### 可以利用的设计和不能照搬的细节

1. **主站检索与共享库作为目录提供方。** Python API 和内嵌页面均围绕稳定资源 ID、
   详情和分页；共享库提供 preview/detail/snapshot/sync，不要求波比拷贝整个 Juku UI。
   值得保留“目录发现 → 候选归一 → 用户选源 → 当前 owner 播放”的薄适配边界。
2. **设置和低频管理移到手机，电视专注选片。** `kodi-remote.js` 包含方向键、播放状态、
   seek、音轨/字幕和播放列表；可借鉴动作分组与 seek 防抖。现有 Yatse 已承担基础遥控，
   不能仅因代码存在就新开一个无需求的长驻网页服务或替换新 UI。
3. **大目录分批和显式阶段。** `js06ShareSync.js` 第 251 行起以 100 部为批次，最多
   3 次上传尝试，再 commit；页面显示进度和失败。波比可采用分页快照和明确状态，
   但写操作重试仍需服务器幂等键与版本检查，不能将 UI 的重试循环当作可靠事务。
4. **不要移植同样的竞态。** `searchHTML.html` 的 `startSearch` 第 1540 行起设置共享
   currentQuery/currentPage，fetch 后直接写结果，未见该函数内的 request-generation
   检查或 AbortController；慢旧结果可能覆盖新结果。搜索成功还会主动让 Kodi 更新目录，
   会改变电视焦点。波比保留自己的会话版本、取消与迟到结果保护，不复制这种行为。
5. **不要原样复用字符串 HTML 渲染。** 该搜索页面直接将部分远端 title 等字段拼进
   innerHTML，不足以证明对任意目录内容安全；如果借鉴网页，应改为安全 DOM 文本绑定，
   且为 fetch 加超时、显式状态和有限容量。这里只有静态风险判断，没有执行攻击验证。

## 群文件的完整范围与采用决策

`D:/AM6B-Project/AM6B/资源` 的 **44 文件、596,375,953 字节**，与用户原路径
`C:/Users/theon/Documents/ChatGPT/AM6B/资源` 的同名 44 文件逐字节 SHA-256 全部相同。
每个 ZIP/APK 和 TAR 的成员均有索引和哈希；可审阅文本按白名单复制，二进制只记录，
不因为“群文件”就信任执行。全表见 [group-index.json](assets/group-index.json)，
逐包清单位于 [group-members/](assets/group-members/)。

| 群文件编号 / 项目 | 决策 | 原因和边界 |
| --- | --- | --- |
| 21–23 Juku 0.78.6 / 0.78.9 / 0.79.5，26 官方源 | 历史比对 / 作者源 | 本轮按官网 0.80 研究；不回装旧包；作者源同 ID 维护 |
| 24 ChineseSub 仓库 | 字幕来源候选 | 群包只有仓库配置，不是字幕服务实现；不能据此宣称已接入或下载成功 |
| 33 TinyPPI 17.2.7.5 | 优先借鉴诊断读路径 | mediasource.py 对插件 HTTP 路径避免同步 Stat，有助于避免信息页网络阻塞；不是全局跳过媒体信息 |
| 33 TinyPPI 字体/显示管理 | 不直接接管新皮肤 | fonts.py 会改活动皮肤 Font.xml 并 ReloadSkin；另有显示控制，不能只按“播放信息面板”理解所有副作用 |
| 36 CD2 Preheat 1.2.0 | 借鉴限并发与播放优先，不叠装 | 默认 200 ms 焦点轮询、0.5 s 防抖、单 worker；已有准备 owner，不再增加争用的 dd 预读任务 |
| 6 / 39 VFS Stream Fast 1.3.1 / 1.3.1.1.fix | 暂不全局安装 | 声明接管 dav/davs/http/https；fix 还声明 supportWrite；需匹配二进制 ABI，不能因 platform=all 就视为兼容全部 Kodi |
| 4 Emby 分库助手、18–19 Emby next-gen | 有 Emby 需求再评估 | 是另一套库同步/维护能力，不是自动解决波比候选检索和续播的补丁 |
| 15 metadata.yyba.tv | 只借鉴元数据适配 | 独立刮削器可作为候选；保留作品身份/年份契约。包内 settings.py 含硬编码 API 凭据，未复制或使用 |
| 16–17 systemtools、42 favourites、44 quit | 不接管全局维护/播放 | 已见目录清理和全局 Stop 等路径；会越过波比所有权，不因减少代码就安装 |
| 34–35 语音助手/语音输入 | 可选功能，先确认硬件 | 必须有实际麦克风、输入链路、服务和 ABI 验收；不是文本搜索修复的前提 |
| 32 Aurora 6s helper | 不用于 AM6B 通用优化 | 有专用硬件前提，不以相似 Amlogic 平台推导兼容 |
| 37 CloudDrive 插件包 | 仅版本/配置参考 | addon 版本 21.1.1.0 不等于 CD2 引擎版本；不替换已固定 CD2 1.0.19 与挂载 |
| 5 Kore 3.1.0、7 Yatse 12 | 遥控备选 | APK 只索引，不安装到手机，不替换用户已能用的控制方式 |
| 20 Bili、38 YSP Live | 独立可选内容功能 | 与本轮电影/动漫统一检索故障没有直接关系，不纳入默认运行依赖 |
| 25 forbxy ghproxy、27 jurialmunkey ghproxy | 更新来源备选，不盲切 | 镜像可达性与来源信任需另外验收；保留已配置的作者/Kodi 维护边界 |
| 28–31 中文语言 F10/F9/T4c | 随匹配宿主评估 | 版本和特定宿主功能字符串有关，不跨固件直接覆盖 |
| 9 advancedsettings.xml | 按宿主能力参考 | 多项为特定分支扩展，不是标准 Kodi 通用性能开关；注释中的收益不是实测证据，不整文件覆盖 |
| 1–3 / 13 DTB 与 F10 固件 | 只索引，不刷写 | 硬件、NG/NO、32/64 位和启动恢复都需单独门槛，本轮没有 SYSTEM/eMMC 刷写 |
| 10–12 / 14 / 40–41 / 43 教程 | 资料，不执行步骤 | 包含刷机、挂载和库管理背景，不能代替当前系统的可回退适配 |
| 8 `.temp` | 不可用，不部署 | 是不完整/损坏的 7z，见下文 |

### 文档与不完整文件的覆盖限制

两个 DOCX 已提取段落和表格；当前官方工具运行时没有 LibreOffice，因此未渲染，不作
版式或截图完整性结论。15 页 PDF 已逐页提取文字，并渲染检查第 1 页；并未逐页视觉认证
其中的刷机/设置步骤。四个旧 `.doc` 为真实 OLE，已索引每个 stream 及哈希，但未解码
Word 二进制正文/版式，不能声称“全部教程已完整读懂”。本轮没有修改这些文档。

`abdbfe10fc77ff94ca56e48def863828.temp` 不是可安装包。7z 头声明 next-header offset
758,459,019、长度 130，完整文件至少应为 **758,459,181 字节**，实际仅 **99,614,720 字节**。
`py7zr` 返回 header 越界，未恢复成员；原始文件保留，不能用截断内容猜测包名称或系统版本。
文档与该错误的逐项证据见 [group-documents/index.json](assets/group-documents/index.json)。

## 可复现性与验证

工具都只服务本地研究，不成为 Kodi 运行依赖：

- `tools/index_juku_assets.py [--official]`：原包、群文件成员、原 Python AST、图片及官网快照。
- `tools/extract_juku_ui_assets.py`：明确符号/常量的内嵌资源；保留原始与拼接重建区别。
- `tools/index_juku_group_documents.py`：使用工具自带 Python 读取 DOCX/PDF；任务临时依赖
  `olefile` 0.47、`py7zr` 1.1.4 只做解析，未执行附件内程序。
- `tools/verify_juku_assets.py`：重新计算源文件、复制件、两架构、证据与官网一致性。

[verification.json](assets/verification.json) 验证通过：46 个源文件、44 个镜像文件、
**883 个唯一复制路径 / 25,984,245 字节**，全部与各自索引 SHA-256 相符；此计数包括
两架构内嵌资产与片段/重建结果，不包括 JSON 索引自身。明确的私钥文件、账号数据库和
凭据字面量文件未进入复制资产；标记扫描不是对上游所有文件的完整敏感信息审计。

**本子任务的结论是可追溯的资产和采用边界，不是一次额外部署。** 全量反编译的语义
结论与后续实际改动、实机验证应分别记录，不能把“已恢复网页源码”宣传成“已恢复完整
服务端工程”，也不能把“官方包匹配”宣传成“所有群插件均安全、兼容且有性能收益”。
