# 私有 CE 影院候选：安装与验证

**最终设备状态：已恢复原深度定制；1909 候选已停用，所有设备操作与测试暂停。**
恢复 run `20261019-220212` 已回到 `skin.am6b.cinema` 首页、旧 F9 `8962740e…`、
定制 JackTorr `1.2.2+am6b.317` 和旧准备服务；13 个 bobbi 自有组件停用，profile
哨兵未变。恢复后没有试播，不能据此宣布全部播放问题解决。见
[最终恢复记录](CE-LEGACY-RESTORE-20261019.md)及
[真实回执](../review-evidence/ce-legacy-restore-1792418552005660600.json)。

最新审查产物为 **0.2.0-private.1 / CoreELEC 2026101909 / 22 组件、13 自有事务组件**，
不再是活动设备版本。1908/1909 的安装、通过与失败记录全部保留；稳定与公开发布门禁关闭。

用户已收窄范围：**CE 优先，Windows/Android 停止构建和测试**。下文保留的
1905 原生产物、安装及维护回执只是历史候选，不能与新 CE 22 组件混称同代，
也不因等待多端产物阻塞本轮 CE 工作。

## 1909 审查候选（已停用）

冻结 run `20261019-214404` 已实际升级 1909，未再次迁移 profile。
完整包 `dist/private-releases/bobbi-private-2026101909-coreelec.bobbi-update.zip`
SHA-256 为 `4c48464fc15850ac87f94f564ae8b84a446cb130103d87540086a904127379bb`；
对应 `dist/private-components-2026101909/manifest.json` SHA-256 为
`3a239ac3e279c45c4c37e7c17e9ac7349c34be8eeef2a8a5fcaa43fd88feeff0`。
22 组件、1,371 文件的签名及边界结果见
[1909 包审计](../review-evidence/private-artifact-boundaries-ce1909.json)。

该代《Flip Flappers》回归未确认 AV_STARTED，《东京教父》仍出现启动异常并保留
`trace_passed=false`。用户随后要求停止测试并恢复旧系统；没有以继续重播补齐验收。
最终顺序为旧 F9 原生回退，再恢复旧入口/定制 JackTorr/准备 owner；不是回退到 1907。
完整候选和待审问题见 [Web 交接](WEB-REVIEW-HANDOFF-20261019.md)。

## 1908 历史检查点文件与真实哈希

1908 包为 `dist/private-releases/bobbi-private-2026101908-coreelec.bobbi-update.zip`，
对应真实构建清单 `dist/private-components-2026101908/manifest.json`，22 组件、1,371 文件。
清单 SHA-256：

```text
742c21e994f7c661039624d10abb51e1d2be63d26d9482965ce0675b9eccfdbb
```

CE 签名离线包 SHA-256：

```text
483022c6d40738daec55ec800348d9cc14dc3a810039b630547a9418e7d52c5e
```

不要使用旧公开 `repository/`、旧助手 APK、无代次名的暂存包或混合散件来拼接本轮版本。
私有包只通过授权渠道交付，不把 GitHub 登录 Token 塞进客户端。

历史 1907 / 1906 包与清单继续保留，不作为新的安装或重放路径：

| 历史文件 | SHA-256 |
| --- | --- |
| `dist/private-components-2026101907/manifest.json` | `4260627e405bceb9662535e64618a9c3241b1532cc559c46c1137636ab20bbef` |
| `dist/private-releases/bobbi-private-2026101907-coreelec.bobbi-update.zip` | `56d679b77bf43ab47450d9e3ecb9aba5aa9a437b93261da158da406b6af6d214` |
| `dist/private-components-2026101906/manifest.json` | `27e8fb81df7bcc6cd15f9ae5e91c7f095bd2526252d1846dc7119cb3c2cc613e` |
| `dist/private-releases/bobbi-private-2026101906-coreelec.bobbi-update.zip` | `4301ca3443a59bde9850e07618aaf03762aff4a2460350020f821fe52d40f3f5` |

## CoreELEC / 1908 历史候选行为

