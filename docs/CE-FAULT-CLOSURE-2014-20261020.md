# CE2014：安装恢复、片尾判定与选源界面收口

冻结基线：`ee65742bfcbaf08831f70306faed11bd1f8d6cc6`，tree
`8444201262d9ab298c901a0ed6f599b9b13735eb`。本轮独立执行，无子代理。
保留通用 CE、新 UI、原码流和手动选源，不新增型号门槛，不改固件或原生播放器。

输入原包：[PR2 Web 审查 ZIP](../review-evidence/ce2012-original-web-review.zip)。
原冻结源码复跑 18 项，10 通过、8 失败；原始失败与测试运行环境错误均保留。
旧对话的三个源码路径缺口作为待复现问题，不称作 Web 已实机测败。

## 逐类改动

| 类别 | 旧行为 | CE2014 行为与边界 |
| --- | --- | --- |
| R01 启动 | 文件已核验、待激活却被 service boot gate 拦住；enabled 不代表运行 | 待激活/待恢复可运行；staged/switching/restoring 仍拒绝；必须得到真实 owner 队列回应；enabled-but-dead 有界补启动一次 |
| R02 恢复 | 进程退出后遗留 runtime 登记反复超时 | 获取稳定 OS lease 后核验关闭状态、清死登记；锁文件身份不变；替换期间持有 lease |
| R03 快照 | RPC 未知可能被记为 disabled | GetAddonDetails 失败尝试完整 GetAddons；未知/畸形结果仍拒绝事务，不伪造关闭向量 |
| R04 可选字幕 | 下一集视频已就绪，字幕可耗光 EOF 期限 | 字幕子预算最多 2 秒，且保留 1 秒提交；不延长原 20 秒绝对期限；手动 Off、取消与账号代际仍优先 |
| R05 进度 | 无效读数给旧 EOF 位置续命 | 有效进度时间与关联观察时间分离；0/0、seek 空白不刷新旧证据 |
| R06 工具 | 业务失败仍退出 0 | transport/trial 退出状态分别记录，观察或停止失败返回非零 |
| 持续安装失败 | recover 异常可能阻断菜单 | 真实 main → recover_interactive → 原事务支持重试、已核验旧代次回退、退出；恢复持续失败也保留菜单 |
| 外部接管 | isPlayingVideo=false 时可能漏外部音频 | 明确外部音频也撤销旧下一集；不停止音频、不清播放列表、不禁止普通 CE 续播 |
| 关闭边界 | HTTP/engine/catalog 任务未退完就释放进程 lease | HTTP、ShareStream、图片服务等待已接收请求退出；engine/catalog/preparation drain 完成才释放。安装器 15 秒等候耗尽则拒绝替换，不强行越过 |
| 用户 EOF 误报 | native NATURAL_EOF 后瞬时 owner 读取失败被折叠成 UNKNOWN | 在原 3 秒预算内读取同 boot/epoch/request/instance 终态；网络不可用不是明确撤销；不推测 EOF、不复活取消权 |
| 选源闪动 | 每次结果增量 reset 全列表、重建 ListItem/画质标签 | 保留 native 卡片对象和相对顺序，新结果追加，仅变更实际变化字段；精确 BT→115 替代只删除该行；无关结果不重选焦点 |
| 新增 UI | 片尾、登录等样式不统一 | 统一新皮肤面板/字体/pill按钮/动效及减少动效开关；账号菜单、NAS、安装恢复沿用已换肤的 Kodi 对话框 |
| 实测 4:3 漏项 | 1440×1080、960×720 被标成未知，阻止同版续播 | 补标准 4:3 HD 尺寸；竖屏、任意尺寸和矛盾标签仍未知；不放宽组名、容器、编码、季集和剪辑版 |

### 自然结束与无下一集

用户确认《学生会也有洞》第 2 集无同来源第 3 集，不能为续播擅自换源。
21:51 原始日志为 native `NATURAL_EOF`、cinema `UNKNOWN`：
[原现场](../review-evidence/ce-recent-terminal-1792504982315952400.json)。
修复后用户第 3 集于 23:02:40 自然结束，native/cinema 均为 `NATURAL_EOF`，
随后 `EOF_WITHOUT_VERIFIED_NEXT`，不是异常退出：
[真实自然片尾](../review-evidence/ce-recent-terminal-1792508568918283800.json)。
该条是用户作品回归，不算新作品覆盖。

