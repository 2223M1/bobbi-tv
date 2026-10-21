# CE2024 构建、重签、真实入口与 CI 独立审查

## 结论

固定审查对象为 `c4e0baca6acefa58f031979bff71e7cd1028efdf`，tree 为 `bb4256d63465fefb9c5820f3ce1ec9cca33ff546`。本分项审查认为：**旧 D02 的文档清理与构建/入口审核契约冲突已实质关闭；旧 D03 的错误代次、任意输入、来源代次冒称及失败后发布半成品问题，在当前源码和 35 项真实 RSA/ZIP 测试范围内已修复。真实 CE2024 入口已取得原始字节，并通过完整签名、全部组件、全部 Git 运行文件与完整入口组合核验。**

这是一项明显进步，不能沿用上一版“未取得实际包”或“CI 尚不能构建”的否定结论。本次未发现新的产品包字节或签名缺陷。交叉复核另外确认一项 **P2 测试回执来源绑定缺陷**，详见第 8 节；它影响后续证据工具可信度，本轮另行取得的真实 CI 与实际包映射已补足当前版本身份。是否允许稳定交付仍取决于产品运行、播放、回退及其他分项审查；本报告不把 ZIP 验签或 CI 通过解释为这些设备门禁已完成。

仍保留一项边界：最初 CE2021 外层交付 ZIP 已丢失，无法补做该精确原始生产输入的重新签名正例。当前文档明确承认这一点。35 项测试使用临时生成的真实 RSA 密钥和真实 ZIP；它们不是找回原包、使用生产私钥或完成真实设备测试的证明。

## 1. 固定来源及独立证据

| 项目 | 本次直接核验结果 |
|---|---|
| 固定 head | `c4e0baca6acefa58f031979bff71e7cd1028efdf` |
| 固定 tree | `bb4256d63465fefb9c5820f3ce1ec9cca33ff546`，GitHub recursive tree 未截断 |
| 产品 commit | `d2fffa570fe59b90cd1d33499efcf7c6684b2647`；其与 handoff head 的产品目录关系由总审查另行核验 |
| 真实入口 | `review-packages/ce2024/script.bobbi.start-0.2.15-ce2024.zip` |
| 入口大小 | **95,916,922 字节** |
| 入口 SHA-256 | `cb355eb2a80b3974e985a9bc404fb74a8be1c98ab1319d30e4399eb503c06e9c` |
| 入口 Git blob SHA-1 | `d52e0da8cf4f2807bf13d31da7071b67fba70472`，由实际下载字节重新计算并与固定 tree 一致 |
| 内嵌完整载荷大小 | **95,817,630 字节** |
| 内嵌载荷 SHA-256 | `d53bc3b6ad0c4dc905a831d1906575a7c53ad15c0e6a6d6d7b12188e0d33c096` |
| 签名身份 | sequence **2026102024**，profile **coreelec**，channel **private-candidate** |
| 验签方式 | 产品 `SignedBundle.check_all()` 与独立 `cryptography` RSA-3072 / PKCS#1 v1.5 / SHA-256 均通过 |

公开校验信任根 `release_trust.json`、主要验证工具和 `source-inventory.json` 均先匹配固定 Git blob。验证过程未持有生产私钥，未输出应用配置明文。

证据：`ACTUAL-ENTRY-VERIFIED.json`、可重新执行的 `verify_actual_entry.py`。入口获取记录由总审查保存在 `ce2024-metadata/ENTRY-DOWNLOAD-VERIFIED.json`。临时下载授权 URL 不属于交付证据。

来源：[固定交付报告](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/docs/CE2024-DELIVERY.md)、[固定入口](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/review-packages/ce2024/script.bobbi.start-0.2.15-ce2024.zip)。

## 2. 真实包的完整性与源码映射

校验不只读取作者报告里的散列，也不只调用作者审核器。对实际入口执行了 CRC、重复/大小写碰撞成员、安全路径、成员类型检查，随后执行签名及逐字节映射。