这是已有系统的受控迁移，不是新刷固件或通用 CE 安装器。1908 在精确匹配的 F9 基线上
使用只改目录对象持有方式的原生候选，保留 CD2、账号、挂载和外部代理。只用[CE 迁移说明](CE-MIGRATION-20261019.md)中的
设备本地状态迁移及签名组件事务；不要在播放中手工覆盖 addons。
事务期间停止/屏蔽相关 owner，不能让新旧准备服务同时写同一份状态。

### 1908 已归档现况：安装成功不等于所有播放通过

- 冻结 run `20261019-205008` 实际升级 1908，未重新迁移账号/profile，CD2 和挂载未改。
- 原版 `plugin.video.jacktorr` **1.2.2** 已恢复，origin 为 `repository.jacktook`；作者仓库
  0.0.5 启用，9 个上游依赖仍保留原来源。TorrServer 仍由独立系统服务拥有。
  这是原版恢复证据，不是所有未来版本更新兼容性认证。
- 已应用原生候选 SHA-256
  `d750a88c3dc041d17ea34d06e2b2ddadcf4db0f9fffdaaa727c8a6b7427f21d3`。
  仅 `Directory.cpp` 增加局部 shared_ptr 持有；未改音画源码或固件。
  原源码控制构建精确复现旧二进制。链接有 LTO，不能声称最终所有音画机器码逐字不变。

| 1908 实际作品/片源检查 | 已观察结果 | 判定边界 |
| --- | --- | --- |
| 新电影《窃听风暴》115 / BeiTai 1080p x265 10bit | 首次 AV 观察约 9.01 秒；连续正时钟窗口 30.46 秒无观测停顿；德语 DTS-HD MA 5.1、内嵌简中已启用、全屏 | 本次有界实播通过，不代表全片/HDR/所有片源通过 |
| 新电影《东京教父》115 / 1080p REMUX | 启动后 caching 连续约 6.499 秒，其中解码帧固定约 5.996 秒；后续恢复播放并加载外置字幕 | 启动验收不通过；原 9.496 秒指标还混入时间值未更新但帧增长区间，不删除原失败证据 |
| 新动漫《灰羽联盟》S1E1 / ace BT | 已取得目标文件资料，但首段缓冲慢并最终 `buffer_timeout`，未进入 AV | 不通过，不能把目录或 metadata 成功写成播放成功 |
| 《Flip Flappers》同合集回归 | 实际文件尾缀 `HEVC-yuv420p10 AAC` 被 unscoped-range 技术标记规则拒绝，仍 `target_unresolved` | 已定位通用语法缺口，待 1909 修复/部署验证；重复旧作品不算新增作品验收 |

《东京教父》外置字幕初始化晚于缓冲开始约 3.20 秒，不能解释停顿起点。首个读取窗口的
耗时支持启动供数/缓冲不足更可疑，但聚合带宽不能证明每一时刻都有数据，也未完全排除
字幕延长后半段。原失败判定保留，后续稳定段不覆盖启动失败。

证据：[1908 升级](../review-evidence/ce-20261019-205008-upgrade.json)、
[原版插件状态](../review-evidence/ce-upstream-restored1908.json)、
[原生应用](../review-evidence/ce-native1908-apply-1792414260170029200.json)、
[原生审查与维护顺序](CE-NATIVE-REVIEW-20261019.md)、
[窃听风暴 trace](../review-evidence/ce-new-work-lives_of_others-select-1792414703779619000.json)、
[音轨/字幕](../review-evidence/ce-new-work-lives_of_others-inspect-1792414716802481100.json)、
[东京教父失败 trace](../review-evidence/ce-new-work-tokyo_godfathers-select-1792416087634125000.json)、
[对应日志](../review-evidence/ce-playback-log-1792416377770746500.json)、
[灰羽缓冲超时](../review-evidence/ce-new-work-haibane_renmei-wait-1792414887601259700.json)、
[Flip 当前失败](../review-evidence/ce-new-work-flip_flappers-inspect-1792417075983956300.json)。

后续 1909 部署、程序往返、原生回退与最终旧系统恢复另有回执；以上 1908 失败不因此
改为通过。真实换号、同版续播及完整音画认证仍未完成，用户停止测试后不再继续验收。

### 历史 1903–1907 检查点

