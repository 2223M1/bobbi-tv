# CE2021 新交付：安装恢复、停机与入口审计分报告

## 结论与范围

**当前 GitHub 分支无法证明 CE2021 安装与停机整改已进入可继续开发的源码。** 本域核对的 10 个关键文件，均与先前受审 CE2014 字节相同；旧 F01 的裸路径 `RunScript` 恢复分支仍在。报告所述受管恢复、认证本机协作退出、关闭失败保留 lease 并可重试等实现，没有出现在这次提交的产品差异中。本结论针对分支源码；不能据此断言另一份本地已测 CE2021 安装包没有这些修复。

**另已独立确认新增清理工具与当前入口审计之间存在契约冲突：清理删除 `bootstrap/LICENSE`，而入口审计无条件读取该文件。** 窄型复跑为 2 项中 1 通过、1 失败、0 执行错误。该问题并入主报告的构建/交付一致性项；它没有证明 Kodi 入口启动失败。

本域不把这些事实重复计成多项“本轮新增 P1”，也不把旧标准 history 停机加固建议升级为已证实的数据损坏。

| 身份 | 固定值 |
| --- | --- |
| 仓库与分支 | `2223M1/bobbi-tv` / `codex/ce2021-clean-delivery-20261021` |
| 候选 commit | `b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2` |
| 候选 tree | `bbe592e62a7a6790c62725738b63dae9b9f9405a` |
| 本次父提交/重写基线 | `f6ef6a7e3c5868a2ab8ed8e600a592d51ba97167` |
| 旧受审 CE2014 | `c8de17ae9dabbe0f37753e1751b1d88107311316` |
| 当前清理签名序列 | 报告和工具标为 `2026102022`；本域未下载或验签真实安装资产 |