提示改为“本集已播完／未能确认同版下一集，可查看分集或返回”。不明终态也不一概声称异常。
默认焦点为返回，不自动开播或换源。

### 《十二怒汉》根因

同原选 58,762,851,801 字节 UHD REMUX 文件复测，上游 `state=false`、`errno=4100010`，
即分享取消，266ms，未获得播放地址：
[同文件分类回执](../review-evidence/ce2012-same-file-grant-1792506024130793400.json)。
新增安全阶段/异常类别/API码/HTTP状态关联，不保存 Cookie、签名 URL 或正文。
没有修改码率、解码、缓存或全局重试。**原分享仍不可用，不能宣称该片源已修到可播。**

## 验证和证据层级

- Web 原行为断言适配到实际候选模块：最终 [18/18](../review-evidence/ce2014-web-contracts/RESULT.json)。
  仅接入新的 owner-readiness 与 GetAddons 读取边界，没有放宽行为断言；
  [接线说明](../review-evidence/ce2012-web-contracts/ADAPTER-NOTES.md)。
- 旧契约 [15/15](../review-evidence/ce2014-prior-contracts/RESULT.json)。
- 本地最终主套：[1745 通过，6 跳过](../review-evidence/ce2014-primary-final.xml)；跳过为本机 symlink 权限，交 Linux CI。
- 独立 Kodi 继承套：[761 通过](../review-evidence/ce2014-baseline-final.xml)；
  准备链：[177 通过](../review-evidence/ce2014-preparation-final.xml)。
- 安装测试走真实 `ce_install_ui.main`、事务/journal、真实文件与 OS 锁；仅 Kodi IO/错误注入为替身。
  覆盖持续/瞬时激活错误、持续恢复错误、静默无效、进程退出、旧 boot gate，以及死登记与活 owner。
  音视频分离、20秒内外部音频结束、读空、seek、手动停止、新选择、换号及迟到字幕 Off 均保留。
- UI 实机执行真实 WindowXMLDialog、SourceListSession 与渲染器，使用合成二维码/卡片，不发起账号交换：
  [回执和五张实机图](../review-evidence/bobbi-ui-smoke-1792508990684104200/result.json)。
  追加5个结果，reset=0、selectItem=0，原卡片对象/焦点保留。二维码默认取消和片尾默认返回通过。
  已实际查看图：新 UI 面板、文字与按钮正常。普通 TakeScreenshot 空白不算视觉通过；
  最终用 `/dev/fb0` 当前 GUI 显示层，不包含硬件视频层。
  CE2014 [逐帧补验](../review-evidence/bobbi-ui-smoke-1792509859790208700/result.json)：
  连续70次采样，首个旧卡片静态文字/底色区域像素一致；reset和焦点重选仍均为0。
  这是受测区域和增量场景的防闪证据，不宣称任何交互/全屏每像素都永不变化。
- 4:3 新反例首轮 3失败/8通过，修复后语义/传输组合 75通过。
  一项测试最初错误地要求无季号文件的季2指纹为空，改为“不得等于季1”，另保留明确 S02E02 冲突拒绝。
  不改实际产品季号策略。原失败与测试接线错误都保留。
- 同代入口 bootstrap、完整签名载荷、fresh interpreter 导入与篡改负例通过：
  [入口](../review-evidence/ce2014-entry-audit.json)、[载荷](../review-evidence/ce2014-artifacts.json)。
  两次 source-check，63个输出字节一致。source-check 不冒充可安装包。

## 新作品实播与仍开放问题

本轮新电影《罗生门》(1950, TMDb548)、新动漫《星际牛仔》(1998, TMDb30991)。
身份选择保留于 `ce2012-new-identities.json`；后续同作品重播只算修复回归。

《罗生门》所选 1080p AVC REMUX / 日语 PCM / 中文外部字幕真实开播。
[启动首败](../review-evidence/ce-new-work-rashomon-select-1792506974960339200.json)仍保留：
约6.54秒 caching，其中约5.03秒 decoder 也静止；另约3.99秒时钟静止但 decoder 推进，
不能简单声称电视实际卡13秒。
[后段](../review-evidence/ce-new-work-rashomon-observe-1792507042151350800.json)30.319秒推进30.322秒，
全屏、无解码错误。后段正常不冲销起播验收失败。