历史进程保留如下，不改写为当前代次的验收：

- 1903 首次通过 run `20261019-174118` 实际部署：新 UI、F9 精确二进制适配、唯一新宿主及
  准备服务运行正常；迁移的 14 部/58 条准备来源和 3 条直连状态属于当前账号。
- run `20261019-181420` 实际完成升级 1904/程序回退 1903。
- run `20261019-182310` 升级 1905，不重跑迁移，账号与准备记录保持。
- 历史 run `20261019-190604` 已实际升级 **1906 / 22 组件**，回执为 `upgraded`；
  保留既有当前 profile，不重新迁移账号，CD2 和挂载未改动。回执明确 `playback_verified=false`。
- 历史冻结 run `20261019-211907` 已实际升级 **1907 / 13 自有组件事务**，回执为 `upgraded`，
  `program_sequence=2026101907`、`migration.performed=false`、`cd2_and_mount_untouched=true`、
  `playback_verified=false`。没有重新迁移账号/profile，没有试播、换号或实际回退。

1907 当时验签并完整检查全部 22 组件的哈希、归档和插件身份，只有 13 个自有组件进入
替换、备份、恢复事务。9 个上游插件不覆盖、不补装、不自动启用、不改来源，保留 Kodi /
作者原仓库独立维护；缺失或版本不足时明确提示通过 Kodi 安装/更新。
升级前后 9 个插件的版本、启用状态、origin、已安装内容指纹均一致
（内容指纹排除运行时 `__pycache__` / `.pyc` / `.pyo`）。这证明本轮保留原件，
不等于实际执行过官方插件更新往返。设置提供 Kodi 原生依赖与已装插件管理入口，
详见[上游维护边界](UPSTREAM-ADDONS-20261019.md)。

历史 1906 首次 BT 回归使用同一《Flip Flappers》合集，已进入新 adapter，约 5 秒后以
`target_unresolved` 正常回到选源，未出现先前旧协议 `superseded` 后长时间等待的表现。
**视频并未开始，不能称为 BT 播放通过**；通用季集目标选择仍需排查。这是回归证据，
也不能替代从未测试过的新作品验收。

1906 新增 `plugin.video.bobbi.torrent` 薄适配插件，修正父插件与旧 JackTorr 的
属性/IPC 不一致：按当前 bobbi owner 解析用户选定的同一片源，并报告有界失败。
只迁移已有 TorrServer 的连接配置，复用既有兼容后台，不引入 daemon/native 库，
不接管或停止旧 BT 后台。继续保留同版续播、原语言原声优先、历史/最近播放回到手动选源；
不转码、不降分辨率、不因失败静默换发行版本。
1907 历史检查点的 JackTorr 仍为旧 `1.2.2+am6b.317` fork，当时尚未替换为原版。作者仓库
`repository.jacktook` 0.0.5 已通过 Kodi 原生从 ZIP 安装，origin 由 Kodi 自然写入，
但盒子打开 `addons://repository.jacktook/` 提示无法连接插件库；日志两次读取作者索引
MD5 URL 失败，独立直连 5 秒超时。电脑可取得作者索引和 1.2.2 原包，原包 SHA-256
与缓存一致；电脑可访问不能证明盒子可访问。随后仅通过原生 `Addons.SetAddonEnabled`
停用本轮新增且不可达的仓库，原版恢复及一键更新仍未完成。
主插件独立 TorrServer 文件浏览/手动字幕路径仍调用 JackTorr 公开 `buffer_and_play`
路由；增强选源使用新薄适配器，不能笼统宣称已没有 JackTorr 路由依赖。

上述维护过程中，Kodi 于日志时间 **20:06:19 原生崩溃（segfault / exit 139）**，
服务自动恢复至 `MainPID=21453`、`NRestarts=1`。现有证据不能断言仓库超时是崩溃原因，
该次 1907 维护未改 F9。旧 JackTorr 当时未替换、原 profile 设置 SHA 未变、TorrServer `PID=4025`
未变；停用新增仓库后已回主界面。没有进行影片播放、真实换号或循环回退试验。
崩溃线程调用栈为 `CVariant::operator[]` → `XFILE::IDirectory::ProcessRequirements`
→ `CDirectory` → `AddonBrowser` → `ActivateWindow`，记录了原生目录/窗口路径，
仍不等于已经确定最初触发原因。最终健康记录为首页、宿主 ready、preparation RUNNING，
账号 epoch 1 与 14 部/58 条准备来源、3 条直连状态保持，无 Python 失败。

