# CE2021 新交付：播放、UI 与实机证据独立复核

审查日：2026-10-21。目标仓库：`2223M1/bobbi-tv`。

固定审查对象：`codex/ce2021-clean-delivery-20261021`，commit `b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2`，tree `bbe592e62a7a6790c62725738b63dae9b9f9405a`。

## 结论

**本次 Git 分支不能作为“F02/F03 已修复并可独立复现”的源码交付接受。** 与重写后的 CE2014 基线 `f6ef6a7e3c5868a2ab8ed8e600a592d51ba97167` 相比，它只新增整改报告、打包结果和打包工具三个文件；播放和 UI 产品源码没有新增提交。对固定 head 的小范围复验仍得到旧 F02 的两个失败和旧 F03 的两个失败。

这个结论只针对已取得、校验过的 Git 源码。**本审查没有取得并解包作者所述“清理前已测 CE2021”与“2026102022 重签”载荷，不能把旧源码的失败外推为新安装包内实现也失败。** 当前首先缺少的是修复源码、安装包、测试和实机回执之间可审计的对应关系。

附件与分支内整改报告逐字节一致；报告明确承认旧测试和可重现构建结果属于清理前候选，当前工作区 source-check 失败，重签包未重新部署。这些边界说明是正确的。它们没有消除源码交付缺口，也不能替代原始证据。[来源：报告第 161–199 行](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/docs/CE-REVIEW-CLOSURE-2021-20261021.md#L161-L199)

## 1. 源码核验方法及结果

使用 GitHub 固定 commit 的完整 tree，而非随时变化的分支名称，核对 blob SHA-1；对 UI、native player、playback request 三个关键文件另行抓取固定 commit 内容。再对运行时实际读取的本地快照计算 SHA-256 和 Git blob SHA-1。全部匹配当前 tree，且与上一轮 CE2014 评审快照逐字节相同。记录见 `SOURCE-PROVENANCE.json`。

| 文件 | 当前 Git blob SHA-1 | 与旧 CE2014 内容比较 |
| --- | --- | --- |
| `addons/plugin.video.bobbi/lib/gui/source_select.py` | `75709649cba63d2800593f3ed4414f24577157ef` | 相同 |
| `addons/plugin.video.bobbi/lib/native_player.py` | `ad17c8b8c1d84fbc07b52376632b05558c703733` | 相同 |
| `addons/script.module.bobbi.core/lib/bobbi_core/playback_request.py` | `ba40a13c099823537748c5fa75b930d0aad3d102` | 相同 |
| `addons/script.module.bobbi.core/lib/bobbi_core/playback_owner.py` | `b7c534105ac2fcff12f417e3293d8daccc982848` | 相同 |
| `tests/private_baseline/test_source_incremental_ui.py` | `c965e322da47dc378d2ca23fb0b437ae5241a5f3` | 相同 |
| `tools/ce_ui_smoke_remote.py` | `775bf535add302f47435da1de0c29f513b3780ee` | 相同 |
| `tools/ce_standard_real_remote.py` | `b27946f212d00fec82e602fea61932fa916ce1f8` | 相同 |

因此，此处不是把一个较旧 checkout 误作最新版本，也不是因新内部接口变化而把旧夹具错误算成产品失败。

## 2. F02、F03、G03 是否已进入这个分支

### F02：异步列表绑定后的非首卡与画质焦点，分支仍未收口

报告声称结构变化后排队一次 `selectItem`，按 source key 和画质 key 保持。当前 `source_select.py` 第 872–880 行仍在 `addItems()` 后立即读取 `getSelectedPosition()`，只在读到的位置不同才补发选择；第 250–272 行增添画质标签没有相应的稳定 key 焦点恢复。[来源：实际源列表](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/gui/source_select.py#L872-L880)、[实际画质列表](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/gui/source_select.py#L250-L272)

当 native bind 尚在队列中时，Python 读到的仍是旧 index 1，于是没有补偿；随后 bind 执行又把焦点变成 index 0。画质列表添加 4K 标签后，同样能从 1080p 退回“全部”。这两项在当前 head 上均独立复现，详见 `ui-current-head.json`。

保留首卡、bind 提前派发、只有完成状态而没有结构变化三个对照均通过。它们同时说明：首卡静态截图或同步替身通过，不能覆盖非首卡异步时序。

### F03：临时不可用与同实例 EOF 仍可能被归为 superseded

报告声称改为一次新鲜 snapshot，分类 `ACTIVE / TERMINAL / SUPERSEDED / UNKNOWN`。当前 `native_player.py` 第 709–712 行仍是两个布尔判断，任一不成立立即标记 `_was_superseded=True` 并退出。[来源：当前 monitor](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/native_player.py#L707-L712)

当前 head 两个失败：

- 短暂 IPC 读失败后，权威 request 与 native instance 均仍是原实例，视频仍在播放，旧 monitor 却把它当作已替换并清理；本地 terminal 留在 `UNKNOWN`。
- `isPlayingVideo()` 与后续所有权检查之间，同实例自然 EOF 已在 owner 端成立、observed 已清空；旧 monitor 仍把它判为 superseded，没有完成自然终态对账。

持续有效实例、明确新选择、明确取消三个对照通过。原始输出见 `native-current-head.json`。此处仍是继承旧问题，不宣称新包出现了新的回归。

### G03：条件性加固未进入分支，维持原定性

当前第 844–847 行只在 seeders/peers 为真且未缓存时写值，没有在值归零或缓存后显式清空。报告声称的“每次明确写值或清空”没有进入此分支。[来源：字段更新](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/gui/source_select.py#L844-L847)

但普通 `SourceListSession.publish()` 使用 `entries.setdefault(key, source)`，同 key 新对象不会常规覆盖原对象。因此，仍不能把这个潜在陈旧字段路径说成已证实的日常故障。保留条件性加固定位，不新增一个未经实证的高优先级故障。[来源：publish](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/script.module.bobbi.core/lib/bobbi_core/source_list_session.py#L54-L65)

## 3. 本次独立小范围复验

| 组别 | 总数 | 通过 | 失败 | 运行错误 |
| --- | ---: | ---: | ---: | ---: |
| UI queued-bind 契约 | 5 | 3 | 2 | 0 |
| native monitor 契约 | 5 | 3 | 2 | 0 |
| 合计 | 10 | 6 | 4 | 0 |

两个脚本原样复用，未修改被测源码、未调整断言、未适配内部接口。进程退出码 1 来自已记录的契约失败；不是环境导入错误。脚本副本在 `checks/`，摘要、完整命令、读取源码摘要及结果摘要在 `SOURCE-PROVENANCE.json`。

这些是执行实际产品逻辑、在 Kodi/IPC IO 边界使用明确替身的反例；UI 队列模型参考 Kodi 21.3-Omega 的 `Control.cpp` 与 `GUIBaseContainer.cpp`，出处记录于结果 JSON。它们不是新一轮真实 CE 设备测试。本次没有连接、升级或操作任何设备。

## 4. 报告中的原始证据没有进入交付 tree

报告包含 **26 个不同的 `../review-evidence/...` Markdown 链接，26 个均不在完整固定 Git tree 中**。涵盖 A/B 双审查回执、各测试 XML、UI 截图索引、恢复现场、三部作品起播/观察、续播日志、最终设备状态、构建日志及原签名验证。完整清单在 `EVIDENCE-MATRIX.json`。

这是确定的分支交付证据缺口。单独 release 合集 ZIP 可能含这些文件；本分报告没有解包该 ZIP，不能宣称所有交付渠道都不存在原始证据。若后续取到，应先核对 SHA、生产该证据的源码身份、attempt、设备与安装序列，再更新结论。

尤其是适配后的 A 14/14、B 48/48：把 EOF 注入点迁移到真实单次 snapshot 边界，或把零次 select 假设改为结构变化后恰好一次补偿，原则上可能合理。但目前分支既没有这些修复代码，也没有适配 diff、原始失败和最终结果，无法独立判断是否保留原契约。**“报告披露了适配”本身不等于“适配已被独立审查通过”。**

## 5. 实机声明应如何记账

下表均为交付说明报告的结果，当前未由原始回执独立复核。[来源：报告第 87–132 行](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/docs/CE-REVIEW-CLOSURE-2021-20261021.md#L87-L132)

| 项目 | 报告所述 | 本次可接受的边界 |
| --- | --- | --- |
| UI | 第二张卡、1080p，追加五个 1080p 来源及 4K 标签；key/位置/筛选保持；五次补偿，70 帧局部 ROI 一致 | 属特定时序和局部区域声明；不是全屏或任意焦点永不变化的认证；当前 Git 源码独立复验仍失败 |
| 《天使爱美丽》TMDb 194 | 选定 115 1080p HEVC；约 14.19 秒见 AV；后段约 30 秒正常推进；法语、chi 已启用 | 有限窗口起播/原声/字幕启用声明；没有证明整片连续观看或字幕同步 |
| 《元气囝仔》TMDb 67048 S1E1 | 诸神 1080p 全集 BT，metadata 约 30 秒/49 poll 超时，0 个 AV 样本 | 仍失败；故障阶段在进入播放器前，不能据此归因解码或硬件性能 |
| 《乒乓》TMDb 60811 S1E1 | 115 Vodes 1080p HEVC，约 4.62 秒见 AV；约 30 秒后段正常推进；日语；只有英语内嵌字幕，未找到匹配中文 | 有限视频/原声窗口与“中文失败”并存；视频通过不能覆盖字幕项 |
| 《乒乓》尾段续播 | StartPercent 98.8 → 同实例 NATURAL_EOF → SAME_VERSION_HANDOFF → S1E2 新 request/instance，AUTO_VERIFIED_FILE，推进 26.645 秒 | 尾段自然结束与同版交接声明；不是整集观看、完整用户旅程或中文通过；需完整有序日志关联父子身份 |

作者将首次导航错误、pending 服务恢复期间误发起播与独立播放 attempt 分开，且保留先前失败，方向合理。最终计数仍应由原始回执确认，不能删除失败 attempt，也不能把同作品尾段复验算成另一部新作品。

## 6. 后续优先级

1. **先恢复可审计源码交付。** 取出清理前实测实现与相对基线修复 patch，提交正确候选源码；将它与签名包内所有运行时代码逐文件关联。不要先在旧分支上机械重写作者可能已经修过的代码。
2. **复核 F02/F03 的真实修复及夹具适配。** 保留异步排队、完整 owner-loop、明确取消/替换的反例，防止为了绿灯削弱契约。正确修复后的测试注入点应跟随真实边界，行为断言不变。
3. **按两个独立失败阶段处理片源。** 《元气囝仔》调查 BT 元数据取得；《乒乓》调查中文候选获取、身份、时间轴及加载。无证据时不调整全局缓存、码率或硬件要求。
4. **把首播、视频推进、原声、中文、自然 EOF 和准确同版续播分别验收。** 保留原画、原声优先、手动选源、手动 Off、严格同版约束和通用 CE 定位。

具体可执行任务及验收见 `NEXT-PLAYBACK-GUIDANCE.zh-CN.md`。此分报告不修改产品源码，也不承担对未取得安装包的执行认证。
