# CE2041 新作品命名阻断独立审查

范围：只读源码、已保存的实机回执与原始日志；未修改产品、未操作设备、未访问云端。
修复由 root 实现，本报告仅记录独立复现与复审。CE2041 部分保留
2026-10-22 07:29 +08:00 历史快照；后续 CE2042 补证单列，不覆盖历史失败。

## 天国大魔境：选集回退后 60 秒自动关闭

请求 `66b5f52cdd2c40c7bb13f8705c62268c`，TMDb 208891 S1E1，实际选择的卡片为：

`[Flugel] Heavenly Delusion S01 (BD Remux 1080p AVC FLAC) [Multi Audio] | Tengoku Daimakyou`

`ce2041-heavenly-delusion-flugel-raw2/kodi.log` 的实际关联：

- 07:18:19.973，producer 有 hash binding、目录上下文可用、16 个目录别名。
- 07:18:20.250，PLAY_ISSUED；此事件不等于视频解码或 AV 已开始。
- 07:18:24.440，加载 DialogSelect.xml。
- 07:19:24.745，TORRENT_CANCELLED；metadata 2788 ms/5 polls，selector 60629 ms，
  总计 63846 ms，没有 buffering 阶段。
- 最后 inspect 回到源列表，cancelled=true/failure=cancelled。Root 未手动取消。

源码链与上述时序一致：自动 select_file 得到 target_unresolved 后，Resolver 调用
manual_candidates/Owner.choose_file；选择框使用 FILE_CHOICE_SECONDS=60 的 autoclose；
无选择返回 -1/None，Resolver 记录 TORRENT_CANCELLED。因此该终态不能解读为用户取消，
也不是无 seed、预载超时或播放器解码失败。

独立确定的一个充分阻断是实际卡片中的 `Remux`：episode_scope 复用的技术词集合此前
不认识 Remux/BDRemux。即便提供两种完整作品别名，实际 release_scope 仍为 unknown；
只移除 Remux token 就变为 matched。真实 producer → select_file 的最小复现同样报
TORRENT_EPISODE_FILE_IDENTITY_UNRESOLVED/filename_identity，手动候选仍存在。

反例文件 `test_independent_ce2041_flugel_scope.py`；修前回执
`independent-ce2041-flugel-scope-before-v1.xml` 为 2 fail/2 pass。该反例使用实际卡片标题，
但使用干净的合成文件名来隔离 release 语法，绝不把它冒充真实 torrent 文件目录。
Root 随后的 `ce2041-existing-torrent-metadata1.json` 对该已取消 hash 的 get 被拒，
因此在该 CE2041 快照时尚未排除真实目录中存在第二个独立命名阻断。
此项取证缺口现由下述 CE2042 真实目录正控补齐，原失败证据保留。

Root 修复仅将完整技术 token remux/bdremux 加入闭合词法；未知语义、跨季、错误年份、
OVA 和 RemuxUnknown 仍拒绝。独审通过哈希：
`4966FC9571A997836BF7D042563ABF6747777376F8BCA56A3634D28C3EE371A9`。

## 夜行者：已播放不等于准备身份通过

请求 `3ff91092921743339568c5a2806ce091` 的实际准备诊断
`ce2041-nightcrawler-preparation-diagnose1.json` 显示：账号、provider、4 文件 metadata、
catalog 均成功，verified_intents → prove_work → release_title 第 68 行抛 ValueError；
账本尚无该任务。普通播放已 AV 的事实不能替代这项失败。

实际 basename 含：

`Nightcrawler (2014) {imdb-tt2872718} 2160p Bluray Remux h265 DV HDR10 Atmos 7.1.mkv`

电影原词法已支持 Remux、Atmos 和括号年份；实际阻断是年份之后的 IMDb 标签被归一化为
未知 token `imdb` / `tt2872718`。这不是 BT 供数、CD2、选错文件索引或资源仍在下载。

独立测试从 CE2041 已签名完整包加载原 catalog_identity 模块，在回执中的真实四文件
metadata、media、selected tuple 上重现相同异常。新代码仅复用已获取的 same-ID TMDb
details.imdb_id，不增加请求；prove_work 仅消费与其完全一致的规范 basename 标签。
原 title/year 校验继续执行，原文件路径、ID、大小和版本派生输入不改。

`test_independent_ce2041_nightcrawler_preparation.py` 明确区分：真实回执字段来自 root；
期望 IMDb ID 和 response digest 是本地 catalogue fixture，不冒充新网络取证。它验证
新 verified_intents 保留真实 exact tuple，并拒绝缺失/冲突 ID、错误年/名、未知标签和
附加语义。独审通过哈希：
`AD120CB6FA78987D336EEA10C374BA0C8AECD4468142A4AC4048BF2D33A9A2BD`。