21→22 使用固定候选哈希及外部冻结的迁移边界，原签名信任钥不变；旧 21 组件客户端
直接拒绝新 22 组件包，不放宽完整名单校验。有旧未完成 journal 时先阻止新升级，
由对应冻结控制器恢复。1907 遇到旧完整 22 项 `previous.json` 时，仍校验所有历史备份
哈希，包括上游备份，但只恢复 13 个自有组件；未完成旧 22 项 journal 则拒绝由新控制器
解释，必须使用对应冻结控制器恢复。历史跨名单恢复不能依赖旧 21 组件更新器解释
22 组件事务。回退只恢复自有程序及规定的启用/界面状态，不回滚观看数据。

**1907 历史阶段没有进行实播、换号或实际回退。** 1906 BT 失败没有被该次升级证明已修复。
1908 后续有界实播结果见上节；其存在不把这些历史未执行项改为通过。
同版续播、完整字幕/音画、实际程序回退及设备断电恢复仍需各自证据。

## 历史 Windows x64 候选 — 当前暂停

以下仅记录 1905 的 21 组件原生产物，不是本轮 CE 22 组件交付。其历史清单为
`dist/private-components-2026101905/manifest.json`，SHA-256
`60e36b83a6d373e8b52f5d9e96326bf437f62e33d39b213834359094c66fcff8`。
`dist/native/` 下名称含 `2026101905` 的原生包及当时 Windows/Android 签名组件包
均只保留供追溯；本轮不继续构建、测试或宣称更新为 22 组件。

历史产物包括完整便携 ZIP 和用户级安装器。正常入口是 **`bobbi.exe`**，不要直接启动
`host/kodi.exe`；原生入口会检查 launcher 继承的生命周期凭据。
便携版 profile 位于程序旁，安装版使用 `%LOCALAPPDATA%/bobbi TV/profile`。
安装器采用新版本目录，不覆盖旧原生目录；卸载保留共享 profile。

该包已含 Kodi 21.3、Python 3.8 和组件，不需要另装系统 Python。
EXE 尚无 Authenticode 签名，SHA-256 回执不是微软信任签名。不要为安装关闭系统防护。

关闭影院后，可由 launcher 导入**本机文件**形式的 Windows 签名完整代次：

```text
bobbi.exe --apply C:\path\candidate.bobbi-update.zip
bobbi.exe --rollback
```

维护前后都检查独占生命周期。回退保留序号高水位，不能回退后重放旧序号当作新更新。
原生宿主二进制更换与组件回退是不同层：保留旧版本目录供宿主恢复，勿把组件包当宿主安装器。
真实 launcher 在临时 profile 的 apply/逐字节 rollback、篡改拒绝、并发锁检查已通过；
1905 用户级安装器已执行，4,397 个安装文件与冻结镜像逐字节一致；便携新 profile
启动及该代签名更新/回退也有实际回执。1902 已安装模式启动、卸载且保留 profile
为历史验证，不冒充 1905 卸载已经执行。真实影片音画另见实播记录，不从安装结果推定。

## 历史 Android 8+ / API 26 候选 — 当前暂停

历史 APK 分为 `arm64-v8a` 和 `armeabi-v7a`。两包均包含实际 Kodi 原生播放器、
完整影院 UI 和当时的 21 组件，不是需要再装 Kodi 的助手，但不包含新 CE 22 组件。
应用 ID 保持
`org.bobbi.helper`，版本号 `2026101905`，发行签名沿用原钥。

APK 更新通过 Android 系统安装确认；发生签名冲突应停止检查，不能先卸载或清除数据。
现有应用数据的实际覆盖升级仍需真机验证。若需回退原生程序，必须交付同签名、
更高 versionCode 的恢复 APK，不承诺系统允许直接降版本。