| 检查层 | 结果及准确范围 |
|---|---|
| 组件集合 | 全部 **22 个**签名组件，与固定源码 inventory 的组件集合完全一致 |
| Git 文件 | **1,349 个**文件 SHA-256 与 inventory 一致，Git blob 也与固定 tree 一致 |
| Git 文件分布 | `addons/` **1,142**，`third_party/addons/` **207** |
| 唯一构建注入项 | `script.module.bobbi.core/resources/tmdb-project.json`，237 字节；只记录散列，未披露内容 |
| 实际组件总文件数 | **1,350**：1,349 个 Git 文件 + 1 个明确的应用配置输入 |
| 自有产品文件数 | **1,143**：1,142 个 Git 自有文件 + 1 个应用配置；与设备报告中的 1,143 口径相容 |
| 外层入口 | **17 个**成员，精确等于签名 start 组件的 2 个文件 + 同代 platform 的 14 个 bootstrap 文件 + 1 个完整载荷 |
| 额外/缺失成员 | 0 |
| 被政策排除的独立文档 | 0 |
| 隔离 bootstrap 导入 | 当前实际入口的全新隔离 Python 进程导入通过 |

外层 `addon.xml`、`default.py` 同样逐字节比对签名 start 组件；因此本次检查超出了原 `audit_ce_entry.py` 仅核对指定 bootstrap 模块的范围。实际包中的字体、声音、Python、XML 和其他运行文件都在完整 inventory 与 Git blob 映射中核验。没有发现清理政策误删运行资产或加入不明运行文件。

唯一应用输入的 SHA-256 为 `2afc6cdf088af273f683ff41ba5256a2fe2a4cfd5d57402c44421896bfb4a0cd`。这证明该包包含一个可识别的构建输入；它不等于验证该配置的服务权限、外部 API 可用性或用户账号状态。

## 3. D02：政策、构建、入口构建和审核已经一致

当前 `tools/delivery_policy.py` 提供同一 `private-document-clean-v1` 排除规则；`build_release.files()` 对完整文件集合执行 `require_clean()`，随后继续进行精确 inventory 比较。它会拒绝不合政策的源码集合，不会把任意运行文件静默过滤掉。

`build_ce_entry.py` 不再强制读取已按政策删除的 platform `LICENSE` 并复制为 bootstrap 文档；`audit_ce_entry.py` 也不再把这个文档存在作为入口通过的前提。签名、同代 bootstrap 和隔离导入检查继续保留。

相关测试修改仅调整独立文档存在条件。字体字节 SHA-256、图标字体哈希/字形、原始运行资产不变等断言仍保留。`test_vendor_licenses.py` 改为确认历史可选工具在缺失文档 manifest 时明确失败，未将它改为虚报许可验证成功。依据本次仓库指令，不要求把独立说明文档重新加入产物。

本次关闭证据有三层：当前 CI 的两次真实 source-check 均成功；实际 CE2024 入口审核通过；实际包所有 1,349 个 Git 运行文件及完整组合逐字节吻合。它们足以关闭旧的文档契约冲突。这里没有对第三方法律许可状态作新的判断。

源码：[统一政策](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/delivery_policy.py)、[构建器](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/build_release.py)、[入口构建](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/build_ce_entry.py)、[入口审核](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/audit_ce_entry.py)。

## 4. D03：重签输入、代次、来源和原子发布

当前 `package_ce2021_github.validate_input()` 在处理原包前验证精确 CE2021 身份锁：外层、payload、entry SHA-256，外层 manifest 的成员集合和每项长度/散列，entry 嵌入的 payload 字节一致性，以及真实 `SignedBundle` 的签名、完整组件集合、profile、channel 和实际 sequence。输入代次必须为整数 **2026102021**；布尔值不能冒充整数。

`checked_sequence()` 要求显式输出代次，且严格大于输入代次、2026102022 和传入登记表的全部已分配值。它依赖调用者提供最新登记表，不会联网检查设备/Release，也不会自行维护全局并发序列登记。因此后续签包仍须先更新并核对登记表；已交付 2026102024 之后不能继续把旧 reservation 文件当作最新全局事实。

