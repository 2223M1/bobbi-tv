# CE2021 播放与 UI 后续执行指导

供 Codex 与人工复核共同使用。固定起点：`b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2`。先阅读同目录分报告和 `SOURCE-PROVENANCE.json`。

## 任务 0：恢复真实修复源码与证据关系

**目标：取得能对应已测 CE2021 代码的候选实现，然后决定需要修什么。** 当前 Git 分支仍是旧播放/UI 实现。不可仅用报告中的成功数量关闭旧问题。

执行：

1. 从作者保留的原 CE2021 交付合集取得工作区 patch、修复源码、原始测试、适配 diff、设备回执与安装包；原件只读保留，记录 SHA-256。若无法取得，明确记录阻塞，不能自行编造“恢复成功”。
2. 在隔离分支恢复修复代码，处理与当前基线的真实冲突。产出固定 commit/tree；不要把本次打包脚本的文档清理结果当作产品修复来源。
3. 展开签名 manifest 与组件，确认相同执行入口及运行时文件的身份。逐文件列出 Git 候选与已测原包、重签包的相同项和差异项。版本号相同、外层 ZIP 哈希不同都不能单独证明代码相同或不同。
4. 每份测试与实机结果登记 `producer_commit/tree`、包 SHA/签名 sequence、工具 SHA、UTC 时间、attempt 和适配摘要。恢复后实际重跑的结果与历史结果分开保存。

完成条件：任何一项“修复已通过”都能追溯到可取得源码及准确测试对象；缺失证据被显式标成未验证。首先审已有修复的正确性，再决定补写代码，避免在旧实现上重复返工。

## 任务 1：F02 列表及画质焦点

必要契约：结构变化仍保留已存在的 ListItem；按稳定 source key/quality key 恢复选择。将 bind 与选择按正确顺序排入真实控制队列；不能依据 bind 未派发时读到的旧 index 判断是否需要补偿。纯字段更新不重绑、不 reset、不抢焦点。

验收矩阵：

| 场景 | 必须观察的结果 |
| --- | --- |
| 非首卡已选，追加来源，bind 延迟派发 | 派发完成后 source key 与原选择一致；现有对象身份不变；一次必要的补偿 |
| 同场景，bind 在读取前已派发 | 同样保持 source key；不会重复补偿或产生反向跳动 |
| 1080p 标签已选，新增 4K 标签 | 可见选中项和生效筛选均保持 1080p |
| 只有来源状态/完成标记变化 | 不重绑，不额外选择，不改变滚动或焦点 |
| 首卡、显式用户切换、原选项确实消失 | 对照行为明确；消失时采用预先定义的有效回退，不把已不存在的卡复活 |

实机 smoke 要记录 queue/dispatch、source key、quality key、选中 index、筛选结果和控件变更计数。截图可补充视觉事实，但首卡的一个 ROI 不能证明其他卡或画质焦点正确。

G03 若实施，仅添加保留 ListItem 上 seeders/peers 的明确写值/清空，并用有条件的对象更新场景验证。保持“条件性加固”的说明，除非另有真实产品路径证据，不把它升级为已发生日常故障。

## 任务 2：F03 读取不确定性与自然终态

一次新鲜权威 snapshot 应完成本轮分类，明确区分 `ACTIVE`、匹配的 `TERMINAL`、确有证据的 `SUPERSEDED` 与 `UNKNOWN`。未知状态不能赋予新控制权，也不能直接伪装成旧请求已撤销。

保留原定有界观察预算；报告声称的 3 秒不得在 helper、重试、terminal reconciliation 之间层层叠加。明确 request/instance/file 身份匹配规则。人工取消、明确替换后不可复活旧任务、触发下一集或清理新 owner UI。

必要反例：

- 短暂读失败后恢复，原 request/instance 仍有效：保留监控，不能误标 superseded。
- 同实例 EOF 恰好发生在播放器检查和 snapshot 之间：匹配终态进入一次对账及必要的同版交接。
- snapshot 超过预算仍未知：有界结束或降级，不无限等待，不执行有副作用的成功路径。
- 明确新请求、明确取消：旧监控退出，不写新实例状态。
- 其他 request/instance 的旧 EOF、重复 EOF、迟到回执：不能触发当前会话续播。

旧脚本摘取实际产品方法，可定位旧缺陷；真正关闭本项还需在完整 native owner-loop 及真实 request adapter 组合上运行，保留慢 IO、异常和终态竞态。若内部边界确已变化，可以迁移注入位置，但在 diff 中解释新旧边界与行为断言对应关系；不可把失败断言改成“允许退出”来获得通过。

## 任务 3：《元气囝仔》BT metadata_timeout

当前报告给出的失败发生在 BT metadata 阶段，尚未到播放器。已有 resolver 在 `metadata_files(info)` 可用后才进入文件选择，再进入 preload；默认 metadata 预算为 30 秒，超时产出 `TORRENT_METADATA_TIMEOUT / metadata_timeout`。对应有界 poll 诊断测试已存在。[resolver](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/resolver.py)、[现有测试](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tests/test_bobbi_torrent_adapter.py)

执行顺序：

