# CE2035 · 同版 BT / 115 接力工作记录

状态：2026-10-22，**工作中，CE2035 已部署，尚未完成观看验收**。
工作区后续 setup / 起播等改动不等于已部署；不得覆盖本次已签名入口。
本文件不作为“自动卡顿接力、后两集预存、全场景播放已验收”的交付凭据。

## 已保留的实机失败

- 《千钧一发》原 115 FGT 4K REMUX：block 初始整块等待与缓存停进有关；
  旧 progressive 同文件试播仍失败，不能把改模式本身写成修复。
  新 progressive 首个上游 Range 扩大到原有 segment 上限，队列、并发、
  accepted-suffix 重试、EOF/长度校验及 block 默认不变。候选通过本地真实 HTTP
  和独立审查，仍需受控同文件试播。设备已恢复 block、关闭临时 debug。
- 《永生之酒》Moozzi3 S01E01：90 秒仅预载约 3.3 MB / 32.2 MB，2 peers、
  约 38 KB/s，确实供数不足。最后一次 status 跨截止时间又被误归控制请求失败，
  绕过原“继续等待一轮”。修复分类和单次只读重试不等于种子本身能流畅播放。

## 预存失败：已经定位的事实

旧 request `884f21e1df5a4688aa18e728b5814dd2` 先被 CD2 不可达挡住。
唯一现存 Docker CD2 1.0.19 已恢复启动；原镜像、Config、HostConfig、挂载不变，
没有 pull、重建、升级、换号。为何 enabled 的 Docker 最终 inactive 尚无完整因果证据。

恢复后该 request failed / ValueError。独立阶段诊断证明：

- 本代际账号与 CD2 实际账号匹配；该 source 在账本 tasks 中为零。
- 本代际 torrent-file-metadata 缓存不存在。
- TorrServer `/echo` 为 200；同 hash 的 `get` 为 **404**，不是认证错误。
- 尚未执行 Catalog、同版/集数选择器或云任务提交。

原请求不会手工改 journal 复活；修复后由真实重新选择产生新 request。
诊断工具仅重放已知 hash 的目录读取与纯验证；TorrServer get 可能重新激活已保存
种子、接触 peers，因此不是“无网络副作用审计”，但不创建云任务、不存缓存、
不改账本。异常只保留阶段、类名和栈位置，不输出签名 URL、凭据或错误正文。

## 本轮修复边界

1. 在有效账号代际下，先校验实际 BT 文件目录和作品身份、保存已证明的目录，
   再等待 CD2 就绪执行云准备。该阶段只是本地 pending 计划，不能发布 ready。
2. 保留所有 ScopedProvider 实际 UID、账号代际和云 IO 就绪门；错账号不转存，
   注销后的迟到结果不缓存、不入队。恢复时沿用原去重，uncertain 只核对不重送。
3. 来源校验失败明确记录 metadata / catalog / identity / metadata_cache 阶段；
   本地入队失败为 publication。HTTP 404、认证和后台失败有固定分类。
4. 当前集锚点滚动准备 E、E+1、E+2。每个位置独立、严格同版验证，不递归整季。
   同一个打包种子的云端转存仍是同一个去重任务，窗口限制的是准备目标，不声称
   云提供商支持从打包磁力链接只转存三个文件。
5. 下一集云端优先与精确同版 BT 兜底已通过独立本地审查；最终开播前重新看
   云端就绪状态，不让早先缓存的 BT 候选阻止升级为 115。验证 pending 不能
   冒充明确不可用：保留 115 路线，由正常子请求解析再次核验。

## 本地证据（不等于实机通过）

证据根：`D:/AM6B-Project/ce2029-results-20261021`。

- metadata 修前：6 failed；修后 metadata / recovery / Host：28 passed。
- 独立真实 Session / 队列 / worker 组合检查：18 passed，报告
  `independent-ce2035-preparation-metadata-review-20261022.json`。
- 原 HTTP 404：`ce2035-baccano-validation-http.json`。
- 滚动窗口：235 项回归通过；独立报告
  `independent-ce2035-rolling-review-20261022.json`。
- progressive 首 Range：25 项真实 HTTP 回归、58 项相关检查及独立审查通过；
  `independent-ce2035-progressive-initial-candidate-review.json`。

保留全部失败记录，包括测试收集路径错误、恢复测试将 snapshot.titles 误写为
entries 的断言错误。它们修正后重跑，不能删除后当作首轮全过。

## 尚未解决/验收

- 同集自动接力必须保留卡顿处秒级断点、手选音轨、字幕 Off / 外置字幕 / 延迟。
  原 F9 缺少完整实例绑定恢复接口；不能用全局 Seek / SetSubtitle 冒充。
  用户已明确批准原生小型交接接口及实机验证，新候选已隔离构建、独审和部署，
  真实播放中接力尚未验收。只以 8962740e 基底增量修改，不叠加已经回退的
  Directory 候选；新接口不会刷新固件或 SYSTEM/eMMC。
- 《永生之酒》新请求真实转存、115 实播已观测；中文字幕和后两集准备仍未通过，
  详见下面 attempt 2，不得只靠恢复 CD2 代替验收。
- 《千钧一发》大 Range 候选已经实播但仍有停顿，不宣称起播卡顿已解决。
- 既存多目标 `_complete` 部分入库：后一个目标异常时可能已有前一个 queued。
  独立确认该实现本轮未改变；failed 不应理解成“零任务”，工具已读取实际账本。
- 新改动未借用 CE2034 的 CI 或设备验收；不得覆盖旧 CE2034 包。

## 继续执行记录（2026-10-22，部署前）

用户确认由我完成部署、完整操作测试，阻断交给独立审查后由实现者修复，
实测通过后才推私库。审查与实现分离；未将既有通过数当作真实播放验收。

- 同集 controller 的独立 14 个反例与 199 项产品回归通过。
- 跨层独审发现新增 `audio_intent` 令同事件序号的字幕观察停滞；保存了
  8 fail / 2 pass 原反例。修复为可选、精确非负整数、同实例存在性一致和
  单调递增；旧 F9 完全不带该字段仍支持，ReceiptHistory 仍拒绝同序号事件。
  独立 10 项复验及产品 91 项回归通过。
- 跨层独审另发现原生 capsule 仅恢复 `subtitle_file_applied`、遗漏对应
  `subtitle_file_sha256`，会让真实消费者拒绝恢复后的外置字幕状态。旧候选
  `a74ebd17` 未上机，审查结论已撤为待修复；保留 2 fail / 2 pass 原始证据。
