# CE2024 播放、UI 与字幕域独立审查

## 结论

固定审查对象为 `c4e0baca6acefa58f031979bff71e7cd1028efdf`，tree 为 `bb4256d63465fefb9c5820f3ce1ec9cca33ff546`；产品提交为 `d2fffa570fe59b90cd1d33499efcf7c6684b2647`。本报告中的源码、测试与回执全部按该固定 tree 校验，不把工作区不完整、作者自述或新分支的名字作为已验证结果。

**旧 F02 和 F03 在本次审查所对应的代码缺陷层面可以关闭；新字幕季集放宽存在一个已复现的 P2 问题，应在下一轮交付修复。** 同时，真实影片的整片表现、原音与中文字幕体验仍不能宣布完成。

独立旧反例：F02 原脚本原样重放 **5/5 通过**；F03 维持原断言、仅适配新 IPC 调用边界后 **5/5 通过**。仓库定向测试最终 **59 个唯一用例全部通过**。新增字幕独立矩阵 **20 项中 14 项通过、6 项错误放行**；这 6 项在 CE2021 基线均被拒绝。

## 审查范围与限制

- 实际读取当前 SourceSelect、native monitor、PlaybackOwner/PlaybackAuthority、字幕候选与缓存 scope、fallback、playback_control 与 share_stream 的相关路径。14 个重点源码文件的 Git blob 和 SHA-256 在 `results/validation-summary.json`。
- 运行了实际产品函数和仓库测试。独立脚本仅替换 Kodi、IPC 时钟/传输或字幕 provider I/O；没有修改产品实现，没有运行设备命令。
- 12 份作者设备回执均另行从固定 head 取回并校验 Git blob。解析结果在 `results/receipt-audit.json`。它们是**独立核读的作者设备证据**，不是审查者重做的实机认证。
- UI 截图文件未重新取得/逐像素查看；只核读其 JSON 与原脚本的队列模型。没有新做自然整集 EOF、下一集交接、电视升级、登录、4K 整片或字幕前中后同步试验。
- share_stream 关闭与 producer 存活问题由生命周期分报告负责；本报告的 59 项通过不覆盖慢响应头下的所有线程关闭顺序。

## 新发现 PB-01：明确其他季/特别篇的弱集号字幕被当作 S1E1 候选

**严重程度：P2。状态：候选发布层已复现，自动应用路径静态可达；没有声称设备已经加载错误字幕。**

### 触发条件

当前作品具有有效的 `SingleSeason` 证据，目标为 S1E1，文件用新支持的 `EP01` 或 `第01話` 标记。provider 包名包含当前作品标题，但文件还明确写着 `第2季`、`第二季`、`2nd Season` 或 `OVA`、`Specials`、`番外篇`。

复现所用 TMDb 风格记录与文件名都是合成夹具，不代表公开 provider 已实际返回这些错误文件。记录同时含 specials（S0）和唯一正规季（S1），可以通过现有 `from_details`；这也是仓库新增正控允许的记录形状。

### 原因与位置

