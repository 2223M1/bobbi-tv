# CE2021 clean：构建、重签、发布与 CI 独立审查

## 结论

当前 `b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2` 适合作为**待补齐来源的重签交付记录**。它还不能作为已可复现构建、已通过当前 CI、已完成清理包入口审计的源码候选。需要先补齐完整候选源码与测试，再修复文档清理后的构建、清单及审计契约，随后取得最终发布资产做独立验签和入口检查。

本审查直接下载并核验了当前 GitHub Actions 的 JUnit artifact；源码取自固定提交，关键文件的 Git blob 哈希与该提交的 Git tree 一致。对 draft release 仅取得元数据，尚未取得三个 ZIP 资产的实际字节。因此本文不把 `packaging-result.json` 的声明当作本次独立验签结果，也不把构造探针当作当前 release 资产或设备测试。

| 对象 | 固定身份与状态 |
| --- | --- |
| 分支 | `codex/ce2021-clean-delivery-20261021` |
| HEAD | `b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2` |
| Tree | `bbe592e62a7a6790c62725738b63dae9b9f9405a` |
| 当前 CI | run `39525777378`，push，verify job `118979948586`，failure |
| CI artifact | `12313666129`，`verify-push-39525777378`，102,202 B |
| CI artifact SHA-256 | `06312c59736013153a1a18058382adaced7d24ab9c22d05f162420580a528e45` |
| Draft release | `419038503`，`ce2021-clean-delivery-20261021`，draft=true |
| Release target | `codex/ce2021-clean-delivery-20261021`，当前为分支字符串 |

