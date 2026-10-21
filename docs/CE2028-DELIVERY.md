# CE2028 双审查与 Claude UI 联调交付

日期：2026-10-21。仅 CE；未推送、合并、发布，未运行远端 CI。
独立候选分支 `codex/ce2025-review-remediation-20261021`；Claude 的
`codex/ce2024-reviewed-delivery-20261021` 工作树只读，未覆盖其未提交工作。

## 冻结身份与产物

- 基线：`c4e0baca6acefa58f031979bff71e7cd1028efdf`。
- 最终产品 commit：`0b4dad0454632d5d2eb31792444dd1456ab34a42`。
- 产品 tree：`2a5dc88063d60cc36ccb7c889a2765b237632a82`。
- 序列：`2026102028`；入口 `0.2.19`，皮肤 `0.1.3`。
- 完整入口：`script.bobbi.start-0.2.19-ce2028.zip`。
- 同代签名载荷：`bobbi-private-2026102028-coreelec.bobbi-update.zip`。
- 原 CE2024–CE2027 包与旧失败记录全部保留，没有覆盖旧包冒充新版。
- 最终文档/证据另行提交；交付目录 `DELIVERY.json` 记录 handoff commit，
  与产品冻结身份分别列出。打包器禁止冻结后 addons/third_party/release 漂移。

## 双审查整改与前后行为

| 故障类别 | 旧行为 / 反例 | 本轮处理 |
| --- | --- | --- |
| 安装排空 | 异常重入可能先 disable，现代 marker 消失被当旧协议 | 现代/未知状态先拿 OS lease，只有完整旧协议正控允许旧路径；15 秒预算不增大、不强杀 |
| 历史写入 | 诊断出口抛错能杀 worker，close 可能假成功 | 诊断隔离；accepted/completed/failed/diagnostic_failures；死亡/未排空不能成功 |
| ShareStream 关闭 | handler join 超时被当整个服务排空 | 服务级 producer 登记与 admission lock；等待真实 IO 退出，退出锁不互相阻塞 |
| 字幕集号 | EP01,02 / 顿号 / 分号等多集文本误接纳 | 拒绝多集枚举，保留单季弱集号正控，不改视频版本语法 |
| 字幕季号/特别篇 | 中文季号、序数季号、OVA 等反证丢失 | 去规范片名后逐字段判断，保留可信同季包 |
| 验收身份 | recorder 工作区身份可能替代实际执行端 | schema 2 记录执行前后 root/commit/tree/status；拒绝 dirty、unknown、变化中和旧 schema |
| 解码诊断 | 多通道计数被覆盖，累计错误归入后续窗 | 原文、hash、时间和全部通道；同实例同通道无 reset 才计算增量；DV 双层不相加 |

原审查：`review-evidence/ce2025/review-a`、`review-b`。
外部证据：交付目录 `results/before`、`results/after-1`。
原字幕 AST 探针在辅助函数拆分后 exit 2，是接口不兼容；适配版只加载新增依赖，
不改断言。decoder 旧探针证明历史信息丢失，不能把它的 exit 0 当修复通过。
干净冻结版的正式门禁与这些诊断性 dirty 执行分开保存。

## Claude 四项需求

1. `tools/ce_ui_preview.py`：显式 source-root；只部署新皮肤和波比弹窗 UI，
   备份/暂存/journal/切换/ReloadSkin/真实 framebuffer，支持同事务回滚；
   并发变更拒绝覆盖。14 文件部署、回滚、再部署均实机成功。
2. 片库：Label2 + Kind/Manage；Kodi 清空 Label2 时保留独立 Location 属性，
   来源卡显示该属性。文件使用真实大小/日期，本机一次 scandir，网络一次目录 RPC。
   不对每个文件发 Stat/HEAD，不伪造未知大小。未登记可共享源的 NAS 可能被 Kodi
   metadata API 拒绝，浏览/手选播放可用但大小日期未知；本轮不声称真实 NAS 通过。
3. 自有插件所有翻页：`下一页` + `Bobi.NextPage=true`；保留页号/查询条件。
   未改独立上游插件的更新渠道。
4. 中文拼音：真实 `shi` 候选 500–509 → XML 400–409，10/10 写入；完成返回“试”。
   未用 setText / Input.SendText 代替真实选字。

交接命令、路径及接口详见 `CLAUDE-CE-UI-HANDOFF.md`。
预览不是 Kodi ZIP 安装认证；framebuffer 只有 GUI 平面，不代表硬件视频画面。

## 测试与实机状态

最终干净版：主测试 1963 passed / 6 skipped，历史基线 789 passed，准备回归 177 passed，
共 2929 passed / 6 skipped。跳过项是 Windows 环境不能建立 symlink 的夹具；
另有一条 JUnit record_property 格式警告，不隐去这些覆盖限制。
十项 schema 2 门禁全通过：三组测试、两次 source-check、重复构建比对、client-build、
sign、entry、artifact-audit，执行身份均绑定最终产品 commit/tree，前后 clean 且 stable。
产物审计 1357 文件与源码对应，签名及组件篡改负控均拒绝。

