# Bobbi TV CE2049 独立审查报告

审查日期：2026-10-22。对象为公开测试预发布 [ce2049-reviewed-20261022](https://github.com/2223M1/bobbi-tv/releases/tag/ce2049-reviewed-20261022)。这是对实际发布资产、固定源码、CI 和维护者原始设备记录的新审查；没有操作用户设备、账号或 GitHub 写接口。

远端最后复核：2026-10-22 08:32:27 UTC（北京时间 16:32:27）；标签、main、8 个资产的 ID/大小/摘要和发布正文均未变化。

## 1. 结论与发布建议

**CE2049 在安装完整性、取消控制和失败状态保留方面有实质进展，可以继续作为有限范围的测试预发布；目前不具备稳定版放行依据。**

上轮坏旧备份回退和入口外壳绑定两项已关闭；慢 header/body 返回后残留线程的原反例也已关闭。本轮还独立确认了本地 Back 与 IPC 恢复交错修复，以及失效分享跨普通查询退出推荐的主路径。

本次新增两项可复现的 **P2**：

1. **R49-01：QQdocs 可选失败记忆写入超时，会覆盖已经产生的播放成功值或原始错误。**
2. **R49-02：合法 localhost 双地址建连重复消耗 timeout，突破保活请求总预算并延迟 Back。**

这两项均有原始 JSON、源文件 SHA 和独立脚本，主审均已复跑。未将故障注入说成设备发生率，也未把 R49-02 误写为函数返回后仍有线程存活。

观看验收仍有明确阻塞：维护者的《心灵驿站》在播放位置 36.269 秒进入持续缓存，后续 30.390 秒播放进度为 0。《日常》取得短时正向结果，但不足以替代长时间观看、自然 EOF、BT→115 同版交接和字幕视觉/同步验收。

**下一轮建议：先分别修复这两项 P2，再聚焦持续缓存及观看证据。暂缓扩大功能和新一轮 UI 改版。**

## 2. 固定对象与实际资产

| 对象 | 本次核验值 |
| --- | --- |
| 发布标签 | ce2049-reviewed-20261022 |
| Release ID | 420442133 |
| Release 状态 | draft=false；prerelease=true；immutable=false |
| 标签 / 审查时 main / CI head | 43e3a296f5982a6b235421cbffb61c3eae65a84e |
| 交付树 | 78873689f059a5af677eddade372bf635ca66be2 |
| 产品修复提交 | 81482d32fd25c04ca6ebb73ef5636f5e35414a3e |
| 产品树 | e127c75423fc598f3b98a5efd1719d8154b83ecd |
| 上轮交付基准 | 1ce3ec9cb779be5fc3effcfe56d0422e3c5039fd |
| 上轮产品基准 | 5d6a77d78a278984517f3e4af99c239054e9ba4a |
| 完整源码核验 | 4,865 个 Git blob；539,622,132 字节；每个 blob 的 Git SHA-1 与 SHA-256 已复算 |
| 两次交付间差异 | 182 个文件：154 新增、28 修改；其中 145 个为 review-evidence，37 个为其他文件 |
| 产品改动范围 | 15 个 Python 文件、6 个 addon.xml；其余为测试、工具、索引和文档 |

标签与 main 已固定为同一提交。通过两个 Git tree 的逐路径比较，产品提交与交付提交中的 addons、third_party/addons 和 source-inventory 完全一致；后续维护工具和证据提交没有改变已签组件。详见 [固定提交](https://github.com/2223M1/bobbi-tv/commit/43e3a296f5982a6b235421cbffb61c3eae65a84e)、[本次差异](https://github.com/2223M1/bobbi-tv/compare/1ce3ec9cb779be5fc3effcfe56d0422e3c5039fd...43e3a296f5982a6b235421cbffb61c3eae65a84e) 和包内 metadata。

### 实际公开安装包

| 资产 | 字节 | SHA-256 |
| --- | ---: | --- |
| script.bobbi.start-CE2049.zip | 95,976,371 | bcd8470f2450f5c563455221809c0d837f46654e78f2b46ccb0905ba03c75dde |
| BobbiTV-CE2049.bobbi-update.zip | 95,871,137 | d602adcc310391b08de0dc4e94905e829bc1dad7ba33581eab1835d94569cc94 |

已下载并核对全部 8 个 Release 附件的大小和 GitHub 发布摘要，报告附件也与固定源码中的交付报告逐字节一致。

对真实安装包另外完成：

- 验证内嵌完整载荷签名和序列 2026102049；
- 验证内嵌载荷与公开更新包逐字节相同；
- 验证 22 个组件的成员集合和源清单中的每个文件摘要；
- 使用已验证的源码及安装包内唯一明确的应用配置输入，在临时目录重建全部 22 个组件 ZIP，均与签名载荷内组件逐字节相同；
- 验证外层 17 个成员严格来自同代签名入口、bootstrap 和完整载荷；17 是本版观察值，审计逻辑没有把成员数量硬编码；
- 检查成员集合没有额外的账号目录、设备备份或私钥条目。完整包含既有构建契约允许的 TMDb 项目应用配置；其内容没有在审查输出中披露。

“签名有效”“来源一致”“可重复重建组件”分别有检查，不以其中一项代替其他项。没有签名私钥，也没有宣称重新生成了整个签名发行包。详见包内 check_published_delivery.py、delivery-verified.json 和 [入口审计源码](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/tools/audit_ce_entry.py)。

## 3. 上轮及本轮修复复核

| 原问题 / 主张 | 本次判断 | 独立依据 | 保留边界 |
| --- | --- | --- | --- |
| R47-01：坏旧备份仍被记为 restored | **关闭** | 原反例 4/4；新增真实进程丢失 4/4；安装恢复专项 65 passed | 未冒称所有文件系统故障或冷安装认证 |
| R47-03：外壳未完整绑定签名入口 | **关闭** | 真实 CE2049 原件 + 7 种变异共 8/8 | 下一发行包仍需绑定自己的真实摘要 |
| R47-02：慢 header/body 返回后有残留保活线程 | **关闭原反例** | 原慢体 2/2；源码真实 HTTP 探针 14/14；返回时及 close 后均 0 worker | 建连阶段另有 R49-02，不能写成全部 HTTP 总预算已完整解决 |
| 本地 Back 后 IPC 恢复又触发播放 | **关闭至已覆盖代码路径** | 原反例 1/1；字幕及最终派发交错 4/4；均 0 次媒体派发 | IO 边界使用明确替身，没有代替设备所有操作时序 |
| 失效分享跨普通查询仍推荐 | **主路径关闭** | 11 个现有回归通过；Planetes 同稳定键跨新查询退出推荐 | 可选写入路径另有 R49-01；该作品未播放成功 |
| 上轮 preAV 区分取消与控制不可用 | **保持关闭** | 独立旧反例 6/6、activation 边界 12/12 | 没有用异常吞噬或重发派发恢复 |
| 上轮“缺少实际 CE2047 安装 ZIP”证据缺口 | **本次 CE2049 已补齐** | 本次实际完整包、更新包和 22 组件来源核验 | 不追认未公开的旧包 |
| 像素无闪动、字幕视觉与整集观看 | **仍未完成** | 维护者报告保留 INCONCLUSIVE / 未验收 | 不因代码和安装测试绿态改写 |

### 3.1 回退修复为何足以关闭旧问题

[ce_installer.py](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_installer.py#L27-L57) 现在记录旧程序的路径、模式和内容向量；主动回退在改 journal、停服务和移动 live 之前检查完整恢复计划。缺备份时，仅允许已经移回且与旧向量完全匹配的 live；不是简单用 backup.exists() 判断。

新进程丢失探针在实际 os.replace 之后执行 os._exit，覆盖升级移动空隙、回退移动空隙、已回退一个组件以及此后剩余备份损坏。前 3 类能恢复；第 4 类拒绝继续，保持恢复中状态和启动门，不把混合代次宣布为 restored。用户数据和无关插件哨兵不变。

旧 schema=1 正常终态允许继续升级；缺旧收据时不现场补造证明、不破坏性回退；host_pending、旧服务启动谓词和高水位兼容保留。原 4 例脚本逐字未改。

### 3.2 外层入口修复的真实资产验证

[审计器第 30–47 行](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/tools/audit_ce_entry.py#L30-L47) 从已认证的入口组件推导允许成员和字节，再绑定同代 platform bootstrap。实际 CE2049 ZIP 对 default.py、XML 版本、额外 Python、缺少成员、bootstrap 改动、重复成员和父目录路径全部拒绝。变异 ZIP 未执行、未安装，内嵌载荷字节没有被改变。

原 CE2045 反例硬编码的是旧资产摘要，不能冒称验证了新包。因此本次新增绑定 CE2049 真实摘要的探针，保留旧攻击条件并增加四类边界。

### 3.3 慢读与本地取消修复

请求现在有独立连接池和可 shutdown 的已建立 socket；调用线程拥有 Requests/response，watchdog 和 chooser worker 都 join。原慢体 Back、确认各约 0.048 秒返回，返回及 Backend.close 后 worker 均为 0；同 hash 只有一次 get，没有重发 add/preload。14 个源码探针使用发行树中的 Requests 2.31.0、urllib3 2.2.3，覆盖慢 header/body、取消、替代、异常、deadline 和 HTTP 拒绝。

原慢体脚本输出中的 production_join_seconds=6 是保留原脚本的历史字段；本版实际为无参数 join，不以这个历史字段描述 CE2049。

本地 Back 的 event 已贯穿 activation、可选字幕和两种最终派发路径。在服务端取消未送达而 IPC 恢复的反例里，仍无播放派发。参见 [native_player.py](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/addons/plugin.video.bobbi/lib/native_player.py#L123-L175)。

## 4. 新发现 R49-01 — P2：可选 SQLite 写入覆盖播放结果

### 位置与实际影响

[QQdocs catalog.py:329–347](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/addons/script.module.bobbi.catalog/lib/bobbi_catalog/catalog.py#L329-L347) 新增 remember()，给本地 Cache 0.2 秒预算，但只捕获 OSError 和 sqlite3.Error。真正的预算检查通过 [guard():20–24](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/addons/script.module.bobbi.catalog/lib/bobbi_catalog/catalog.py#L20-L24) 抛 ShareError('deadline')，该错误会向上逃逸。

| 远端已产生的结果 | 后续可选写入暂停 250 ms 后的当前结果 | 应有结果 |
| --- | --- | --- |
| 成功 URL | deadline，URL 无法交付 | 返回原成功值，继续执行原所有权/取消检查 |
| share_revoked，带原 HTTP/API 信息 | deadline，原类型/API 码丢失 | 保留原错误对象 |
| identity_changed | deadline | 保留原身份错误 |
| network_timeout | 原错误不变 | 保持；这类错误不写撤销记忆 |

### 复现强度

使用实际 resolve、selected、Cache 和真实临时 SQLite；远端 API 是替身，在远端结果已产生后、可选 Cache 的真实 bounded_sql 设置完成后注入 250 ms 调度/I/O 暂停。没有替换 guard、SQLite 错误或直接抛假 deadline。每例 API 只调用一次。

- CE2047 原 resolve AST 对照：6/6 通过。
- CE2049：3 通过、3 失败。
- 主审重新执行得到同样三个失败；另一审查分支完成源码因果链交叉复核。
- 证明这是条件性回归，不证明盒子已出现该故障或某一发生频率。

最终有效回执为 share/optional-metadata-deadline-final.json。对照源文件已与旧 Git blob d0ed85f598ebff815b4dfa13d045aac9ace808b9 对齐；早期多一个空行的副本仅作为历史保留，不能作为最终绑定。主审复跑为 share/root-crosscheck.json。

### 修复要求

将失败隔离限定在可选元数据路径自己的预算错误；保留原成功值或原错误对象、HTTP/API 信息。不要在 resolve 外层吞掉所有 ShareError，不延长到几秒来掩盖问题，不重复调用远端 API。

用户取消、请求替换、账号代际变化，以及远端本身的 deadline，仍必须中止。新增验证应覆盖成功、永久错误、远端临时错误、取消和账号变化与可选写入重叠；同时保持现有 6 小时、1024 条、账号+epoch+精确 tuple 的记忆边界。

## 5. 新发现 R49-02 — P2：localhost 双地址建连叠加预算

### 真实本机复现

这是实际操作系统地址枚举和 socket 故障夹具，没有伪造 DNS 或 connect。合法 endpoint 为 http://localhost:随机端口，系统返回 ::1 和 127.0.0.1；两个监听 socket 的 accept 队列都被填满。

| 指标 | 专项审查 | 主审复跑 |
| --- | ---: | ---: |
| 保活请求预算 | 2 秒 | 2 秒 |
| 请求总耗时 | 4.022 秒 | 4.025 秒 |
| Back 后等待 | 3.957 秒 | 3.960 秒 |
| 建连期间 socket 注册次数 | 0 | 0 |
| 返回后 worker | 0 | 0 |

单地址对照约 2.017 秒完成；单独 0.3 秒 deadline 约 0.310 秒返回。这排除了“只是所有网络测试都慢”的解释。

### 原因和范围

[http_io.py:49–53](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/http_io.py#L49-L53) 在整个 super()._new_conn() 返回后才注册 socket。vendored [urllib3 connection.py:60–77](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/third_party/addons/script.module.urllib3/lib/urllib3/util/connection.py#L60-L77) 对每个地址重新应用相同的 timeout；[backend.py:147–151](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/addons/plugin.video.bobbi.torrent/lib/bobbi_torrent/backend.py#L147-L151) 只在进入请求前计算一次剩余时间。watchdog 无法关闭未登记的连接，chooser 的 join 必须等待后续尝试结束。

配置明确允许 localhost，因此不能用“不允许远程域名”排除这个用例。它是总预算和取消响应的窄范围缺口，**没有复现返回后残留线程，也不证明真机宕机或错播**。

另一个 getaddrinfo 阻塞用例是明确 IO 替身，只记录为 socket 创建前的范围限制；不把它提升成真实设备 DNS 事故。

### 修复要求

每个地址尝试共享一个绝对截止时刻，进入下个地址前重查剩余预算和当前所有者；将正在建立的 socket 纳入本请求的可取消管理。保留 localhost、IPv4/IPv6 和 HTTPS Host/SNI/证书校验，不修改上游通用库全局行为，不取消其他请求的连接。

包内 assert_connection_budget.py 将观察转成显式门槛：2 秒预算允许 0.4 秒调度容差，Back 建议在 0.5 秒内返回且 0 worker。这是审查提出的工程验收值，不是宣称已有设备响应认证。缺双栈环境必须记 INCONCLUSIVE，不准写通过。缩短 join、改 daemon、放任后台连接继续运行均不满足要求。

## 6. 设备证据：取得的进展和不能扩大的结论

以下为**维护者收集的设备记录，审查者独立读入、复算并检查截图**；本轮没有直接控制设备。

### 6.1 安装、坏备份拒绝和正常回退

原始记录支持 CE2048 菜单安装、暂时移走旧备份文件后的拒绝、恢复备份后正常回退，以及用更高序列 CE2049 重新安装。

- 坏备份演练工具记录 live 和 journal 未变，移走文件已复原。
- 正常回退记录 phase=restored、host_pending=null，工具记录 12 个组件匹配旧向量。
- 最终 CE2049 为 complete、host_pending=null；真实皮肤保留确认后为 skin.bobbi.cinema。
- 记录保留安装等待超时、皮肤未确认和重启等待超时，未覆盖失败原件。
- 维护者经受限传输暂存入口后操作真实入口/菜单；这支持该安装路径，**不等同于 Kodi“从 ZIP 安装”浏览器的冷安装认证**。

CE2048 回退后保留高水位，因此另签 CE2049 的做法有依据，不能要求重新播放旧序列或手改 journal 来刷通过。参见 [固定交付说明](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/docs/CE2049-REVIEW-DELIVERY-20261022.md) 及包内 device-evidence-recomputed.json。

### 6.2 《心灵驿站》：启动有进展，持续观看明确失败

TMDb 2056，2003，选取同一 1080p AMZN NTb BT 源。选择到首次观察 AV 为 4.0866 秒；此值是观察上界，不是精确原生开始事件时间。原 select 记录仍为 exit=1、trace_passed=false，启动轨迹的异常没有被抹掉。

后续观察中：

- 4 个采样均为 caching=true；
- 播放位置始终 36.269 秒；
- 墙钟推进 30.3895 秒，播放推进 0；
- 解码帧计数保持 886，丢帧/硬件错误仍为 0；
- 英文音轨和外挂字幕应用状态有记录。

所以“4 秒开播”“无硬件错误”“字幕已加载”都不能证明观看通过。停播后的同 hash 状态请求得到 404，只支持停播后查询结果，不能推断停播前断供根因。需要在卡住当时采集同 request/native instance/file identity 的播放器、下载和后端状态。参见 [select 原件](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/review-evidence/ce-new-work-station_agent-select-1792654576203689600.json) 和 [observe 原件](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/review-evidence/ce-new-work-station_agent-observe-1792654643260298900.json)。

### 6.3 《日常》：短时通过，启动和字幕结论须限定

TMDb 44684，2011，S01E01；选取 7³ACG 1080p HEVC/OPUS。首轮错误 TMDb 夹具和旧稳定键选择被拒绝的记录保留，不计作产品错误或通过。

确认具体 S01E01 文件后成功进入 AV，长人工停留未使种子丢失。选择至首次 AV 观察为 154.5787 秒，包含人工停留和 preload，不是“秒开”。

后续 4 个采样：

- 墙钟 30.3486 秒，播放从 59.347 推进到 89.627 秒，差 30.280 秒；
- 同一请求、native instance、open_epoch 和文件身份；
- 采样 caching=false，解码帧从 1444 增至 2171，无丢帧/硬件错误；
- chi / chs[FLsnow] 字幕处于启用状态。

可以记为**该 30 秒观察窗口的有限通过**。10 秒左右间隔的 4 点采样不证明中间没有任何短顿、渲染完全连续或整集完成。音轨语言字段为空，不能仅凭作品原语言和 OPUS 标签宣称已验证日语原声。两张审查者查看的字幕平面截图均未捕捉到可见对白，不能认证字幕字形、裁切或同步，也不能把 GUI 平面黑图直接认定为视频黑屏。参见 [首次 AV 记录](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/review-evidence/ce-new-work-nichijou-wait-1792655190347874000.json) 和 [后续观察](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/review-evidence/ce-new-work-nichijou-observe-1792655278920873100.json)。

### 6.4 《星空清理者》：失效卡状态保留有证据，播放失败原因不能补写

同稳定键 c04661468ccc9e37880b2f5b24a62d1542ff92d4b97d2a92e555b5ecb6e40aa8，旧普通查询为“推荐”；新 ordinary_ui=true、force_select=false 查询后为“分享已失效 · 可手动重试”，推荐标记为空，BT 候选仍在，generation 从 57 到 67。

这支持跨查询状态保留和退出推荐，不支持上游分享修复或该片播放成功。本轮 wait 只有一个 cancelled=true、native={}、failure=null 样本，health 记录 PLAY_ISSUED 后 SELECTION_CHECK_SELECTIONCHANGED，没有给出该 attempt 的 typed 4100010 回执。**不能把上轮的 API 码填进本轮缺口。**

详见包内 share/planetes-evidence-summary.json、[查询前卡片](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/review-evidence/ce-new-work-planetes-cards-1792655431500827700.json) 和 [查询后卡片](https://github.com/2223M1/bobbi-tv/blob/43e3a296f5982a6b235421cbffb61c3eae65a84e/review-evidence/ce-new-work-planetes-cards-1792655606534145300.json)。

## 7. CI 与测试计数

实际 [GitHub Actions run 39743912719](https://github.com/2223M1/bobbi-tv/actions/runs/39743912719)，push / attempt 1，head=43e3a296…，2026-10-22 07:59:23 UTC 完成，conclusion=success。日志中的实际 checkout commit 和 tree 均与本次对象一致。

下载原始 Actions artifact 12410596397，82,677 字节，SHA-256 为 ed800897b83840e49a566fd182d87961ae9035f5a477ab33424a1bd9c6688637。Release 的 CI-tests.zip 为 80,939 字节，容器摘要不同，但三个 JUnit 文件逐字节相同，没有把维护者改写的摘要当原始 CI。

| CI 分组 | 通过 | skipped | xfailed |
| --- | ---: | ---: | ---: |
| primary | 3565 | 6 | 1 |
| baseline | 1027 | 0 | 0 |
| preparation | 254 | 0 | 0 |
| **合计** | **4846** | **6** | **1** |

共有 4853 个互不重复的 testcase ID，0 failure、0 error。另有 1 条 record_property 兼容警告。CI 执行两次 source-check 组件构建和字节比较；source-check 不含本地应用输入，不能当可安装包。

维护者 Windows 本地最终 JUnit 为 **4844 passed / 8 skipped / 1 xfailed**。Linux 与 Windows 的跳过集合不同：Linux 跳过 5 项真实 Windows 管道 API 和 1 项可选大型 Matroska/ffprobe fixture；Windows 跳过 8 项 POSIX 模式/符号链接用例。净差 2 项通过并不矛盾。盒子补测的模式和链接不能把其余本地 skipped 全部改写为 passed。

xfail 仍是《别对映像研出手！》真人行缺少强类型证据的已知项目；本轮没有修复或重新验证它的产品表现。

审查者选取的 65 个安装/恢复测试和 11 个分享回归共 76 个仓库用例均通过，属于 CI 子集，不累加。原反例、新故障注入、CI 和维护者设备观察分层保留。R49-01 的 3 个失败与 R49-02 的门槛失败是本轮主动复现的开放问题，不应隐藏。

## 8. 后续规划与验收顺序

### 第一阶段：两个最小产品修复

分开提交 R49-01 与 R49-02，先保留红态，再完成修复及回归。R49-01 只隔离可选本地元数据错误；R49-02 只补齐建连阶段绝对预算和取消所有权。保持播放器、选源身份、分辨率、码率、原语言、释放版本、无重复 add/preload、既有签名和高水位语义。

完成条件：新增反例从红变绿，原回退 4 例、恢复空隙 4 例、外壳变异、慢读、取消及分享隔离全部保留；全量三组 CI 基于实际待交付提交重跑。

### 第二阶段：查清《心灵驿站》持续缓存

在同一原始 NTb 1080p 选源上，采集卡顿前后同步证据：请求/native/open_epoch/文件身份、播放时钟、decoder frame、caching、TorrServer 同 hash 的状态/下载速率/有效 buffer、本次文件大小和实际 Range 行为。避免用停止后的 404 解释停止前的原因。

根据证据定位供给不足、流请求/Range、生命周期或播放器消费问题，再决定代码修复。不得为了绿态换低码率源、降分辨率、转码或关闭解码功能；一次失败也不应永久拉黑整部作品。

### 第三阶段：补齐观看证据

保留《日常》的新作品正向样本，延长观察并覆盖至少一次接近或完成自然 EOF 的真实路径；测试准确同版续播。字幕应在真实对白段采集可见内容和同步观察，同时验证用户关闭字幕后不会被自动打开。BT→115 交接必须保留精确作品/季集/文件与版本映射、播放位置、音轨与字幕意图，不得静默换源。

冷安装按照既有稳定版条件补齐当前目标环境的 Kodi ZIP 浏览器路径，不新增未知设备弹窗、机型白名单、第二台设备准入或原生哈希门槛。其他硬件仍标明未测；既有“全部稳定”表述在完成前保持关闭。

### 第四阶段：准确交付

使用真实新的高水位序列，记录产品 commit/tree、交付 commit/tree、实际资产字节和摘要、签名验证、组件向量、原始 CI run、设备收据及未完成项。CE2045 和 CE2049 旧发布原件保留，不覆盖或重放旧序列。README/Release 继续简明提供下载、安装路径和已知限制，不把内部审查脚本和实现细节塞入普通用户安装流程。

执行步骤、文件位置、命令、验收矩阵详见 **02-CODEX-EXECUTION.zh-CN.md**。

## 9. 交付包与复核方式

包内提供：

- 本报告、下一轮 Codex 执行说明、机器可读验收矩阵；
- 两项新问题的实际可执行探针、最终回执及主审复跑；
- 上轮反例、本轮恢复与外壳负面验证、原始 JUnit/日志；
- 实际 Release 元数据、两个 Git tree、完整源码 blob/SHA-256 清单、CI 原始附件；
- 145 个本轮新增或修改的维护者证据文件及其固定 URL / 摘要索引；
- 公开资产下载与校验脚本、安装包来源核验和设备证据复算脚本；
- MANIFEST.sha256 与包外 ZIP SHA-256 文件。

完整安装 ZIP 和完整 Git 源树不重复塞入审查 ZIP；通过固定公开 URL 下载并校验。包内脚本只做本地临时文件、测试签名、隔离解释器和回环 socket 验证，不安装 Kodi 插件、不调用设备工具、不发布 GitHub 内容。

审查范围的限制已经写入每项结论：源码测试不代表观看认证，IO 替身不代表真实网络事故，短时播放器进度不代表整集/字幕视觉通过。所有开放项在验收矩阵中保留。