输出来源代次在修改 manifest 前从实际签名输入捕获，外层记录原 outer/payload/entry 散列；清理记录包含路径、原始散列、字节数、规则及文档/补丁类别。每个组件的非文档 inventory 仍作逐字节比较，输出重新签名后再走真实 `SignedBundle` 检查。

CLI 先验证输入，在输出目录同级的临时目录完成打包及验证，最后将已验证目录一次重命名为最终输出。注入最终验证失败时，最终输出目录不存在；这修复了旧版留下可被误认为可交付半成品的风险。

本地独立运行作者的 35 项聚焦测试：**35 passed / 0 skipped / 0 failed / 0 errors**，Python 3.12.14。覆盖旧/较新/布尔输入代次，错误 profile/channel/trust，损坏组件，未签名额外成员，嵌入不一致，四类身份锁不匹配，外层成员缺陷，合法正例，清理保留运行文件，来源记录，末尾验证失败无发布和序列碰撞。测试使用临时 RSA-3072 密钥，不接触生产私钥。证据为 `local-delivery-junit.xml` 和 `LOCAL-DELIVERY-VERIFIED.json`。

**关闭状态：源码缺陷已修复，真实密码学夹具正反例已验证；原始 CE2021 外层生产 ZIP 丢失这一历史证据缺口仍然保留。** 真实 CE2024 包走当前产品构建路径且已独立验签，不能用它冒充“原始 CE2021 外包重签正例”。

