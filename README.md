# bobbi TV · 波比影院

私有完整影院候选：新 UI、手动选源、自己的 115 / NAS / 片库，以及独立的字幕和续播流程。

## 当前 CE 状态（2026-10-20）

最近设备交接为 **CE 2026102006 / core 0.1.11**，保持原 F9，现用新 UI。
已补身份解析、播放终态、同版续播、外挂字幕及 RAR/部分字体兼容；
《奇巧计程车》启动缓冲、字幕下缘裁切的电视确认及空白设备/第二账号验收仍开放。
传输保持 block 默认，Windows/Android 暂停，稳定发行门未打开。

[CE2006 审查入口](docs/CE2006-WEB-REVIEW-20261020.md) · [整改与回退](docs/ce-remediation-20261020.md)

以下 1909/1907 内容是保留的历史记录，不代表最新安装状态。

## 1909 阶段记录（历史归档）

> **最终状态（2026-10-19）：按用户要求停止验证，盒子已恢复原个人深度定制版。**
> 原 F9 内核、`skin.am6b.cinema`、Jacktook/JackTorr 定制组合和原准备服务已恢复；
> 13 个 `bobbi` 候选组件停用，全部 profile 保留。只确认启动到首页，没有继续试播。
> 本分支留存 **1909 候选**及全部研究/失败记录供 Web 独立审阅，不能据此自动重新部署。
> Windows/Android 暂停；公开发布、稳定发行与完整媒体验收门禁均未打开。

[Web 审阅入口](docs/WEB-REVIEW-HANDOFF-20261019.md) · [原深度定制恢复回执](docs/CE-LEGACY-RESTORE-20261019.md) · [完整 Juku 研究](docs/research/juku-full-20261019/SUMMARY.zh-CN.md) · [发行门禁](release/gates.json)

1909 修复了 BT 合集像素格式后缀误拒绝、准备请求受理/回执、续播请求预算和私有字幕
账号归属边界；完成过签名升级和分层回退，但**仍有真实失败**：冷门 BT 缓冲超时、
115 首次播放停顿、后台准备的独立季集误识别疑点。完整实播、字体与同版续播不能标为通过。
最新主测试记录为 1426 passed / 6 skipped；跳过和重复子集不计入额外通过数量。

