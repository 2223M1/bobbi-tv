# Bobbi TV CE2047 独立复审

审查日期：2026-10-22。产品基线：`5d6a77d78a278984517f3e4af99c239054e9ba4a`；网页入口与本次 CI：`1ce3ec9cb779be5fc3effcfe56d0422e3c5039fd`。

## 结论

**CE2047 的局部整改可以认可，整版验收尚未完成。** 上轮的前 AV 读取异常分类、窗口显示前错误反馈和 BT HTTP 诊断丢失均获得独立复跑支持；长时间人工选文件后仍保留同一 torrent 的回执也有实质进展。

本轮保留 **1 项 P1、2 项 P2**：

1. **R47-01 / P1：损坏旧备份仍被当作回退完成。** 缺目录会造成新旧代混装；缺文件或改动内容也会进入运行目录，随后报告 `restored` 并开放启动。这是沿用问题。
2. **R47-02 / P2：新保活线程在缓慢 HTTP 正文读取时无法及时收束。** 用户返回或确认后等待 6 秒，方法返回时仍留有在途读取。这是 CE2047 新线程路径暴露的总时限缺口。
3. **R47-03 / P2：入口外壳审计仍未精确绑定成员和字节。** 外层入口代码、XML 版本或额外程序成员变化仍能通过旧审计。这是上轮 R45-02 的延续。

本次实际审查的是固定源码、公开回执与 CI 原始结果，执行了本地独立测试和临时故障注入。没有连接设备、发起媒体播放、修改产品源码或写入 GitHub。**未取得 CE2047 完整安装 ZIP，不能签发该版本二进制一致性、签名实物核验或完整安装验收结论。**

## 一、固定对象与证据层级

