# Bobbi TV CE2049 独立复审

审查日期：2026-10-22（北京时间，Asia/Shanghai）  
审查对象：[ce2049-reviewed-20261022](https://github.com/2223M1/bobbi-tv/releases/tag/ce2049-reviewed-20261022)  
审查方式：固定源码、实际公开发布字节、独立反例与测试、维护者原始设备记录交叉核对。

## 结论与处置建议

**CE2049 的五类整改有实质效果，上轮反例均已取得关闭证据。本次确认 1 项新增 P2：账号在搜索进行中切换后，当前卡片可能保留上一账号的失效标签和推荐降级。未确认新增 P0/P1 代码缺陷。**

建议继续按测试预发布管理，先修复这个可确定的状态问题，并针对《心灵驿站》同源播放约 36 秒后持续缓存进行有界定位。现有证据不支持将 CE2049 标为稳定版：该电影实播明确失败，Kodi ZIP 浏览器冷安装、字幕视觉/同步以及其他既有延期项目仍未完成。这里延续项目现有发布口径，不增加设备、账号或原生播放器准入条件。

本轮把“关闭旧反例”“新发现”“维护者设备事实”和“未验收事项”分开记录。当前包已独立取得真实字节并验签；本审查没有操作真实盒子、安装或回退实际系统、推送代码、改动 Release 或替换签名包。

## 1. 固定对象与发布来源

| 对象 | 固定值 |
| --- | --- |
| CE2047 审查基线 | `5d6a77d78a278984517f3e4af99c239054e9ba4a` |
| CE2049 产品修复提交 | `81482d32fd25c04ca6ebb73ef5636f5e35414a3e` |
| 产品 tree | `e127c75423fc598f3b98a5efd1719d8154b83ecd` |
| CE2049 tag／本次读取的 main | `43e3a296f5982a6b235421cbffb61c3eae65a84e` |
| tag tree | `78873689f059a5af677eddade372bf635ca66be2` |
| Release 状态 | `prerelease=true`，公开发布时间 2026-10-22 16:00:41 北京时间 |
| 实际 CI | run `39743912719`，job `119707559051`，push，success |
| CI 实际 checkout | 上述 tag SHA，Python 3.11.17；北京时间 15:55:16–15:59:22 |

产品提交到 tag 提交之间，`addons/`、`third_party/addons/`、`release/source-inventory.json` 没有变化。后一个提交增加或调整维护工具、设备记录与交付说明。Release 附带的交付报告与 tag 内同名文档逐字节相同。CI 的实际日志、Release 的 API 元数据及本次下载摘要均保存在 `evidence/`，不是仅凭绿色徽章或维护者摘要判断。

来源：[固定交付报告](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/docs/CE2049-REVIEW-DELIVERY-20261022.md)、[实际 CI](https://github.com/2223M1/bobbi-tv/actions/runs/39743912719)、`evidence/github-release.json`、`evidence/current-ci.log`。

## 2. 新发现 R49-01：进行中的搜索没有完整隔离账号代际

**优先级：P2。状态：已独立复现，待修复。影响：当前查询的失效提示、谨慎标记和推荐状态。**

### 2.1 用户可见结果

账号 A 曾对某个精确文件得到 `share_revoked`。随后开始新的搜索，在外部请求尚未返回、或者 Juku 已发布首批结果但尚未完成时切换到账号 B。B 的当前查询仍可能显示 A 的“分享已失效”，并且不再推荐这张卡。关闭当前结果后另起一次查询，两个 provider 都会正确读取 B 的状态。

| 受控交错 | 最终目录层结果 | 当前 SourceListSession 结果 | 切换后另起查询 |
| --- | --- | --- | --- |
| QQdocs：查询起点 A，外部响应期间切 B | 仍为 A 的 `share_revoked` | 失效标签保留，推荐为空 | 正常，无旧失效标签 |
| Juku：先发布 A 的失败卡，刷新期间切 B | 已正确清空失效状态 | 仍保留首批 A 的失效标签，推荐为空 | 正常，无旧失效标签 |

正控制是切换前 A 的查询确实有失效标签；反控制是切换后的独立新查询没有该标签。Host 的实际账号变化回调确实触发，provider 与 session 却未随之取消或更新账号显示代际。

### 2.2 代码原因

1. [catalog.py 第 229–278 行](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/addons/script.module.bobbi.catalog/lib/bobbi_catalog/catalog.py#L229-L278) 在开始时读取一次账号 scope，慢请求返回后继续用该 scope 读取失效覆盖层，没有对发布时的账号变化重算。
2. [source_list_session.py 第 54–68 行](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/addons/script.module.bobbi.core/lib/bobbi_core/source_list_session.py#L54-L68) 通过 `setdefault` 保留旧对象，只合并非空 `shareFailure`。Juku 后续返回正确的空状态，仍不能清掉旧对象上的标签。
3. [search.py 第 2137–2141 行](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/addons/plugin.video.bobbi/lib/search.py#L2137-L2141) 的搜索 session 没有账号代际。已有播放授权撤销不等于搜索 UI 状态已经随账号更新。

### 2.3 证据强度与边界

重放使用实际 AccountManager、Host dispatch/账号回调、SQLite、两套目录逻辑、ProgressiveSearch、OS admission lease、TorrentStream、排序和 SourceListSession。QQdocs 进一步使用实际 `Client.get/search/resolve`，只替换远端 opener 的响应；Juku 公共元数据接口与 IPC 传输为替身。主审已独立重放，结果一致。

这证明应用内部可达交错下的当前查询状态错误；未执行 Kodi renderer，也未证明用户凭据串用、媒体身份替换或播放授权绕过。不要将它写成账户安全漏洞或“所有换账号查询都失败”。不需要真实第二个账户即可在本地夹具验证。

证据：`evidence/catalog-epoch.json`、`evidence/catalog-epoch-root-replay.json`；复现：`repros/catalog/repro_catalog_epoch.py`。基线观察脚本退出 0 表示观察成功，**不代表缺陷修复通过**。正向验收另见 RUNBOOK 与 ACCEPTANCE。

### 2.4 最小修复方向

将失效覆盖层与其来源的 `account_id + epoch`、精确文件 tuple、结果先后关系一起传到发布/合并边界；账号变化时让旧覆盖层失效，并为当前账号重算。让经过有效新状态确认的空值能够清除旧标签，同时阻止迟到的旧账号结果重新覆盖。保留稳定键、焦点、BT 卡、手动重试和当前播放授权边界。

不能直接把所有空 `shareFailure` 当成有权清除新失败：旧 provider 的迟到空值同样可能覆盖更新的撤销结果。正常成功压过更早失败、账号隔离、精确 tuple 隔离、TTL 与容量上限都应继续成立。这是现有显示状态的一致性修复，不增加登录、机型或播放器准入步骤。

## 3. 上轮五类问题的关闭结果

| 上轮故障 | 本轮独立结果 | 状态与边界 |
| --- | --- | --- |
| 本地 Back 后，IPC 读取恢复仍成功移交 BT | 原反例原样重放，成功派发由 CE2047 的 1 次变为 0 次；远端 owner 仍未取消，取消属性仍未发布 | 原 P1 反例关闭；未据此宣称实机所有按键时序通过 |
| 慢 HTTP body 让保活线程在返回后继续运行 | Back 0.222 秒、确认 0.212 秒，均仅 1 次 get；返回及 close 后 worker 均为 0 | 原 P2 反例关闭；另做旧/新请求真实 socket 隔离通过 |
| 撤销分享重新进入普通推荐 | 同账号普通重查会保留失败标签并退出推荐；手动重试、新成功、精确 tuple、TTL/容量和新账号查询的回归通过 | 原正常重查故障关闭；本轮 R49-01 是进行中账号切换的新边界 |
| 缺失旧程序备份仍写 restored | 新收据与完整向量预检生效；独立 8 项边界通过，包括损坏拒绝、中断续恢复及旧 journal 兼容 | 关闭，不再沿用旧 OPEN_SCOPE_HELD 状态 |
| 外层入口未与签名组件完整绑定 | 实际 CE2049 包控制通过；代码、XML、加成员、缺成员、bootstrap 五种变异全部拒绝 | 实际发布包范围内关闭 |

取消修复见 [native_player.py](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/addons/plugin.video.bobbi/lib/native_player.py#L116-L158) 与最终派发边界第 453–475 行。HTTP 修复见 [http_io.py](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/http_io.py) 及 Resolver 的实际 join。回退修复见 [ce_installer.py](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_installer.py#L111-L156)；入口修复见 [audit_ce_entry.py](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/tools/audit_ce_entry.py#L32-L47)。详细命令和范围见 `notes/installer-review.md`、`notes/playback-review.md`。

慢 body 的旧脚本末尾本来断言“缺陷仍存在”。在新版本上它因 worker 已归零而退出 1；原 JSON 和 stderr 均保留，未改断言假装旧脚本正常通过。新请求隔离脚本与项目 14 场景正向 HTTP 回归另行断言正常收束。

## 4. 实际安装包的独立验证

| 实际下载资产 | 字节数 | SHA-256 |
| --- | ---: | --- |
| `script.bobbi.start-CE2049.zip` | 95,976,371 | `bcd8470f2450f5c563455221809c0d837f46654e78f2b46ccb0905ba03c75dde` |
| `BobbiTV-CE2049.bobbi-update.zip` | 95,871,137 | `d602adcc310391b08de0dc4e94905e829bc1dad7ba33581eab1835d94569cc94` |

全部 8 个 Release 附件的大小和摘要与 GitHub API 一致。入口内嵌 payload 与单独 update ZIP 逐字节相同。独立脚本使用 cryptography，按固定源码中的公钥验证 RSA-3072 / PKCS#1 v1.5 / SHA-256 签名通过；22 个组件的大小、摘要、成员集、ID、版本与签名清单一致；1362 个 Git 受管源文件与产品提交逐字节一致。

唯一额外显式构建输入是原有契约允许的 TMDb 应用配置，字段契约有效。输出仅保留摘要，不包含其配置值。该输入不是账号登录状态。证据：`evidence/actual-artifact-source-binding.json`、`evidence/downloaded-assets.json`。

核心版本为入口 0.2.37、platform 0.1.28、core 0.1.31、影院 0.1.30、catalog 0.1.3、BT 0.1.10、皮肤 0.1.7。CE2048 是维护者用于安装/回退演练的序列；CE2049 是同一组组件的新签名序列，维持高水位，没有通过重放旧序列绕过恢复规则。

这些结果足以关闭“当前 ZIP 没有独立取得和对应源码”的证据缺口，但不能据此推导 Kodi 冷安装、真实观看或其他硬件已经认证。

## 5. 独立测试、CI 与构建

本次实际执行环境：Linux x86_64，Python 3.12.14，使用仓库测试依赖；三个 suite 各自独立进程。

| Suite | passed | skipped | xfailed | failure/error |
| --- | ---: | ---: | ---: | ---: |
| Primary | 3565 | 6 | 1 | 0 |
| private_baseline | 1027 | 0 | 0 | 0 |
| preparation_regression | 254 | 0 | 0 | 0 |
| 合计 | **4846** | **6** | **1** | **0** |

共 4853 个用例。Primary 约 256.25 秒。5 项跳过是真实 Windows inherited-pipe API，1 项是缺少可选真实媒体/ffprobe 夹具；既有 xfail 和 record_property/xunit2 warning 保留。额外专项、维护者测试及 GitHub CI 不重复累加。

实际 CI 使用 Python 3.11.17，同样是 3565＋1027＋254＝4846 passed、6 skipped、1 xfailed。维护者的 Windows 本地结果 4844 passed、8 skipped、1 xfailed 与此不矛盾：差异是 POSIX 模式/符号链接两项。本轮 Linux 确实执行了这两类语义。

两次串行 source-check 各构建 22 个组件，63 个文件逐字节一致；产物实际摘要也逐一匹配各自 manifest。source-check 不含本机应用配置，不是可安装或可签名发行包，不能替代上节对实际 Release 的审查。

首轮并行构建出现产物与自身 manifest 不一致和额外临时文件，比较失败；原日志及观察值保留于 `evidence/initial-concurrent-build-observation.json` 和 `evidence/build-compare.log`。随后使用新输出目录逐次串行构建、核对 manifest、比较全部文件通过。并行异常根因未定位，本报告不将它编造为已确定的产品缺陷，也不把失败的那一轮计作通过。

证据：`evidence/independent-validation-summary.json`、三个 XML/日志、`evidence/current-ci.log`、`evidence/release-ci-junit-summary.json`、`evidence/build-serial-compare.log`。

## 6. 设备原始证据复核

本节是对维护者已提交记录的再分析，**本轮没有新增真机执行**。便携脚本读取固定 tag 的原始 JSON，输出 `evidence/device-receipts.json`，避免把报告文字当成唯一依据。

### 《心灵驿站》：开播成功，连续观看失败

TMDb 2056，2003 年，保持同一 1080p AMZN NTb 版本。重启后的同一 hash 约 4.0866 秒进入 AV。英文音轨、外挂字幕应用回执存在，但随后的观察中播放停在约 36.269 秒：30.3895 秒观察窗口内推进 0 秒，处于缓存状态。因此严格实播失败，不能用“约 4 秒开播”替代连续观看结果。

后续同 hash 的 404 采样发生在停止播放之后，不能单凭它判定停播前是种子被清理、插件失去租约或 BT 供数不足。下一轮应围绕同 hash、同文件、同 request/native instance、同质量版本，对卡顿前后做有界取证，先分清供数、HTTP 读取、owner 生命周期和原生播放状态，再决定修改位置。

### 《日常》：短时连续播放有正证据，启动耗时仍长

TMDb 44684，S01E01，7³ACG 1080p HEVC/OPUS，保持原选定文件。人工选择和 preload 的总启动观察约 154.6 秒；这不能叫快速开播。随后同 request/native instance 的 30.3486 秒观察内，播放推进 30.28 秒，末点约 89.627 秒，采样未缓存、解码丢帧与硬件错误为 0。

内嵌 `chi / chs[FLsnow]` 已启用。截图未捕捉到实际对白，因此本轮没有证明中文字幕字形、裁切或同步。短时样本也不是整集、自然 EOF 续播或完整 BT→115 接力的通过证据。

### 《星空清理者》：失败状态跨查询修复有设备佐证

S01E01 的同一 CoolFansSub 文件仍被上游撤销。重新查询时，同一稳定键从原“推荐”转为“分享已失效 · 可手动重试”，推荐标记为空，其他 4 张卡仍在。这支持旧故障已修复，并不表示撤销的分享已经恢复播放。

### 安装与回退记录

维护者记录了 CE2048 实际安装、移走一份旧备份后拒绝回退、恢复备份后正常回退、再安装新序列 CE2049。原安装等待超时、皮肤确认遗漏、重启观察超时等失败记录被保留，后续成功观察单列。最终记录为 CE2049 complete、无 host_pending、影院皮肤保留，Kodi active / NRestarts=0，BT 后台仍为原进程。

上述路径通过受限传输暂存入口并运行真实菜单/Installer，不是 Kodi ZIP 浏览器冷安装认证。既有像素测试仍为 INCONCLUSIVE；其他 CE 硬件、长时间弱 BT、完整 EOF/BT→115 以及字幕视觉等继续按既有范围标注未验收。

来源：[固定设备证据目录](https://github.com/2223M1/bobbi-tv/tree/43e3a296f5982a6b235421cbffb61c3eae65a84e/review-evidence/ce2048)、本包 `evidence/device-receipts.json` 与 `notes/catalog-ui-review.md`。

## 7. 给 Codex 的执行顺序

1. **修复 R49-01。** 按两个 provider 的已复现交错处理账号覆盖层的发布和清除。将基线观察迁入正常回归，正向断言修复状态。保留同账号撤销、显式重试、新成功压过旧失败、BT 不被遮蔽和精确媒体身份。
2. **定位《心灵驿站》已知卡顿。** 在已授权维护范围内以同源有界观察收集因果链，证据支持哪里再改哪里。供数不足不能靠换版、降码率、重提 add/preload 或隐藏失败刷通过；如未定位，保留 OPEN 与可复核记录。
3. **完成一次针对改动的验收与交付。** 修改后跑受影响专项、三组隔离 suite 和两次串行 source-check；需要新包时沿用既有发布流程、新序列与真实 CI，不覆盖 CE2049 原件。设备未测项继续明确，不给未知机型新增阻断。

详细任务、验收矩阵与命令在 `CODEX-TASK-CE2049-NEXT.zh-CN.md`、`ACCEPTANCE.zh-CN.md`、`RUNBOOK.zh-CN.md`。本包是审查与整改交接材料，完整安装包仍以用户指定 Release 为来源。
