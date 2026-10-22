# 私人候选执行记录 · 2026-10-19

> 本文件保留 **1903 阶段的执行检查点**，下列“仍未完成”是当时状态。
> 后续 1904 真实升级/回退与 1905 部署、实播发现，见
> [当前安装记录](PRIVATE-RELEASE-20261019.md)、
> [设备发现](research/DEVICE-FINDINGS-20261019.md)及 [gates](../release/gates.json)。
> 不能把旧回执继承为新代次全项已验收，也不要把本页旧计数当最终测试计数。

本轮以用户批准的三端整改计划为准。`2223M1/bobbi-tv` 已转私库并经 GitHub API
再次读回 `private=true`；`am6b-community-baseline-v4` 仍为私库。未改 Ninja Slayer。
旧公开副本不能追溯撤回。已建独立工作区，不改旧 dirty 工作树。

账号、挂载、VPS、CD2 及真实观看数据不随源码复制。

## 状态解释

本文件不是完成证明。各子项完成后附原始回执；编译成功、模拟测试和真机认证分别标注。
CE 未通过离线回归前不部署；Android 未证明可靠远程返回 CE 前不切换系统。
只接受完整影院 APK，不将原助手 APK 冒称 Android 播放器。

## 1903 冻结与已完成源码检查点

版本 `0.2.0-private.1`，完整组件代次 **2026101903**。21 组件冻结清单：
`dist/private-components-2026101903/manifest.json`，SHA-256
`9872802aba2757af5a62e1832745774579ecfcd3ebb0b6c76c0071df895b3081`。
旧 `repository/` 与 `0.1.0-alpha.1` 的历史公开安装文档不作为本轮发行输入。

- 恢复新 UI 与可维护入口，不恢复旧皮肤搜索逻辑为唯一入口。
- 统一主站/共享目录/本地缓存的渐进检索、完整/部分/过期状态、请求合并与有界后台刷新。
- 一个可移植宿主管理账号代次、播放链接、图片缓存和可选 CE 准备能力；不是再运行一套
  目录守护进程。Windows/Android 空配置不导入 CE 的 CD2/ffprobe 原生后台。
- 字幕按内容质量/身份匹配，时间轴与字体就绪不再绑成视频准入；手动字幕意图优先。
  同包/显式目录字幕引用可走独立有界下载，OpenSubtitles 可选手动入口已打包。
- TMDb 图片经独立只读 loopback 缓存；官方 HTTPS 优先，有界 DoH 回退保持原域名 TLS。
  **专用 TMDb 应用配置仍待用户**，不能把传输实现和旧私有配置迁移冒称应用认证完成。
- 平台绑定的 RSA 签名完整离线代次、真实独占生命周期、前代程序回退与高水位防重放。
  修复签名输入路径/二次读取、超大回退清单和 Windows 捆绑 Python 父 PID 错报。
- CE 实测发现 Cryptodome 的 DSS/ECC 跨命名空间不兼容；改为一次 P-256 自检选择整套
  namespace 并缓存。CE 实际选 Crypto，Windows 原生宿主选 Cryptodome，均通过签验。
- CE 的 mount namespace 使 `/proc/PID/exe` 与解引用后重开的同名路径指向不同二进制；
  1903 直接打开并校验内核 exe 对象，不放宽 F9 哈希 pin，也不更换原生 Kodi。

## 本轮验证，不累计重复 targeted tests

三套独立 pytest 进程的完整结果为：

| 套件 | 结果 |
| --- | --- |
| primary（包含状态迁移及 proc/exe） | 817 passed，2 skipped |
| private_baseline | 685 passed |
| preparation_regression | 177 passed |

两跳过均是 Windows 无法建立符号链接测试夹具；未把它们折算为通过。
逐套命令、原始 stdout 与 JUnit 见 `review-evidence/final-unit-tests.json`。
不要把此前 117/213/100 等重叠 targeted test 再相加宣传。

实际 21 个组件共 1,358 文件，压缩 95,927,210 字节、展开 189,790,869 字节；
全部通过真实 updater 的解包约束。三平台 1903 离线包验签及成员哈希通过；错误平台、
篡改签名、篡改单成员、缺少成员均拒绝。见 `review-evidence/private-artifact-boundaries.json`。

## 三端原生与设备证据分开

- **Windows**：实际 Kodi 21.3 + 捆绑 Python 3.8，launcher 控制的新 profile 启动；
  `skin.bobbi.cinema` 启用，7 个 `Player.Bobi*` 接口注册，正常退出。实际 launcher 在
  throwaway profile 完成 signed apply、3,059 个文件逐字节回退、序号重放/篡改/并发锁拒绝。
  1903 用户级静默安装已实际执行，4,397 个冻结镜像文件哈希一致；1902 的安装模式
  启动和保留 profile 卸载仍标为历史回执，不冒充 1903 卸载或音画实播。EXE 尚无
  Authenticode 签名。
- **Android**：1903 ARM64 / ARMv7 完整 Kodi APK 已生成；保留应用 ID/原签名，
  versionCode 2026101903。独立核对实际包中各 1,358 个冻结组件文件及 45 个原生库，
  均匹配库存/回执。见 `release/native-host-artifacts-20261019.json`。两 verification
  回执仍明确 `real_device_verified: false`。不含旧助手 BT 服务，不宣称已经真机升级。
- **CE**：只读预检核对 Kodi/Python/ffprobe/font tool 的 ARM32 ABI、pycryptodome3.4.3、
  本机账号 UID 与旧状态可迁移性。实际 P-256 签验及隔离 package 加载通过。控制器和
  1903 经 run `20261019-174118` 实际部署；新 UI、宿主 ready/native owner、准备 RUNNING
  与当前 account 匹配，旧准备服务 inactive。新快照有 14 部/58 来源及 3 条 direct 状态。
  普通电影选源已显示 15 个来源，35 秒保持选源且不自动播放；仍有两个 provider 超时
  提示，不能把部分目录成功算成播放或全部检索通过。实际回退及新作品实播另行验收。

对应回执：`review-evidence/native-windows-startup-1903-20261019.json`、
`review-evidence/native-windows-update-roundtrip-1903-20261019.json`、
`review-evidence/native-windows-installer-1903-20261019.json`、
`review-evidence/native-windows-uninstall-1902-20261019.json`、
`release/native-host-artifacts-20261019.json`、`review-evidence/ce-dependencies-preflight.json`、
`review-evidence/ce-20261019-174118-deploy.json`、`review-evidence/ce-runtime-health.json`。

## 仍未宣称完成

用户的 TMDb 专用应用配置、Android 真机安装/升级/实播、1903 Windows 安装模式启动/卸载、
各平台 HDR/DV/直通和长时间观看、断电设备恢复、CE 本轮真正新作品字幕/续播验收。
OpenSubtitles 的用户 API Key 可选，未配置不是视频阻断项。
新作品候选与排除旧测试证据见 `docs/research/CE-PREFLIGHT-20261019.md`。

本轮安装/更新路径见 [PRIVATE-RELEASE-20261019.md](PRIVATE-RELEASE-20261019.md)，
CE 设备本地迁移与程序/flags/gui回退边界见 [CE-MIGRATION-20261019.md](CE-MIGRATION-20261019.md)。
`release/gates.json` 的公开/稳定门禁继续为 false，后续只凭具体新回执更新单项。