- 冻结 audio 后三套隔离全量：primary 2324 pass / 1 fail / 6 skip / 1 xfail；
  baseline 943 pass；preparation 234 pass。唯一 primary 失败是新增 audio 修复
  尚未刷新源清单，不能跳过该检查；等待新原生 hash 后统一刷新并重跑。
- 设备预检仍为 CE2034、空闲主界面；CD2 原容器和镜像未变，挂载与三个本地
  端口均可用。TorrServer 实际为 MatriX.144.1，未改变其配置或启动新种子。

## 受控实机验收矩阵（全部仍待执行，不是通过记录）

1. 完整签名入口更新、程序文件核对、重启、账号/字幕位置/CD2 保持；再部署
   重新冻结的原生候选，保存旧启动配置和回退凭据，不刷固件。
2. 《千钧一发》同一 FGT 4K 的 progressive 新首 Range：记录选源到 AV、停顿、
   实际音视频/中文字幕及诊断。不靠换源、降低码率或隐藏初始停顿过关。
3. 《永生之酒》普通手选生成全新 request：本地元数据验证、prepare accepted、
   账本任务、真实 115 qualified 和实播分开核验；不是只看 CD2 服务已启动。
4. 新作品《缺席的人》10778 与《太空丹迪》60874 S01E01：手动选源、
   原声/中文字幕、播放推进、暂停/seek、菜单交互与真实字幕 GUI 截图。
5. 同集接力：卡顿触发到 capture/STOPPED/child/RESTORED 的关联；秒级断点、
   音轨、音轨延迟、字幕 Off/内嵌/外置/延迟。故障注入必须明标注入，不冒充
   自然网络故障。普通 GUI 测试输入也不冒充产品的原生实例绑定控制。
6. 平稳 BT 的当前＋后两集准备、同版下一集最终就绪复查与 115 优先；
   不足同版证据时保持手选，不绕过账号代际、取消或文件身份。
7. 每项失败保留记录并重新审查；最终记录实际通过范围、未能满足的外部条件、
   最终构建/commit/tree/新 CI，不能用旧 CE2034 成功替代。

## 本次真实安装与失败重测

- CE2035 完整签名入口 95,988,300 字节，SHA256
  `08b4c893ffcb407cd9dcebf54c53dbb24a441d41a40887a54a2a30697c3075c7`。
  同代 bootstrap / 内附签名 / 隔离导入通过。真实入口安装事务
  `dfc66701b7aa4b24a04a2c0bc9ab92e1` complete，1159 个自有程序文件匹配。
- 确认输入后 26 秒仍显示旧代次曾被误判为阻断；独审证明当时尚在安装准备。
  `choose` 退出零仅表示按键已提交，不证明安装完成。现在工具重验聚焦后的
  窗口/标题/选项，另用 `wait-install --expect-sequence` 等真实完成；21 独立
  回归通过。没有为这次延迟绕过或重写安装事务。
- 原生维护首次 apply 被旧更新器 CE2021 状态误拒绝，旧二进制/配置未动。
  修复为读取真实入口的 complete 代次，停服务后再次核对原 journal 字节。
  保留旧误拒、反向误放行及无 JSON 失败证据；78 产品测试和 20 独立反例通过。
- 新原生 `632758f5d1ca5494e9b049446d3908bead70589b4d18640bb5d06e830a2b57eb`
  已应用，维护 receipt=applied，原 conf 备份仍在 2026102035 overlay 目录。
  CD2 原容器、挂载、三个本地端口均保持正常；没有刷 SYSTEM/eMMC。
- 部署前完整三套：2325 primary / 943 baseline / 234 preparation 通过，
  6 skipped / 1 xfailed；之后维护工具、诊断和 UI 的新增定向测试不能冒充已
  再跑当前全套，最终冻结后仍须重跑。

### 《千钧一发》attempt 3：仍未修复

CE2035 新 progressive 首 64 MiB + 原 F9 同源 FGT 4K，request
`0ed3043bc7424b159264ad87fe64504d`，首次观测 AV 10.53 秒，停顿约20.97秒。
4K 解码采样无 drop / hardware error，但不能据此算播放通过。
独立复核确认最初 demux 断粮，随后原 F9 的 16 秒恢复缓存门槛延长等待；
初始断粮究竟来自上游、回环写入还是播放器读取，现有逐段统计不足以唯一归因。
HTTP response 事件只说明首前缀就绪，不能误称视频首字节已被下游 ACK。
试后恢复 block 模式、原 debug false/false/[]，原始日志留外部私密证据目录。

### 《永生之酒》attempt 2：云准备成功，BT 起播仍失败

新 request `1e4b0d8c5bf14ad8a6058d50c463ef4b` accepted，真实任务
`27a1b1f0a3cf4052a68f53ce4702cdee` ready，1 个精确文件 binding。
BT 约98 KB/s、2 peers，90秒仅预载6.46MB/32.21MB；另有30秒询问等待，
最终 BUFFER_TIMEOUT。不是元数据404，也不是 CD2 不可用。

随后**原有 pre-AV 失败回退**自动重选同文件115 request
`2a73297274994d4abda844a7e7fe9ee9`，实际 1080p H264 / 日语 LPCM，
25秒连续观测正常，无 caching；暂停/恢复及片尾 seek 后 NATURAL_EOF 已确认。
这不是新原生“播放中卡顿接力”通过，也不是已验证整片连续观看。
该源内嵌仅日/英，外部字幕返回 ASSRT_API_30002，未出现中文字幕，不算字幕验收。
E2/E3 滚动任务存在，但两轮均 NO_VERIFIED_SAME_RELEASE，尚未 prepared；
不得将“任务已排队”当作后两集已存好。自然结束回首页，未误报异常退出。

用户新增建议：对照 Juku 缩短选源到播放。独审已证 Juku 的 CLOUD115
分享/个人盘直接交付解析 URL，不经过其 ProxyManager；其它 provider 的并发
下载逻辑不能用来解释115。准备做同文件受控对照；尚未切换产品传输策略。

### 后续实机与独审收口（仍未交付）

- 《缺席的人》10778，76.6GB CiNEPHiLES 4K DV REMUX：原英语 DTS-HD MA、
  内嵌简中，首观测 AV 15.78 秒、初始约 5 秒停顿，启动仍未通过；后段 30 秒
  推进30.36秒无缓冲。手动字幕 Off/On、延迟调整恢复正常。真实字幕 GUI 平面
  单行下缘22像素且完整，不能代替双语/电视 overscan 验收。截图及 measurement：
  `ce2035-new-movie-subtitle/layout-1792606904580429900.*`。