Juku 0.80 两架构的 **38,132 个已识别函数全部尝试反编译**，38,125 个输出伪 C，
7 个失败保留汇编与原因。是完整静态证据导出，不是原始 Go 工程恢复或逐函数语义认证。
源码与索引在本分支，大型完整研究归档和历史构建产物见
[私库审阅附件](https://github.com/2223M1/bobbi-tv/releases/tag/audit-20261019-private-ce1909)。

## 1907 阶段记录（历史归档，非当前设备状态）

下文保留 1907 当时的交付、限制和测试记录，不随 1909 或恢复操作抹去。
其中“当前”“本轮”“尚未”均指该历史阶段；最终状态以上方及审阅入口为准。

| 平台 | 当前交付 | 已有证据与未完成项 |
| --- | --- | --- |
| CoreELEC / AM6B | 1907 签名离线完整 22 组件验证、13 自有组件事务；9 上游插件保留原件 | run `20261019-211907` 实际升级成功，未重新迁移账号/profile；9 上游插件前后内容指纹、版本、原仓库来源及启用状态一致。原生 Kodi、CD2 与挂载未改。本轮未试播/换号/实际回退；1906 BT 失败仍待修，1903→1904→1903 程序回退仅为历史证据 |
| Windows x64 | **暂停**；现有 1905 完整影院 ZIP/安装器为历史候选 | 历史 1905 实际 Kodi/Python 3.8、新 UI、用户级安装、launcher 签名更新/逐字节回退/并发锁通过；1902 安装模式启动与保留 profile 卸载另有回执。不是 CE 22 组件同代包；HDR/直通未认证，EXE 无 Authenticode 签名 |
| Android 8+ | **暂停**；现有 1905 ARM64/ARMv7 APK 为历史候选 | 历史两 ABI 实际 Kodi native library、21 组件内容与发行签名已核对；未完成真机安装/升级/实播。不内嵌旧助手 BT 后台，也不包含本轮新 22 组件代次 |

历史 Android 包保留原应用 ID `org.bobbi.helper` 和发行签名以维持升级兼容。本轮不继续多端构建/测试，也不为等待这些产物阻塞 CE。不得把旧 APK、CE ARM32 库或 CE 的 DV 补丁混装到其他平台；签名冲突不能靠卸载清数据或关闭系统防护解决。

## 本轮能力

- 新 UI 和素材按私人使用范围恢复，保留原作者归属；电影/动漫选中后进入选源，不擅自播放首选版本。
- 原目录、腾讯补充目录、漫迪、动漫检索和获授权的 Juku 主站/共享目录统一参与选源。保持作品、年份、季集和版本身份；相同已可用 115 文件优先于重复 BT。
- 一个宿主管理账号代次、可续期播放链接和目录刷新。Juku 仅接入目录协议，不运行其后台、不借用其私有应用密钥或共享登录态。
- 借鉴 Juku 的账号交互：已登录状态提供扫码切换/重新登录与确认退出，提交后刷新当前目录；保持波比的账号代次与取消保护，不必把所有插件 ID 改名。本轮只部署交互，未换号验收。
- “更新与恢复”提供 Kodi 原生依赖/已装插件管理入口；9 个原版依赖由原仓库维护，13 个波比定制组件由签名事务维护。JackTorr 作者仓库 `repository.jacktook` 0.0.5 已由 Kodi 原生安装，但盒子访问失败，现已停用；旧 JackTorr fork 未替换，原版恢复/一键更新尚未完成。主插件的独立 TorrServer 文件浏览/手动字幕路径仍使用 JackTorr 公开 `buffer_and_play` 路由，增强选源才走新薄适配器。
- 新增独立 `plugin.video.bobbi.torrent` 薄适配插件，使用当前 bobbi 播放归属协议解析所选 BT。CE 只迁移现有 TorrServer 的连接配置，不安装新 daemon、不接管或停掉旧后台服务；该代实际 BT 播放仍待验。
- 自动字幕不再以时间轴验证为播放门槛；优先中文质量和双语，保留手动换字幕、延迟调整和关闭。手动意图优先，不声称自动匹配已经同步。
- 原生播放器契约承接字幕归属与续播；CE 的准备、同包字幕和字体工作为显式配置的可选能力，不在 Windows/Android 空配置启动时强行加载 Linux 后台。
- 不转码、不降低分辨率、不为找字幕换低画质视频。原语言原声优先；HDR、DV、音频直通最终仍取决于系统和设备实测。
- 保留同版续播约束，不因解析失败静默更换发行版本；历史/最近播放回到手动选源。代码与单元回归不替代这些交互的设备验收。

**TMDb 专用应用配置仍待用户完成。** 当前没有把该步骤标记为完成，也不借用第三方 Key。已有 CE 用户私有配置的本地保留，不等于本项目专用应用已经申请并验证。缺配置时应明确提示，NAS/本地片库不依赖该 Key。OpenSubtitles 是可选手动字幕入口，需要用户自己的 API Key；不配置不阻断视频或其他字幕来源。Assrt Token 只留在设备私有 profile。

上述 TMDb 状态属于历史阶段；CE2006 已完成专用应用配置，见最新整改记录。

- **自己的媒体**：多个 SMB / NFS NAS、WebDAV 网盘、本机 / U 盘，以及自有直链 JSON 片库；可增删连接和更新目录，不动远端文件。
- **115 资源目录**：合并原目录与补充分享，安装者用自己的 115 App 扫码。二维码本机生成；不内置共享 Cookie，不自动转存。
- **自选片源**：动漫候选、115 分享，以及自己配置的检索服务；保留作品、年份、季集与版本过滤。

补充维护记录：访问新装作者仓库失败期间，Kodi 于日志时间 20:06:19 出现一次原生 `segfault / exit 139`，服务自动恢复；[崩溃线程](review-evidence/ce-upstream-ui-1792411741018097300.json)位于 `CVariant` / 目录要求处理 / AddonBrowser 窗口切换路径，不能断言仓库超时导致崩溃。未修改 F9，旧 JackTorr profile 设置与 TorrServer 进程保持不变，已停用本轮新增且不可达的仓库并回到主界面。[恢复后状态](review-evidence/ce-runtime-1907-after-upstream-recovery.json)显示宿主 ready、准备服务运行且无 Python 失败，但不代表实播、真实换号或循环回退验收。

## 同代更新，不在播放中热替换

本轮 CE 使用平台绑定、原 RSA 信任钥验签的完整 **22 组件离线代次**，所有组件仍校验哈希、归档结构与身份，但升级和回退只替换 **13 个自有组件**。9 个上游依赖不覆盖、不补装、不改启用状态或来源；缺失/过旧时提示通过 Kodi 安装或更新。旧 21 组件客户端仍拒绝新 22 组件包，不放宽白名单或更换信任钥。不把旧 `repository/` 公开资产或历史 Windows/Android 包当作当前 CE 发行，也不混装散件。组件包不含账号、设备备份、私人代理或签名私钥；没有匿名自动更新地址。

CE 使用专用停止/屏蔽 owner 的事务控制器，见[迁移说明](docs/CE-MIGRATION-20261019.md)。旧完整 22 项备份须全部验哈希，但当前控制器只恢复 13 个自有组件；未完成的旧 22 项 journal 必须由对应冻结控制器恢复，不能按新策略重新解释。原版与定制组件的具体归属见[维护边界](docs/UPSTREAM-ADDONS-20261019.md)。Windows launcher 与 Android 整体 APK 的历史维护边界见安装说明，本轮不执行其新一代构建、测试或交付。

回退只恢复自有程序代次和规定的启用/界面状态，不回滚用户观看数据、不删除云端文件。1903/1904 CE 往返与历史 Windows launcher 维护已有回执，**不能冒充 1906 或 1907 回退通过**；当前代次实际回退、断电恢复和完整音画/字幕/续播仍有门禁，不能用旧作品重复播放代替。

## 开发与证据

```sh
python -m pip install -r requirements-test.txt
python -m pytest -q tests --ignore=tests/private_baseline --ignore=tests/preparation_regression
python -m pytest -q tests/private_baseline
python -m pytest -q tests/preparation_regression
python tools/build_release.py --output dist/private-components-check
```

三套测试须独立进程运行，避免历史 Kodi stub 相互污染。最新 CE 1907 对应记录为 **primary 1225 通过、6 跳过（132.04 秒）／baseline 741 通过／preparation 177 通过**；跳过不算通过。原始 JUnit：[primary-final](review-evidence/ce1907-unit-primary-final.xml)／[baseline](review-evidence/ce1907-unit-baseline.xml)／[preparation](review-evidence/ce1907-unit-preparation.xml)。

历史 CE 1906 为 primary 1047 通过、5 跳过（73.09 秒）／baseline 741 通过（6.39 秒）／preparation 177 通过（7.13 秒）。旧记录继续保留：[primary](review-evidence/ce1906-unit-primary.stdout)／[baseline](review-evidence/ce1906-unit-baseline.stdout)／[preparation](review-evidence/ce1906-unit-preparation.stdout)。

[final-unit-tests.json](review-evidence/final-unit-tests.json) 仍是 1905 历史汇总，未更新为上述结果；[private-artifact-boundaries-1905.json](review-evidence/private-artifact-boundaries-1905.json) 也仅证明旧 21 组件和当时三平台包。当前 [CE 1907 包审计](review-evidence/private-artifact-boundaries-ce1907.json) 已核对 22 组件、1,371 文件，并拒绝错平台、签名篡改、组件篡改及缺失组件四项负例。[1906 的 1,370 文件审计](review-evidence/private-artifact-boundaries-ce1906.json) 保留为历史。真实哈希及升级回执见[安装与验证](docs/PRIVATE-RELEASE-20261019.md)，这些仍不代表实播成功。

此前定位并修复的范围包括成功 BT 响应被慢请求丢弃、账号代际字幕库路径及历史 Windows resolver 弹窗身份。1906 BT 回归中未再出现旧协议 `superseded` 长等待，但《Flip Flappers》合集仍未确定目标文件；正常回选源不算播放通过，1907 本轮未重测该问题。
[发现与未解决项](docs/research/DEVICE-FINDINGS-20261019.md)及[新作品验收](docs/research/NEW-WORK-ACCEPTANCE-20261019.md)
保留失败证据：Assrt 493 不等于已下载；未收到正确原生终态及同版证据时，不声称续播通过。

原生构建和发行签名使用 [native/README.md](native/README.md) 的固定工具链。现有 APK 签名与离线更新信任钥不得静默换新，私钥不提交、不进安装包。[执行记录](docs/PRIVATE-EXECUTION-20261019.md) 区分源码、宿主、设备和待用户步骤。

## 归属与使用范围

感谢 Kodi、Jacktook / Sam-Max、Minsk / Confluence、Arctic Fuse / jurialmunkey、TorrServer / YouROK、AnimeGarden、Juku 与各原作者。本项目不是这些服务的官方客户端。

新增代码 GPL-3.0-or-later，独立模块及原始代码、素材、字体沿用各自声明；不是全仓统一 MIT。恢复私人素材不代表取得对所有第三方素材的公开再分发或商业许可。私库不取消版权义务，反编译研究材料也不冒称作者原始源码。

只管理和播放你有权访问的内容。目录不含影片媒体文件，也不授予第三方影片、字幕或字体版权。旧公开发行记录仅供追溯，不作为本轮安装路径；详见[第三方审计](docs/THIRD_PARTY_AUDIT.md)。

[验证记录](docs/RELEASE_VALIDATION.md) · [第三方许可](docs/THIRD_PARTY_AUDIT.md) · [发行门禁](release/gates.json)
