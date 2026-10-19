# 私库独立审查交接 · 2026-10-19

## 当前状态与阅读顺序

这是 **CE 2026101909 候选的审查资料**，不是继续安装/测试的授权，也不是稳定发行。
**设备已恢复原深度定制，全部测试和设备操作暂停。** 恢复 run `20261019-220212`
返回 `legacy_restored`：旧皮肤首页、F9 `8962740e…`、定制 JackTorr `1.2.2+am6b.317`、
旧准备服务 active/enabled，13 个 bobbi 自有组件停用，profile 哨兵未变。
见[最终恢复记录](CE-LEGACY-RESTORE-20261019.md)和
[真实回执](../review-evidence/ce-legacy-restore-1792418552005660600.json)。
恢复后没有试播，不等于完整播放认证。**最终 Git 提交/附件 URL 待上传完成后补充。**
此处保留全部已发生的失败，不等待继续试播，也不重新测试已播放作品补齐门槛。
Windows/Android 已暂停；其源码、原生产物与历史证据仍保留，但不是当前 CE 同代认证。

建议先读：

1. 本文及最终恢复回执，区分“审查候选”和“用户实际运行系统”。
2. [当前候选安装记录](PRIVATE-RELEASE-20261019.md)、[CE 迁移边界](CE-MIGRATION-20261019.md)、
   [原生改动与维护顺序](CE-NATIVE-REVIEW-20261019.md)。旧检查点以各自明确的代次为准。
3. [新作品验收边界](research/NEW-WORK-ACCEPTANCE-20261019.md)、
   [设备问题](research/DEVICE-FINDINGS-20261019.md)、`review-evidence/` 原始结果。
4. [Juku 完整研究结论](research/juku-full-20261019/SUMMARY.zh-CN.md)、
   [设计比较](research/juku-full-20261019/DESIGN.md)、
   [官方插件及群文件审查](research/juku-full-20261019/ASSETS.md)。

`release/gates.json` 已区分停用的审查候选 1909 与活动的旧深度定制系统；1907 状态
单独归入历史。历史失败不能因为新代次编译/安装成功或恢复完成而被改成通过。

## 候选代码与可复核状态

源码来源是产品基线 `863304fdb61c310f8912f04051f7789e6d4ee4a7` 与旧深度定制
`ff530e09c34c6285ccb05c1d4179140b097174fb` 的明确整合；保留来源、许可证和第三方 ID。
目录、账户、字幕、传输、更新事务等改动需分别审查，不能只评 UI 或统计测试总数。

1909 已有真实升级回执：
[run 20261019-214404](../review-evidence/ce-20261019-214404-upgrade.json)。
该回执明确没有再次迁移 profile、没有改 CD2/挂载，且 `playback_verified=false`。
[原生旧版下的启动](../review-evidence/ce-runtime-upgraded1909-native-old.json) 与
[原生候选下的启动](../review-evidence/ce-runtime-upgraded1909-native-new.json)
是不同状态检查，均不能代替完整媒体验收。

| 冻结对象 | SHA-256 |
| --- | --- |
| `dist/private-components-2026101909/manifest.json` | `3a239ac3e279c45c4c37e7c17e9ac7349c34be8eeef2a8a5fcaa43fd88feeff0` |
| `dist/private-releases/bobbi-private-2026101909-coreelec.bobbi-update.zip` | `4c48464fc15850ac87f94f564ae8b84a446cb130103d87540086a904127379bb` |
| 旧 F9 原生程序 | `8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b` |
| 目录对象生命周期原生候选 | `d750a88c3dc041d17ea34d06e2b2ddadcf4db0f9fffdaaa727c8a6b7427f21d3` |

[1909 产物审计](../review-evidence/private-artifact-boundaries-ce1909.json) 验证 22 组件、
1,371 文件及签名/成员哈希；完整包 95,966,702 字节。13 自有组件事务与 9 个保留上游
依赖的边界见 [上游维护说明](UPSTREAM-ADDONS-20261019.md)。

1909 最后两次已知回归不是新增作品覆盖，也没有全部通过：

- 《Flip Flappers》：有界像素格式文件名规则已修复，仍保留实际文件身份核对。
  [选择追踪](../review-evidence/ce-new-work-flip_flappers-select-1792417911193221200.json)
  没有捕获 `AV_STARTED`；[后续观察](../review-evidence/ce-new-work-flip_flappers-wait-1792417961031737200.json)
  也未确认开播。[TorrServer 状态](../review-evidence/ce-torrent-flip1909-live.json)
  显示所选种子处于 preload，不能把目标识别修复写成播放通过。
