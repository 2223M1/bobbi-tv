# PR #3 发布、验收工具与设备证据独立审查

固定 head：`c8de17ae9dabbe0f37753e1751b1d88107311316`。Base：`ee65742bfcbaf08831f70306faed11bd1f8d6cc6`。本报告只进行源码、已存回执与 CI 核查，没有连接盒子、修改仓库或发布。

## 结论

上一轮 R06 在原 `ce_playback_trial.py` 范围内已修复。原四项正反例全部通过，另加的 11 项 operation 结果检查全部通过，两者存在覆盖重叠，不应合计成 15 个独立问题或全新覆盖。真实《罗生门》失败回执也正确保留 `transport_exit_code=0`、`trial_exit_code=1`、`exit_code=1`。

未在本次发布/验收工具审查范围确认新的阻断性产品缺陷。新辅助工具的落盘退出码仍有一致性改进项 C01；它不推翻 R06 原修复。新标准链设备证据比 PR #2 更完整，但应按真实范围描述。

## 原始 CI 核查

两套原始 ZIP 已通过 GitHub Actions 专用下载工具获取，并核对 GitHub 提供的摘要及每份 JUnit：

| 对象 | 实际 checkout | 树 | JUnit |
| --- | --- | --- | --- |
| push 39448450410 | c8de17ae9dabbe0f37753e1751b1d88107311316 | cc12e00ccba0d7cb9a8b310306437e0e8ef84ae3 | 1746 + 761 + 177 = 2684 passed，5 skipped，0 failures/errors |
| PR 39448461338 | f6adafd1fd5a39b58853f0d6f0d43dd758ba3062 | 同上 | 同上 |

5 个 skip 均为 `tests.test_maintenance_lease` 的真实 Windows inherited-pipe API binding 变体。两份日志均出现 `Reproducible files: 63`，对应工作流的第二次 source-check 构建比对。日志为 shallow checkout，parents 空字段不表示提交没有父节点。

原始 ZIP：push 45,977 字节，SHA256 `353cdc54be97b5906e29290f4acf395b1c2642bb48f004d2f31e9c04b8393db2`；PR 46,396 字节，SHA256 `7e0894e4fe85e7d9cf54e137cf38ba20f3f62aed46d2194cc013dfd36f85fc93`。

