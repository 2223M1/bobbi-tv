# CE2021 新交付独立审查与后续规划

审查日期：2026-10-21（北京时间）  
仓库：2223M1/bobbi-tv  
分支：codex/ce2021-clean-delivery-20261021  
冻结提交：`b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2`  
冻结树：`bbe592e62a7a6790c62725738b63dae9b9f9405a`

## 一、审查结论

**这份交付可以保留为私库中的清理重签候选归档，但目前不能作为“CE2021 修复已完整进入源码、可以从 GitHub 重建并完成验收”的交付关闭。PR #3 继续保持 Draft。**

最先需要解决的是源码交付与构建链。报告描述的 CE2021 修复没有进入本分支的产品源码；当前提交的 GitHub CI 实际失败；即使修正源码清单，真实 Kodi 入口构建还有一个独立的已删除文件依赖。继续增加播放演示或重复重签旧包，都不能补上这些缺口。

同时，不能据此否认原安装包中的修复。报告对清理前测试、清理重签、未部署新包和未解决播放问题有明确区分；重签脚本也实现了实质的完整性检查。这次审查发现的是**可访问源码与交付链不能闭环**，不是已经证明重新签名后的安装包运行失败。

### 审查边界

本次已独立核查：

- 固定提交、父提交、全部提交差异、未截断 Git 树、PR #3 状态和草稿 Release 元数据。
- 新增重打包脚本，以及恢复、Host 关闭、标准播放器关闭、增量列表、native monitor 和真实入口构建的相关源码。
- 新提交对应的 GitHub Actions 原始日志与步骤结果。
- 7 项针对当前源码或受控夹具的缺陷观察：生命周期 3 项、UI/monitor 3 项、入口构建 1 项。
- 报告相对证据链接与 Git 树的对应关系；源码显式清单的路径成员关系。

本次没有连接或操作 AM6B Plus，没有提交、推送、评论、合并或修改 GitHub 状态。没有在本地重新运行全部产品测试；全套结果引用的是本提交实际 CI。

Release 页面可读取，但安装包下载跳转被 Chrome 以 `ERR_BLOCKED_BY_CLIENT` 拦截。本次未取得安装包字节，因此**没有独立执行新包 RSA 验签、逐文件比对、包内修复审查或设备实测**。下文严格区分源码事实、可重复本地结果、报告声明和待验证事项。

## 二、先分清三个不同的交付对象

| 对象 | 实际身份 | 可以支持的结论 |
|---|---|---|
| 当前 GitHub 源码 | b20e972，父提交 f6ef6a7 | 本次可独立审查；仍是上一代产品实现 |
| 报告所述原 CE2021 包 | 序列 2026102021 | 报告中的原实机、原测试和原构建成绩 |
| 清理重签候选包 | 序列 2026102022，Release 419038503，Draft | 新资产元数据可读；脚本与结果声明显示重签及内容检查；尚未独立核验包内字节或实机 |

PR #3 仍指向 `f6ef6a7e3c5868a2ab8ed8e600a592d51ba97167`，没有指向新交付分支。PR #3 的历史检查不能证明 b20e972，更不能证明未提交的本地 CE2021 产品修改。

四个关键版本也没有对齐：

| 组件 | b20e972 中 addon.xml | 交付报告所述包版本 |
|---|---:|---:|
| plugin.video.bobbi | 0.1.9 | 0.1.15 |
| script.module.bobbi.platform | 0.1.11 | 0.1.17 |
| script.module.bobbi.core | 0.1.15 | 0.1.16 |
| script.bobbi.start | 0.2.6 | 0.2.13 |

版本差异是辅助证据。决定性证据是提交差异和运行代码仍保留旧逻辑，不能仅修改版本号来“对齐”。