源码：[重签器](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/package_ce2021_github.py#L124-L205)、[冻结输入身份](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/release/ce2021-input-lock.json)、[真实 RSA/ZIP 测试](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tests/test_ce2023_delivery.py)。

## 5. 本次真实 GitHub CI

直接取得 GitHub job 原始日志及原始 JUnit artifact，未挪用作者报告中的本地测试成绩。

- run **39537767479**，job **119018276236**，状态 completed / success。
- 日志实际 checkout 的 commit/tree 与本报告固定 head/tree 一致。浅克隆日志 `parents=` 为空不表示该提交没有父提交。
- artifact **12318492520**，**47,962 字节**；实际 SHA-256 与 GitHub digest 一致：`05f88c6c78878dee189ce76fbc101ed229746c6791fe1e1983752a2bdb98f4f8`。
- 两次日志均显示 `Built 22 components from explicit source inventory; source-check`；比对结果为 **`Reproducible files: 63`**。

| JUnit 套件 | 通过 | 跳过 | 失败 | 错误 |
|---|---:|---:|---:|---:|
| 当前 CI primary | 1,838 | 5 | 0 | 0 |
| 当前 CI baseline | 789 | 0 | 0 | 0 |
| 当前 CI preparation | 177 | 0 | 0 | 0 |
| **当前 CI 合计** | **2,804** | **5** | **0** | **0** |

总测试条目为 **2,809**。五个 skip 均为 `test_windows_lease_uses_toolhelp_and_preserves_lifecycle_guards[...]` 的 Windows inherited-pipe API 实机绑定场景。当前 CI 运行于 Linux/Python 3.11.17，它们不能算 Windows 门禁完成。

作者交付文档的本地 **1823 passed / 6 skipped + 789 + 177** 是另一次运行。当前 CI 的 **1838 / 5 + 789 + 177** 与其不同，必须保留两套来源和范围。CI 双构建属于 `source-check`，没有应用配置和签名私钥，明确不可安装、不可签发；不能仅凭这项双构建声称私有生产签名包也已被 CI 重建。

证据：`CE2024-current-CI.zip`、`CI-JUNIT-VERIFIED.json`、`CI-METADATA.json`、`ci.log`。来源：[真实 CI run](https://github.com/2223M1/bobbi-tv/actions/runs/39537767479)、[固定工作流](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/.github/workflows/verify.yml)。

## 6. 后续执行指导

1. 把本次固定 head、入口/payload 散列、当前真实 CI run 与 JUnit 数字补入后续交付包的独立复核部分；保留作者原始本地回执，不覆盖成同一来源。
2. 每个后续实际入口复用完整 22 组件 inventory/Git 映射及外层精确组合检查。可将本次独立验证器中的完整外层检查归入正式审核器；当前审核器的 `account_state_copied=False` 是返回字段，本身不是对任意额外成员或账号文件的检查。**本次实际包已补做精确组合核验并通过，故此建议不构成本次包的已复现缺陷。**
3. 保持应用配置仅作为一个明确的维护者构建输入，回执仅保留散列，不把生产配置或签名私钥复制到交付审查包。新增输入时须变更明确白名单，不能无声放宽 inventory。
4. 下一签发代次必须来自更新后的登记表，包含已使用的 2026102024；不要把旧候选 reservation 当作未来仍未占用的代次证明。若继续操作 CE2021 专用重签器，保留原始外包缺失结论，或取得并匹配被冻结 outer SHA-256 的真实原件后再验证正例。
5. 构建/验签关闭后，后续主要精力应转向总审查列明的真实播放、字幕策略、热态 UI、完整回退闭环等剩余门禁。不要通过重复已经充分核验的构建测试来替代设备结论。

## 7. 可复现命令

在具备固定源码快照、原始入口及固定 Git tree JSON 的环境中，可执行以下只读验证。路径由使用者按本地目录调整，运行器需要 `cryptography` 和项目测试依赖；命令不需要生产私钥。

```sh
python verify_actual_entry.py \
  --repo /path/to/fixed-source \
  --fixed-source /path/to/fixed-source.json \
  --entry /path/to/script.bobbi.start-0.2.15-ce2024.zip \
  --output /path/to/ACTUAL-ENTRY-VERIFIED.json

python -m pytest -q tests/test_ce2023_delivery.py \
  --junitxml=/path/to/local-delivery-junit.xml
```

验证器在任何签名、字节、成员、源树身份或约定不匹配时直接失败，不把错误结果写成通过回执。它不会联网、推送、部署、改写产品或操作设备。

## 8. 交叉复核：P2，测试回执记录错误的源码仓库身份

`tools/closure_gate.py:19` 使用调用方传入的 `root` 作为真实命令工作目录；第 24 行却在记录器常量 `ROOT` 下读取 `git rev-parse HEAD`。当干净检出或其他执行仓库与记录器仓库不同，即使命令确实在另一提交成功执行，回执的 `commit` 仍会指向记录器提交。`tools/package_ce2024_handoff.py:72–83` 又把这项 `commit == PRODUCT` 当作本地 gate 条件，因此这不是单纯显示标签问题。

总审查提供的回归使用两个真实临时 Git 仓库、真实命令和真实 Git，无 subprocess mock。本分审查独立复跑同一回归，结果 **同仓库对照 1 passed，异执行仓库 1 failed**：实际 stdout 中的 Git HEAD 为执行仓库提交，而回执记录为另一记录器提交。证据为 `closure-gate-peer-junit.xml` 和 `closure-gate-peer-check/*.json`。

`dirty=True` 是保守硬编码，不构成“把脏仓库冒称干净”的证明；它同时意味着该字段没有测量真实清洁状态。应与上述真实的 commit 错绑区别说明。

建议优先修复：记录实际执行根目录对应的 Git top-level、commit、tree 和 status，在命令前后校验身份稳定；记录器来源如有需要另设字段。执行根无可核验仓库身份或发生身份漂移时应明确拒绝作为产品 gate，不要回退到记录器仓库。补齐异执行仓库回归后再让 handoff 以这些字段作为通过条件。

**边界：该反例没有证明本次 clean24 测试确实运行在错误源码，也不能否定本次 CE2024 签名包。** 本次独立 CI checkout 记录和全组件 Git 映射提供了额外身份依据，实际包通过结论仍有效。本 P2 针对现有回执工具与后续自动验收可能错归来源的问题。

源码：[回执生成器](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/closure_gate.py#L14-L25)、[handoff gate](https://github.com/2223M1/bobbi-tv/blob/c4e0baca6acefa58f031979bff71e7cd1028efdf/tools/package_ce2024_handoff.py#L72-L83)。