- 《太空丹迪》60874 S01E01 hchcsen 同包，真实准备 E1/E2/E3 三个 qualified
  bindings。BT 自然卡顿24秒没有同集接力，保留 `ce2035-space-dandy-live-handoff2.json`。
  同文件 fresh verifier 0.828秒成功，不能把故障归咎于云文件未就绪；真实 monitor
  拒绝阶段仍缺证据。节目仅英字，外置中文没有加载成功，字幕未通过。
- 监督 seek 99.5% 后第一集真实 NATURAL_EOF，正常产品自动续播 request
  `c6909d929acc44ca8ed9276594aebe95`：同版115第二集，PLAY_ISSUED→首观测视频
  约2.711秒、前台确认。其后19.506秒推进19.562秒、无缓冲，日语 Opus；已精确
  停止这个子实例。此项证明EOF到已准备115下一集，不证明播放中卡顿接力。
  原始关联 `ce-playback-log-1792608256422865100.json`，观察
  `ce2035-space-dandy-e2-115-observe1.json`。旧 trial inspect 的 USER_CHANGED_SELECTION
  是测试工具不认续播子请求，不能误写成用户实际换片。
- 尚未部署的 pre-AV 提前115接续：独审抓到两级取消竞争，包含 caller 最后检查
  与服务准入之间的 Stop。修复使用原 authority/owner 串行原子 retry_from 守卫，
  不新建第二控制器，不让自动接续覆盖Stop。原失败保留，独审33项及555项相关
  产品复跑通过；仍需新代次实机。
- Juku式direct诊断工具原版有Kodi退出信号缺口，独审4个反例失败；实现方已修，
  未经独审复验前不运行。对照必须说明同文件之外的native/window/字幕差异，
  不能直接用旧F9 baseline与新native的时间差推断纯transport因果。
- 新native同文件常规UI attempt4：9.122秒首观测AV，但视频时钟尚未正向推进即
  被STOP。原始日志明确 `handle_playback_start: Local service temporarily unavailable`，
  随后通用异常分支调用cancel；没有人工停止。独立真实方法/authority组合保存了
  4失败反例，原因是呈现控制异常被当作媒体失败，不是已证实网络或全屏超时。
  本地候选已修但须独审/新代次设备验证。
- direct诊断run1/2尚未播放：旧CE2035 Python select helper不接受account_scope，
  但同代authority支持带scope的wire。改用原同字段wire，保持账号CAS；独审从已签名
  CE2035包复跑current-account/changed-account/unavailable边界通过，未删账号保护。
- direct run3实际正常播放，外部10秒观察无缓冲、4K/英语TrueHD/内嵌中文保持；
  工具自身却在第6次采样后挂起。该采样0.774秒耗尽0.5秒间隔，使waitForAbort(0)
  按Kodi定义无限等待。已精确停止实例；不能给run3虚构完整起播曲线或自动停止成功。
  零等待修复经独审后重新采样。清理等待脚本的闲置重启超出工具25秒观察窗，随后
  只读确认服务active/running、Result=success，没有重复发重启。

### 同条件传输对照与CE2036候选

v4监督工具，同native `632758…`、同51.3GB FGT文件、同windowed列表项、同设置，
未增加字幕自动搜索，实际内嵌中文保持。顺序为direct→block→direct→block；
网络及CDN热缓存不是受控变量，因此不宣称普遍固定倍数。四次均精确停止确认：

| 路线 | 解析开始→首观测AV | 观察到的后续播放 |
| --- | --- | --- |
| direct run4 | 3.750秒 | 约42秒，无缓存停顿 |
| block run1 | 15.369秒 | 约31秒，无缓存停顿 |
| direct run5 | 4.626秒 | 约42秒，无缓存停顿 |
| block run2 | 15.588秒 | 观察窗内未出现缓存停顿 |

这些不是用户点击→AV计时；包含取址/注册，但不含正常选择UI。签名地址不入报告。
随后同工具同native试progressive：9.473秒首观测AV，但54个Caching样本约27秒停顿，
观察窗最终仅播放8.721秒。失败保留；已恢复block并确认账号代际/原生不变。
精确传输事件47条见 `ce2035-gattaca-progressive-exact-transport2.json`，尚待独审定位。

裸direct虽然明显更快，但现实现无法保留ShareStream透明续签；没有把这种功能
退化默认装进产品，也没有新增另一daemon。保留既有传输，继续查保续签的改法。

CE2036签名候选（不是最终观看交付）：入口96,000,163字节，SHA256
`c0fc01bfb760a063cf2b4a975177020d492c9d3b5a05ffa84f36ae3052a7cb30`。
22组件、同代bootstrap、签名、隔离导入检查通过。最终冻结三套为2560 primary、
1020 baseline、234 preparation通过，6 skip/1 xfail。旧初次UI128等focused不能
代替这些最终全套，也不能代替设备测试。新UI两项独审边界（前窗关闭异常、
嵌套等待突破绝对期限）已修，所有旧失败记录保留。

### CE2036 实际部署与后续阻断（2026-10-22）

- CE2036 真实入口事务 `1d5cf72c749a4d16b5182a1fee636cac` complete，
  sequence/highwater `2026102036`，1161 个自有文件与签名候选一致。
  staging `20261022-032500`；上一入口保存在同次设备事务的 `previous-entry`。
- 《千钧一发》普通 UI attempt5 不再因临时 IPC 错误取消已开始的影片，
  加载窗正常关闭并进入全屏。仍有约 14.452 秒初始停顿，不能算播放全过。
- 《混沌武士》S01E01 DragsterPS 是新作品测试。当前及后两集三个精确
  qualified bindings 均 ready。BT 初始约 47 秒才开始，之后观察及 65% seek
  未自然触发持续缓冲；不能据此宣称同集卡顿接力已通过。
- 该片实际存在日语 index 3，却自动选了英语 index 0。独审二进制及源码对照
  确认：真实旧 `8962740e…` 有原声绑定消费逻辑，而本轮 `632758…` 没有。
  所谓 original 源码也缺这段，旧对象与旧源码不等价；此前重新链接原对象
  的成功不足以证明重新编译保留了原功能。暂停最终交付，恢复已有 audio314
  实现并重新核查受影响编译单元；不能用晚到的全局音轨 setter 掩盖回退。
- 此时测试影片暂停在约 1276.780 / 1403.552 秒，request
  `c500910fad134ef59dd2f8d6020c90f0`、instance
  `e0626891-aaa8-4145-8fe0-c9fe2ab07399`。已人工切日语并开内嵌英字。
  测试字幕延迟 +0.100 秒、音频延迟 +0.005 秒，结束时必须恢复并核对。
  外置中文未找到，不把内嵌英字算中文字幕通过。

