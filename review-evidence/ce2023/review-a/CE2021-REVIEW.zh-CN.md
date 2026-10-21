# Bobbi TV CE2021 clean 交付独立审查

审查日期：2026-10-21，用户时间采用 Asia/Shanghai。审查对象是固定 Git 提交及其 Draft Release 的可取得证据，不以随时变化的分支名代替版本身份。

## 1. 审查结论

**建议要求修改，暂不把这份 GitHub 交付作为“CE2021 修复已进入源码、可复现构建并完成独立验收”的版本接受。** 当前分支新增的是报告、清理回执和重签工具；报告描述的 F01–F03 与协作停机修复没有进入产品源码。当前 CI 失败；新增重签工具还有一个已独立复现的输入代次校验缺口。

**这个结论不等于判定作者本地已测 CE2021 安装包无效。** 本轮没有取得三个 Draft Release ZIP 的实际字节，无法独立判断它们内部是否包含所述修复。现有事实能够证明 Git 交付未闭环，不能把旧源码的失败直接外推成未取得的二进制失败。

交付报告对历史证据边界说明得较清楚：1764/782/177、原始实机试验与 63 项源码产物属于清理前候选；当前清理后的 source-check 失败；重签序列 2026102022 没有再部署。这些说明应保留。问题在于接手者仍无法从当前 Git 源码重建和复核那份已测候选。[原交付报告末段](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/docs/CE-REVIEW-CLOSURE-2021-20261021.md#L161-L199)

本轮主发现分为 **2 项 P1、1 项 P2**。旧 F01–F03 的源码状态、缺失证据链接与入口审计冲突分别并入对应交付问题，避免把同一个来源缺口重复计数。P1 在这里表示阻断源码交付验收，不表示已发生设备损坏或密钥泄露。

## 2. 固定身份与审查范围

| 对象 | 固定身份 / 状态 |
| --- | --- |
| 仓库、分支 | `2223M1/bobbi-tv` / `codex/ce2021-clean-delivery-20261021` |
| 本轮 head | `b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2` |
| 本轮 tree | `bbe592e62a7a6790c62725738b63dae9b9f9405a` |
| 父提交 / 重写 CE2014 基线 | `f6ef6a7e3c5868a2ab8ed8e600a592d51ba97167` |
| 上轮实际受审 CE2014 | `c8de17ae9dabbe0f37753e1751b1d88107311316` |
| 当前 main，首次读取时 | `910334b132de882a116761e4ea9e493c3071dc06` |
| 当前 CI | push run `39525777378`，固定 head 相同，结论 failure |
| Draft Release | ID `419038503`，目标是上述分支字符串；拟用 tag `ce2021-clean-delivery-20261021` |
| 原始已测代次 | 报告标为 `2026102021` |
| 清理重签代次 | 工具、回执及 release 描述标为 `2026102022` |

完整检查了本轮新增的三个文件，并用未截断的 Git tree 比较保留文件的 blob 身份；安装、播放、UI、构建、入口审计等关键路径再逐文件计算实际读取字节的摘要。旧快照复用只发生在 blob 与当前 tree 完全一致时。本地是经身份核对的源码快照，不是完整安装资源 checkout；源码构建结论来自真实 GitHub CI 完整 checkout，未把本地未下载文件当作产品缺陷。

原始来源：[固定提交](https://github.com/2223M1/bobbi-tv/commit/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2)、[与实际父提交的差异](https://github.com/2223M1/bobbi-tv/compare/f6ef6a7e3c5868a2ab8ed8e600a592d51ba97167...b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2)、[CI run](https://github.com/2223M1/bobbi-tv/actions/runs/39525777378)。机器证据见 `evidence/SOURCE-IDENTITY.json`、`evidence/GIT-TREE.json`、`evidence/TREE-DELTA-VS-CE2014.json`。

## 3. D01 · P1：真实修复源码尚未进入 Git 交付

### 事实

相对实际父提交，这次只有一个 commit、三个新增文件，共 463 行：

| 新增路径 | 行数 | 作用 |
| --- | ---: | --- |
| `docs/CE-REVIEW-CLOSURE-2021-20261021.md` | 199 | 整改和历史实机说明 |
| `review-evidence/ce2021-clean-packaging-result.json` | 32 | 打包结果摘要 |
| `tools/package_ce2021_github.py` | 232 | 清理原包并重签的工具 |

与上轮实际受审的旧 CE2014 tree 比较，结果是 **新增 3、删除 83、修改 0**。83 个删除项来自清理后的历史基线；它们不是说本次单独 commit 删除了 83 个文件。全部保留产品文件的 blob 均没有发生变化。这与报告中受管恢复、单次 snapshot、队列选择补偿、协作关闭等修复描述不对应。

版本文件也提供了直接交叉证据：

| 组件 | 当前分支 `addon.xml` 实读 | 报告称原包 / 清理包版本 |
| --- | --- | --- |
| plugin.video.bobbi | 0.1.9 | 0.1.15 |
| script.module.bobbi.platform | 0.1.11 | 0.1.17 |
| script.module.bobbi.core | 0.1.15 | 0.1.16 |
| script.bobbi.start | 0.2.6 | 0.2.13 |

版本不同只是辅助证据；决定性证据是完整 tree 差异与关键文件字节身份。即使两个包版本号相同，也仍须比较实际源码和签名 manifest。

### 旧问题在当前源码中的状态

| 项目 | 本轮确认 | 本轮验证层级 |
| --- | --- | --- |
| F01 恢复 | `ce_install_ui.py` 仍调用裸路径 `RunScript(.../service.py)`；quiesce 仍先禁用再等 lease | 静态逐字节确认与上轮受审实现相同；未将旧反例重算为本轮执行 |
| F02 非首卡 / 画质焦点 | 延迟 native bind 后 source index 1 退到 0；新增 4K 标签后 1080p 选择退到全部 | 当前 head 实际复跑 5 项：3 通过、2 失败、0 errors |
| F03 临时未知 / EOF | 临时 IPC 失败与同实例 EOF 竞态仍被误归为 superseded | 当前 head 实际复跑 5 项：3 通过、2 失败、0 errors |
| G01 / 旧 C02 停机收尾 | history、字幕短 join，Host 的 stopping 早返回与 finally 释放 lease 逻辑未变 | 源码未闭环；没有新增真实数据库损坏证据 |
| G03 字段清理 | seeders/peers 仍只在非零且未缓存时写入 | 条件性加固未进入分支；不升级为已证实的日常故障 |

准确定位：[F01](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py#L174-L201)、[F02 source bind](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/gui/source_select.py#L872-L880)、[F02 quality](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/gui/source_select.py#L250-L272)、[F03](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/native_player.py#L707-L712)。原始结果位于 `evidence/playback/`。

### 证据链接也未形成可复核交付

报告内 26 个不同的 `../review-evidence/...` Markdown 链接，**26 个均不在当前完整固定 Git tree 中**。包含适配后 A/B 双审查、测试 XML、UI 记录、三轮恢复、影片起播、续播与最终状态等。详见 `evidence/playback/EVIDENCE-MATRIX.json`。

这些文件可能在独立 release 合集 ZIP 里。本轮没有取得合集字节，因此本结论是“当前分支没有这些证据”，不是“所有渠道都没有证据”。同理，A 14/14、B 48/48 是作者报告中的历史成绩，本轮未审查适配 diff，也未重跑这两整组，不能把它们登记为独立通过。

### 影响与关闭条件

接手者无法从当前源码定位实际修复、检查适配是否保留原行为断言，或可靠重建已测包。下一步应取得作者保留的真实 CE2021 工作区或完整补丁、原始交付包和回执，先恢复来源关系，再决定哪些代码仍需修。直接在旧实现上照报告重写，会丢失已有修复的实际细节。

**关闭 D01：** 固定候选 commit/tree 包含实际修复与测试；运行时代码与原始已测包、清理包有逐文件映射；每个成功结论绑定 producer commit、工具摘要、包摘要、签名 sequence 与原始回执。不能只补报告或只改版本号。

## 4. D02 · P1：清理政策与清单、构建、入口审计不一致

### 当前 CI 的独立核验

取得实际 Actions artifact `12313666129`，102,202 bytes；SHA-256 为 `06312c59736013153a1a18058382adaced7d24ab9c22d05f162420580a528e45`，与 GitHub 记录一致。解开三份 JUnit 后：

| 测试组 | 通过 | 失败 | 跳过 | errors |
| --- | ---: | ---: | ---: | ---: |
| primary | 1741 | 5 | 5 | 0 |
| private_baseline，独立进程 | 761 | 0 | 0 | 0 |
| preparation_regression，独立进程 | 177 | 0 | 0 | 0 |
| **合计** | **2679** | **5** | **5** | **0** |

五个失败分别为：

1. `test_preview_is_reproducible_and_dependency_closed`：preview 显式 inventory 与清理后 platform 文件集合不符。
2. `test_fonts_are_unchanged_and_licensed_in_project_assets`：`assets/fonts/LICENCE-HarmonyOS-Sans.txt` 缺失。
3. `test_public_inventory_is_exact`：当前组件文件集合与 `release/source-inventory.json` 不符。
4. `test_actual_private_skin_restores_exact_fonts_but_not_legacy_scripts`：FontAwesome license 缺失。
5. `test_checked_in_notices_and_truthful_unresolved_status`：`licenses/THIRD-PARTY.json` 缺失。

两个 `build_release.py --source-check` 都以 `Source inventory changed: plugin.video.bobbi` 中断；`check_repository.py` 没有执行到。这是实际当前 CI，不是由本地不完整快照造成的缺失。历史 1764/782/177 与旧双构建结果不应覆盖它。[CI 原始 run](https://github.com/2223M1/bobbi-tv/actions/runs/39525777378)

### 入口审计还有一个独立可达的矛盾

新工具递归删除 `script.bobbi.start/bootstrap/LICENSE`，当前 `audit_ce_entry.py:49` 却无条件读取它；`build_ce_entry.py:40` 也仍从 platform 包复制该文件。新 cleaner 自己的 ZIP、签名和非排除字节检查，不会覆盖这个既有入口契约。

窄型复跑使用真实 cleaner、真实 audit、真实 bootstrap 模块和独立 Python 导入：原件通过；只删除该 LICENSE 的清理件失败为 `KeyError`；两份非排除 bootstrap 字节相同，清理件 `check_nested` 通过。**2 项，1 通过、1 失败、0 执行错误。** 签名/组件载荷在这一探针中明确使用夹具；它没有对真实 release 验签。证据见 `evidence/installer/CLEAN-ENTRY-AUDIT-CONTRACT.json`。

源码：[删除规则](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/package_ce2021_github.py#L20-L23)、[清理执行](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/package_ce2021_github.py#L70-L75)、[入口审计 L49](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/audit_ce_entry.py#L49)。这证明检查契约冲突，没有证明 Kodi 运行会失败；实际 `default.py` 不靠读取 LICENSE 启动。

### 修复方向

先明确既定清理目标在源码仓库、构建输入和分发 ZIP 三个范围内分别意味着什么，再统一 inventory、构建器、cleaner、审计器和测试。保留真实签名、同代 bootstrap、独立导入和账号状态排除等有效保障。不应通过整组 skip、关闭 exact inventory 或删除入口 audit 取得绿灯。

**关闭 D02：** 完整新 checkout 的三组测试无失败/错误；两次 source-check 成功且实际比较产物；用同一源码生成最终签名包和入口，完整入口 audit 对最终真实字节通过；文档策略改变有明确测试与删除清单。

## 5. D03 · P2：重签器接受错误旧代次并写错来源

工具明确定位为“对已有 CE2021 候选进行清理”，内部输入路径固定含 2026102021。但第 145 行只拒绝 `sequence >= 2026102022`，没有要求输入等于 2026102021；第 213 行又把 `original_sequence` 固定写成 2026102021。[输入检查](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/package_ce2021_github.py#L139-L150)、[输出来源字段](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/package_ce2021_github.py#L212-L217)

独立构造临时 RSA-3072 签名输入，只将信任配置接到临时测试密钥；实际 main、签名、ZIP 和 `SignedBundle` 检查均运行，未读取生产私钥或修改产品：

| 场景 | 当前观察 | 契约判定 |
| --- | --- | --- |
| 正确输入 2026102021 | 接受，输出 2026102022，记录真实原代次 | 通过 |
| 合法签名旧输入 2026102014 | **接受，输出 2026102022；记录 original_sequence=2026102021** | **失败** |
| 输入 2026102022 | 拒绝，非递增 | 通过 |
| 错误 profile | 拒绝 | 通过 |
| 未受信任输入签名 | 拒绝 | 通过 |

**5 项，4 通过、1 失败、0 执行错误。** 旧输入与输出都经过真实 `SignedBundle` 检查。见 `evidence/packager/INPUT-GENERATION-RESULT.json` 与 `checks/reproduce_input_generation.py`。

这是维护者拿错一个更早合法包时的输入防错和来源记录缺陷。攻击者仍不能无钥重签；也没有证据证明本次真实 release 用错了包。修复应钉住专用工具的预期输入 sequence、原始交付及内嵌 payload 摘要、组件身份；`original_sequence` 从已经验证、尚未修改的输入派生。分配新的输出代次时核对已有序列，不复用已登记代次。

**关闭 D03：** 旧合法包被拒绝；正确原件仍可处理；错误 key/profile/channel、非递增、嵌入不一致等负控仍拒绝；外层 manifest 对真实输入如实记账。原 trust、输入签名、组件 hash/size、非排除文件字节一致和输出验签保障保留。

## 6. 资产与报告：哪些对上，哪些还不能签字

仓库回执列出的四项资产 name/bytes/digest 与 Draft Release 元数据相符。报告附件和仓库报告同为 16,320 bytes，SHA-256 为 `a21661ec171c39300b182a1521e65ce0532db38a023d63ce1dcc91a8022f8722`，也与 release 元数据相符。

仓库 packaging-result 为 968 bytes；release 元数据为 1000 bytes。将仓库文件的 32 个 LF 改为 CRLF，恰好得到 release 元数据的完整摘要与大小，因此这个差异不作为内容矛盾。检查详见 `evidence/release/ASSET-METADATA-COMPARISON.json`。

| 资产 | bytes | GitHub 元数据 / 仓库回执 SHA-256 |
| --- | ---: | --- |
| `bobbi-private-2026102022-coreelec.bobbi-update.zip` | 96,135,572 | `c0ebea710ef3dda667c4336aa42b4b212469399468f6081f60d806e8171ca696` |
| `script.bobbi.start-0.2.13-ce2021-clean.zip` | 96,233,587 | `bf10e21a30f98a74c99671985600a79da692371733f5ca17a21179565a72cb6b` |
| `ce2021-clean-delivery-20261021.zip` | 199,794,948 | `4188691ab12040ac0f1e33bcba6761c6a02fc5bc6c00932f23991192988da708` |

以上是**服务端元数据与回执核对**，不是本轮对三个 ZIP 下载字节的重算。当前连接可取得 Git 源码、release 元数据和 CI artifact，但没有取得这些 release 二进制。因而签名有效、22 组件、49 个删除项、非文档内容保持、内嵌同代 bootstrap、合集补丁与原始设备证据，仍属于作者工具/报告声明，尚无本轮真实资产级独立结论。

这次工具已有几项合理保护：原维护者 key 与 trust 比对、原签名、内嵌/独立载荷一致、组件 hash/size、非排除叶子摘要、新输出签名、原件不覆盖。这些设计值得保留；它们验证“从输入到输出”的关系，不能自动证明“当前 Git 源码就是输入来源”。

## 7. 实机报告的有效信息与未完成事项

下表来自作者报告，未由本轮原始设备回执重新核实。不得记成本次独立实机通过。[报告播放部分](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/docs/CE-REVIEW-CLOSURE-2021-20261021.md#L87-L132)

| 作品 / 场景 | 作者报告 | 后续判断 |
| --- | --- | --- |
| 三轮恢复 / 关闭 | CE2021 三轮恢复通过，idle、lease、ready 证据；慢任务收尾和协作退出整改 | 取得真实实现后验证 owner 线程、音频/视频/未知状态拒绝、旧代次兼容、失败保留 lease 与重试 |
| UI | 第二张卡 + 1080p，新增五项及 4K 标签后保持；70 个局部 ROI 样本 | 是有价值的指定场景观察；不能替代真实代码和异步队列反例，也不等于全界面持续不闪 |
| 《天使爱美丽》TMDb 194 | 约 14.19 秒首次 AV，后段约 30 秒正常推进，法语与 chi 启用 | 有限窗口起播/原声/字幕启用声明；不是整片稳定或字幕全程同步认证 |
| 《元气囝仔》TMDb 67048 S1E1 | 诸神 1080p BT metadata 约 30 秒、49 poll 超时，0 个 AV 样本 | **仍失败**；故障发生在播放器前，先查元数据取得，不据此归因硬件解码 |
| 《乒乓》TMDb 60811 S1E1 | 115 Vodes 1080p HEVC，约 4.62 秒首次 AV，日语及后段推进正常；只有英语内嵌字幕 | **中文字幕仍失败**；视频通过与中文通过分列 |
| 《乒乓》尾段续播 | StartPercent 98.8 → NATURAL_EOF → SAME_VERSION_HANDOFF → S1E2 新 request/instance，推进 26.645 秒 | 可支持尾段自然终态与同版交接的声明；需完整有序父子日志，不能算整集观看或另一部新作品 |

报告保留了首次导航错误、服务恢复 pending 时的起播误操作、旧失败和后续复验的区别。这种记账方式应继续使用。`transport_ok`、`trial_passed`、`exit_code`、`pending` 分开记录，pending 不得直接算成功或产品失败。

## 8. 建议的下一轮顺序

### 第一阶段：恢复可信的候选来源

取到原 CE2021 已测工作区/完整补丁、原包、清理包及回执；只读保留并记摘要。在隔离分支恢复真实修复，记录旧 c8de17a 到重写 f6ef6a7 的映射。每个运行文件建立“Git → 组件 ZIP → 原包 → 清理包”的对应。若原始完整源码尚缺，包内 Python 文件只能是恢复线索，不能直接宣称完整可重建源码已经恢复。

**阶段产物：** 固定 commit/tree、来源映射、原始/适配测试 diff、可访问证据索引。T01 完成前不关闭 F01–F03。

### 第二阶段：统一交付契约并完成当前源码门禁

解决 D02 的文件政策和 D03 的精确输入检查；保留有效安全与行为断言。三组测试按 CI 方式独立进程执行；完成两次 source-check 与实际字节比较。旧反例用当前候选再跑；真正内部边界变化时，可以迁移注入点，但须保留原行为契约和正负对照。

**阶段产物：** 当前提交对应的 CI/JUnit、源码构建/比较日志、四类独立反例结果、适配解释与差异。

### 第三阶段：验证最终真实安装资产

从上述固定来源产生最终 payload 与用户入口；钉住准确 release commit，记录唯一签名序列和所有摘要。用真实 key/trust 完成签名检查与负控、内嵌载荷一致、同代 bootstrap、隔离导入、完整入口 audit。输出每个删除项的路径、原始 hash、命中规则，过滤 patch blocks 另行计数。当前只有 `removed_entries=49`，不够逐项复核。

**阶段产物：** 能重复核验的实际资产、组件/源码映射、删除清单、签名及入口回执。通过不等于新增实机认证。

### 第四阶段：集中修两个明确播放缺口

《元气囝仔》固定原 resource identity，记录 backend 健康、add、metadata、文件选择、preload 和 first AV 分段；与同 backend 已知可取得 metadata 的来源作有限对照。上游没有 metadata 时如实失败和返回选源；只有存在证据时才改 resolver。

《乒乓》固定原视频文件，记录“内嵌轨 → 查询/鉴权/限流/超时 → 候选 → 中文文本 → 作品/集数/版本 → 时间轴 → 加载 → 实际字幕轨”的逐级结果。无合格中文保持未通过；有匹配候选却被误拒才修对应环节。人工字幕/Off 不得被迟到自动结果覆盖。

设备复验在已有明确授权范围内按实际包执行并保留回退证据。通用 CoreELEC、原画原码流、原声优先、手动选源、准确同版续播继续作为产品约束；设备型号只记为环境事实。

## 9. 验收与停止条件

| 门槛 | 可接受的证据 | 仍不能替代它的材料 |
| --- | --- | --- |
| 实际修复已进入源码 | 固定 commit/tree、源 diff、关键运行文件与包内映射 | 修复说明、版本号、自报 passed |
| 当前源码可构建 | 当前完整 checkout 的三组 JUnit、双 build 与比较日志 | 清理前成绩、部分源码目录运行结果 |
| 当前包正确 | 最终包 hash、真实验签、嵌入一致、完整 entry audit | release 元数据、fixture 验签、旧入口 audit |
| 原问题关闭 | 当前候选行为反例与正负对照；适配 diff 可审计 | 只改预期、只跑首卡、只测 helper |
| 实机行为 | 明确包、sequence、attempt、父子身份与窗口的原始记录 | 报告摘要、pending、视频通过覆盖字幕失败 |

只要前三项未闭环，保留 Draft 和“来源未完成独立核验”的状态。若源码/资产已修而两部作品仍失败，应分别报告交付门禁通过与对应播放问题开放，不用一个总的 passed 掩盖差异。

## 10. 本轮验证清单与交付

| 本轮实际执行或核实 | 结果 | 性质 |
| --- | --- | --- |
| Git 完整 tree + commit 差异 | 3 新增；相对旧受审 tree 83 删除、0 修改 | 真实 Git 元数据与字节核对 |
| 当前 CI artifact | 2679 通过、5 失败、5 跳过、0 errors | 真实下载并校验 ZIP，独立解析 JUnit |
| UI | 3 通过、2 失败、0 errors | 真实产品方法 + 明确 Kodi 队列边界替身 |
| Native monitor | 3 通过、2 失败、0 errors | 真实产品方法/owner + 明确 IO 边界替身 |
| clean entry / audit | 1 通过、1 失败、0 errors | 真实清理/审计/独立导入；签名载荷边界夹具 |
| 输入代次重签 | 4 通过、1 失败、0 errors | 临时 RSA key、真实签名及 SignedBundle；不是生产资产 |
| Draft 三个 release ZIP | 未取得字节 | 仅核对元数据，不计独立验签 |
| 当前设备 | 未操作 | 未新增设备证据 |

四组独立反例合计 17 项、11 通过、6 失败、0 执行错误；这个数字不与 CI 混算，不表示全产品覆盖率。完整旧 14 项、B 48 项、prior18/prior15 的本轮执行均未发生。

本包包括本报告、可直接交给 Codex 的任务书、三个分域报告、四份反例脚本、真实 CI ZIP/日志、来源和资产元数据、机器可读发现及文件摘要清单。执行入口见 `CODEX-EXECUTION-PACK.zh-CN.md`；播放专项细则见 `reviews/NEXT-PLAYBACK-GUIDANCE.zh-CN.md`。本次评审没有修改产品、部署、推送、合并、发布或发出 GitHub 评论。