| 对象 | 本轮固定身份 | 含义 |
| --- | --- | --- |
| 已发布安装包 | [CE2045 Release](https://github.com/2223M1/bobbi-tv/releases/tag/ce2045-main-f6c9bd4)，产品 `f6c9bd4e25199516451b128c7662f8ae54fedd66` | 仍为公开预发布包，不包含 CE2047 整改 |
| CE2047 产品与维护者证据 | [5d6a77d](https://github.com/2223M1/bobbi-tv/commit/5d6a77d78a278984517f3e4af99c239054e9ba4a)，tree `5a9d7663fb5f4612696d4645197a88af29fa6875` | 本轮代码审查基线 |
| 网页审查入口 / main | [1ce3ec9](https://github.com/2223M1/bobbi-tv/commit/1ce3ec9cb779be5fc3effcfe56d0422e3c5039fd)，tree `977fb192442ac10ea8e83dcfcad194a6840fddfc` | 相比产品提交只新增 `docs/CE2047-WEB-REVIEW.md` |
| 本次远端 CI | [run 39732748172](https://github.com/2223M1/bobbi-tv/actions/runs/39732748172)，push、attempt 1、success | 检出 main 的 1ce3ec9，不是旧 CE2045 CI |
| 维护者本地已装候选 | sequence `2026102047`；事务 `a4900858146d43c5be05c16cafa644d5` | 公开设备回执中的声明，本审查没有重新装机 |

本轮对产品 tree 的 **4,710 个文件、533,762,706 字节**逐一计算 Git blob 与 SHA-256，全部与 GitHub 固定 tree 相符。相对 CE2045，产品提交新增 100 文件、修改 20 文件；其中主要产品变更是 7 个 Python 文件与 4 个 addon.xml，另有 6 个维护工具、3 个测试文件、2 个交付索引/清单及文档和回执。完整文件身份在 `metadata/source-verified.json`；main 与产品快照只差网页入口的事实由完整 tree 比较确认，见 `evidence-recomputed.json`。

维护者自测、远端 CI、本轮独立夹具、维护者实机观察分别记账。截图可说明界面状态；程序方法分发到替身可说明控制流；它们都不自动成为 AV_STARTED 或整片播放证据。[网页入口](https://github.com/2223M1/bobbi-tv/blob/1ce3ec9cb779be5fc3effcfe56d0422e3c5039fd/docs/CE2047-WEB-REVIEW.md)已经明确这些边界。

## 二、上轮问题如何结案

| 上轮问题 / 本次整改 | 本轮结论 | 独立依据与仍保留的边界 |
| --- | --- | --- |
| R45-01：前 AV 单次 IPC 读取失败被误当换片，或异常逃出入口 | **原代码缺陷范围关闭** | 仓库相关 119 例通过；旧独立 6 例由 3/6 变为 6/6；新增命令边界 12/12。只重试读取，恢复后重新判断取消、替换、boot、epoch；未盲重发命令 |
| 窗口尚未显示时只有隐藏 property，没有可见错误 | **关闭** | 两个实际 doModal 方法场景通过；持续故障发通知并取消该窗口的查询任务 |
| R45-03：人工确认后的 HTTP 错误丢失状态和阶段 | **关闭** | 200、401、403、404、409、429、500、503 八种回放均符合预期；保留封闭字段，失败不 preload，不重复 add |
| R45-02：入口外壳未完整绑定 | **开放 → R47-03** | 原件通过；改 default.py、改 XML 版本、添程序成员三个负例仍被接受 |
| R45-04：交付索引停留 CE2044，发布与本地安装混淆 | **主要问题关闭** | 新索引明确 published=CE2045、installed=CE2047；网页入口解释本地“未推送/未 CI”为历史时点。本轮已核对新的 CI，可在下一文档提交补精确运行编号和时间 |
| 人工选文件超过 torrent 空闲期限 | **正常路径整改有证据；收尾仍有 R47-02** | 同 hash、同文件、框内额外等待 35 秒后进入 preload；真实慢正文边界仍留下线程 |
| 像素空读/短读被当作有效 hash | **判定逻辑已修；视觉结论保持未定** | 新测试覆盖异常读；两份原始帧记录独立重算均为 INCONCLUSIVE |
| 旧备份完整性 | **开放 → R47-01** | 本轮真实 Installer + 临时签名包再现缺目录、缺文件、改内容三类失败 |

前 AV 关键实现是 [playback_request.py](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/script.module.bobbi.core/lib/bobbi_core/playback_request.py#L29-L41)、[native_player.py](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/plugin.video.bobbi/lib/native_player.py#L123-L147)、[resolver_window.py](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/plugin.video.bobbi/lib/gui/resolver_window.py#L86-L106)。保留“有界只读重试 + 新鲜上下文核对 + 命令回执不盲重发”的边界即可，下一轮没有必要重写这条已通过的路径。

## 三、R47-01：回退不能证明旧代完整，却报告成功

**优先级 P1，沿用问题，条件是旧程序备份缺失或损坏。**

真实入口走 [ce_installer.Installer._restore](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_installer.py#L76-L113)。该实现不能借用另一个 `UpdateEngine.rollback()` 已有摘要校验来证明自身安全。

本轮用真实 `Installer.apply()/rollback()`、临时 RSA3072 签名的两代完整组件包及真实临时文件系统复现，只有 Kodi RPC 用替身。正常对照的 12 个托管组件全部回到 1.0.0；三个故障如下：

| 故障注入 | 实际结果 |
| --- | --- |
| 删除旧 plugin.video.bobbi 目录 | 该组件仍为 2.0.0，另外 11 个恢复 1.0.0，形成混代 |
| 删除旧组件中的 code.py | 旧 XML 恢复，但程序文件缺失 |
| 改动旧 code.py 内容 | 改动内容被恢复进运行目录 |

三例均没有异常，仍写 `phase=restored`，清空 `host_pending`，`blocked=False`。用户历史和无关插件哨兵均保持原样。结论限于故障恢复可靠性，不代表正常回退普遍失败，也没有用户数据丢失或真实设备备份被破坏的证据。

直接原因是旧目录缺失时跳过、存在时直接回移，同时 journal 未记录足以证明旧代的文件向量。**只加 old.exists() 会破坏合法崩溃恢复**：某组件可能已回移完成，旧备份路径理应不存在。

建议先记录有界旧程序向量，恢复前核对整组计划；逐项区分“备份尚在”“已回移且当前内容与旧向量一致”“原本不存在”。主动回退发现坏备份时保留当前完整代；已经中断的恢复不能证明完整时保留故障状态，不写 restored。旧 journal 的兼容必须明示，不能伪造缺失摘要。保留已有进程中断重入、host 恢复、用户数据隔离与版本高水位行为。

独立证据：`installer/backup-integrity.json`，**1 passed / 3 failed，exit 1**。已有安装/恢复测试另跑 **57 passed**，它们没有覆盖这三个坏备份反例。脚本与结果绑定见 `installer/final-script-output-binding.json`。

## 四、R47-02：选文件保活的 HTTP 读取没有真正受总时限约束

**优先级 P2，CE2047 新保活线程暴露既有 HTTP 总时限检查的缺口。**

[choose_with_status](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/resolver.py#L270-L316)每次给 status 两秒预算，关闭选择框后设置停止事件并 `join(6)`。但 [Backend.request](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/backend.py#L131-L184)要等 `iter_content(4096)` 交出一个块，才检查取消和截止时间。socket 的两次读取间隔限制不等于完整响应的总时间限制。

独立夹具用项目自带 Requests 2.31.0 / urllib3 2.2.3 和临时 127.0.0.1 服务，返回合法 JSON，每 0.1 秒送一个字节，约八秒才完成。同步点在真实正文 iterator 开始之后；只缩短首次保活等待，生产两秒预算和六秒 join 保持原样。

| 操作 | 实际返回 | 等待 | 返回时 / Backend.close 后存活 worker |
| --- | --- | --- | --- |
| 返回 Back | None | 6.0 秒 | 1 / 1 |
| 确认原文件 | TORRENT_CONTROL_UNAVAILABLE | 6.0 秒 | 1 / 1 |

两例均只发同一虚构 hash 的一次 status get，没有 add、preload 或打开媒体。夹具最终等待并清理所有线程。结果为 **0/2 达到“返回前读取已收束”目标，exit 1**，见 `bt/keepalive-slow-body.json`。

这证明选源延迟和资源收尾问题，未证明错误开播、真实盒子无限卡死或所有 Kodi 宿主都不能退出。夹具线程为非 daemon；产品线程会继承宿主属性。初版同步点偏早的回执保留为 `*-initial.json`，没有计入最终案例。另一审查者已核对时序与机制，见 `preav/cross-review-bt.md`。

修复需要让这次 status 的真实响应读取受总时限和取消信号约束，且上层返回前确认自己的 worker 已结束。延长 join、设 daemon、吞错或仅 Session.close 都不构成闭环。仍要保持同 hash、同文件、取消/更替优先、人工确认后二次身份核对，以及不重复 add/preload。慢 header、慢 body、Back、取消、更换请求、HTTP 拒绝需用真实打包 HTTP 栈复验。

## 五、R47-03：外层入口代码与签名内容没有完整绑定

**优先级 P2，延续 R45-02，审计实现与 CE2045 字节相同。**

[audit_ce_entry.py](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/tools/audit_ce_entry.py#L16-L55)检查内嵌签名载荷、bootstrap 同代字节及 XML 少量字段，未完整比较外层入口组件的所有成员。

本轮用 CE2047 审计代码读取已核验的 CE2045 公开原件，创建一次性负例。原件通过；仅改外层 default.py、仅改 addon.xml 版本、增加额外 .py，三者仍被接受。内嵌签名包不变，改动后的入口未执行，临时 ZIP 已删除。原 CE2045 原件前后 SHA-256 相同。

证据 `installer/outer-binding.json` 为 **1 passed / 3 failed，exit 1**，显式标注 `ce2047_binary_reviewed=false`。这说明审计覆盖不足；不说明原发布包实际遭到篡改，也不能替代 CE2047 实物验包。

修复应从已验签的同代 script.bobbi.start 组件、bootstrap 构建规则与 bundle 导出完整预期集合，比较每个成员和字节，拒绝非预期成员，避免硬编码文件总数。继续遵循现有分发政策，无需把独立许可证、授权文件或硬件资格新增为前置门槛。

## 六、播放和 UI 证据能支持到哪里

### 1. 长选择回归有进展，但尚未开播

公开回执已补上原同 hash 的超时关闭记录、CE2047 的真实选择框、框内额外停留 35 秒后的确认，以及随后同 hash 仍处于 Torrent preload、目录 13 项的状态。原根因“人工选择超过引擎空闲期限”现在有比旧版更完整的关联证据。

上游固定 MatriX.144.1 提交的 GetTorrent 延长存活 torrent 的空闲期限，与该修复方向相符；没有把 API 对缺失 torrent 返回 404 的实现推定为原故障实测状态码。详见 `bt/BT-REVIEW.zh-CN.md` 与 [公开长选择回执](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/review-evidence/ce2047/bt-after-long-choice.json)。

这里可认可的成果是“长时间选择后进入缓冲”。缓冲时 peer 供数仍弱，没有 AV_STARTED，不能扩写成 BT 影片通过。

### 2. 两部新作品均未形成新的观看通过证据

| 样本 | 公开回执与本轮重算 | 结论 |
| --- | --- | --- |
| Paterson / 帕特森，2016，TMDb 370755 | 80 个采样无 AV_STARTED；原手选 1080p 版本；缓冲 8,880,128 / 32,212,254 字节后 TORRENT_BUFFER_TIMEOUT | 本次新电影未通过开播；no_observed_stall=true 不构成成功 |
| Planetes / 星空清理者，2003，TMDb 34102 S1E1 | 76 个采样没有 AV_STARTED，出现 OPEN 后终态 ERROR；115 返回 share_revoked / 4100010；重新查询同 source_key 再出现 | 本次新动漫未通过开播；需继续查失效卡片状态与恢复路径 |

数据来源为[电影选择回执](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/review-evidence/ce-new-work-paterson-select-1792647678689562200.json)、[动漫诊断](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/review-evidence/ce2023/entry-device-diagnose-1792648472666383300.json)和[重查卡片](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/review-evidence/ce-new-work-planetes-cards-1792648630962508400.json)。本轮独立关联摘要在 `bt/published-playback-receipts-summary.json`。

**不能由“同卡片重现”推导“系统完全没有失效记忆”。** 源码已有 denied_proofs、invalidate_proof 和 invalidate_share；[invalidate_share](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/addons/script.module.bobbi.core/lib/bobbi_core/source_list_session.py#L109-L120)明确保留候选、撤掉旧验证状态。当前 cards dump 未记录 verifiedShareFile，不能证明它仍被标成验证可播。

下一轮应沿失败到重新查询的真实路径，记录验证状态、用户可见原因、排序和重试条件。精确分享已撤销、临时网络故障、账号过期要分别处理；状态按账号代次和精确分享/文件隔离，新验证成功后可恢复。禁止按整部作品永久屏蔽，也不自动更换用户选择的版本。

### 3. UI 语义检查有支持，像素结论仍是 INCONCLUSIVE

两轮公开实机 UI smoke 的旧卡片对象、焦点、1080p 筛选保留，列表 reset=0。截图为真实安装 UI，内容使用合成二维码/候选，没有执行登录或播放。

| 回执 | 基线 | 到源期间 | 独立重算 |
| --- | --- | --- | --- |
| CE2046 smoke | 10 个有效一致样本 | 51 个样本：50 有效一致，1 个翻页无效 | INCONCLUSIVE |
| CE2047 smoke | 10 个有效一致样本 | 48 个样本：47 有效一致，1 个翻页无效 | INCONCLUSIVE |

两份 JSON 的 `passed=false`、`stable_card_pixels=false` 与上述严格判断一致。外层进程 exit 0 只表示工具执行结束，不把它当视觉通过。无效读既不是闪动证据，也不能被删掉以得到 PASS。复算与 PNG 身份记录在 `evidence-recomputed.json`；源码判定在 [framebuffer_patch / patch_stability](https://github.com/2223M1/bobbi-tv/blob/5d6a77d78a278984517f3e4af99c239054e9ba4a/tools/ce_ui_preview_remote.py#L173-L229)。

### 4. 没有新增的整片功能通过结论

本轮公开新作品没有成功 AV，因而没有新的字幕画面、原音轨、seek、手动字幕 Off、自然 EOF 或 BT→115 中途接续通过证据。现有旧回执保留历史价值，不能替代本轮。无需为这次审查新增第二设备资格、硬件白名单或原生播放器哈希门禁。

## 七、CI 与本轮测试账本

CI 运行在 2026-10-22 06:19:20 UTC 完成；job 119671302120 所有步骤成功。已下载 artifact 12406132007，大小 82,702 字节，SHA-256 为：

`0989a0333e1cd5971b21a39b3ab700dbbdcf3114172ec2c4afb377852f7a03fb`

与 GitHub 元数据相同。压缩包中是三份 JUnit 原件，逐 testcase 重算，三个进程没有重复 testcase ID。

| CI 组 | 通过 | skip | xfail |
| --- | ---: | ---: | ---: |
| Primary | 3,543 | 6 | 1 |
| private_baseline | 1,027 | 0 | 0 |
| preparation_regression | 254 | 0 | 0 |
| 合计 | **4,824** | **6** | **1** |

CI 日志也记录两次 source-check 构建均为 22 组件，比较的 63 文件一致。这是无发布密钥的源码构建，不是 CE2047 完整安装 ZIP 的可重复性证明。CI Linux 的 6 个 skip 是 5 个 Windows API 绑定与 1 个可选大附件 fixture；维护者 Windows 本地的 6 个 skip 是符号链接夹具，虽然总数相同，未覆盖项不同。1 个 xfail 是保留的真人版/动画强类型证据不足问题，不应写作全通过。

| 本轮独立执行 | 结果 | 记账说明 |
| --- | --- | --- |
| pre-AV 仓库两文件 | 119 passed | 属于 CI 的子集 |
| BT 与诊断仓库两文件 | 172 passed | 含 12 个像素读取用例，属于 CI 的子集 |
| 安装与恢复仓库两文件 | 57 passed | 属于 CI 的子集 |
| 三组仓库测试合计 | **348 passed** | 不与 4,824 相加 |
| 前 AV 旧独立回放 | 6/6 | 与仓库业务覆盖交叉 |
| 前 AV 独立命令边界 | 12/12 | 实际方法、真实 owner、显式 IPC/GUI 替身 |
| BT 独立 HTTP 回放 | 8/8 | 实际方法、内存 HTTP 响应替身 |
| 回退完整性反例 | 1 pass / 3 fail | 真实临时包与文件系统；exit 1 |
| 外壳完整性反例 | 1 pass / 3 fail | 真实 CE2045 原件 + 临时负例；exit 1 |
| 保活慢正文反例 | 0 pass / 2 fail | 真实 vendored HTTP + 回环服务；exit 1 |

维护者另有 4,824 passed / 6 skipped / 1 xfailed 原始 JUnit，已经核对；维护工具 166 passed 与其重叠。所有计数来源、失败和初次夹具记录均保留，不用重复累加制造更大的成功总数。

## 八、下一轮安排

| 顺序 | 交付目标 | 验收重点 |
| --- | --- | --- |
| 1 | R47-01 回退恢复计划与旧代向量；R47-02 BT status 可取消读取 | 三类坏备份在移动当前代前拒绝；中断恢复可重入；真实慢正文退出无残留 worker |
| 2 | R47-03 完整入口外壳绑定 | 原件通过，改入口/XML/多成员均拒绝；集合动态导出 |
| 3 | 新候选交付身份与证据 | 完整 ZIP、精确 SHA、提交/tree、签名清单/成员比对、本次 CI 和安装事务可关联；不覆盖旧 tag/Release |
| 4 | 失效分享可见状态与播放验收 | 同账号精确失败状态跨查询可解释、可恢复；新电影/动漫真正 AV 后才记录字幕、音轨、seek、EOF |
| 5 | UI 像素补证 | 保留全部原始样本，消除采样缺口或明确限定测量范围，继续区分界面语义与像素结果 |

仓库报告记载“禁止新增校验”，但没有在本次材料中给出具体适用范围。本审查因此保留两项完整性问题的开放状态，交付明确的代码位置、最小方案和失败夹具；不会把未实施算作关闭，也不会据此扩展新的硬件或许可门槛。后续执行以用户当轮实际约束为准，见任务书的范围处理规则。

**发布建议：继续作为候选审查，不将这轮局部修复描述为稳定版或完整观看通过。** 公开分发权限与技术验收状态分别成立。后续无需增加与现有约束无关的门禁，应把工作量集中到三项具体缺陷、真实交付包和本轮播放证据。

## 交付包导航

- `00-START-HERE.zh-CN.md`：阅读顺序、复跑命令和退出码。
- `02-CODEX-EXECUTION.zh-CN.md`：可交给 Codex 的后续任务书。
- `03-ACCEPTANCE.json`：机器可读的开放项与验收条件。
- `preav/`、`bt/`、`installer/`：分项审查、复现脚本和原始结果。
- `metadata/`、`ci/`、`evidence-recomputed.json`：固定源码身份与本次 CI 原件。
- `maintainer-evidence/`：选取的公开回执；完整源文件索引提供固定 URL 和 SHA-256。
- `MANIFEST.sha256`：本交付包文件校验清单。

本包是独立审查与执行指导包，CE2047 完整安装包仍需由维护者另行提供。