### 后续候选与测试边界

- 尚未上机的 ShareStream 改动只合并当前已排队碎块，最多既有 128 KiB，
  不等待未来数据、不扩队列，保留续签、取消与 Range 校验。独审 106 项通过，
  不代表已修复 progressive 的约 27 秒真实停顿。
- BT Owner.wait 的非正剩余时间原会进入 Kodi 的无限 waitForAbort(0)；
  保存了真实 Owner/Resolver 三个失败反例，候选修后通过，相关独审 173 项。
  没有证据把所有历史 BT 等待都归因于该缺陷。
- 当前未做 TorrServer SIGSTOP、限速或断网注入。受控断供工具仍在实现与
  独审，必须先证明可独立恢复、精确进程及播放绑定再执行。若执行，明确
  标注故障注入；不冒充自然网络故障，也不影响 CD2 或其他服务。
- 裸直链仅完成监督诊断，不是默认产品路线。用户尚未回答过期续播取舍时，
  保留自动续签。后续源码已有修改，CE2036 冻结通过数不适用于新的最终候选。

### CE2038 原声恢复候选、安装与验收起点

- 独立目录 `native/ce-original-audio-handoff-20261022` 恢复保留的 audio314 原声
  实现；手动选择及同文件交接胶囊优先，不引入晚到的全局切轨。
  实际 `VideoPlayer.h` 三个消费者一并重编，总计五个翻译单元。
  独审核对 272 个旧输入、9 个冻结源码、58 个旧 Bobi 符号；原声/胶囊宿主
  测试、97 项维护回归及 70 项跨层回归通过。这仍不是实机播放证明。
- 新原生 SHA256 `8bb2a99e2154432a4403ac55a81e3c253d7ab74f0e15369b85085f1a8bf4fd14`，
  完整构建报告 SHA256 `0c6069fe71c83c491dd48f363ca44efb3c2dbd775aa8fd0aaccc944c6aca52c9`。
  安装前任是实际 632，不混同构建来源 896；新维护 profile 显式锁定前任
  文件、启动器及 drop-in，原 2035 profile 与证据不变。整个新构建报告固定，
  旧输入与额外 ABI 输入须严格为不相交并集。
- CE2038 包含两项已审 Python 修复及精确原生兼容声明。入口版本 0.2.28，
  96,000,913 字节、SHA256
  `a44f0458b2273183cba731a8eafb0d3e44a2da8f009a6304a51f4c5fdc9faa87`。
  三套产品测试：2639 primary / 1020 baseline / 234 preparation 通过，
  6 个本机 symlink fixture 跳过、1 个既有 xfail，1 个 JUnit 元数据 warning。
  后新增测试工具的用例另外记，不倒改此轮收集的测试数。
- 完整入口真实事务 `aee6c809e6d0464f9bc1100dd8eb5640` complete，sequence 和
  highwater 均为 `2026102038`；1161 个自有程序文件与签名包一致。首次25秒
  观察仅到 switching，继续观察后完成，未把等待超时误写成安装失败。
- 旧 Samurai 实例已精确停止；测试音频/字幕延迟分别实读恢复到 0.000 秒。
  初次字幕减延迟动作收到 ACK 但数值未变，未以 ACK 冒充恢复；读取仍为
  +0.100 后再操作，最终数值及 intent 变化均确认。
- 后续新作品只读身份核验为《窃听大阴谋》The Conversation（1974，592）及
  《死亡游行》Death Parade（2015，61901）；尚未用这些作品宣称播放通过。
- pidfd 只读自进程能力预检在实机通过，无 signal。完整故障注入工具独审
  找到退出信号打断恢复与进程 exe 变化边界，未批准、未执行断供。
- 新原生8bb2实际应用成功，维护 receipt=applied，前任632原目录及配置备份
  保留。《混沌武士》同一 DragsterPS 文件的已准备115版，普通手选 attempt2
  点击到首次观测 AV 约3.609秒；约35.47秒连续正向采样无停顿、前台正确。
  实读自动音轨 index3 日语 AC3 5.1，audio_intent=0，无人工切轨；原声回归
  这一场景通过，尚不代表BT接力/中文字幕全过。外置字幕源仍暂不可用。
- 新 progressive 对照前，旧 v4 诊断工具拒绝 `HISTORY_MISMATCH`：它固定
  attempt3，而普通UI后续重播已更新历史。没有删除历史绑定保护来跑通工具，
  保留拒绝回执；改用真实产品普通UI的新 attempt6，不混称同工具四路对照。
- Gattaca attempt6 的 progressive+碎块合并仍失败：首观测AV约7.070秒，
  随后21.480秒停顿。新独审确认本次队列峰值仅241664字节，不能沿用上一轮
  队列满的解释。原生HTTP/HTTPS分类没有按127.0.0.1改变读因子的分支；
  302方案也被源码否决，因为Kodi会保存最终CDN URL并在seek时绕过本机续签。
  已精确停止、恢复block，账号与原生均未变。下一实验仅为有界诊断，不默认开启。
- 新作品《死亡游行》普通手选6.09GB Killua REMUX：13.590秒到首AV，但仍
  观测9.479秒初始停顿，不能算新作品播放通过。完整原始日志已另存，精确停止。
- Samurai HYBRID BT仅2 peers，约50秒只预载5.1MB/32.2MB；同文件115已就绪，
  实际触发 `TORRENT_PREPARED_READY`，不等90秒满超时。子请求
  `1a1027a5de5d4265882bd64d6d8a2514` 从PLAY到视频约1.98秒并前台确认；
  已精确停止。这验证开播前提前切云，不是播放中断点胶囊通过。
- 另一 Anime Time BT 同样在开播前转115，当前子请求
  `8f66b223e26e41d2ba342f4c6a9c6c83`、instance
  `c793bfa5-9244-425d-8704-eb6268e6b67a`。后续主线程停止命令被本机执行策略
  拦截，命令未执行；未通过其他控制入口绕过，已请求用户用Yatse停止。
  此时不重启/部署/开始另一影片，只继续本地修复与审查。

### CE2039 待部署的字幕与性能诊断