来源：[push run](https://github.com/2223M1/bobbi-tv/actions/runs/39448450410)、[PR run](https://github.com/2223M1/bobbi-tv/actions/runs/39448461338)。本地证据：`CI-JUNIT-VERIFIED.json`、`CI-SUMMARY.json`、两份原日志及 ZIP。

## R06 修复与 C01 建议

`tools/ce_playback_trial.py:12–34` 为 select/observe/stop/cancel 定义必须为 true 的字段；明确 false 和缺失必须字段返回非零，cards/inspect 正常读取及 not_tested 有区分。main 在写证据前计算业务结果，保存三种清晰字段，最终命令采用业务结果。

源码：[ce_playback_trial.py](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/tools/ce_playback_trial.py#L12-L34)。

新增 `ce_standard_real.py:44–48` 的回执仍保存 `exit_code=rc`，而其命令实际返回值另行计算。读取首轮真实失败回执，通过真实 main 与明确的临时 transport 替身重放：

| 输入 | 实际命令结果 | 落盘 exit_code | 落盘 trial_exit_code |
| --- | --- | --- | --- |
| 原始标准续播失败，passed=false | 1 | 0 | 缺失 |
| 原始标准续播成功，passed=true | 0 | 0 | 缺失 |
| 明确 running / passed=null | 0 | 0 | 缺失 |

这证明落盘通用字段的含义与命令结果不一致。应同步统一新标准链、UI、grant 辅助工具的结果信封，明确 transport、trial 和 pending。当前标准工具对明确业务失败的进程退出已经正确，running=0 可以表示异步启动/轮询命令成功，因此不宜把这些现象写成“播放失败仍被 CLI 当成功”或直接升级为新的产品 P1/P2。

建议编号 C01，非阻断的证据一致性改进；不要用这些工具的 `exit_code` 单独汇总播放通过率。`ce_ui_smoke.py:40–49`、`ce_grant_probe.py:105–108` 同样值得统一字段。

反例脚本：`check_trial_drivers.py`。执行：

    python check_trial_drivers.py --repo /path/to/bobbi-tv --evidence /path/to/pr3-release/evidence --output /path/to/new-result-dir

输出 `tests` 是 11 项独立操作契约；`new_driver_observations` 是客观记录而非人为添加失败断言。没有真实网络或设备调用。

## 设备证据的实际强度

### 标准策略真实来源下一集

已读最终回执 `ce-standard-real-1792509830895851000.json`，并核对 `ce_standard_real_remote.py`：未替换 next_loader，真实 Juku/115 寻源/取址，真实 StandardSession、StandardPlayback、Handoff。

- 首集同版来源为 `[philosophy-raws][Cowboy Bebop][01][BDRIP][Hi10P FLAC][1440X1080].mkv`。
- 明确 `StartPercent=97`，从片尾开始；不等于整集播放验收。
- 第1集以 1482.693 / 1483.523 的最后有效进度结束，历史记录为 NATURAL_EOF、completed=true。
- 后继标题只改为 [02]，第2集获得新 request、记录 STARTED，进度到 11.198 / 1337.568 秒。
- `last_handoff` 记录该后继 submitted。原回执有一次新后继开始，但它不是每次底层 RPC 调用的完整逐条日志。
- 最后的 SERVICE_STOPPED 属于测试清理；F9 原生方法用于限定实例的清理，不用于标准生命周期判断或后继交付。

工具仍是临时 RunScript 组装薄 Accounts/view 适配，history 回调改为记录回执，未经过普通用户完整选源 UI 与真实观看历史持久化。因此可说“真实来源的标准策略片尾交接得到实机证据”，不可说“普通用户全链、整集流畅、中文字幕或其他 CE 硬件全部认证”。

来源：[最终回执](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/review-evidence/ce-standard-real-1792509830895851000.json)、[生成工具](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/tools/ce_standard_real_remote.py)。

### UI 70 次采样

最终 result.json 明确为真实已安装 UI、合成卡片和 example.invalid 二维码，无账号交换或播放。来源工具以约 40ms 轮询 `/dev/fb0` 的首卡静态文字/底色 ROI；70 次摘要相同，reset=0、focus_commands=0、原 ListItem 和选中 key 保留。

这是受测 ROI 与增量追加场景的证据，不是完整视频的 70 个连续帧，也不覆盖所有 UI 交互。本轮取得并 Git blob 校验 account、metadata、sources-after 三张 PNG；terminal、sources-before 因 GitHub 当前二进制接口边界未能取得，不声称已查看它们。

来源：[最终 UI 回执](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/review-evidence/bobbi-ui-smoke-1792509859790208700/result.json)、[采样逻辑](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/tools/ce_ui_smoke_remote.py#L73-L85)。

### 开放观看问题

《十二怒汉》同一已选文件：58,762,851,801 字节；本次取址 266ms，resolved=false、ShareError/share_unavailable，API state=false、errno=4100010，安全词表归为 share_cancelled。词表同时包含“已取消”和“已失效”，严谨表述是“上游明确报告分享取消/失效类别，原分享仍不可用”，不说已经修到可播。

《罗生门》：80 个连续启动采样保留。约 6.539s caching，其中约 5.032s decoder 静止；另有约 3.989s 媒体时钟静止但 decoder 推进。旧健康判据记录 13.025s 综合异常段仍失败，但这不能等同于画面实测冻结13s。后段30.319s推进30.322s且4点正常，只证明后段观察窗口。

《四叠半》《玲音》《这个男人来自地球》的遗留问题仍在交付文档中开放，没有删除原失败或用后段通过冲销。设备回执来源和精确哈希列于 `DEVICE-SOURCE-PROVENANCE.json`。

## 发布资产核对边界

草稿 release id 418559049：draft=true，prerelease=false，target_commitish 精确等于本次 head。draft 已确保尚未发布，prerelease=false 本身不代表已经稳定发行。

- 用户入口 0.2.6，96,178,248 字节，SHA256 `59e133cf78faf6448475752c8e040dcdaf6146c4cd17184378b88db73aadd15d`。
- 载荷代次2026102014，96,011,740 字节，SHA256 `1658413e9d037beccfdf50161d2d4b9e959f530fb2dcc2d8ac4e9c102f3187a7`。
- 源码 ZIP 214,280,820 字节，SHA256 `206aee7a5becb8ee281a4f305d29e0a64d2e9068859f27063a375250f023af2d`。

资产大小、GitHub digest、入库 entry/artifact 审计报告相互吻合。现有报告写22组件、1392文件，签名、同代bootstrap、fresh-interpreter导入与篡改负例通过。本轮没有重新下载96MB真实包，也没有独立重做包验签；不能把这层元数据/报告核对写成“本轮实际安装包验证全过”。

源：[CE2014 私库草稿](https://github.com/2223M1/bobbi-tv/releases/tag/untagged-7e586cd5524fbc914b32)、[交付文档](https://github.com/2223M1/bobbi-tv/blob/c8de17ae9dabbe0f37753e1751b1d88107311316/docs/CE-FAULT-CLOSURE-2014-20261020.md)。

本轮新产物维护部署最终run为20261020-231800，文档明确只回到CE2013；普通clean ZIP、现场音画、第二真实账号仍未认证。这些边界应保留，不以第二台硬件缺失新增未知设备安装门槛。

## 补充生产补丁覆盖

最终收口时另读了以下 7 个固定 head 生产补丁、调用处及相关测试/XML。此处是独立代码复核；根审查者报告已执行的相关 89 项验证不计作本分审查者新跑的测试，也不与 CI 数量叠加。

| 模块 | 本次变更 | 本轮核对的行为 |
| --- | --- | --- |
| `bobbi_catalog/api.py` | 增补 ShareError 固定类别与有限数值 HTTP/API 状态 | HTTP 拒绝、直接 socket 超时、无效 JSON、明确 API 失败继续抛业务异常；未输出响应正文、Cookie 或带签名 URL。状态值只接受指定范围的严格 int。 |
| `bobbi_core/share_stream.py` | 流回执新增安全错误分类，HTTP handler 关闭等待 | `share_*` 类别与原 transport 大写类别都经过闭合 schema；观察字段保留 request/file 关联，不代替失败/取消策略。关闭先封闭 admission、撤销 binding/socket，再等待 handler 退出。 |
| `bobbi_core/image_cache.py` | HTTP handler 改为非 daemon，关闭时 join | `ImageService.close()` 先设 stop，再停 listener/等待 handler，随后移除其自身 token 对应的 runtime 文件；与 Host 释放运行 lease 的顺序一致。此改动提高 drain 完整性，不表示每个外部 IO 都有新增加的总截止时间。 |
| `bobbi_core/preparation_host.py` | owner join 从 0.3 秒改为等待完成 | 调用来自 Host 关闭路径；未见 owner 自行调用 close 形成 self-join。先撤销 lease，owner 的 finally 关闭 Session；ExitStack 最后注册的执行器先等待已接纳 IO，再关闭 provider/SQLite。未在账户提交锁内等待 owner。 |
| `bobbi_core/resolution.py` | 精确识别 1440×1080、960×720 两组 4:3 HD | 未扩展任意宽高范围；竖屏、任意尺寸、显式标签与尺寸冲突仍为 unknown。同版 `release_envelope` 的组名、季集、音频/编码、封装等身份约束未在此处放宽。 |
| `bobbi_platform/account_dialog.py` | 新 XML 二维码窗口 | 控件 100/101/102/103/9001 与 XML 对应，初始化设取消焦点；取消点击及后退动作只修改窗口取消状态。没有账号写入或播放器动作。 |
| `bobbi_platform/cloud_ui.py` | 原手工二维码窗口改用上述 presentation | 账号 expected scope、一次提交、取消/中止后的 late-confirm 防护、未确认回执不重复提交、finally 取消 QR 流及清理临时目录仍保留。窗口创建前失败也可由 window=None 安全清理。 |

对应阅读包括 `tests/test_ce2012_share_failure.py`、`test_share_stream_observations.py` 的错误 schema、`test_account_ui.py`、`test_ce2013_ui_style.py`、`test_ce2014_four_three_release.py`、`test_preparation_host.py`，以及 `test_ce2012_recovery_ui.py`/`test_runtime_host.py` 的 lease/drain 契约。`test_provider_streaming.py` 的变更仅使替身接受新增关键字参数。`account-login.xml` 的控件、焦点和样式契约已交叉核对；原始 UI 图片与纹理 blobs 的查看由根审查者另行覆盖。

在上述七项变更内未确认新的阻断性遗漏。明确保留一个非阻断诊断边界：当前 `Client.get` 将直接 socket 超时分类为 `network_timeout`，但 `URLError(reason=socket.timeout(...))` 仍落入原 `network` 类别。这是错误分类不完全细分，不会把请求失败变成成功，也不应列成额外播放阻断项。实际固定 head 函数配合明确构造的 opener 异常已重放三项正控/变体，记录在 `SUPPLEMENTAL-DIAGNOSTIC-OBSERVATION.json`；这些输入不是新的实机日志。若后续要求精确区分连接超时，可只规范化安全的 `URLError.reason` 类型，继续丢弃原异常文本。

此补充不推翻其他分审查的安装生命周期、非首行选源焦点及原生 monitor 问题。选源队列语义的独立官方 Kodi 源码交叉挑战另见 `UI-CROSSCHECK.zh-CN.md`，应与本段七项补丁的确认范围分开引用。
