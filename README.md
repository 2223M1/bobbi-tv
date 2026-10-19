# bobbi TV · 波比影院

大海报、遥控器友好的导航、自选片源。把自己的网盘、NAS 与片库放进同一个影院。

[下载测试版](https://github.com/2223M1/bobbi-tv/releases) · [安装说明](docs/INSTALLATION.md) · [接入网盘与 NAS](docs/LIBRARIES.md) · [反馈问题](https://github.com/2223M1/bobbi-tv/issues)

> **0.1.0-alpha.1 公开测试版。** 已完成源码、仓库安装入口、通用 Android APK 和离线验证；尚未完成 Android 真机全新安装 / 音画实播。不要直接覆盖日常看片环境。APK 是安装与 BT 后台助手，**不是独立播放器，也不包含 Kodi**。

## 怎么装

只区分操作系统，不选盒子品牌或型号。

| 你现在用的系统 | 下载 | 接下来 |
| --- | --- | --- |
| CoreELEC / Kodi 21 | `repository.bobbi-0.1.0.zip` | Kodi「插件 → 从 ZIP 文件安装」；再「从库安装 → bobbi TV → 程序插件 → bobbi 开始使用」 |
| Android 8+，ARM32 / ARM64 | `bobbi-tv-0.1.0-alpha.1-android.apk` | 打开 APK，按「安装影院」提示保存仓库 ZIP；没有 Kodi 时先安装官方 Kodi 21 |

「bobbi 开始使用」会让 Kodi 自动安装皮肤、影院、片库和设置向导，不需要逐个拼装插件。
打开向导后，按需登录自己的 115、添加 NAS / WebDAV，或连接本机 BT 后台，最后选择「进入波比影院」。
Android 用六位短时配对码连接助手，无需手抄地址或密码；系统文件选择器不可用时，可从下载页取得相同仓库 ZIP。

无需刷机、root、SSH、ADB 或电脑常开。Kodi 的 ZIP 安装授权、Android 安装确认、扫码登录确认仍由你操作。

## 可以做什么

- **新影院 UI**：延续波比新 UI 的布局、橙色点缀、字体层级、焦点与克制动效；音轨 / 字幕快捷菜单保留。
- **自己的媒体**：多个 SMB / NFS NAS、WebDAV 网盘、本机 / U 盘，以及自有直链 JSON 片库；可增删连接和更新目录，不动远端文件。
- **115 资源目录**：合并原目录与补充分享，安装者用自己的 115 App 扫码。二维码本机生成；不内置共享 Cookie，不自动转存。
- **自选片源**：AnimeGarden 动漫候选、漫迪目录、115 分享，以及自己配置的检索服务；保留作品、年份、季集与版本过滤。
- **不改音画质**：标准 Kodi 播放，不转码、不降分辨率、不更改 HDR 或音频直通设置；首个片源始终手选。BT 合集还需确认具体文件。
- **后续更新**：Kodi 仓库检查组件新版本；APK 使用固定发行签名，可覆盖升级保留设置，仍需系统确认。

海报和影视搜索需要自己的 **TMDb API Key**（向导内配置；NAS / 直链浏览不需要）。不保证 GitHub、TMDb 或每个资源站在所有网络均可访问，不内置私人代理。

## 先了解边界

| 能力 | 本版状态 |
| --- | --- |
| 个人来源管理、115 扫码、准确文件解析、手选播放 | 已实现并离线测试；个人账号实际授权和播放仍需你验收 |
| Android 助手 | 实际 ARM32 / ARM64 引擎、Release 签名、单测与 lint；未真机安装 |
| CoreELEC 本机 BT | 向导按运行架构下载固定哈希引擎；只在本机启动；未在新装设备验收 |
| 自动找外部中文字幕、自动续播下一集 | **未移植私人后台逻辑**；使用 Kodi 标准字幕选择 / 延迟调整和手动选集 |
| 其他品牌网盘、Emby / Jellyfin / Plex | 通过 WebDAV / SMB / NFS / 自有直链接入；不是所有厂商的原生登录 / 服务端 API 客户端 |
| HDR / Dolby Vision / 音频直通 | 取决于系统、Kodi 与硬件，未做型号认证；Android 与 CE 并非完全等价 |
| 更新与回退 | 使用 Kodi 原生仓库；没有启用实验性整组热更新器，也不宣称断电原子回退 |

目录命中不等于可播放，文件名的「双语」不等于字幕已验同步。失效分享、需要会员的账号能力、BT 活跃度和网络速度由对应服务决定。

## 更新 / 回退

建议 Kodi「插件更新」选择 **通知，但不要安装更新**，停止播放后再更新。不要在播放中替换皮肤或影院组件。
APK 下载同一仓库的新版本直接覆盖安装；不要先卸载。遇到签名冲突请停止，不关闭系统防护。

回退时先切回 Kodi 默认 Estuary，退出 Kodi 并备份用户数据，再从旧 Release 安装同一发行的组件。账号与连接配置独立保存在设备 profile，不在发行包中。详见[安装与恢复](docs/INSTALLATION.md)。

## 开发与复现

```sh
python -m pip install -r requirements-test.txt
python -m pytest -q tests
python tools/build_release.py --output dist/repository-check
```

普通构建只读取仓库内源码与明确清单，不依赖私人项目、旧备份或迁移暂存目录。Windows Android 构建：

```powershell
python tools/bootstrap_android.py build --accept-required-sdk-license --release
python tools/sign_android.py
```

签名命令仅用于维护者，会创建本机 `.private` 中的独立密钥；自己的构建不能覆盖本项目发行签名的 APK。**请备份该密钥，永不提交 Git。**

[验证记录](docs/RELEASE_VALIDATION.md) · [第三方许可](docs/THIRD_PARTY_AUDIT.md) · [发行门禁](release/gates.json)

## 致谢与许可

感谢 Kodi、Jacktook / Sam-Max、Minsk / Confluence、Arctic Fuse / jurialmunkey、TorrServer / YouROK、AnimeGarden 与所有原作者。仓库不是这些服务的官方客户端。

新增代码 GPL-3.0-or-later；独立目录模块保留 MIT 声明；原代码、素材、字体各按原许可。Arctic Fuse 衍生美术为 **CC-BY-NC-SA-4.0**，不是全仓统一 MIT，也不提供整体商业素材授权。未修改的 HarmonyOS Sans（华为）及 Font Awesome Free 随附许可证；没有再分发 Netflix Sans、方正或 Font Awesome Pro。

仅用于管理、检索和播放你有权访问的内容。片库是索引与分享入口，不包含影片媒体文件，不授予第三方影片或字幕版权。