- 官方 ASSRT 30002 是搜索引擎不可用，不是没有字幕。独审复现两点并由另一个
  实现者修复：后续30002保留已有合格待DETAIL元数据；单条DETAIL 20900仅跳
  当前候选。若保留候选都失败仍报告原30002，不伪装成功空结果。
  30秒预算、3次查询/6候选详情/每候选2文件上限、认证/配额/取消及手动Off守卫
  不变。390项定向回归、18项独立真实provider路径复验通过；尚未设备部署，
  不承诺之前三部动画已找到中文字幕。
- 独审支持 start→EOF 的短跑诊断，维持8MiB队列、原身份与续签、取消和公平
  让出；不得把原按64MiB重置的错误预算改成整片仅3次。实现中，不是性能结论。
- 完整断供工具已通过82项组合回归及专用Linux测试进程真实pidfd实验；仍未在
  盒子暂停TorrServer。actor自身SIGKILL/OOM不保证自动恢复，备用CONT仅对
  确认actor已退出且原boot/PID/start/inode匹配的原目标；禁止重复旧run解除
  后来外部暂停。所有这些只是工具安全验证，不是BT→115实机接力通过。
- 长Range候选1的独审复现：取消且尚无响应头时，handler回到HTTP/1.1等待下个
  请求，客户端及Host.close多等客户端超时。原219通过/1失败及线程堆栈保留。
  实现者仅关闭这条未完成连接返回路径，不加超时、不提前释放迟到producer
  或host lease。新独审222项通过，两个新测试独立进程30/36通过。
- 候选1在源码更新过程中运行的全量保存为2767通过/1失败：唯一失败是原清单
  和刚修的share_stream哈希不一致。它不是最终冻结结果；candidate1不签名，
  candidate2重新刷新清单、构建和跑全量，不用修改测试预期掩盖该失败。
- CE2039 candidate2签名入口0.2.29，96,002,460字节、SHA256
  `c4a2b3a9b59bf86a5080c3d28660696f21bc7fc01c9aaecd37e2aae88886167f`。
  真实ZIP签名、bootstrap一致性、隔离导入通过；尚未在设备安装。
- candidate2三套冻结已完成：2769 primary / 1020 baseline / 234 preparation
  通过，6个本机symlink fixture跳过、1个既有xfail，1个JUnit元数据warning。
  对应`ce2039-*-freeze2.xml`。新测试独立导入失败已由作者补显式路径并重测，
  原失败没有删除。用户尚未回答停止请求；只读观测同一实例正常播放到
  20:38 / 23:21，选择等自然结束而非绕过被拒绝的停止操作。

### CE2039 实际部署及长 Range 首轮结果

- 上述 Anime Time 实例于 04:44:35 自然结束，回执为 `NATURAL_EOF` / 
  `EOF_WITHOUT_VERIFIED_NEXT`，没有异常退出误报；此后只读确认空闲。
  已告知用户无需再按停止，未绕过之前被拦截的停止命令。
- candidate2 已通过真实入口安装：事务 `2178ffb3245045d89cf149fca65713c8`，
  sequence/highwater 均为 `2026102039`，phase=complete；staging 为
  `20261022-044600`，原入口保留在该事务备份。1161 个自有程序文件匹配签名包，
  空闲重启后仍使用原生 `8bb2a99e…`。此前“尚未部署”只描述当时状态。
- 全局 ShareStream 仍是 block。open-range 仅用于一次有界诊断，未改默认。
  首轮同文件 Gattaca request=`0d481334e3634e1cba8b2f2edc18cb11`，
  instance=`a7f7246e-124d-4195-90f5-58fc39da5573`；解析开始到首观测 AV
  7.749 秒，89 个采样中 46 个 Caching=true，45 秒观察内影片仅推进约15秒。
  这仍是失败证据，不能把缩短首画面时间写成持续播放改善。
- 此轮精确停止回执 `stop.confirmed=true` / `reason=STOP`；顶层旧字段
  `stop_state=unconfirmed` 未同步，是工具回执缺陷，不能据此重复发 Stop。
  原始结果不覆盖，另由实现者修工具、独立审查者复核。
- 通用日志探针要求正常产品 `SESSION_ACTIVATED`，因此不适用于该诊断请求。
  已保存原始日志；探针断言与外层 JSONDecodeError 保留，不伪造产品事件。
  独审按 transport hash 提取白名单传输字段进行离线关联。
- 现场另有 `ASSRT_HTTP_493`，当前未归因；两项字幕候选修复部署不代表真实
  动画已获得中文字幕。播放中 BT→115 接力、外置双语字幕仍未完成验收。
- 当前 8bb2 / v5 / 同文件的后续诊断：direct 解析→实际首观测 AV 3.722秒，
  block 14.184秒；二者观察窗中均没有 Caching=true，分别推进41.631/31.226秒。
  sample.wall 是查询起点，不能用它的3.611/14.096秒冒充实际观察时间；
  向用户的初步约数随此正式回执更正。两个都精确停止、设置及用户文件不变。
  网络与CDN缓存未控，各route此轮仅一次；不是产品入口或普遍倍数证明。
- open-range首窗队列峰值仅204KiB，没有8MiB队列满；同一响应后续更快，
  不能只怪64MiB重连。独审观察到约67,032次put、45,499次send，支持在显式
  诊断中做首前缀立即、后续固定最多2ms的微批A/B。仍不改普通传输默认；
  需同观测开销的0ms控制组，不把线程重叠累计耗时相加当总耗时或预判GIL根因。
- 新作品《葬送的芙莉莲》S01E01 普通选源选7³ACG 01–28包：BT仅1 peer，
  约59.36秒预载1.82MB/32.21MB，随后 `TORRENT_PREPARED_READY` 转同文件115。
  父请求 `f6e252dae5244513b653cffc77765aec`；子请求
  `be088c1f039f461abd6e067ddfa6e346`、实例 `7719b9a8-2f00-4bb1-b2d6-9f63aab5c0d2`。
  当前和后两集有3个ready bindings；这是开播前转云，不是播放中故障接力。
  初次trace在AV前结束保留not_covered，后续父请求控制正确拒绝USER_CHANGED_SELECTION。
- 对上述子实例单独25秒采样，片时41.019→64.876秒持续前进、无Caching；
  只记录该观察窗，不能宣称整集无卡顿。已加载内嵌 `chs&jpn[Haruhana]`，
  单音轨语言标签为空，不能仅凭自动index0证明原语言识别。
- 对该新作品实际截图两张GUI/字幕平面（不含硬解视频平面），中文样式注释与
  中日双语对白均完整可见，没有下缘截断；截图路径在外部证据
  `ce2039-frieren-subtitles/`。此结果不替代中英外置字幕、HDR或电视物理过扫描验收。
  受监督seek到21%后实读5:25.518，音频/字幕延迟均0.000；未改变字体或边距设置。