[`subtitle_episode.py` 19–25](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/subtitle_episode.py#L19-L25) 在建立单季证据时排除 S0；[34–48](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/subtitle_episode.py#L34-L48) 只验证授权与弱集号，没有否决文件中的其他季/特别篇声明。上游 [`subtitle_candidates.rank` 122–137](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/subtitle_candidates.py#L122-L137) 的季号提取仅覆盖 `Snn` 与 `Season nn`，所以这些明确冲突不会进入现有拒绝分支。

实际调用链是 `rank` → `AssrtCandidates.candidates` → `remote_candidates` → `inspect_text` → `publish`。6 个错误文件都通过真实中文 SRT 正文检查并被写成不可变候选，返回 `state=candidate`，不是只做正则表达式单测。

后续 [`SubtitleFallback._run` 171–175](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/plugin.video.bobbi/lib/services/subtitle_fallback.py#L171-L175) 不再复核季集；[`KodiNative.external_subtitle` 228–238](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/plugin.video.bobbi/lib/services/playback_control.py#L228-L238) 在 prepared 未 ready 时使用 fallback。若无可用内嵌中文、当前 owner/instance 与手动意图未改变，[`PlaybackAuthority._auto_external_subtitle` 709–748](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/playback_authority.py#L709-L748) 接受 `candidate` 并可提交 `subtitle_file`；这些后续检查保护播放身份、文件导出和用户意图，没有补上语义季集判断。排序只涉及双语、release、简体和介质，也不会修复误匹配。

### 完整 20 项独立矩阵

下表文件名省略共同前缀 `Ping Pong The Animation` 与后缀 `.chs.srt`。两版本使用相同 provider/正文夹具；旧版不认识新 scope，因此新增能力的正控被拒绝是基线能力差异，不能算当前版本回归。

| 检查 | 期望 | CE2024 | CE2021 基线 |
|---|---|---|---|
| 单季 `EP01` | 接受 | 接受 | 拒绝 |
| 单季 `第01話` | 接受 | 接受 | 拒绝 |
| `EP02` 错集 | 拒绝 | 拒绝 | 拒绝 |
| `S02E01` 错季 | 拒绝 | 拒绝 | 拒绝 |
| `EP01-EP02` 范围 | 拒绝 | 拒绝 | 拒绝 |
| `第01話-第02話` 范围 | 拒绝 | 拒绝 | 拒绝 |
| `OVA EP01` | 拒绝 | **错误接受** | 拒绝 |
| `Specials EP01` | 拒绝 | **错误接受** | 拒绝 |
| `番外篇 第01話` | 拒绝 | **错误接受** | 拒绝 |
| `第2季 EP01` | 拒绝 | **错误接受** | 拒绝 |
| `第二季 第01話` | 拒绝 | **错误接受** | 拒绝 |
| `2nd Season EP01` | 拒绝 | **错误接受** | 拒绝 |
| `EP01` 无 scope | 拒绝 | 拒绝 | 拒绝 |
| `EP01` 与 scope 的 TMDb 不同 | 拒绝 | 拒绝 | 拒绝 |
| `EP12` 超出已证实 11 集 | 拒绝 | 拒绝 | 拒绝 |
| 明确 S02 包、S2 目标、文件 `EP01` | 接受 | 接受 | 拒绝 |
| S02 包、S1 目标、文件 `EP01` | 拒绝 | 拒绝 | 拒绝 |
| 文件没有集号 | 拒绝 | 拒绝 | 拒绝 |
| `S01E01` 无单季例外 | 接受 | 接受 | 接受 |
| `EP01 EP02` 冲突集号 | 拒绝 | 拒绝 | 拒绝 |

原始结果：`results/subtitle-scope-matrix.json`、`results/subtitle-scope-matrix-ce2021-control.json`。每例记录 rank、provider 调用、是否输出候选、实际输出字节数/哈希以及停止原因。

### 修复方向

只收紧字幕弱集号的 scope 推断。统一识别并拒绝明确冲突的自然季标记及 specials/OVA 歧义，再考虑 `SingleSeason` 或包级季号授权；不能让“只有一个正规季”覆盖文件自身的反证。处理标记时应避开作品规范标题本身，避免对合法标题做全局词语黑名单。保留已证实的 `EP01`、`第01話`、`[01]` 与显式包季号正控；不必重写播放器，不应降低视频文件选择或自动续播的身份要求。明确或无法排除冲突的候选可留给手动选择，不能自动应用。

## 旧问题关闭复核

### F02：原生列表绑定导致非首项/画质焦点回零

当前 SourceSelect 在实际增删产生 `LABEL_BIND` 后追加同队列 `selectItem`，而且变更前先捕获稳定 key。源码位置：[画质列表 250–284](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/plugin.video.bobbi/lib/gui/source_select.py#L250-L284)、[片源列表 745 起](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/plugin.video.bobbi/lib/gui/source_select.py#L745)。

上一轮独立脚本未修改重放：非首项晚绑定、增加画质标签、首项正控、提前调度绑定、没有新卡的完成状态共 5 项通过。关键失败例现在观察到队列 `bind → select`，额外 reset 为 0；只有数据元信息/完成态时不新增 bind 或 select。仓库的撤回近邻、用户随后导航、画质标签计数等边界亦通过。

作者实机 JSON 明确标注“真实已安装 UI，合成 QR/card，无登录交换或播放”。5 次到卡保住非首项与 1080p，`resets=0`、补偿 focus 命令 5、74 帧 ROI 稳定。它支持本轮 UI 修复方向，但不证明所有遥控手势、热 UI timeout 或账号真实登录路径已完成。JSON 路径：`review-evidence/bobbi-ui-smoke-1792551057134188800/result.json`。

### F03：暂时读不到 owner / EOF 竞态提前退休监控

[`monitor_state` 206–240](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/addons/script.module.bobbi.core/lib/bobbi_core/playback_request.py#L206-L240) 把 ACTIVE、UNKNOWN、SUPERSEDED、同实例 TERMINAL 分开。当前 monitor 对 UNKNOWN 暂停可变操作并使用绝对等待窗口，明确替换/取消仍立即退休；超时不清理仍可能属于当前播放的全局状态。清理入口额外比较 boot、epoch 和已固定 native instance。

旧独立脚本保持同样的 5 个行为断言：连续当前、三次 IPC 暂时失败后恢复、`isPlayingVideo` 后同实例 EOF、明确 replacement、明确 cancel，全部通过。脚本只作两处接口适配：允许 `timeout` 关键字且断言 `0 < timeout <= 0.3`；EOF 注入从旧两次 owns/matches 读取的第 2 次改为新单次 monitor_state 的第 1 次，**仍位于 isPlayingVideo 检查之后、authority 读取之前**。没有用改变预期、吞异常或增加时间预算获得通过。

仓库定向测试另外覆盖持续 UNKNOWN/畸形快照约 3 秒退出、不清理，boot/epoch/native instance 变化，STOP 与正常 EOF 等。它们是独立重跑的作者断言，不冒充新编写的独立断言。实机整集 EOF 和下一集真实交接本轮未新增，不能由这个代码缺陷关闭推导整条连续播放已认证。

## 真实影片回执复核

| 作品与回执 | 独立核读到的结果 | 能证明的范围与后续缺口 |
|---|---|---|
| 乒乓 attempt 4；select `1792551258994701500`、inspect `1792551289427135300` | 115 1080p；select→首次被观察到 AV 为约 4.688 秒；71 个 AV 样本，最长连续正进度跨度约 34.479 秒。inspect 中 native 外挂 applied=true，SHA-256 为 `0e933dfb680de97b2de666ec4d9fc4c9c5264819349f633f8717d459e5d3aa82`，字幕 enabled=true，音轨 jpn。 | 外挂实际应用与启用有回执，不只是 UI 标签。回执未包含该 SHA 对应字幕正文及完整候选映射；provider detail 只证明文件名/标签存在。不能独立证明内容正确、前中后同步或整片中文可读性。 |
| 布达佩斯 4K REMUX；select `1792551406474811700` | transport=0、trial=1、trace_passed=false；约 11.206 秒观察到 AV；最大观察停滞约 17.477 秒，4 次播放时钟不连续，连续 caching 样本跨度约 10.503 秒。 | 启动异常仍成立。时钟跳变不等同用户 seek；caching 与解码状态只能提供线索，不足以归因。 |
| 同一布达佩斯实例后续 observe `1792551462588057300` | 后续 wall=30.331 秒、play=30.155 秒、`passed=true`。 | 只能说明该较短窗口内时钟大致前进，不能抹掉前一启动失败。额外发现：末尾 decoder 原文 channel 0 的 drop/fra/hw error 均为 8，而 channel 1 为 0；采样扁平计数却全为 0。应由工具审查确认多 decoder channel 的解析/门槛，不能泛称“解码零错误”。 |
| 比宇宙更遥远的地方；select `1792551613815505200`、inspect `1792551658645820500` | 40 秒捕获没有 AV 样本，coverage=not_covered、passed=null；随后 inspect 在约 84.781 秒上界看见 AV。实际音轨 eng/默认 5.1；当前 EnglishFullMegaMTBB 字幕且 enabled=false；UI 是候选未能加载。 | 原音与中文闭环未完成。日志中 metadata=1.552 秒、buffering=46.401 秒、阶段总计 48.496 秒；84.781 是观察上界，不能当 native 精确启动耗时。 |

更远宇宙的 metadata_presence 仅表明当前 `en-US` 缓存条目存在、`zh-CN` 对应条目不存在。**这不等于作品 original_language=英语，也不能单凭缓存键解释为什么原音提示未生效。** 下一步应记录同一 request 的 TMDb 原语值、cache locale/年龄、原音 hint 是否生成/绑定、BT 子进程是否传递、native 最终选轨原因。当前不足以在上述任一环节宣布根因。

乒乓候选 detail 中 LittleBakas 的 `EP01` 与 GTX-Raws 的 `第01話` 确实存在，说明新增支持解决的是实际命名形态。同期日志有另一个候选下载超时，同时保留 `candidate CANDIDATE_NOT_SYNC_PROOF`；不能由其中一次下载失败推断最终没有外挂，也不能反向把加载成功推断为所有候选健康。

Barakamon 的旧 metadata 失败没有被这次新作品替代；CE2024 文档写明其本轮搜索为 0 候选，尚未重到 metadata 阶段。此项文档边界合理。本报告没有重拉 Barakamon 三份原始 JSON，故将其作为文档保留项，不列为本报告的独立设备证明。

## 本域后续执行顺序

1. 修复 PB-01 的字幕弱集号 scope 否决规则，先让独立 20 项矩阵全通过，并保持 2 个真实命名正控。代码范围限制在字幕身份解析及其回归，不扩展到播放器重写。
2. 更远宇宙原音/字幕按同一 request 采集完整证据链，先区分 hint 缺失、传递失败、native 未采用；字幕则区分 cache scope 缺失、provider detail、下载、正文、候选导出、native 提交和确认。失败不换片、不改 release、不自动降质。
3. 布达佩斯保留启动失败作为基线；补足同一实例的分 channel decoder、cache、时钟、HTTP 请求模式与分段耗时后再定原因。30 秒时钟前进不代替启动与整片 gate。
4. 字幕恢复后做前/中/后三段可读与同步，验证手动 Off/切轨不会被后台改回；自然 EOF、取消、STOP、replacement 分开留回执。整片与升级/回滚门槛由主报告统一组织。

## 复跑与证据文件

在审查工作区运行；`--repo` 也可指向已核对固定 SHA 的完整 checkout：

```bash
python ce2024-playback/checks/reproduce_native_list_focus.py --repo ce2024-review --output ce2024-playback/results/native-list-focus.json
python ce2024-playback/checks/reproduce_native_monitor.py --repo ce2024-review --output ce2024-playback/results/native-monitor-original-five.json
python ce2024-playback/checks/reproduce_subtitle_scope.py --repo ce2024-review --output ce2024-playback/results/subtitle-scope-matrix.json
python ce2024-playback/checks/reproduce_subtitle_scope.py --repo ce2021-review --output ce2024-playback/results/subtitle-scope-matrix-ce2021-control.json
python ce2024-playback/checks/audit_receipts.py --workspace . --output ce2024-playback/results/receipt-audit.json
```

定向产品用例：

```bash
cd ce2024-review
python -m pytest -q tests/test_ce2023_subtitle_episodes.py tests/private_baseline/test_ce2023_subtitle_scope.py tests/private_baseline/test_ce2015_list_binding.py tests/private_baseline/test_ce2015_monitor.py tests/private_baseline/test_ce2020_native_stop.py tests/test_share_stream_observations.py
```

初次执行 56 通过，3 项在创建 localhost socket 时被环境 EPERM 阻断；授权的本地 loopback 重跑相关 13 项全部通过，其中 3 项补齐、10 项重复。最终是 59 个唯一产品用例通过，不能把 56+13 写成 69 个独立用例。原始 XML 保留首次环境失败和后次通过，以便复核。独立字幕脚本当前因 6 个已确认反例退出 1，属预期揭露问题；旧版对照因不支持 3 个新增正控也退出 1，两者不能混为同一种失败。