1. 固定 TMDb 67048 / S1E1、原诸神 1080p BT 版本的 provider、release identity、infohash/资源标识摘要；不依赖展示标题猜测是否同源。
2. 为一个明确 attempt 捕获 `request_id`、各阶段起止/elapsed、backend 健康状态及版本、add 确认、metadata poll 次数、文件数量、可用的 peer/传输摘要、结束原因与取消回执。敏感 URL、Cookie、令牌不进入公开日志。
3. 用同一 backend 对一个已知能取得 metadata 的 BT 来源作有限对照，再重查原失败来源。区分 backend/连接问题、特定资源 metadata 不可得，以及引擎状态解释错误。换一个来源成功只能证明对照来源可用。
4. 检索阶段的两个 provider 失败/超时与所选 torrent 的 metadata 超时分开记账；不要把部分搜索结果存在当作选中资源已就绪。
5. 若确有 resolver 缺陷，修最小责任边界；若上游本身无 metadata，提供真实可理解的失败状态、保留返回选源与用户再次选择能力。

验收：原始失败保留；对同一原资源的成功必须有 metadata 文件表、严格集数选择证明、最终目标及 AV 样本。无法取得 metadata 时，按既有预算结束，不重复 add、不无限等待；取消后旧 attempt 不继续产生文件选择或播放副作用。禁止为掩盖失败而加大全局 timeout/retry、自动降画质或替换不同版本。

## 任务 4：《乒乓》中文缺失

固定 TMDb 60811 / S1E1、115 Vodes 1080p HEVC 与其确切文件。原声日语播放通过与中文字幕未通过分开处理。

产品已有 `NO_QUALIFIED_CHINESE_SUBTITLE`、`SUBTITLE_PROVIDER_AUTH_REQUIRED`、`SUBTITLE_PROVIDER_RATE_LIMITED`、`SUBTITLE_LOOKUP_TIMEOUT`、候选不可用、身份拒绝、文本拒绝、时间轴拒绝及 `MANUAL_PRESERVED` 等状态。优先利用既有状态解释失败，不先发明一套平行分类。[来源：subtitle status 投影](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/services/playback_control.py)

建立一个逐级 funnel：实际内嵌轨道 → 查询发出与鉴权/限流/超时 → 返回候选数 → 中文文本/语言验证 → 作品、集数、版本身份 → 时间轴 → 绑定/加载 → Kodi 实际当前字幕轨。每一级记录数量及拒绝原因，而非只保存一个“未找到”字符串。

合格中文若客观不存在，正确结果仍是“无合格中文”；不能把英语轨、文件名“中字”、已下载但未绑定文件、错误集数或偏移字幕算作成功。若存在匹配候选却被错误过滤，添加针对原因的最小修复和反例。

验收：正确文件上存在并启用匹配的中文字幕，至少有字幕出现、可读中文、多个位置同步观察；同时原音轨与原码流保持。人工切换字幕或选择 Off 后，迟到自动结果不能覆盖；新 request/instance/账号变化不得继承前一次绑定权限。若未达到，独立列出中文字幕未通过，视频通过仍保留。

## 任务 5：首播和严格同版续播

一次播放旅程分别记录六项：从用户选源到首次 AV、稳定视频推进、原声轨、中文字幕、自然终态、准确后继。每项可独立通过或失败；禁止用整体 passed 掩盖字幕或版本不符。

首播回执至少包含：用户选择的稳定 source key、作品/集数、目标文件身份、请求时间、后端阶段时间、首次 AV 时间、sample 时间与播放进度、实际宽高/codec/audio、当前 subtitle 状态。进入播放前必须验证上一窗口和请求确已退出；失败导航保留为单独 attempt。

续播必须按有序证据证明：

1. 父 request 与 native instance 对应正确第一集及原文件。
2. 自然 EOF 来自该父实例；测试注入、显式 stop 或全局 seek 不冒充完整观看。
3. SAME_VERSION_HANDOFF 消费正确父终态一次。
4. 子请求是准确下一集，且 provider/release/version/family/file proof 满足原严格规则；出现新 request 与 native instance。
5. 子实例实际见 AV 并产生正进度；停止操作作用于该后继实例。

当新实例已经淘汰旧 terminal 时，完整有序日志可以是合理证据；仅有当前快照不足。日志必须含可关联父/子 request、instance、文件身份、事件顺序和时间，且没有中间冲突或重复消费。`AUTO_VERIFIED_FILE` 标签本身不能替代文件证明。

StartPercent 98.8 的尾段回归可验证边界，不得统计成整集观看。需要全片/整集连续观看时另设明确验收，不为获取绿灯重定义原结论。

## 复验命令与输出约定

在已安装项目声明测试依赖的环境中，对隔离 checkout 运行两份反例。以下只读取产品源码并输出本地结果；它们不操作设备：

```bash
python -B checks/reproduce_native_list_focus.py --repo /absolute/path/to/candidate --output ui-result.json
python -B checks/reproduce_native_monitor.py --repo /absolute/path/to/candidate --output native-result.json
```

固定旧 head 的预期现状为两组各 3/5 通过、2/5 失败、0 errors。修复后的真实接口若需要适配，保留原脚本、适配副本、diff、变更理由及适配前结果，不覆盖旧证据。真实设备执行需要独立明确授权；本包未执行任何设备命令。

最低交付文件：源码 commit/tree 与包内文件映射；原始/适配测试及 diff；所有实际命令、退出码和原始 JSON/XML；每个作品 attempt 的逐阶段回执；限定窗口与未完成项清单。`transport_ok`、`trial_passed`、`exit_code`、`pending` 分列，未知和失败均不能计为成功。

所有任务继续保持：新 UI、原画和原码流、原声优先、手动选源、手动字幕 Off、严格同版续播、通用 CoreELEC。设备型号只作为测试环境事实记录；没有证据时不建立机型白名单、专机前提或新的硬件准入门槛。