- 第二张中日双语字幕截图，在1080高GUI平面中最下方可见字形到y=1029，
  底部保留50像素（中心下方区域RGB和>72）；这是原字幕样式，不是强行改边距。
- 受监督seek98.7%后，第1集实测自然EOF→`NATURAL_EOF_SAME_VERSION_HANDOFF`，
  同版115第2集 request=`75df622a31304e3aacdf236270cfc637`、instance=
  `99b75085-c82f-4d67-963d-5fc11c150990`，前台确认。独立20秒观察片时
  54.946→74.591秒，双语字幕保持开启且无Caching；不是未经seek整集观看证明。
  已用经48项独审回归的明确实例Stop停止，精确TERMINAL/STOP确认，延迟仍均0。
- 新电影《窃听大阴谋》1974普通UI选70.3GB HDHIVE 4K REMUX失败，request=
  `3ba3b950423547549dcca9a9cfccf67a`。已捕获 grant / 195ms / 0 bytes，
  ShareError api_code=4100010 / share_revoked，随后本机503与原生ERROR；
  不是已有证据支持的码率、缓存或解码失败。原始日志及首次失败trace保留。
  当时UI仅显示旧“1个来源查询失败或超时”，此条具体失败是否正确展示已交
  另一只读审查者追踪；尚未归为影片可用或中文字幕通过。

### CE2040 显式微批诊断整代

- 新增open_range_microbatch，首前缀立即，后续固定至多2ms，128KiB批量与
  8MiB队列不变。两组显式诊断同开CPU/片段大小/取消累计指标，默认block不变。
  最终独审257项通过，原始反例保留；新工具v6明确区分target_terminal与STOP确认，
  未知ACK不重试，日志探针显式诊断receipt不冒充SESSION_ACTIVATED。
- 完整入口0.2.30，96,003,895字节，SHA256
  `377efb84de8f538172c3971a006c53e78b2b429abc7ef026bc54ae8ab33eb024`；22组件，
  签名、同代bootstrap、隔离导入通过。主2863 / 基础1020 / 准备234通过，
  6环境skip/1既有xfail/1JUnit元数据warning。对应ce2040-*-freeze1.xml。
- 正式入口事务 `1e4db692421d477cba5d8ea3e1ea6b71` complete，sequence/highwater
  2026102040；1161自有文件匹配签名包。staging=20261022-052400，原入口已备份。
  第一次25秒只读等待到switching，第二次确认完成，未盲重装。原生保留8bb2。
  当前只是诊断可部署证明，尚无微批实机性能结论，未提交/推送GitHub。
- 闲置重启后CE2040实机v6控制/微批首轮均失败：0ms解析到首观测AV6.875秒，
  89样本中49次Caching，末片时13.964；2ms8.218秒，90样本中44次Caching，
  末片时15.094。两次都是完整诊断completed/精确STOP，设置与用户文件不变。
  微批主stream send由控制37,207降到6,730，但仍没有消除停顿；不启用为默认。
  CPU与取消/读/队列/发送壁钟有重叠，不能累加或直接断言GIL/账号检查是根因。
  safe logs分别为ce-playback-log-diagnostic-1792618071629436400/1792618173125863300，
  外部原始日志ce2040-gattaca-control-raw1和ce2040-gattaca-microbatch-raw1。

### CE2041 本地候选：仍未部署、未提交

- 新增仅显式诊断的 `open_range_bound_guard`，结构校验一次后，每次仍在
  原账号RLock内比较完整scope，不缓存授权true、不新增权威状态。v7只给该
  模式固定0ms，普通block/原控制保持原检查。独立组合241项通过，最终stream
  哈希 `5ccedfcc44be31eceddc72537b09c77fbd66fcb0851074b0465f57dbda320024`；
  尚无实机性能结论，不切换普通默认。
- 分享失效错误链已完成本地实现与另一审查者复核：exact Binding安全typed失败、
  固定30秒负缓存、PRE_AV错误实例/URL摘要关联、账户与展示时效复查、精确旧proof
  撤销。无resident负记录不能一律撤销历史正常proof；SQLite撤证写失败再重启时
  不保证持久负缓存。保持原grant与startup预算，不自动关闭未知Kodi模态。
- 新作品《进击的巨人》S01E01 ZeroBuild真实BT开播，自动原声为日语。监督测试
  临时选英语、字幕Off、字幕+0.100秒、音频+0.005秒以验证接力胶囊；结束前须实读
  恢复原声和两个0.000延迟。request=`9b68dc38b3d045e7bb7640e61be1e799`，
  instance=`38cc2776-adaa-4eca-96a0-21a755651913`。未执行TorrServer STOP/CONT。
- 已观测自然Caching与WATCH_THRESHOLD，但VERIFY_NO_CANDIDATE，不能称接力通过。
  task=`0d1b6f9efcc648d3a6250d91696883bb`三个目标、零binding，连续7次
  qualify/ProbeError/BYTE_BUDGET。离线任务已完成，阻断处不是仍在下载。独立本地
  合成Matroska大字体附件能复现读满16MiB，但实际文件原因须等exact目录诊断。
- 独立审查发现跨季/衍生作品的自动文件校验缺口（合成实际selector反例5fail/4pass，
  非实际错片播放证明）：旧hash proof只有集数映射，v1只查basename漏父目录冲突。
  正由另一实现者修复通用作品/季/类型边界；原失败证据保留，尚未认定完成。
- root补ProbeError固定数值统计进入既有audit，独审发现极大整数在isfinite转换
  时抛OverflowError；已先检查界限并补反例，33项通过。无调度/授权/预算改变。
  当前工作树混合开发中，旧CE2040通过数和CI不能代表此候选。
- 后续30秒只读观察仍是同一个BT实例，片时10:33至10:51后再次Caching，未发现接力。
  在准备下一代部署前已逐项实读恢复日语index0、字幕开启、音频/字幕延迟均0.000；
  随后精确原生实例Stop确认TERMINAL/STOP，未停止其他播放。证据为
  `ce2041-aot-restore-*.json` 与 `ce2041-aot-native-stop1.json`。当前盒子已空闲。
- 实际EBML首轮工具在account_before失败，媒体GET/字节均0；原因是外部Python
  的默认runtime.call依赖Kodi的xbmcvfs，不是视频问题。已保留失败并交原实现者修复，
  独审将补无xbmcvfs的默认宿主链测试；不得把模拟工具通过冒充实际目录已读取。