两项相关作者与独立测试合计 121 passed，回执
`independent-ce2041-real-naming-after-v1.xml`。另 1 项明确排除的是保留在原反例文件中的
“旧行为仍拒绝”见证断言；原 2 fail/2 pass 证据未删除或改写。

## 交付结论

CE2041 历史结论：两项本地修复当时可进入下一冻结候选，但尚未在已安装 CE2041
上生效；当时源码/包差异见独立交付边界报告，不能据此描述后续设备当前代次。
Root 后续报告 CE2042 已安装。Flugel 的真实目录选择与普通准备接受现已有下述正控；
Nightcrawler 修复后的正常新请求准备发布仍不在本次新证据内，不能手工改账本复活旧
failed request。Root 已精确停止该次 Nightcrawler；首张截图无字幕帧，不能称字幕
视觉验收通过。

## CE2042 补证：真实 13 文件目录及普通准备正控

新增只读来源：`ce2042-heavenly-existing-metadata1.json` 与
`ce2042-heavenly-preparation1.json`。前者模式为
`existing_torrent_metadata_no_add_or_preload`，Flugel hash 为
`edc729b678556a6bdc09660a15bc45c9177605ae`，包含 13 个唯一真实文件 ID 1～13。
其中 E1～E3 的精确目录前缀为：

`Heavenly.Delusion.S01.1080p.BluRay.Remux.AVC.FLAC.2.0-Flugel/`

| 集数 / ID | basename | 字节数 |
| --- | --- | ---: |
| E1 / 1 | Heavenly.Delusion.S01E01.1080p.BluRay.Remux.AVC.FLAC.2.0-Flugel.mkv | 6436462259 |
| E2 / 2 | Heavenly.Delusion.S01E02.1080p.BluRay.Remux.AVC.FLAC.2.0-Flugel.mkv | 6107001741 |
| E3 / 3 | Heavenly.Delusion.S01E03.1080p.BluRay.Remux.AVC.FLAC.2.0-Flugel.mkv | 7197656493 |

外部独立正控 `test_independent_ce2042_flugel_real_metadata.py` 用保存的完整 13 文件
metadata 重放当前真实 producer → select_file：E1、E2、E3 均精确匹配上述 tuple，
未改写真实目录或消去 Remux。另将 E1 作为当前目标运行 verified_intents，结果严格是
E1 current、E2 next、E3 next；三者实际 tuple 保持原样，版本均为
`85194383e94394791ef7dc8b2a865bc43177d3c6c0da5269e9dbd80382975d8a`，与实机准备回执一致。
Catalogue details/aliases/response digest、测试账号和目的目录明确是本地 fixture，
不冒充新的网络取证。回执 `independent-ce2042-flugel-real-metadata-v1.xml`：5 passed。
这些本地正控不是设备认证。

实际普通请求 `404628222c014400a772c13066c6681d` 的准备状态为 accepted；E1～E3
均归属单个任务 `e1e483341ded409abf440804ffd96ae9` 和上述同版本。
source_proof 为 present=true、next_present=true，anchor 为 E1。
实际 audit 有 requested、submit_intent、submitted、observed；ledger 此时为
mapping、targets=3、bindings=0，qualified_targets 为空。投影内各 target 的 queued
状态与 ledger mapping 是不同层级，不能把它们合并描述为 ready。

因此这批回执证明真实目录无本次本地重放可见的第二个命名阻断，且新代普通准备入口
已接受当前集和后两集并提交一个实际云任务；它本身不证明云端 ready、云文件可播、
AV 已开始、持续 BT 供数或中途 BT→115 接力成功。元数据中 1,390,643 B/s、14 seeders
只是采样瞬间；同文件的 Nightcrawler get 被拒也不属于 Flugel 成功证据。
Root 的后续实际观察须以另行回执验收，不从本补证推定。

### 后续准备回执单列

`ce2042-heavenly-preparation2.json` 后续显示同一个任务为 ready、targets=3、bindings=3，
E1～E3 qualified 均 ready；E1/E2 为 ffprobe/bounded_demux，E3 为
matroska_container_header/prefix_to_first_cluster，均无 media_profile。该状态不覆盖
preparation1 的历史 mapping 快照，也仍不等于中途接力成功。实际随后自然缓存触发的
capture 返回 UNSUPPORTED，独立定位为 8bb2 漏编 JSONRPC.cpp 导致二进制 RPC schema
仍旧；完整证据见 `independent-ce2042-native-schema-review-20261022.md`，不是本次真实
目录选集/准备身份失败。