这些历史 APK 不包含旧助手的 TorrServer/BT 服务。115/NAS 不需要 BT 后台；BT 需要单独的
兼容后台能力，不能把同应用内的旧配对菜单当作服务已经存在。
1905 Android 组件签名包仅用于当时同代验证/构建，不代表已启用运行中导入或组件热更新。
16 KiB 页尺寸、硬解、HDR/DV、音频直通、后台生存均待真实硬件验证。

## 应用配置与字幕

- TMDb 专用应用配置仍待用户完成；不提供 Juku 或其他应用的共享 Key。CE 既有私有配置
  的本地保留不是专用应用申请/验证的替代。不要把 Key 发进公开日志或安装包。
- Juku 使用每个安装自身的设备身份访问获授权目录；本次 CE 迁移只保留同设备已有身份。
  不搬入 Juku 后台程序、共享账号或其他人的 Token。
- 1907 借鉴 Juku 的账号交互：已登录状态明确显示扫码切换/重新登录、确认退出，提交后
  刷新当前目录；取消保留现有账号，并保留波比的账号代次检查。不需要重命名全部插件 ID，
  也不把 Juku 的账号后台整体搬入。本轮没有实际换号验收。
- OpenSubtitles 的用户 API Key 是可选项；缺省不阻断视频和其他字幕来源。
- Assrt 自动字幕 Token 保存在设备 profile；已有 CE Token 由控制器在设备本地迁移。
  字幕按质量排序，时间轴不作为硬门槛；用户可手调延迟，自动流程尊重手动关闭/更换。
  此前真实候选下载返回 HTTP 493，尚无恢复成功证据；错误提示不等于已加载。

## 验证分层

| 层级 | 已有证据 | 不能据此推定 |
| --- | --- | --- |
| CE 1908 组件/原生 | 22 组件/1,371 文件包审计、受控升级、d750 原生 overlay 应用、JackTorr 1.2.2 原来源恢复 | 1909 已部署、回退已通过、所有 BT/HDR/字幕/续播已认证 |
| CE 1908 有界实播 | 窃听风暴通过；东京教父启动缓冲失败；灰羽 BT 超时；Flip 技术尾缀拒绝已定位 | 后续稳定可抹掉启动失败、旧片回归等于新作品验收 |
| 历史 CE 1907 源码回归 | primary-final 1225 通过/6 跳过，132.04 秒；baseline 741 通过；preparation 177 通过；三个独立进程 | 实播成功、跳过项通过或多端测试重新启动 |
| 历史 CE 1907 组件 | 真实 22 组件/1,371 文件解包与哈希审计；CE 包验签；错平台、签名篡改、组件篡改、缺失组件四项负例拒绝；受控 stage/upgrade/inspect | BT 实播、该代实际回退或其他平台包已通过 |
| 历史 CE 1907 维护边界 | 13 自有组件事务；9 上游原件前后内容指纹、版本、origin、enabled 一致；不改 CD2/挂载、不重迁账号 | 官方更新往返或账号切换已实测通过、当时 JackTorr 已原版化 |
| 历史 CE 1907 作者仓库试接入 | Kodi 原生安装 repository.jacktook 0.0.5；盒子访问失败后仅停用新增仓库；一次 Kodi exit 139 后自动恢复，旧设置与 TorrServer 未变 | 当时仓库可用、一键更新完成、JackTorr 已替换，或已证明网络超时导致崩溃 |
| 历史 CE 1906 | primary 1047 通过/5 跳过，baseline 741、preparation 177；22 组件/1,370 文件包审计、升级成功；BT `target_unresolved` 未播放 | BT 失败已解决，或该代实际回退已完成 |
| CE 历史部署 | ARM32/P-256；1903 账号范围迁移、1904 实际程序往返、1905 新 owner/准备服务；1906 升级保留当前 profile、CD2 与挂载 | 所有 ready 映射可播放、当前 BT/字幕/续播/回退或设备断电恢复 |
| 历史 Windows 1905 | 新 profile 启动、新 UI、7 个 Player.Bobi 接口、launcher 维护往返、用户级安装；1902 安装模式启动/卸载回执 | 本轮 22 组件同代、1905 安装模式卸载、HDR/直通或全部影片播放 |
| 历史 Android 1905 | 两 ABI 实际 libkodi、当时 21 组件逐文件校验、同发行签名 | 本轮 22 组件同代、真机安装/升级、硬解及后台行为 |