- 《东京教父》：[最后一次追踪](../review-evidence/ce-new-work-tokyo_godfathers-select-1792418072567343100.json)
  的 `trace_passed=false`、`status=observed_anomaly`。后续恢复 AV、字幕显示和持续正时钟
  不能抹去启动停顿，也不能把旧指标 10.944 秒直接当作精确解码冻结时长。
- 1908《窃听风暴》有界实播通过；《东京教父》启动缓冲、《灰羽联盟》缓冲超时，以及
  更早的字幕 493、续播不确定等失败仍保留，详见上述安装记录和新作品验收文档。

### 未修复的独立待审问题：准备意图的 NxM 语法

停止设备验证后，只读研究在实际 40 文件 torrent metadata 加 fixture catalog 上复现：
`source_intent.verified_intents → mapped_family → release_identity.bound_family`
中的 `STRONG` NxM 正则仍将 `1920x1080` 识别为季集标记，抛出
`Release episode markers...`。这是准备意图/同版绑定路径的问题，与 1909 实际文件
selector 的像素后缀修复独立，**生产代码尚未修复**。

设备日志中的 `PREPARATION_INTENT_ValueError` 只记录异常类型；尚无该次实际 catalog
和调用栈证明设备失败必然是完全同一原因，不能把本地复现写成生产根因已证实。
下一轮先独立审查两条路径及证据，取得用户新的执行许可后再决定修复/部署；本轮不继续
试播，也不把这一发现写成“已修好”。

新增诊断不改变读取范围、块增长、重试或片源身份；回调有界且在释放同文件读取门后
记录，但同步日志不等于零开销。人工控制工具明确非原子，标准 RPC 的检查—执行竞态
不能宣传为 expected-instance 原子控制。测试 XML/JSON 是各自范围的结果，不把相互
重叠的 focused suites 相加成“独立测试数量”。

## 必须提交的源码与小型证据

以下路径应完整纳入私库提交，保留现有历史，不做整树清理或删去失败结果：

| 路径 | 内容 |
| --- | --- |
| `addons/` | 全部自有插件、皮肤、声音与目录数据；真实账户状态不在此树 |
| `third_party/addons/`、`licenses/`、`assets/` | 原版依赖、许可与素材；包括固定哈希的公开 `certifi/cacert.pem` |
| `tests/` | 主测试、隔离的 `private_baseline`、`preparation_regression` 与夹具 |
| `tools/` | 构建、签名、诊断、部署/恢复、静态研究工具；不附签名私钥 |
| `release/` | 来源清单、依赖锁、素材溯源、平台产物哈希、门禁；旧结果标明代次 |
| `native/` 的源文件、补丁、锁文件、JSON 与日志 | 原生修改、可重复构建输入和本次基线/控制/候选证据；生成二进制另附 |
| `docs/`、`review-evidence/` | 完整研究和执行记录，包括失败、未确认、停止测试及恢复回执 |
| `.github/`、根配置、`android/`、`overlays/`、既有 `repository/` | 保留已有完整工程上下文；历史公开仓库产物不是当前候选安装入口 |

原生重点证据目录为
`native/ce-directory-lifetime-20261019/run-1792413397048752728/`：
`build-result.json` 和编译/链接日志留在 Git；源码在其父目录的
`Directory.original.cpp`、`Directory.patched.cpp`、`build_isolated.py`、`reentry_test.cpp`。
链接使用 LTO，不能宣称最终全部音画机器码逐字不变。

根忽略规则只对 `third_party/addons/script.module.certifi/lib/certifi/cacert.pem`
作精确例外：其 SHA-256 为
`b301535dca491d9814ea28faa320ac7a19d0f5d94237996fa0a3b5a936432514`，包含 139 个公开
CA 证书、没有私钥标记，并已列入源码/依赖清单。不得整体放开 `*.pem`。

## 必须保留并作为私库附件交付的生成产物

以下为**交付清单，不代表已经打包或上传**。附件需列出原始相对路径、字节数和 SHA-256；
上传后再读回附件列表/大小，最终在本文补上下载 URL。大归档按平台或代次分包，不把
超过 Git 单文件限制的产物强塞进提交，也不为了大小删除本机成果。