来源：[固定提交](https://github.com/2223M1/bobbi-tv/commit/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2)、[PR #3](https://github.com/2223M1/bobbi-tv/pull/3)、[交付报告](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/docs/CE-REVIEW-CLOSURE-2021-20261021.md)、[草稿 Release](https://github.com/2223M1/bobbi-tv/releases/tag/untagged-b57c2f96aec43f5080c0)。

## 三、需要整改的四项交付问题

| 编号 | 优先级 | 问题 | 影响 |
|---|---|---|---|
| D01 | P1 | CE2021 产品修复及新增测试没有提交 | 从分支取到的仍是旧实现，修复无法审查、维护或重建 |
| D02 | P1 | 当前提交的清单、测试与实际文件不一致，CI 和源码构建失败 | 干净检出不能按现有流程构建 |
| D03 | P1 | 入口构建硬依赖已删除的 LICENSE | 只修清单后，真实入口 ZIP 仍不能从清理后的组件生成 |
| D04 | P2 | 报告的 26 个相对证据链接全部不在当前树 | 从分支报告无法独立追溯测试和实机证据 |

这里的 P1 表示应在本轮交付关闭前解决的工程阻塞，不等于安装包已经损坏，也不是四个新播放器回归。F01/F02/F03/G01 的旧源码现象属于 D01 的具体证据，避免重复计算问题数量。

### D01：实际提交没有包含报告描述的产品修复

b20e972 相对父提交只增加三个文件：

1. `docs/CE-REVIEW-CLOSURE-2021-20261021.md`
2. `review-evidence/ce2021-clean-packaging-result.json`
3. `tools/package_ce2021_github.py`

没有新增或修改产品代码、产品测试、组件版本或构建清单。

这意味着报告中的修复可能保存在本地工作区、补丁或安装包中，但还没有成为本分支可检查的源码事实。正确的下一步是**找回已测修复并完整提交**，不是让下一个执行者仅凭报告重新猜一遍实现。

源码链接：[比较父提交与新提交](https://github.com/2223M1/bobbi-tv/compare/f6ef6a7e3c5868a2ab8ed8e600a592d51ba97167...b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2)。

#### F01 在当前源码里仍走裸 RunScript 恢复

`ce_install_ui.py:174–200` 的 `ensure_running()` 在没有收到 owner snapshot、能够短暂取得 runtime lease 时，于第 197 行执行：

```python
RunScript(special://home/addons/plugin.video.bobbi/service.py)
```

这是报告声称已替换的旧路径。当前 `quiesce()` 也仍先停用插件，再等待 lease，未包含报告所述的认证协作退出协议。

更明确的是，`tests/test_ce2012_recovery_ui.py:93–104` 还将裸 RunScript 命令作为正确预期。因此旧测试通过并不验证报告中的新恢复契约。

所需验收：enabled-but-dead 在 Kodi 服务管理器下恢复，收到真实 owner 回应；维护前由 owner 核验空闲并协作退出，确认 lease 后再替换；音频播放和未知状态不能被当作安全空闲。

来源：[恢复代码](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py#L89-L200)、[旧测试期望](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tests/test_ce2012_recovery_ui.py#L93-L104)。

#### G01 在当前源码里仍会过早释放锁

`Host.close()` 的现有逻辑为：

- 一开始设置 stopping，第二次看到 stopping 就返回。
- 按顺序关闭组件；其中一个抛异常，会跳过后续组件。
- finally 无条件释放 runtime lease。

因此，“开始关闭”和“已经关闭”被混在一起：关闭失败之后其他 owner 可以取得锁，而原宿主再次 close 又不继续清理。

标准路径还存在另一个表现：HistoryWriter 只 join 0.3 秒，下一集和字幕 worker 只 join 0.1 秒；没有确认这些工作结束就继续释放宿主锁。HistoryWriter.close 后 save 仍可入队。

本次对完整真实 Host、Runtime、InstanceLock、StandardPlayback、HistoryWriter、StandardSession 模块完成三个本地复现，仅替代 Kodi Player 和慢存储边界：

| 注入场景 | 观察结果 |
|---|---|
| images.close 抛异常 | streams 未关闭；真实 OS lease 已能被另一个 owner 取得；再次 close 不重试 |
| 历史存储工作尚未结束 | standard.close 已返回，worker 仍活着；随后 Host.close 已释放 lease |
| HistoryWriter 已关闭 | 新记录仍被接纳进没有消费者的队列 |

这些是当前 GitHub 源码缺陷的复现，不能外推为新 Release 包也有相同问题。

来源：[Host.close](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/script.module.bobbi.platform/lib/bobbi_platform/host.py#L346-L379)、[HistoryWriter](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/services/standard_playback.py#L18-L38)、[StandardPlayback.close](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/services/standard_playback.py#L285-L290)、[StandardSession.close](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/script.module.bobbi.platform/lib/bobbi_platform/standard_session.py#L196-L200)。

#### F02 在当前源码里仍缺少排队重绑后的焦点补偿

`source_select.py:872–880` 在 addItems 后同步读 getSelectedPosition，只有下标不同才 selectItem；画质标签新增/删除路径也没有恢复画质 key。

Kodi 21.3 的官方实现中，addItems 会发送异步 LABEL_BIND，容器消费时以参数 0 选中首项。Python 此时读到的可能还是旧下标，所以“同步读出来没变”不能证明重绑完成后焦点不变。

本次受控消息队列夹具使用原方法复现：原来选中 1080p，追加 4K 标签，方法返回时仍是下标 1；消费 LABEL_BIND 后高亮变为“全部”。这里测得的是**画质标签焦点/高亮丢失**，不能扩大为过滤条件必然被改写。

所需验收：保留 ListItem 对象；结构变化后按 source key 和画质 key 各补偿正确的排队选中；纯字段变化不重绑；不把无条件每帧 select 当作修复。

来源：[当前增量列表](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/gui/source_select.py#L872-L880)、[画质标签](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/gui/source_select.py#L250-L272)、[Kodi Control.cpp](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/interfaces/legacy/Control.cpp#L1243-L1284)、[Kodi GUIBaseContainer.cpp](https://github.com/xbmc/xbmc/blob/21.3-Omega/xbmc/guilib/GUIBaseContainer.cpp#L484-L493)。

#### F03 在当前源码里仍将未知或同实例终态误当作被接管

`native_player.py:708–712` 连续调用两个读取 ownership/observed 的函数。任意一次得到 false，就设置 superseded 并直接返回，跳过后面的 3 秒 terminal reconciliation。

当前读取函数又把 IPC 暂时不可用、observed 为空等情况都折成 false。真实终态记录可能已经保存、observed 同时清空，不能据此认定另一个实例接管。

本次原方法控制流复现了两种情况：

- 短暂读取失败、下一次读已恢复，monitor 仍直接进入 superseded。
- 第一次快照 ACTIVE，第二次已是同 request/native instance 的 NATURAL_EOF 且 observed=None，仍进入 superseded。

两种情况都没有执行 terminal wait 或 queue next，并置取消事件。夹具使用 AST 提取的原完整方法，属于控制流复现，不等于 Kodi 实机验证。

所需验收：一次新鲜快照分类 ACTIVE / TERMINAL / SUPERSEDED / UNKNOWN；UNKNOWN 不授予控制权，也不直接认定为换主；利用原有预算重观察，不叠加超时；同实例自然 EOF 进入精确同版交接，真实新实例接管时旧 owner 不再控制播放器。

来源：[monitor](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/native_player.py#L653-L760)。

### D02：本提交的 CI 已实际失败

工作流：Verify private sources，run `39525777378`，job `118979948586`。  
触发类型：push；受测 SHA 就是 b20e972。北京时间 2026-10-21 09:10–09:12。

| 检查 | 本次真实 CI |
|---|---|
| 主测试套 | 1741 通过、5 失败、5 跳过、1 warning |
| 继承 Kodi 测试 | 761 通过 |
| 准备链回归 | 177 通过 |
| 第一次 source-check | 失败：Source inventory changed: plugin.video.bobbi |
| 第二次 source-check | 同样失败，未进入有效的产物字节比较 |

5 个跳过是 Linux 上的 Windows inherited-pipe API 测试，不能与报告中 Windows 环境的 6 个 symlink 跳过混为一谈。

主套失败集中在清理后的文件策略未贯穿构建和测试：

| 失败测试 | 原因 |
|---|---|
| test_preview_is_reproducible_and_dependency_closed | preview 清单仍包含已不存在的文件 |
| test_fonts_are_unchanged_and_licensed_in_project_assets | 读取已删除的字体许可文档 |
| test_public_inventory_is_exact | source-inventory 与文件成员不一致 |
| test_actual_private_skin_restores_exact_fonts_but_not_legacy_scripts | 仍要求已删除的图标许可文档 |
| test_checked_in_notices_and_truthful_unresolved_status | 仍读取已删除的 licenses/THIRD-PARTY.json |

路径核对还确认：显式清单在 **20 个组件**中留下 **45 个不存在的路径**；plugin.video.bobbi 一项即有 11 个。这是路径成员核对，不声称独立重算了全库所有文件摘要。

因此，不能把报告的 1764/782/177 或清理前“两次构建字节一致”写成当前源码通过。报告已承认两者边界；现在需要把后续自动触发并失败的 CI 也纳入最终交付状态。

整改不是关闭 inventory 检查、忽略失败或 blanket skip。应按明确的文件策略校准源码清单、preview 清单、构建工具与对应断言，同时保留运行文件、字体/媒体内容、签名和依赖完整性的检查。

来源：[实际 CI](https://github.com/2223M1/bobbi-tv/actions/runs/39525777378)、[build_release 校验点](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/build_release.py#L95-L110)、[工作流](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/.github/workflows/verify.yml)。

### D03：修好清单仍不能构建真实入口

`tools/build_ce_entry.py:40` 无条件从平台组件 ZIP 读取：

```text
script.module.bobbi.platform/LICENSE
```

该文件已从清理后的源码删除，重签过滤器也会排除它。因此，即使 source-check 修好，从清理后组件重新构建入口仍会抛 KeyError。

本次使用原 build、sources/files、SignedBundle 和 RSA 验签实现，构造两组件临时签名夹具；私钥只在内存，未接触维护密钥：

| 夹具 | 签名与组件完整性 | 原入口构建 |
|---|---|---|
| 平台组件不含 LICENSE | 通过 | KeyError |
| 仅补入该文档的阳性对照 | 通过 | 成功 |

阳性对照用于定位依赖，不是要求恢复用户已决定清理的文档。应将入口组装逻辑与文件策略统一，让程序 bootstrap 从同代签名组件取得，并保留验签和摘要检查。

**这不证明已上传的入口不可安装。** 已上传入口来自旧入口重打包，没有执行这个从组件重新生成入口的路径。

来源：[build_ce_entry.py](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/build_ce_entry.py#L25-L50)。

### D04：分支上的证据链接全部断开

本次 Git 树返回 4326 项，truncated=false。报告中 26 个指向 ../review-evidence/... 的相对链接，在当前树中均找不到。

这包括最终测试 XML、双审查结果、恢复回执、UI smoke、电影/动漫播放回执、同版续播、最终设备状态和清理后构建失败日志。

不能据此说“证据不存在”或“证据造假”：报告说明它们被打进 Release 合集，而本次没有成功取得合集。准确问题是**从这个 GitHub 分支的报告无法访问这些证据**。

建议将体积小的脱敏 JSON/XML/关键日志提交到同代证据目录。大附件保留在 Release，但报告必须给真实资产链接及包内路径，并提供索引：

- 测试对象的 commit、tree 和关键源码摘要。
- 安装入口、完整载荷的实际摘要和签名序列。
- 每份回执对应的测试场景、运行对象、结果、已知限制。
- 历史证据与新代次证据的明确标记。

## 四、重签实现中可以认可的部分

新增 package_ce2021_github.py 并非只修改 ZIP 名称或声称“已签名”。代码确实：

1. 检查维护私钥公钥是否等于固定信任根。
2. 验证输入完整包的 manifest 签名。
3. 核对旧入口内嵌载荷与独立完整包相同。
4. 检查组件成员、长度和 SHA-256。
5. 递归清理并比较非排除文件的内容摘要。
6. 将 bootstrap 与内嵌新载荷分开比对。
7. 对新包调用 SignedBundle.check_all。
8. 递归检查 ZIP 完整性，并记录 device_deployed=false。

仓库中的 packaging-result 与 GitHub 资产元数据在入口、完整载荷、合集和报告的长度/摘要上相符。上传报告与本轮用户附件也有相同 SHA-256。这是元数据交叉核对，不能替代下载后验证。

四个主要资产摘要如下：

| 资产 | 字节数 | SHA-256 |
|---|---:|---|
| 完整载荷 | 96,135,572 | c0ebea710ef3dda667c4336aa42b4b212469399468f6081f60d806e8171ca696 |
| Kodi 入口 | 96,233,587 | bf10e21a30f98a74c99671985600a79da692371733f5ca17a21179565a72cb6b |
| 交付合集 | 199,794,948 | 4188691ab12040ac0f1e33bcba6761c6a02fc5bc6c00932f23991192988da708 |
| 交付报告 | 16,320 | a21661ec171c39300b182a1521e65ce0532db38a023d63ce1dcc91a8022f8722 |

组件版本不变也**不等于升级必然失败**。现有 CE 安装器以签名 sequence 与 high_watermark 判断代次；2026102021→2026102022 满足递增条件。实际更新和回退仍须本代验证。

后续可以顺手加固，但不应当冒充本次已经发生的产品故障：

- 目前只检查旧 sequence 小于新 sequence，却将 original_sequence 写死为 2026102021；应核对实际输入代次与摘要。
- 过滤器和比较器使用同一排除规则；宜输出明确的删除路径及原摘要，用可审查清单证明只删目标文档。
- 合集的新 MANIFEST ZIP 条目未固定时间，不能保证最外层合集逐字节可重现；报告也没有声称这一点。
- 先写部分资产再完成全部检查，后段失败可能留下半成品目录；宜在临时目录验证后一次完成交付。

来源：[重签工具](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/package_ce2021_github.py)、[打包结果](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/review-evidence/ce2021-clean-packaging-result.json)、[CE 安装器](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_installer.py)。

## 五、原实机报告应该怎样理解

下表是对交付报告所述证据范围的评价；本次没有独立读取这些原始实机附件或重做设备测试。

| 报告场景 | 报告支持的进展 | 仍不能算通过的内容 |
|---|---|---|
| CE2021 连续三次停用/恢复 | 为协作退出与受管恢复提供重复实机观察 | 清理重签包本身的安装/升级/回退 |
| 真实选源窗口追加来源及画质 | 支持所测路径的源 key、位置、筛选保持 | 全屏任意区域和任意时序永不闪动 |
| 天使爱美丽 | 从选源到 AV 约14.19秒；有限窗口正进度；法语、chi字幕启用；后段无观测丢帧 | 全片稳定、字幕内容与同步、主观音画验收 |
| 元气囝仔 诸神 BT | metadata_timeout 明确、返回选源；没有擅自换源 | 该资源成功起播，或 BT 问题已解决 |
| 乒乓 Vodes 115 | 约4.62秒观察到AV；有限窗口1080p、日语、进度正常 | 中文字幕仍未通过 |
| 乒乓尾段同版续播 | 98.8%起播后自然 EOF，精确交接同版下一集 | 整集连续观看、中文匹配、所有动漫续播 |

尤其应保留“视频起播通过，中文字幕失败”这种分项结果。字幕字段启用、文件名带中文标签、找到英文字幕，都不能替代用户实际需要的中文字幕。

《十二怒汉》分享取消，以及《罗生门》《四叠半》《玲音》《这个男人来自地球》旧失败，不能被新作品的成功清零。失效资源未必能由播放器修复；产品需要正确识别并允许用户重新手选。

已撤回的 G02 满额焦点推断不重新立项。G03 旧 seeders/peers 清空属于报告中的条件性加固，不能描述为已证明的日常故障。

## 六、后续规划

### 阶段一：找回并提交已测源码

目标是让下一位执行者拿到正确版本。

先定位原 CE2021 完整工作区、交付补丁和原包，保留其原始摘要。把已测产品修复、新增测试、必要构建调整完整恢复到独立候选分支。历史已重写，应用旧补丁前必须核对真实基线及冲突；不能盲目覆盖。

若只剩安装包，可从包中恢复运行文件供比对，但这不自动恢复原始测试、清单或构建输入。应明确记录缺失与重建部分。

完成条件：从新的冻结提交能直接读到 F01/F02/F03/G01 的实际实现和测试；四个关键组件版本与实际代码代次相符；源码与已测包内运行文件可解释地对应。

### 阶段二：修通完整构建链

统一 source-inventory、preview-inputs、实际文件策略、对应测试和 build_ce_entry。不要只运行 --refresh-inventory 后宣布完成；必须审查变化是否超出既定范围。

在干净检出上运行主套、继承套、准备套和既有问题契约。相同输入执行两次 source-check 并比较产物。随后验证真实签名载荷及 Kodi 入口构建；source-check 不可安装，不能替代真实入口。

若存在 Draft PR，分别记录 branch head 和实际 PR merge tree 的 CI，不能拿旧 PR 的绿灯作新源码证明。平台特定跳过应逐项记录，不为“零跳过”强造设备环境。

### 阶段三：从同一冻结源码交付一个新代次

采用大于已有签名代次和设备 high_watermark 的新 sequence，继续使用既有维护信任根，不复用旧序列覆盖不同内容。实际修改的组件版本按现有策略更新。

交付要绑定：

**源码 commit/tree → 显式清单 → 组件文件摘要 → 签名载荷 → 真实入口 bootstrap/内嵌载荷 → 测试回执。**

维护密钥仅在原维护环境使用，不放进仓库、日志或测试夹具。新入口从同一签名代次生成，避免源码和 bootstrap 再次分叉。

补齐小型脱敏证据及索引。重签归档与真正从源码重建应分开标记，原历史产物保持身份，不覆盖或重命名伪装成新构建。

### 阶段四：同一代包的 AM6B 验收

先只读确认盒子当前序列、播放状态、profile 和可回退对象，再按已授权维护流程操作。此次审查没有执行该阶段。

优先完成：

- 从正常 Kodi ZIP 入口安装或维护升级，确认同代宿主 ready。
- 空闲状态的多次受管停用/恢复；音频播放和未知状态下拒绝维护。
- 慢任务、关闭异常、重复 close 的退场行为；程序替换之前 lease 必须反映真实退出。
- 更新失败/启动失败后的恢复菜单，以及回退到已核验前代；保留账号和观看历史。
- 非首卡、非默认画质的增量列表焦点；人工退出、外部接管、自然 EOF 的分支。
- 同 request/native instance 的正常 EOF 后精确同版交接，且旧实例不能干扰新播放。

通用 CE 的未知机型可以继续内测；第二台盒子、第二个真实账号、全新用户认证不是这台个人 AM6B 继续验收的新增门槛。没有做过的范围如实记录即可。

### 阶段五：针对剩余观看问题做有限的定位

**BT：**将 provider 检索超时、磁力/种子元数据、文件选择、首字节、缓冲、进入 AV 分开计时。记录 request、资源身份、阶段错误及取消结果。先判断《元气囝仔》是资源活性、上游失败还是客户端问题，再针对具体阶段修复，不加大全局超时或自动换版本掩盖问题。

**中文字幕：**对用户所选同版资源分别核查内嵌语言、分享同目录字幕和外部字幕匹配，记录实际结果与失败原因。保留手动 Off、账号切换和请求替换的保护。没有找到中文就如实提示，让用户手选。

**观看稳定性：**选一部电影、一集动漫，从首页正常检索、手选并播放，记录原声、实际中文字幕、进度和缓冲。建议将有效连续观察增加到约10–15分钟，再做一次正常结束或严格同版交接；这是下一轮有针对性的验收建议，不把短测冒充全片认证。HDR、直通、字幕同步和主观体验保留给真实观看确认。

## 七、下一轮交付的最小要求

1. 一个明确的最终 commit/tree，含完整修复及测试。
2. 当前提交主套/继承套/准备套和必要回归的原始回执。
3. 两次相同输入的 source-check 结果及字节比较。
4. 从该源码生成的真实签名完整包与 Kodi 入口。
5. 源码、组件、bootstrap 和包内载荷的摘要映射。
6. 同代安装/更新/恢复/回退结果；未做的项明确标记。
7. 电影/动漫观看矩阵，分别列视频、原声、中文、续播与长时观察。
8. 可访问的证据索引；历史证据不会被记为新包实测。

下一轮最有价值的成果，是一份能够从源码重建、能够说明包内到底是哪份程序、并能用同代证据验收的候选。新 UI、原始音视频、中文字幕目标、手动选源和严格同版续播继续保留；固件、SYSTEM/eMMC、CD2、挂载、Yatse 和既有代理不属于本轮整改范围。

## 附件使用说明

执行包内包含：

- 02-CODEX-NEXT-TASK.md：可直接交给 Codex 的完整任务文本。
- 03-ACCEPTANCE-MATRIX.md：按优先级排列的验收条件。
- evidence：本次固定对象、CI 摘录、路径差异、断链清单和本地复现结果。
- probes：三个只读诊断脚本；读取指定本地源码树，不含产品源码、设备控制或维护密钥。

探针针对冻结旧源码定位问题，**不是可以直接塞进新版本 CI 的通用验收套**。退出 1 表示观察到目标问题；退出 2 表示环境/接口不适配；退出 0 仅表示限定探针未复现。后续实现接口变化时应迁移行为断言，不能把运行错误或无覆盖误计为修复通过。