《星际牛仔》标准 Session → StandardPlayback → Handoff + 真实 Juku/115：
[首轮真实片尾](../review-evidence/ce-standard-real-1792509112829842300.json)正确记录自然结束，
但没有续播。进一步[只读诊断](../review-evidence/ce-standard-real-1792509260437794200.json)
为 `RELEASE_ENVELOPE_UNPROVEN`，对应1440×1080漏识别。
CE2014 [同文件诊断](../review-evidence/ce-standard-real-1792509592493143100.json)已返回准确同版第2集。
[最终实际交接](../review-evidence/ce-standard-real-1792509830895851000.json)：
第1集 `NATURAL_EOF` 后准确打开同版 MKV 第2集，媒体进度到11.198秒，Handoff仅交付一次。
工具以原生实例匹配的 stop 清理测试；`SERVICE_STOPPED` 是后续测试清理，不是误判第1集片尾。
初期有读数静止和起播等待，这条通过只认证自然EOF/准确同版后继，**不认证整部流畅或中文字幕**。
测试明确用 StartPercent=97 从片尾开始，不发送无作用域 Seek；不是整集播放认证。
此链在已有 F9 上运行标准策略，不冒充另一台原生普通 CE 硬件认证。

仍开放：原《十二怒汉》分享取消；《罗生门》起播异常；此前《四叠半》起播计时异常与缺中文、
《玲音》缓冲与缺中文、《这个男人来自地球》缓冲。现场 HDR/音频直通与主观同步未替用户验收。
真实干净用户 ZIP 安装、另一台 CE、第二真实账号尚未认证；不据此新增设备安装门槛。

## 实际产物、部署与回退

最终 CE2014：plugin 0.1.9 / platform 0.1.11 / core 0.1.15 / setup 0.1.4 /
start 0.2.6 / catalog 0.1.1，22组件、1392文件。
入口：`dist/private-releases/script.bobbi.start-0.2.6-ce2014.zip`，96,178,248字节，
SHA256 `59e133cf78faf6448475752c8e040dcdaf6146c4cd17184378b88db73aadd15d`。
载荷：`dist/private-releases/bobbi-private-2026102014-coreelec.bobbi-update.zip`，96,011,740字节。
不覆盖或重命名旧CE2011/2012/2013包。入口内 bootstrap 与载荷同代。

盒子按精确备份维护流程先装 CE2012、CE2013，再装 CE2014，最终 run `20261020-231800`。
这是维护升级，不冒充用户 ZIP clean install。账号/profile保留，CD2 1.0.19、挂载、Yatse、
VPS newapi/代理、固件/SYSTEM/eMMC未动。

维护工具曾误用 `runtime_paths.configure()` 覆写 ABI 选择标记，CE2013首次预检拦截，
没有替换程序，也没有开始服务修改。修工具后空闲重启，由真实宿主重新探测恢复 F9 标记，
核对无部署 journal 后才重试；[恢复证据](../review-evidence/ce-idle-restart-1792508713352605800.json)。
原失败不删除，也没有绕过预检。最终测试工具不再发布宿主配置。

普通用户恢复：使用新入口的恢复菜单；持续错误可重试、回到已核验旧代次或退出。
已知本机维护回退必须先核对当前代次与冻结 run，只回退本轮程序，不整库覆盖 userdata：

```powershell
python tools/deploy_ce_candidate.py --transport-source 'D:/AM6B-Project/AM6B/.claude/worktrees/bobi-tv-redesign' --mode status --run-id 20261020-231800
python tools/deploy_ce_candidate.py --transport-source 'D:/AM6B-Project/AM6B/.claude/worktrees/bobi-tv-redesign' --mode rollback --run-id 20261020-231800
```

该 run 回到 CE2013。若需再退，先核对对应旧 run 的当前/前代，不跨代盲调旧 rollback。
最终 commit/tree、实际 diff、branch/PR integration CI、安装包以私库审查交付为准。
不公开发布；没有把账号状态、私钥或 Juku 设备登录状态加入仓库/安装包。