- 默认宿主链修后经另一审查者112项复跑，实际第二轮只读目录成功：
  `ce2041-aot-exact-ebml2.json`，媒体仅164字节/32个精确206请求；前后账号、任务、
  文件映射一致。实际视频4,113,649,288字节，Tracks 41,853字节，Attachments
  15,730,776字节，附带普通/复杂类型尚待检查的Chapters索引。目录仍为partial/
  request_budget，不称已遍历全部、也不推测附件MIME。现布局支持大附件加2MiB
  packet分析耗尽16MiB探测预算的原因；候选仅对普通qualification跳附件正文，
  原subtitle/detail/profile探测链保持不变，实施后还需实际同文件只读验证。
- 首target失败导致后续目标饥饿已有真实SQLite反例（1fail/26pass）；现在原task
  payload保存有界调度游标，未绑定目标按原顺序循环。单IO、60秒退避、账号与
  ready门槛不变，不新增云写。作者准备套254项通过，独审85项通过；先失败首集、
  再成功第二集已通过真实Ledger发布测试，但不是设备播放认证。
- 为下一轮设备验收查询了此前未试播的《夜行者》2014和《天国大魔境》2023，
  TMDb分别242582/208891，直接HTTPS查询无配置代理。当前仅身份核验，尚未开播。
- 已只读核验GitHub仍为PRIVATE；fetch后当前审查分支HEAD与远端相同，尚无本轮
  commit/push，也没有把候选混入main。版本声明预备为CE2041入口0.2.31，非已构建。
- 实际资格候选首轮 `ce2041-aot-qualification-candidate1.json` 仍失败：Tracks读取后
  grammar unsupported转原ffprobe，最终BYTE_BUDGET。没有安装、没有发布ready。
  两轮显式header-only只读诊断将失败定位到0x6D80 ContentEncodings，实际为
  TrackType17字幕、单一order0/scope1/type0/algorithm0、settings0、无加密，
  即默认的字幕packet zlib压缩。每轮只读取42,147字节/14请求，不再fallback读16MiB。
  实现者与另一独审者正按该通用格式类窄修，其他编码/加密/不支持布局仍走原路径。
- 探测独审另抓到普通小MKV前扫重复读取导致read_bytes超过文件大小、真实Ledger
  拒绝的新回归，以及过多Void元素耗尽请求额度。候选必须先修这些回退，不能只证明
  原大附件反例改善；method/coverage也须随真实worker资格事务持久化，不仅工具可见。
- 选源边界独审最终339项通过/1既有xfail，含真实缓存→producer→Resolver及旧版本
  正向对照。修复中曾出现6项普通命名回退和4项目录边界问题，均保留修前证据。
  最后的扩展alias与标点空alias反例由root实现、独审复核；仅保留明确季/类型限定，
  不将同work长别名一律删掉。最终scope hash为
  `77af63ed3e79f625701479baff24cb0060fc6e23c96a3931f571d34ddb9c92b3`。
- 非冻结整合轮：primary 3208pass/2fail（只缺尚未刷新的显式inventory），
  baseline1020pass、preparation254pass；6环境skip、1既有xfail、1JUnit warning。
  运行时probe/alias尚在变动，最终冻结仍须重建inventory并完整重跑，不能把该轮当交付。

### CE2041 冻结安装与后续验收（2026-10-22）

- 后续冻结 primary 3275、baseline 1020、preparation 254 项通过；6 环境 skip、
  1 既有 xfail、1 JUnit warning。两次完整私包构建 63 文件一致，同代入口及签名审计通过。
  入口 0.2.31 / sequence 2026102041，22 组件；事务
  `c1280be758db4497bd5c3ba4a091bdff` complete，highwater 2026102041，
  1164 自有程序文件与签名包一致。原生仍为保留原声修复的 8bb2，不回退旧候选。
- AoT 大附件实际资格修复完成：只接受已核实的单层字幕 zlib 格式；小文件不前扫，
  复杂/不支持布局仍走既有路径，共用原字节/请求/时间预算。实际同文件候选读
  42,403 字节 / 23 请求 / 2.513 秒；安装后真实 worker 自动发布 E1/E2/E3，
  ready / 3 bindings，读取 42403/39789/37344 字节，方法与覆盖范围已持久化。
  不生成完整 media_profile，不替换字幕/字体 detail probe；不是播放中接力认证。
- 共享整剧/本季年份修复最终独审 359 passed / 1 既有 xfail；接受经同 ID 资料
  核实的整剧年或目标季年，不接受其他季年，不增加网络查询。旧 legacy 编号证明
  不升级为自动选集，保留手选；旧反例中该行为差异明确记录，不篡改原预期冒充全绿。
- v7 同文件 Gattaca 的 A1 / bound_guard / A2 已全部收回 completed，三次均确认
  精确实例 STOP；A1 首 AV 9.045 秒、45 秒窗末片时 13.280 秒，bound_guard
  7.214 秒、17.563 秒。A2 与三组 scoped 日志交独审比较。两条实验路线仍有缓冲，
  不能把少量开播差异称为性能通过，普通 ShareStream 继续 block。
- 新作品《天国大魔境》S1E1 普通选 Flugel 64.6GB Remux，request
  `66b5f52cdd2c40c7bb13f8705c62268c`，首 40 秒无 AV，随后观察到文件选择窗、
  最后 cancelled 返回源列表；root 未发取消。原始失败及终态日志保留，交另一
  只读审查者定位，尚不能归因 BT 供数，也不记为播放通过。
- 本轮仍未 commit / push，旧 CI 不代表当前工作树。已准备好不等于全部观看验收。

### CE2042 本地修复与 CE2041 新失败（尚未部署 CE2042）

- v7 A/B/A 独审确认 resolve→首观测 AV 为 9.045 / 7.214 / 7.722 秒；
  约45秒窗末片时 13.280 / 17.563 / 12.098 秒，三组均有约20秒以上缓冲。
  bound_guard 的单位 CPU/MiB 改善不等于流畅。重复成功前缀仅约60–81KB，
  不据此新增大缓存。下一步只做普通 block 1MiB 地板显式诊断，默认仍8MiB。
- 天国大魔境的退出确认为60秒文件选择超时，而非用户取消或无seed。独审用
  实际卡片标题证明闭合格式语法漏了 Remux；root补 Remux/BDRemux 格式词，
  保持未知篇名、季度、年份、OVA仍不放行。实际取消后的 torrent 查询已被拒，
  不把合成文件路径说成实档。修复仍须新代重选验证。