| 附件组 | 明确输入范围 | 说明 |
| --- | --- | --- |
| CE 与历史组件包 | `dist/private-releases/*.bobbi-update.zip`；`dist/private-components/` 和 `dist/private-components-2026101902/` 至 `dist/private-components-2026101909/` 的完整冻结清单与组件 ZIP | 包含历史代次用于审查/复现，不授权重放旧包或降低高水位 |
| Juku 全函数 AMD64 | `docs/research/juku-full-20261019/archives/juku-0.80-amd64-full-static.zip` | 49,114,616 字节；SHA-256 `507afb7d91792188e285f89c2ef84b29aadea766833c0b52b405c43521bef7a9` |
| Juku 全函数 ARM64 | `docs/research/juku-full-20261019/archives/juku-0.80-arm64-full-static.zip` | 51,980,628 字节；SHA-256 `20685353b7567a8eb1702881a24361a06e699a7fd7bc14c651d94cfd9dbc8100` |
| CE 原生构建证据 | 上述原生 run 下的 `baseline.bin`、`control.bin`、`candidate.bin`、三份 `.unstripped`、`candidate/` 与 `control/` 的 `.o`/`.o.d`/`.a`，以及父目录 `reentry_test` | 生成文件约 185 MiB；归档附带同一 `build-result.json` 和源码/日志副本，保持路径对应 |
| Windows/Android 历史实际产物 | `dist/native/` 顶层全部 `.zip`、`.exe`、`.apk`；对应 `release/native-host-artifacts-20261019.json`、`native/build-verification.json` 和 `review-evidence/native-*` | 1901/1902/1903/1905 或无代次历史文件全部保留；未取得 Android 实机认证，不能宣传为当前交付 |
| 其他必要构建中间证据 | `native/build/logs/`、已被文档引用且不含 profile 的诊断/构建输出 | 先逐项白名单，不直接打包 `native/build/`；可重下的 SDK/NDK/toolchain 以 `native/toolchain-lock.json` 复现，不属于待安装成果 |

完整 Juku 函数展开目录 `amd64/functions/`、`arm64/functions/` 已在上述两个归档内，
不必在 Git 重复加入 114,454 个归档条目。Git 仍保留覆盖报告、逐文件清单、索引、调用图、
失败 journal、作者 Python/配置/图片、内嵌网页重建及群文件白名单文本。
两架构共 38,132 个已识别函数全部尝试，38,125 个伪 C 成功，7 个失败保留原因和 ASM；
这不是作者原始 Go 工程、可重编译替代源码或逐函数人工正确性证明。

群资源 44 件的完整输入索引、哈希与副本比较见
`docs/research/juku-full-20261019/assets/`。不要直接上传未检查的原始 Juku 插件 ZIP：
已确认其含 `device_key.pem`，研究副本故意未复制该成员。需要附原始二进制研究输入时，
只能明确提取已索引的 ELF/普通文件，并附原包哈希和排除说明；不能把删成员的新包冒称原包。

## 不上传或装入发行包的状态

- 真实签名私钥、`.jks`/`.keystore`、私密 `release-signing.json`、设备私钥、登录会话、
  Cookie、个人 Token、SSH 认证材料和 `.private/`。
- `native/build/windows-installer-1903/profile/` 与 `...1905/profile/` 已含
  `juku/device.pem`、`session.json` 和账户目录缓存；完整 `native/build/` 不可作附件。
- 设备用户 profile、完整用户数据库/备份、云盘登录状态；恢复回执只保留所需状态与哈希。
  本机保留不等于上传，也不能用源码审查之名清除这些本地数据。
- `dist/native/` 中展开的运行目录不能未经检查整包；已有冻结安装包与其哈希优先。
  目录数据库必须是明确白名单重建的资源目录，不得夹带登录表或未审查页面。

本轮只读扫描在源码/工具/测试/发布清单/证据和研究资料中未识别出真实凭据；命中的
哈希、片源 key 与 minified JS 需要保留精确审查结论，不能扩大忽略到整个目录。
这不是对任何未来新文件或附件的无条件安全认证；打包后仍须检查成员名单与敏感状态。

## GitHub 与提交前检查

只读核对 `https://github.com/2223M1/bobbi-tv` 为 **PRIVATE**、非 fork，默认分支 `main`。
工作分支 `codex/private-three-platform-20261019` 用于独立审查；主任务已 fetch，
`origin/main` 为 `71ea55831c58f26cd6ab89ff5331b86ae33ca869`（`Update README.md`）。
本轮发布独立审查分支和私库 prerelease `audit-20261019-private-ce1909`，不覆盖 `main`；
上传完成前不能把计划中的分支/附件写成已经交付。发布说明见
[审查发行说明](WEB-REVIEW-RELEASE-NOTES-20261019.md)。

当前可提交文件未发现大于 100,000,000 字节的单文件；整个工作区有 32 个超过该阈值的
文件，全部位于已忽略的 `dist/`、`native/.work/`、`native/build/`、`native/downloads/`。
附件边界解决的是交付体积和状态隔离，不是遗漏成果的理由。

最终恢复回执与门禁已同步。剩余交付由主任务完成：全部结果含失败一并提交；附件按
白名单和哈希上传；补写最终 commit/分支及附件 URL。干净克隆重建仍应作为后续审查项，
不能在暂停测试期间自动执行或凭本地已有构建产物认定通过。
在用户重新授权前，不为完善本报告继续试播或重新启用候选系统。
