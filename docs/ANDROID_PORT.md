# Android 助手：工具链与真实 BT 引擎接入

> 公开 alpha 更新：安装器 ZIP 已随 APK 内置，Kodi 仓库自动安装组件；
> 六位短时配对已替代必须导出文件，导出只作备用；115 扫码在 Kodi 向导运行。
> 现已构建非 debug 的 Release APK 并用独立长期密钥签名，11 项 Java 测试通过。
> 真实设备验收仍未完成；以下“预览/待集成”段落为最初调查记录，以 README 为准。

核查日期：2026-10-19。目标是 Android 8/API 26+、无需 root、配合现有 Kodi，
不是重编 Kodi，也不是只有能力声明的空 APK。当前已构建真实 ARM32/ARM64 通用助手 APK，
单元测试与静态检查已经运行；尚未安装到设备，不能据此宣称实播兼容。

## 当前实现与发行范围

- 同一 GitHub 仓库只区分 CoreELEC 与 Android APK；不选择盒子型号，不设品牌白名单。
- 当前 APK 是本机后台预览，不是完整影院；完整安装器、115 扫码与成组更新仍需集成。
- 中文大按钮按启动、首次配对、打开 Kodi 排列；可导出配对文件给 Kodi 向导导入，
  不要求手填地址/密码。状态根据真实控制接口检查，不把进程存在当连接成功。
- 沿用现有新 UI 的背景/卡片/焦点/橙色强调与140ms克制动效，使用未修改的授权字体。
- 手动启动前台服务，不刷机、不 root、不无障碍保活、不静默更换系统播放器。
- 先待用户方便时测试 AM6B Plus 原生 Android，保留 SD 卡上的 CE；Zidoo 后续用同一包测。
  暂不做 Zidoo 专属原生播放器。HDR/杜比视界/音频直通差异留待实测，不降低源画质绕过。

构建：`python tools/bootstrap_android.py build --accept-required-sdk-license`。
工具脚本仅安装明确列出的 SDK 包；正式使用包不需要 SDK、ADB 或电脑常开。
核验：`python tools/verify_android_apk.py`，检查真实引擎、字体许可、签名、最低API和两种ARM架构。
开发签名不等于正式发行签名；公开发布二进制前须提供对应源码/构建材料并完成发行审查。

## 初始调查与现已固定的最小工具链

PATH、常见 Android/JDK/Gradle 用户目录、Program Files，以及 `D:/Tools`、
`D:/Launcher`、`D:/LG_G5_Firmware` 均未找到 `java/javac/gradle/sdkmanager/adb`。
`D:/daily/download` 是 `D:/Downloads` 链接；可见 Kore APK，但没有这些工具安装包。
当时可用工具是 Git 与 GitHub CLI；不能据此声称整盘绝无 JDK。
现已在本项目忽略的工具目录准备下表工具，没有改全局 JAVA_HOME 或安装 Android Studio。

不需要 Android Studio、模拟器或整套 NDK 就能先构建 Java 前台服务与已编译引擎包装。
采用已核实的兼容组合，不照搬上游客户端最新构建依赖：