固定源码索引见 [SOURCE-PROVENANCE.json](../evidence/release/SOURCE-PROVENANCE.json)。[当前 CI](https://github.com/2223M1/bobbi-tv/actions/runs/39525777378) 的日志记录了上述实际 checkout commit/tree，避免混淆旧 PR 的 merge tree 与此次 push head。

## 1. 当前 CI 的实际结果

已读取实际 artifact 字节，先比对 GitHub 返回的 SHA-256，再解析三份 JUnit XML。原始文件见 [CE2021-clean-CI.zip](../evidence/ci/CE2021-clean-CI.zip)，精简计数见 [CI-SUMMARY.json](../evidence/ci/CI-SUMMARY.json)，失败文本见 [CI-JUNIT-VERIFIED.json](../evidence/ci/CI-JUNIT-VERIFIED.json)，完整 job 日志见 [ci.log](../evidence/ci/ci.log)。

| Suite | 总数 | 通过 | 失败 | 错误 | 跳过 |
| --- | ---: | ---: | ---: | ---: | ---: |
| baseline | 761 | 761 | 0 | 0 | 0 |
| preparation | 177 | 177 | 0 | 0 | 0 |
| primary | 1,751 | 1,741 | 5 | 0 | 5 |
| 合计 | **2,689** | **2,679** | **5** | **0** | **5** |

五个跳过项是 Windows inherited-pipe API binding。五个失败项为：

| 失败测试 | 实际原因 | 代码契约 |
| --- | --- | --- |
| `test_preview_is_reproducible_and_dependency_closed` | `Review and update explicit source inventory: script.module.bobbi.platform` | preview 构建的显式清单与当前目录不一致 |
| `test_fonts_are_unchanged_and_licensed_in_project_assets` | 缺少 `assets/fonts/LICENCE-HarmonyOS-Sans.txt` | 设计资产校验仍要求该文件 |
| `test_public_inventory_is_exact` | `plugin.video.bobbi` 的实际文件集合与公共清单不同 | 清单尚未与清理策略同步 |
| `test_actual_private_skin_restores_exact_fonts_but_not_legacy_scripts` | 缺少 `addons/skin.bobbi.cinema/fonts/fontawesome-free-6.7.2-LICENSE.txt` | skin 校验仍要求该文件 |
| `test_checked_in_notices_and_truthful_unresolved_status` | 缺少 `licenses/THIRD-PARTY.json` | provenance/notice 工具仍读取该清单 |

此外，两次 `tools/build_release.py --source-check` 都在 `tools/build_release.py:110` 抛出 `Source inventory changed: plugin.video.bobbi`。第二步 shell 在构建失败后退出，后续 `check_repository.py` 没有运行。因此没有“当前源码两次构建字节一致”的证据。CI 中绿色的 baseline/preparation 不能替代主测试与构建门槛。

该组问题应合并为一项交付阻断：**文档清理变更已落地，依赖这些文件的 source inventory、构建及验证契约没有闭合。** 不宜将五个测试分别包装成五个独立产品缺陷，也不能仅删除测试或放宽 source inventory 检查来获得绿灯。应先确定清理后的正式交付规则，按该规则逐项更新输入清单与证据，再保留完整性、依赖闭包、来源可追溯、入口可审计等实际保证。

本结论是工程契约审查，不判断被删文件是否应因法律原因恢复；本次也未恢复任何文件。依据是实际 CI 失败及 [build_release.py](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/build_release.py)、[build_preview.py](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/build_preview.py) 的现存约束。

## 2. 历史成绩与新交付应如何解读

报告末尾“GitHub 清理重签交付”已经明确说明：新序列是 `2026102022`，组件版本沿用原 CE2021，清理包未部署，原先的设备测试和源码构建失败仍保留其原有含义。这个边界表述是准确且必要的，应保留。

报告前面的 `1764/782/177`、原入口 SHA-256、维护部署与回滚成绩，属于清理前的完整 CE2021 工作区及原安装包。当前 GitHub 分支相对重写基线仅新增报告、receipt 和清理脚本；主审的逐 blob 比较显示，相对之前审查的 CE2014 快照是 3 新增、83 删除、0 修改。不能从这些历史成绩推导出当前分支包含相应产品修复，也不能用新脚本的“非文档文件未改动”推导出“当前 GitHub 源码可构建出这些资产”。

清理器从现成的本地 delivery ZIP 读取输入，不从当前分支构建组件。它可以保持**输入包与输出包**的程序叶子文件一致，但没有证明**当前仓库与输出包**一致。这是后续工作的首要来源缺口。参考 [清理脚本 main](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/package_ce2021_github.py#L119) 与 [交付报告](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/docs/CE-REVIEW-CLOSURE-2021-20261021.md)。

## 3. 重签脚本已有的有效检查

`tools/package_ce2021_github.py` 的关键逻辑具备实质性保护，不能概括成“只换名字”或“只写 true”：

1. `main:127–143` 比对私钥公钥参数与现有 trust pin，并验证原载荷 manifest 签名；输入入口的 embedded payload 必须与 standalone payload 字节相同。
2. `main:147–162` 约束 CoreELEC/private-candidate profile/channel，要求载荷成员集合匹配 manifest，逐组件检查原始长度与 SHA-256。
3. `clean_archive:60–87` 递归清理最多 10 层；拒绝直接处理含 `release.json` 与 `release.sig` 的已签名 payload，避免误删后保留旧签名；APK 进入单独签名流程，不被直接清理。
4. `inventory:103–116` 比较不在排除规则内的叶子文件哈希；组件与入口 bootstrap 均有比较，ZIP 容器重新压缩不会被误判为程序字节改变。
5. `main:163–184` 设置新序列 `2026102022`、重算组件 size/hash、规范化 manifest JSON 后重签，并调用真实 `SignedBundle.check_all()` 检查新 standalone payload。
6. `main:189–219` 刷新外层 `MANIFEST.json`、文件摘要及报告边界，递归检查 ZIP CRC、成员安全与排除规则；现存输出目录会被拒绝，原输入包不会被覆盖。

这些是从固定代码可核实的设计行为。仓库 receipt 声明 22 个组件、49 个移除条目以及 key/signature/ZIP/non-document 检查通过；由于未取得 release ZIP，本次未独立确认这些路径在实际发布资产上都已执行成功。代码与 receipt 的区分应在最终放行记录中保留。

`non_document_files_unchanged` 的实现范围还应写得更精确：它验证的是组件及 bootstrap 中未被规则排除的叶子内容，不是整个 delivery 的所有非文档条目。外层 README、报告、MANIFEST、patch 都可能按流程更新；ZIP 容器字节也会变化。移除记录在内存中收集但最终只写条目数量，尚无 49 个条目的路径、原哈希和规则命中原因清单；建议下一版输出独立审计清单，patch 被删的 diff blocks 也应单独计数。

## 4. 已证实的工具输入代次缺口（P2）

位置：[package_ce2021_github.py:145](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/package_ce2021_github.py#L145) 只拒绝 `manifest['sequence'] >= 2026102022`；它没有要求输入恰好为 `2026102021`。但 [第 212–216 行](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/package_ce2021_github.py#L212) 又固定记录 `original_sequence=2026102021`。

主审使用临时测试 trust 和真实签名构造了输入，执行实际 `main` 与实际 `SignedBundle`，没有接触生产私钥或 release 资产。5 个用例为 4 通过、1 失败：正确 `2026102021` 输入接受；同代 `2026102022`、错误 profile、未受信任签名均拒绝；合法同 trust 的 `2026102014` 输入被接受，输出被真实验签为 `2026102022`，但外层 MANIFEST 错写原序列为 `2026102021`。证据见 `../evidence/packager/INPUT-GENERATION-RESULT.json`。

这是有条件的工具输入验证与来源记录错误：持有正确维护者签名的旧一代输入，被放进约定的 legacy 文件路径后，可以获得新的高序列和错误的原代次标记。**没有证据表明本次 release 实际使用了旧输入**；问题不构成伪造签名或更换 trust 的证据。

针对这个专用 CE2021 清理器，应精确断言输入 sequence 为 `2026102021`，验证预期组件集合和版本，并以审核冻结的原 delivery/payload 摘要约束来源；`original_sequence` 等字段必须由已经验证的输入产生。添加正确代次、合法旧代次、同代/未来代次、错误 profile/channel、错误 trust 的小型真实签名回归测试。若将来改为通用清理器，则应显式参数化输入代次契约，去掉固定的 CE2021 来源声明。

## 5. 清理入口与现有入口审计的契约不一致

新脚本的排除规则会删除 `script.bobbi.start/bootstrap/LICENSE`，而当前 [audit_ce_entry.py:49](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/audit_ce_entry.py#L49) 强制读取它；[build_ce_entry.py:40](https://github.com/2223M1/bobbi-tv/blob/b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2/tools/build_ce_entry.py#L40) 也从 platform 组件复制这一文件。代码同时保留了两套相互冲突的成品契约。

安装域探针调用真实 `clean_archive` 与当前审计器，并执行真实独立 bootstrap import 子进程。原入口通过；仅删除该 LICENSE 的清理入口在强制读取处抛 `KeyError`。非文档 inventory 相同，`check_nested` 通过。探针只在 `SignedBundle/load_trust` 边界使用 fixture，因此它证明的是清理器与审计器不兼容，**不证明实际 release ZIP 验签失败，也不证明 Kodi 启动失败**。证据见 `../evidence/installer/CLEAN-ENTRY-AUDIT-CONTRACT.json`。

这应并入“构建及交付验证契约未闭合”。修复方向是在正式清理规则下，使 builder、cleaner、audit 的输入输出约定一致，同时保留真实入口的 addon.xml、嵌入载荷签名、同代 bootstrap、独立导入等检查。不能把绕过整个入口审计当作解决办法。

## 6. Release 元数据核对

| 资产 | 大小 | SHA-256 |
| --- | ---: | --- |
| `bobbi-private-2026102022-coreelec.bobbi-update.zip` | 96,135,572 | `c0ebea710ef3dda667c4336aa42b4b212469399468f6081f60d806e8171ca696` |
| `script.bobbi.start-0.2.13-ce2021-clean.zip` | 96,233,587 | `bf10e21a30f98a74c99671985600a79da692371733f5ca17a21179565a72cb6b` |
| `ce2021-clean-delivery-20261021.zip` | 199,794,948 | `4188691ab12040ac0f1e33bcba6761c6a02fc5bc6c00932f23991192988da708` |
| `CE-REVIEW-CLOSURE-2021-20261021.md` | 16,320 | `a21661ec171c39300b182a1521e65ce0532db38a023d63ce1dcc91a8022f8722` |

仓库 receipt 中的这四项 name/bytes/digest 与 GitHub release 元数据逐项一致。用户附件与仓库报告实际字节一致，SHA-256 也与 release 元数据一致。

`packaging-result.json` 另有一个可解释的换行差异：仓库是 968 B / `b3241c8ececaea66005b0159affecd9ad76e4089494977b10ecd6e3f0002435a`；release 元数据是 1,000 B / `7e3e621207f131b18cc420b12d015377b84180af890651ae4060d13ac5593c64`。对仓库文件的 32 个 LF 做 CRLF 转换，恰好产生 release 元数据的大小与 SHA-256。该差异可由换行完整解释，不应报成内容矛盾；这仍不是对 release body 的直接下载。完整记录见 [ASSET-METADATA-COMPARISON.json](../evidence/release/ASSET-METADATA-COMPARISON.json)。

Release 当前仍是 draft，`target_commitish` 是浮动分支名。建议下一次形成候选时，在 release/manifest/证据包中明确写入固定 source commit、tree、原输入摘要和实际资产摘要；对外放行时再把 tag 锚定到已审核 commit。这是来源固定化建议，不意味着现有资产内容会随分支自动改变。

## 7. 后续执行顺序与验收门槛

### A. 先恢复可审核、可构建的候选来源

将原 CE2021 修复的完整产品源码、对应测试与现场证据导入独立候选工作区，逐文件对照现有 delivery patch 和报告。不能只把版本号提升到报告中的值，也不能将历史 PR #3 的源码绿灯挪给当前候选。固定一个 source commit/tree，并建立组件源码叶子文件到发布组件的映射。按既定清理要求处理文件，明确更新清单和审计契约。

### B. 修复构建与清理器的可检验缺口

精确锁定清理器输入代次/来源；添加上述真实签名正负例。统一 builder、cleaner 与 entry audit 的文件约定；输出移除条目和 patch-block 审计清单。在这一步，source-check 构建及三组测试必须能够在没有应用 key 和生产签名私钥的环境中运行。

可用于新固定候选的命令如下；输出目录应是该候选专用的新目录，不能覆盖原交付：

```bash
python -m pytest -q -rs tests --ignore=tests/private_baseline --ignore=tests/preparation_regression --junitxml=review-evidence/ci-primary.xml
python -m pytest -q -rs tests/private_baseline --junitxml=review-evidence/ci-baseline.xml
python -m pytest -q -rs tests/preparation_regression --junitxml=review-evidence/ci-preparation.xml
python tools/build_release.py --source-check --output dist/ce2021-review-build-one
python tools/build_release.py --source-check --output dist/ce2021-review-build-two
python tools/check_repository.py dist/ce2021-review-build-one dist/ce2021-review-build-two
```

记录每一步 exit code、实际 checkout commit/tree 和 JUnit。旧 `b20e972` 的红灯应保留为历史事实，不覆盖原证据。只有新候选运行所得的结果可用于关闭该门槛。

### C. 对实际待发资产做独立验证

在有正常 GitHub release 读取能力的维护环境取得最终 ZIP 后，先按冻结的 asset ID、大小、SHA-256 验证，再解包比较 standalone payload 与 entry 内嵌 payload；调用真实 `SignedBundle.check_all()`，核对 sequence/profile/channel/组件集合与版本，执行现行且已修复契约的入口审计：

```bash
python tools/audit_ce_entry.py /absolute/path/to/final-entry.zip --report review-evidence/final-entry-audit.json
```

这里的 `final-entry.zip` 必须是待发布的真实资产。需要同时检查 collection 内的安装器、manifest、patch、报告与单独下载资产一致。不要复用 fixture 的通过记录，不要把 GitHub 元数据核对作为验签。后续若再次改变受签名字节，应使用新的唯一序列并保留原包，不复用已发出的 `2026102022` 内容身份。

### D. 最后进行设备门槛

源码、CI、实际资产三条证据闭合后，再按主审计划在明确授权的设备上验证首次入口、升级、managed enable/disable、播放状态采样、关闭排空与回滚。清理前 CE2021 的现场证据可以指导用例，但不能代替清理后实际待发包的结果。

## 本域证据目录

- `SOURCE-PROVENANCE.json`：8 个关键源码文件的 SHA-256、Git blob、固定来源 URL。
- `CI-METADATA.json`、`CE2021-clean-CI.zip`、`CI-JUNIT-VERIFIED.json`、`CI-SUMMARY.json`、`ci.log`：真实当前 CI。
- `ASSET-METADATA-COMPARISON.json`：资产元数据、receipt、附件及 CRLF 差异核对，明确没有下载 release ZIP。
- `packaging-result.json`：仓库中 receipt 的原字节副本。
- 固定产品源码不重复收入本包；可按 SOURCE-PROVENANCE 中的固定 URL / blob 读取。

输入代次与入口审计的两个窄型探针由主审及安装域分别提供，边界已在各自 JSON 中列明。全部过程为读取与本地审查；未发布、推送、修改 draft release、触碰设备或使用生产私钥。