固定提交与差异来源：[候选 commit](https://github.com/2223M1/bobbi-tv/commit/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2)、[相对父提交的差异](https://github.com/2223M1/bobbi-tv/compare/f6ef6a7e3c5868a2ab8ed8e600a592d51ba97167...b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2)。完整 tree 元数据不截断；差异只有整改报告、清理回执与 `tools/package_ce2021_github.py` 三个新增文件。

## 一、源码身份：可确认的是旧实现仍在

`LIFECYCLE-SOURCE-IDENTITY.json` 保存 Git blob SHA、两份实际源码的 SHA-256 和逐文件相等结论。当前快照的 Git blob 已再次按 `blob <length>\0<bytes>` 计算，并与固定 GitHub tree 相互核对。10 个文件是：

| 职责 | 当前与旧 CE2014 相同的文件 |
| --- | --- |
| 安装恢复/停机 | `addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py` |
| 宿主关闭与租约 | 同目录 `host.py`、`runtime.py`、`instance_lock.py` |
| 标准与原生服务生命周期 | `addons/plugin.video.bobbi/lib/portable_runtime.py`、`services/standard_playback.py`、`services/background_service.py`、`boot_gate.py` |
| 用户入口及其审计 | `addons/script.bobbi.start/default.py`、`tools/audit_ce_entry.py` |

### F01：分支仍是旧恢复路径，CE2021 二进制修复未独立验证

当前 [`ce_install_ui.py:174–201`](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py#L174-L201) 仍在 owner 回应失败且临时 OS lease 可取得时执行：

```python
self.xbmc.executebuiltin('RunScript(special://home/addons/plugin.video.bobbi/service.py)')
```

它与旧审查确认的问题实现完全相同。旧反例已区分原生导入需要 addon 身份、标准宿主需要受管 service handle 两条边界；本轮不把旧结果包装成新实机结果，也没有再跑同一套旧 4 项反例来增加数字。

当前 [`quiesce:89–125`](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py#L89-L125) 仍先发 `Addons.SetAddonEnabled(False)`，再等待 OS lease。它不是整改报告描述的“认证 owner 队列检查空闲 → 本地取消并排空 → 获得 lease → 停用和替换”。因此新协议的请求认证、owner 线程顺序、未知状态拒绝、老代次兼容分流与 15 秒总预算，均没有本轮可审计的新源码。

### G01：报告声称的停机闭环不能由当前源码支持

当前 [`HistoryWriter.close:36–38`](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/services/standard_playback.py#L36-L38) 仍使用 `join(timeout=.3)`；[`StandardPlayback.close:285–290`](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/plugin.video.bobbi/lib/services/standard_playback.py#L285-L290) 仍有字幕线程短 join；[`Host.close:346–379`](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/script.module.bobbi.platform/lib/bobbi_platform/host.py#L346-L379) 保留原先的 `stopping` 早返回与 `finally` 释放 lease。当前实现不能用来证明“任何 close 失败继续清理其他组件，保留 lease，并支持重试”。

旧标准 history 反例只证明晚于 lease 释放的任务仍活着；实际持久层还有自己的锁与合并逻辑，先前没有证明升级损坏数据。本轮继续保持这个限制。新增的协作退出与失败重试实现如果只在另一份安装包里，应取得那份代码和受测身份后独立核对。

## 二、报告的证据边界是清楚的，但证据尚未随分支闭环

交付报告明确说明：原来的 1764/782/177 成绩属于清理前候选，清理后的源码出现 `Source inventory changed`；新签名序列来自对原已测包的文档清理重打包；清理包没有再部署、没有新增干净安装或回退认证。评审应保留这些诚实边界，而不是把报告当作声称“当前源码全绿”。来源：[整改报告第 161–199 行](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/docs/CE-REVIEW-CLOSURE-2021-20261021.md#L161-L199)。

不过，报告用于支持新生命周期的最终测试、最终入口 audit、签名负例与设备恢复回执，在当前完整 branch tree 中并不存在。`REPORTED-EVIDENCE-AVAILABILITY.json` 精确列出本域检查的 10 个路径，均为 `present_in_branch=false`。其中包括最终 adapted review、prior18/prior15、主套/继承套/准备链、入口 audit、artifacts，以及 CE2021 三轮恢复和 CE2019 停机场景回执。

这些文件可能位于 release 交付合集。本域没有取得合集字节，不能写成“证据不存在”，也不能把报告中列出的通过数算成本次独立重跑。下一步需要使证据路径可取、源码身份可追，并说明适配过的夹具有哪些变化、为何仍保留原来的行为断言。

## 三、已复现：清理策略与入口审计不一致

### 源码链

1. 新工具 [`EXCLUDE:20–23`](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/package_ce2021_github.py#L20-L23) 匹配独立 `LICENSE`；[`clean_archive:70–75`](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/package_ce2021_github.py#L70-L75) 删除命中项；第 171 行实际将它用于用户入口 ZIP。因此 `script.bobbi.start/bootstrap/LICENSE` 被清理。
2. 当前 [`audit_ce_entry.py:49`](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/audit_ce_entry.py#L49) 无条件执行 `entry.read('script.bobbi.start/bootstrap/LICENSE')`。
3. 新工具检查 ZIP 完整性、排除规则、非排除文件摘要与完整载荷签名，但没有调用 `audit_ce_entry.audit`；这些通过项不会覆盖上述审计契约。相关位置为清理工具第 90–116、171–184 行。
4. 当前 [`build_ce_entry.py:40`](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/build_ce_entry.py#L40) 还要求从 platform 组件读取 `LICENSE` 再复制进 bootstrap。它与清理后组件的文件集合也未协调；本域仅静态确认该读取，不把它计成另一次实际构建复跑。

### 最小复跑

`reproduce_clean_entry_audit.py` 加载候选真实清理和审计函数，使用候选真实 bootstrap 模块、addon.xml 和 default.py 构造两份入口。原件包含 `bootstrap/LICENSE`，清理件由真实 `clean_archive` 得到。

| 检查 | 结果 |
| --- | --- |
| 原件执行当前入口审计 | 通过 |
| 清理件执行当前入口审计 | `KeyError`，缺少 `script.bobbi.start/bootstrap/LICENSE` |
| 清理件 `check_nested` | 通过 |
| 非排除 bootstrap 字节摘要比较 | 相同 |
| 真正隔离 Python 解释器导入 bootstrap | 实际执行，通过 |
| 统计 | 2 项，1 通过 / 1 失败 / 0 执行错误；脚本退出 1 |

这里仅将 `SignedBundle` 和 `load_trust` 替换在签名/组件载荷夹具边界。没有下载真实 release 资产，没有私钥，没有真实签名校验，也没有设备操作。结果 JSON 明确将该边界写成 `fixture; cryptographic verification not executed`，不会把原 audit 的成功字段误当成验签证据。

复跑命令：

```bash
python reproduce_clean_entry_audit.py \
  --repo /path/to/bobbi-tv \
  --output CLEAN-ENTRY-AUDIT-CONTRACT.json
```

需要候选工具原有的 Python 依赖（包括 `cryptography`）；脚本只读取候选，在系统临时目录生成夹具与隔离导入文件。

复跑结果中的 `review_reference_commit` 只表示本分报告固定的审查基准；`actual_checkout_commit` 从所传仓库本身读取，非 Git 快照或仅位于其他仓库之内时为 `null`。本次复跑使用按 tree 核对的源码快照，因此该字段为 `null`。实际执行文件身份以 `sources[].sha256` 为准，不能把固定审查基准误当作未来候选的 HEAD。

### 实际影响与不能推导的结论

现在同一份清理入口能够满足新工具的“递归 ZIP/排除文档/非文档字节不变”检查，却无法通过仓库的既有用户入口审计。后续维护者不能用两个检查任意替代对方，也不能沿用旧入口 audit 回执来宣布清理入口已通过当前审计。

[`default.py`](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/addons/script.bobbi.start/default.py) 启动时加载 bootstrap 路径并调用安装 UI，没有读取 `LICENSE`。本域没有证据支持“删文档会让 Kodi 启动失败”“签名被绕过”或“媒体字节被修改”。应解决源清单、构建器、审计器和交付规则的同一套文件契约，并保留真正的签名、同代 bootstrap、依赖隔离等保障。

## 四、最小后续执行任务

### 任务 A：先恢复可审计源码与证据链

从已测 CE2021 原始源码或完整工作区补丁取得真实 F01/G01/协作退出修复，应用到隔离的候选分支，提交固定 commit/tree。记录原始已测包、新清理包、源码、补丁与受测夹具的 SHA-256；说明旧重写基线如何映射。把原始失败、适配差异、最终结果以可访问路径纳入交付。不能用旧通过数、清理回执或只补文档代替产品修复。

**完成标准：** 可从固定源码直接查看所有被报告为修复的分支，能够定位受测对象，旧 F01 的两类反例与正控都在同一候选源码上执行。不要机械把路径 `RunScript` 改成 addon ID；必须同时满足身份、service 入口和受管停止闭环。

### 任务 B：统一构建与入口审计的文件契约

按既定清理范围明确生产文件集合，并使 source inventory、入口构建器、清理工具与入口审计表达同一政策。文档项策略与运行/签名安全检查分别表达；修复文件契约时保留真实签名、同代 bootstrap 字节一致性、隔离导入和账号状态排除等断言。对最终实际入口 ZIP 重新执行完整 audit，并记录最终包摘要和序列。

**完成标准：** 本分报告的清理件契约反例被正确解决，且对最终真实安装入口的 audit 通过；不能只跳过整个 audit 或删掉源清单约束。

### 任务 C：验证新增生命周期，而不是扩大等待时间

取得真正新代码后，在同一候选上验证以下并列场景：

- enabled 但 owner 已死：原生实际导入保留 addon 身份，标准恢复随后再次 quiesce 能由受管服务关闭。
- 存活 owner：认证请求由 owner 线程判空闲；音频、视频或未知状态均拒绝安装停机。
- 新旧代次：支持协作协议的代次走协议，不认识该协议的代次按明确兼容逻辑处理；保留恢复菜单与 rollback/exit，保持原 15 秒预算。
- 慢历史写、下一集和字幕任务：停止接纳后取消或排空已接受任务；真实任务未结束时 OS lease 不移交。
- 任一 close 或日志报告抛错：继续清理其余组件，记录未完成状态并保留 lease；同一对象重试能继续，而不是因 `stopping` 已设置立即成功返回。
- 整体停机完成后：旧 owner 和辅助任务结束，enabled 向量及皮肤按 journal 恢复，后续宿主真实 ready。

这些要求落实报告已经承诺的生命周期，不引入额外 daemon、设备白名单、账号迁移或全局重试。设备维护应在源码、构建与实际包检查闭环后，沿原有授权范围做有记录的空闲安装/恢复/回退；本分报告不执行设备变更。

## 交付文件

| 文件 | 用途 |
| --- | --- |
| `INSTALLER-REVIEW.zh-CN.md` | 本分报告 |
| `INSTALLER-ASSESSMENT.json` | 状态、主报告合并建议、执行任务 |
| `LIFECYCLE-SOURCE-IDENTITY.json` | 10 个关键文件的固定 blob 与双快照身份核对 |
| `REPORTED-EVIDENCE-AVAILABILITY.json` | 报告所引用 10 个路径在当前完整 tree 的可用性 |
| `reproduce_clean_entry_audit.py` | 入口清理/审计契约最小复跑 |
| `CLEAN-ENTRY-AUDIT-CONTRACT.json` | 本轮实际执行结果及方法边界 |

本域没有修改产品、调用设备、推送、合并或发布 GitHub 评论。临时获取的产品源码副本不属于用户交付文件。