后续 CE 实播验收须由 root 控播流程选择**从未测试过的新电影与新动漫**，记录具体片源、音轨、字幕、
续播及播放错误。目录命中、文件名“双语”和旧影片重复播放都不算该验收完成。
当前未把这些待验收项改成通过，见 [gates.json](../release/gates.json)。

历史 CE 1907 单元证据：[primary-final JUnit](../review-evidence/ce1907-unit-primary-final.xml)、
[baseline JUnit](../review-evidence/ce1907-unit-baseline.xml)、
[preparation JUnit](../review-evidence/ce1907-unit-preparation.xml)。六项跳过未算作通过。
部署证据：[1907 stage](../review-evidence/ce-20261019-211907-stage.json)、
[1907 upgrade](../review-evidence/ce-20261019-211907-upgrade.json)、
[1907 inspect](../review-evidence/ce-20261019-211907-inspect.json)、
[1907 运行状态](../review-evidence/ce-runtime-upgraded-1907.json)、
[CE 1907 组件及签名包审计](../review-evidence/private-artifact-boundaries-ce1907.json)。
上游原件证据：[升级前](../review-evidence/ce-upstream-content-pre1907.json)／
[升级后](../review-evidence/ce-upstream-content-post1907.json)。
作者仓库补充证据：[原生安装后的状态](../review-evidence/ce-upstream-repo-installed.json)、
[仓库连接与崩溃诊断](../review-evidence/ce-upstream-ui-1792411693451227800.json)、
[崩溃线程调用栈](../review-evidence/ce-upstream-ui-1792411741018097300.json)、
[停用不可达仓库并回到首页](../review-evidence/ce-upstream-ui-1792411661889469900.json)、
[恢复后健康状态](../review-evidence/ce-runtime-1907-after-upstream-recovery.json)。

历史 CE 1906 单元证据：[primary stdout](../review-evidence/ce1906-unit-primary.stdout)／
[JUnit](../review-evidence/ce1906-unit-primary.xml)、
[baseline stdout](../review-evidence/ce1906-unit-baseline.stdout)／
[JUnit](../review-evidence/ce1906-unit-baseline.xml)、
[preparation stdout](../review-evidence/ce1906-unit-preparation.stdout)／
[JUnit](../review-evidence/ce1906-unit-preparation.xml)。五项跳过未算作通过。
部署证据：[1906 stage](../review-evidence/ce-20261019-190604-stage.json)、
[1906 upgrade](../review-evidence/ce-20261019-190604-upgrade.json)、
[1906 inspect](../review-evidence/ce-20261019-190604-inspect.json)、
[CE 1906 组件及签名包审计](../review-evidence/private-artifact-boundaries-ce1906.json)。
未播放成功的 BT 回归：[选源调用](../review-evidence/ce-new-work-flip_flappers-select-1792408222900767400.json)、
[失败后运行状态](../review-evidence/ce-runtime-flip-1906-failed.json)。

[final-unit-tests.json](../review-evidence/final-unit-tests.json) **仍为 1905 历史汇总，未更新为上述结果**。
其余历史证据：[1905 组件与签名包](../review-evidence/private-artifact-boundaries-1905.json)、
[1905 Windows 启动](../review-evidence/native-windows-startup-1905-20261019.json)、
[1905 Windows 维护往返](../review-evidence/native-windows-update-roundtrip-1905-20261019.json)、
[1905 Windows 安装](../review-evidence/native-windows-installer-1905-20261019.json)、
[1902 安装/卸载](../review-evidence/native-windows-uninstall-1902-20261019.json)、
[CE 依赖预检](../review-evidence/ce-dependencies-preflight.json)、
[CE 1903 部署](../review-evidence/ce-20261019-174118-deploy.json)、
[CE 1905 运行健康](../review-evidence/ce-runtime-upgraded-1905.json)、
[新作品验收](research/NEW-WORK-ACCEPTANCE-20261019.md)。