CE2028 通过实际入口、安装器及宿主安装完成：
`run-id=20261021-160900`，`tx=e8d35c47a32742c898aadfa57e870867`，phase=complete。
1150 个自有程序文件匹配最终签名包，原依赖与用户数据不覆盖。
入口是显式维护暂存后调用 packaged default.py/bootstrap，不声称 Kodi ZIP 浏览器安装验收。
CE2027 片库数据（Kind、Manage、Location、12.06kB、日期、下一页）通过；
来源卡视觉检查发现仍显示“打开目录”，CE2028 单独修正实际变量消费位置。
CE2028 `bobbi-library-1792570328053453100` 的最终截图已确认来源卡显示“本机目录”，
文件右栏 12.06kB / 2026-10-21；Manage 与下一页属性通过，临时来源已移除。
首轮 CE2028 探针被旧的已删除临时来源路径挡住（WAIT_EXPIRED），失败记录保留；
探针改为 ReplaceWindow 进入明确根目录，清理前先导航回根目录再 Home，
不让 Kodi 记住即将删除的 fixture 路径。此为验收工具修正，不改产品业务。
弹窗五种场景已截图；50 帧已显示卡片像素稳定、reset=0、选中项和1080p筛选保持。

## 新作品实播及未关闭项目

### 《完美的日子》 / Perfect Days（2023，TMDb 976893）

在 CE2026 上实播。69.1 GB 2160p REMUX DV HEVC，日语 DTS-HD MA 5.1，内嵌简中启用。
select 到观察到 AV 为 14.247 秒。起播严格时钟门禁失败：约 3.972 秒时钟不前进，
随后前跳 4.594 秒；同期解码帧持续增长、caching=false、drop/error=0。
因此不是“全部起播通过”，也不能单凭时钟证明电视画面卡死。
随后 30.299 秒观察内媒体前进 30.417 秒，短窗通过；约 162 秒仍未见解码错误。
原失败回执保留，已按确切播放实例停止；不以后段成功改写起播失败。

### 《别对映像研出手！》（2020，TMDb 92579，S01E01）

起播前已核对年份、标题、动画类型。CE2027 手选 115 的喵萌/VCB 1080p FLAC 版本，
未起播。日志关联同一请求：grant 阶段 152 ms、0 字节，115 API 4100010，
`ShareError / share_revoked`。这是上游分享不可用，不是解码或画质不足；不盲调缓存。
仍须把该源保持为失败，不以另一来源播放成功关闭它。
前两次 UI 探针因 picker generation 更换、旧窗未退出而阻断，未计播放成功。

CE2028 另一次明确手选已查到的喵萌/LoliHouse 1080p HEVC 简繁内封 BT 版本，
结果为 `metadata_timeout`，未取得目标文件资料，40 秒采样内没有 AV_STARTED。
真实选源框显示“等待 BT 元数据超时，尚未取得目标文件资料；请重试或选择其他片源。”
未私自延长全局超时、换种或降画质。这次动漫验收未通过，不能用有候选或已点击冒充播放。
完整记录：`ce-new-work-eizouken-select-1792570403677636000.json`，attempt=4。

### 历史与新增未关闭项

- 《布达佩斯大饭店》原 4K 起播卡顿：本轮没有完成同源复验。
- 《比宇宙更遥远的地方》上轮 ID 76013 实为 NFL Football Fanatic；已改成 76059，
  加起播前身份验证。错误身份不证明语言/字幕机制错误，但原 BT 46.401 秒 buffering
  是真实失败，不能抹除；本轮同 Stye 源未选中/未返回，未关闭。
- 旧《元气囝仔》资料失败：未新复测。
- 《映像研》结果中出现标题明确写 Nogizaka46 Drama 的同名真人版；未选用，
  这是待独立收口的候选身份过滤问题，不能声称全部检索结果正确。
- 完整一集自然续播、seek、手动 Off、播放中字体切换、字幕同步与长时观看，
  本轮没有完整实机覆盖；模拟/局部测试不能替代。
- 中国网络无代理直连、真实第二账号切换、真实 NAS 元数据不在本轮实测覆盖。

## 恢复与安全边界

只部署本轮程序组件。未动账号、CD2 1.0.19、挂载、Yatse、代理/VPS、固件/SYSTEM/eMMC，
未降画质、转码、自动换片源或改变手动字幕优先规则。
UI 预览回滚使用原 transaction；完整升级回滚使用“波比 TV · 开始使用”的已核验上一代，
不要手工覆盖 installation journal。程序回退不整库覆盖账号与观看记录。
签名私钥、账号状态不进入源码证据；维护者 TMDb 配置作为已有受控构建输入注入包。

## 证据定位

- 安装完成：`review-evidence/ce2023/entry-device-view-1792570214260264600.json`。
- 最终设备对应：`review-evidence/ce2023/installed-files-1792570238300310000.json`。
- 最终片库截图/回执：`results/library/bobbi-library-1792570328053453100/`。
- 拼音：`results/keyboard/bobbi-keyboard-1792567368931001500/`。
- 五种弹窗与稳定卡片：源码证据内 `review-evidence/bobbi-ui-smoke-1792567876265750700/`。
- 两次预览/回滚：`results/ui-preview/`。
- 构建冻结：`results/clean28-*/result.json`、三份 `clean28-*.xml`、
  `results/product28-source-package.json`。
- 冻结后仅验收工具/交付守卫补测：`results/final-handoff-tools.xml`，28 passed；
  不把这次 dirty 工作区执行算进冻结版 2929 项。
- 新电影：源码证据内 `review-evidence/ce-new-work-perfect_days-*.json`。
- 新动漫的 picker 阻断、分享撤销、BT 超时：源码证据内 `review-evidence/ce-new-work-eizouken-*.json`
  及 `review-evidence/ce2023/entry-device-diagnose-1792569918118995000.json`。

测试后不保留播放或测试弹窗，临时片库注册已移除。没有删除用户媒体或观看数据。