- 新电影《夜行者》2014的4K DV/Atmos BT已经开播，request
  `3ff91092921743339568c5a2806ce091`，原声英语、3840x2160、truehd_atmos8ch，
  外挂中文已应用，但不断Caching；云准备失败于 identity / validation_failed。
  原始 metadata 和只读重演定位到 basename 的 `{imdb-tt2872718}` 未被识别，
  不是低码率/解码问题。root让同ID既有TMDb详情携带规范imdb_id，只有完全一致
  的该格式标签在作品名校验时忽略；实际文件tuple/version不变，不增加网络请求。
  独审用签名CE2041旧代码复现失败、新代码同四文件元数据通过，缺ID/错ID/年/名
  及未知标签仍拒绝。相关作者145项通过，独审121项通过。准备套254项通过。
- 夜行者首张GUI截图没有可见字幕帧，不能证明字幕边界通过；已精确实例STOP确认，
  字幕/音频延迟仍0.000，没有改其音轨或字幕偏好。失败、日志与空截图均保留。
- 《窃听大阴谋》同一70.3GB HDHIVE 4K分享在CE2041重选失败，request
  `0252ab05ea244e6cbec3b6267f44d5dc`；普通选源窗已正确显示
  “这个分享已被取消，请选择其他来源。”，不再泛化为查询超时。未把无AV当播放通过。
  本次40秒trace超过30秒负缓存窗口，尚未证明真实连续重选负缓存命中。
- 随后测试返回曾报OLD_WINDOW_NOT_RETIRED。独审对照8bb2实际InputOperations.cpp
  和sleep/awake日志确认：首次Input.Back只唤醒屏保，没有投递Back；醒后明确Back
  正常退出源窗，露出底层Kodi“播放失败”确认框，按已观察的确定键回到首页。
  不是已证实的源窗死锁。只改维护工具：观测屏保/DPMS，休眠时先明确报需受监督唤醒；
  通用12002不再按ID自动Back。未添加全局关模态或放松播放权限。
- CE2042已完成22组件签名整代与两次63文件一致构建；主套3338pass/6skip/1xfail/
  1JUnit warning，基础1020pass、准备254pass。入口0.2.32、96,023,211字节；
  tx `6601c16e53f14fb8b226f4dd61db8a3b` complete，序列/高水位2026102042，
  1164自有文件匹配，闲置重启已完成。1MiB显式候选经另一独审443项通过。
  原CE2041包未覆盖；以上为部署资格，不是所有新观看场景通过。
- CE2042实测天国大魔境Flugel request `404628222c014400a772c13066c6681d` 已
  自动选中实际E1并开播。13文件元数据已保留；普通worker发布E1～E3 ready/3bindings，
  同version；E1/E2走原ffprobe，E3走窄header。这次资格修复不是仅工具模拟。
- 同次外部字幕三个 `Tengoku Daimakyo` 梯度查询均成功但rows为空，未查询已有中文/
  英文别名；并无本次493或下载失败证据。旧终态把无同包旁挂的inspect note也算作
  “已匹配未能加载”。另一实现者修正为本次候选失败标志，独审496项通过，尚未部署；
  别名召回缺口仍待有界共用身份实现，不能说当前已自动找到中文。
- 自然缓存触发真实transport_capture但返回UNSUPPORTED，未发送stop或接力；
  不是同文件115尚未就绪。只读Introspect表明实际BobiControl仍只有stop/pause/resume，
  /proc运行映像确为8bb2。独审定位构建漏了真正注册schema的JSONRPC.cpp消费者；
  已重编的JSONServiceDescription.cpp虽读新header，却未替代旧注册表。
  新隔离候选正从8bb2四archive只替换该TU；保留原声与所有原对象，待独审后部署。
- 维护故障工具曾因实际GetActivePlayers多了playertype=internal而误拒NOT_BT_VIDEO，
  已窄修为单一int1/video/internal且保留全套native/URL/account/qualification检查；
  55项独审通过。未因此执行任何TorrServer STOP/CONT。
- 为胶囊测试临时手选English AAC、字幕Off、字幕+0.100/音频+0.005；结束前已逐项
  实读恢复日语FLAC index0、字幕开启、两延迟0.000，再原生CAS Stop确认。不能对
  旧instance `33d527cd-0df3-4b46-8686-3365790839d4`继续发动作。
- 目前正在CE2042/8bb2上进行v8普通block8/1MiB同源对照；不要用正在构建的
  native修复结果倒推这些实验。仍未提交或推送。
- 8MiB/1MiB v8 A/B/A/B独审结束：首AV17.645/14.470/15.774/14.453秒，
  均精确STOP、设置不变、解码器无错误且1MiB组未触60秒诊断期限。但B2仍有
  6.388～7.604秒缓冲，末片时24.108小于A2的29.245。默认保留8MiB，不把
  实验路线冒充全面改善。用户最新确认：首轮冷启动等待不作为上传阻断；不再追加提速实验。
- ba0327新native单TU候选本地独审通过：保留8bb2其余53对象，完整184 RPC
  method与schema一致，原声/字幕/胶囊代码未改；维护278输入和前代46输入未变。
  root已增加schema2043固定部署profile与ABI hash。初版实际staged_files发现
  269历史输入与272即刻前代输入不可直接比较，保留失败后修为精确269→272→278链，
  不是放宽subset；144项部署/回退/音轨综合审查通过。当前只stage未apply，运行仍8bb2。
- 字幕别名候选复用同ID缓存并统一查询/最终匹配；作者527项通过后，独审又保留
  旧rich单季记录遮蔽新basic多季和巨大fetched溢出两类反例，已交不同实现者修复，
  未部署。最终需新完整CE2043程序先安装，再切已审核native，执行真实接力与字幕回归。

### CE2043 快速收口（用户最新范围）

- 字幕别名两项缓存问题已由实现者修复，另一独审最终552项通过；不再是待修阻断。
- CE2043完整包已安装：tx `a43bc74fc9424b189644a05f531c718f` complete，1164自有文件匹配；
  本地主3451/基础1020/准备254通过。完整双构建63文件一致，同代入口和签名审计通过。
- 新native ba0327已实际运行，完整BobiControl schema实读一致；旧注册表漏消费者问题修复。
- 用户要求快速上传，难以当轮解决的项目延期，随后要求本轮直接作为main并删除其他分支。
  本轮不再追加性能实验或长时间故障注入；真实中途接力、当前代字幕边界/线上别名、
  当前代EOF组合复验、我的概览与首页继续观看数据显示差异均明确延期。
- 最终状态、失败/成功边界、恢复说明见 `CE2043-DELIVERY-20261022.md`，不以旧阶段记录冒充最终全过。