| 项目 | 固定候选与官方取得方式 |
| --- | --- |
| JDK | Temurin **21.0.12.1+1** Windows x64 ZIP，205,073,461 B；[Adoptium API](https://api.adoptium.net/v3/assets/latest/21/hotspot?architecture=x64&image_type=jdk&os=windows&vendor=eclipse) 返回版本、固定下载 URL、SHA256、签名；实际下载应固定版本，不能重新解析 latest 后静默升级 |
| Gradle/AGP | **Gradle 8.11.1 / AGP 8.9.2**；[Google 兼容表](https://developer.android.com/build/releases/past-releases/agp-8-9-0-release-notes) 为 API 35、Build Tools 35.0.0、JDK 最低17；[Gradle 表](https://docs.gradle.org/8.11.1/userguide/compatibility.html) 确认从8.5起可用 JDK21 运行；AGP 8.9.2 POM 已实际取得 HTTP200 |
| SDK 管理器 | **Command-line Tools 22.0**，`commandlinetools-win-15859902_latest.zip`，155,655,386 B；[Google 下载页](https://developer.android.com/studio#command-line-tools-only) 公布 SHA256。仓库元数据已有23.0，但页面展示22.0，故明确固定22.0，不混用 latest |
| SDK | `platforms;android-35` rev2，64,273,788 B；`build-tools;35.0.0`，59,878,107 B；应用 `minSdk=26`，初始 `compile/targetSdk=35`，不等于只能运行Android15 |
| ADB | `platform-tools` **37.0.1** Windows，8,044,989 B；只用于后续明确设备验收，不是构建必需品 |

固定 SHA256（下载前比较发布方值，下载后本地 `Get-FileHash -Algorithm SHA256`）：

```text
OpenJDK21U-jdk_x64_windows_hotspot_21.0.12.1_1.zip
f9d6e191ab098c0d416e7d588a24420a8621cd2f4720dab2459b8b7b2d2d8b4e
gradle-8.11.1-bin.zip
f397b287023acdba1e9f6fc5ea72d22dd63669d59ed4a289a29b1a76eee151c6
commandlinetools-win-15859902_latest.zip
90ae805d20434428bffcb699c290860f19bb5f66a67e6b330067e3de801fb04a
```

Gradle SHA 来自[官方独立校验文件](https://services.gradle.org/distributions/gradle-8.11.1-bin.zip.sha256)，
应写入 `distributionSha256Sum`。SDK 包的[官方 repository2-3.xml](https://dl.google.com/android/repository/repository2-3.xml)
目前公布 SHA1（不能冒称 SHA256）：platform35=`0bb560a90a7a2cbd0dd8348224d518b638fe7949`，
build-tools35=`af059bb67cf7786f45ee0db85e2d24985df1b4b6`，
platform-tools37.0.1=`e03e78b1d80b396f1c3358e31251cb31740e1110`。
下载路径由该元数据的 archive URL 拼接 `https://dl.google.com/android/repository/`。
SDK 许可处理是正常安装步骤；准备中仅对明确列出的包接受必需许可，不执行 blanket --licenses。

## 上游固定证据

- [TorrServe 客户端](https://github.com/YouROK/TorrServe/tree/eec3eb36da816c1bb3fcf4fe89480c5b493a2bd5)：
  GPL-3.0，`eec3eb36da816c1bb3fcf4fe89480c5b493a2bd5`；当前客户端143。
  实际配置为 min16/**target28**/compile37、AGP9.4.0、Gradle9.7.1、Java21/Kotlin2.2.10。
  `ServerFile.kt` 把下载 ELF 放 `filesDir/torrserver` 后 shell 后台执行，带可选 root/
  Accessibility 保活与整进程 `killall`；不能原样作为现代通用助手。不要带入广告、
  Firebase、root、Accessibility 或旧账号设置。
- [TorrServer MatriX.147](https://github.com/YouROK/TorrServer/tree/a86d8fa7fd4e07605f240fe69bf299392f7cb023)：
  GPL-3.0；tag 解引用 commit=`a86d8fa7fd4e07605f240fe69bf299392f7cb023`。
  Android CI 实际使用 CGO/NDK、`GOOS=android`、API21 clang、`-tags=nosqlite`，
  提供 arm7/arm64/386/amd64 四个 Android ELF。不是 Linux ARM 二进制替代。

[官方发布资产](https://github.com/YouROK/TorrServer/releases/tag/MatriX.147) 的 GitHub API
`assets[].digest` 已返回 SHA256；当前已下载 ARM32/ARM64 两项并核验 ELF、哈希与 ABI：

| 资产 | 字节 | 官方 SHA256 |
| --- | ---: | --- |
| TorrServer-android-arm7 | 63,929,180 | `8cb44454ff201bd902a9c454e6f046d4fb25937a3b628270d0c7b48f1cc7b94c` |
| TorrServer-android-arm64 | 64,445,000 | `92ccc46a21d87e5861dabf31ece084ac910499dbb752ed5a37f6dceeb91fcf03` |
| TorrServer-android-386 | 63,727,580 | `656154bd6e12737d5da867f306c50e81695cf9331fcc1e583b2e829e49fd3c04` |
| TorrServer-android-amd64 | 66,777,224 | `eafab9353cf0e672a15426fd32c13512d57d6b3f203bbfbcbaaf352d67458959` |

## 最小真实实现与 AAR 选择

当前实现：小型 Java Activity + 明确启动/停止的 ForegroundService，APK 携带按ABI
固定的上述引擎，交由 PackageManager 安装到只读 native-library 位置，再以参数数组
启动/持有准确子进程。不从可写 files/cache 目录执行，不动态下载更新可执行代码，不用
shell 拼接或 `killall`。这是待实测的包装方案，不是上游已经认证的现代 Android 路径。
需检查 ELF/PT_LOAD、实际安装位置、必要的 native-lib 提取/不剥离设置和
[16KB页兼容](https://developer.android.com/guide/practices/page-sizes)。

原因：[Android10执行限制](https://developer.android.com/about/versions/10/behavior-changes-10#execute-permission)
明确禁止 target29+ 从可写应用家目录 `execve`；仅降低 target 来绕过不符合可维护目标。

长期更自然的嵌入路径是上游 `server/mobile/torrserverkit` 的
`StartServer/StopServer/IsRunning` → `gomobile bind` Android AAR。这是真实引擎入口，
但当前官方 CI 只构建 iOS XCFramework，**尚无已发布 Android AAR**。额外要求：

- nested module `go 1.26.0`，高于主模块 `go 1.25.7`；可固定官方 **Go1.26.9**
  Windows ZIP（75,002,909 B，SHA256
  `d722201a9c0c086d1610e111c48203009af690892ed708072bd5ae20160e7a59`），
  版本/hash来自[Go官方JSON](https://go.dev/dl/?mode=json)。
- 上游固定 `golang.org/x/mobile v0.0.0-20260821190718-4776eadac327`；其 Android
  bind 源码确实需要 SDK `android.jar`、`javac/jar`、NDK clang 和 `-buildmode=c-shared`。
  可显式 `-androidapi 26`；**不要求 SDK37**。建议固定 NDK **28.2.13676358/r28c**
  以获得默认16KB支持；Windows包748,118,221 B，官方SHA1
  `086bba43ff2f5eb0e387b15c8278bb4e0d89ba1d`。因此 AAR 路径显著增加工具下载，
  不能声称仅有 Android SDK 就能构建；所有预编译依赖仍须检查16KB兼容。
- kit 的 torrent replacement 仍为 `tsynik/torrent v1.2.31`，主模块已为 `v1.2.32`，
  需要明确对齐而非静默更换。还发现 kit 只预检127.0.0.1，未设置 `ExecArgs.IPs`；
  实际 web 读取该字段，空列表绑定全部接口。必须在独立补丁中明确设loopback后才可交付。

## 下一步与未通过的门槛

1. 确认采用 APK 内固定 ELF 还是构建 AAR；取得并核验对应源码/许可证/二进制，保留
   GPL对应源码、修改与构建清单。先验证引擎可实际启动，不制造空壳“已支持”。
2. 将引擎HTTP严格绑loopback、限定本机授权，私有数据放助手自己的目录；做真实
   `/echo`、torrent元数据、文件选择、Range流读取、停止/崩溃恢复测试，再向Kodi暴露能力。
3. 前台服务在用户操作后启动，及时显示通知/停止入口，按真实用途声明FGS类型；不靠
   Accessibility/无条件开机保活。[Android15 dataSync限制](https://developer.android.com/develop/background-work/services/fgs/timeout)
   为24小时累计6小时，不能拿它冒充无限后台流媒体服务。音画不转码、不降低质量。
4. 已准备 SDK/JDK/Gradle/ADB 并构建 APK、核验 ELF 与签名；尚未连接 Android 设备，
   所以设备后台能力仍是 **unverified**。离线构建不自动改变此状态；仍需安装、启动、
   更新、停止、重启及此前没测试过的新电影/动漫、字幕实播验收。

## 上游媒体鉴权边界

随机配对凭据保护控制 API。当前固定上游的 `/echo` 与已添加种子的媒体流存在免认证路径，
不能宣传“所有媒体均强鉴权”。外部及内部 HTTP 监听必须保持 loopback；不开 LAN 或公网端口。
真正的强媒体鉴权需要修改并重编上游，不能用前置代理掩盖本机免认证端口。
