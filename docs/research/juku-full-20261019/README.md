# Juku 0.80 全量静态反编译与播放器设计研究

2026-10-19，在用户取得作者研究/接入授权后完成。**全量范围是两个 ELF 中
Ghidra 识别的全部函数，包括 Go runtime、标准库、第三方库、Juku 业务代码；
没有用业务关键词过滤。** 两架构共 38,132 个函数全部尝试，38,125 个成功输出
伪 C，7 个失败保留反汇编和原因。所有 Go `pclntab` 函数入口、所有 ELF 函数
符号地址都能在导出索引中找到。

**这些是重建的伪 C、反汇编、符号和调用图，不是完整原始 Go 源码，不是可直接
编译的替代工程。** 全量导出不等于逐函数人工证明；设计结论只对文中列出证据的
路径作语义判断。没有运行 daemon、登录账号、访问盒子、提取/使用私钥或绕过授权，
没有修改生产 addons。

官方仓库当前版本和原始 Python/配置/素材详见 [ASSETS.md](ASSETS.md)；
设计结论详见 [DESIGN.md](DESIGN.md)，简明交付与“已吸收 / 不采用 / 待验证”边界见
[中文结论](SUMMARY.zh-CN.md)。2026-10-19 官方 `addons.xml` 仍列
`plugin.video.juku` 0.80，重新下载两个固定包的哈希与既有样本相同。

## 固定输入与工具

| 输入 | SHA-256 |
| --- | --- |
| `plugin.video.juku-0.80-linux-x64.zip` | `0a384785f3cb9182513b0ea9f387675438217136df0ca751f6011c45ddeea9ca` |
| `plugin.video.juku-0.80-linux-arm64.zip` | `850414fb4829512b44086245e1889f4e9bb9ae44b9f42b3f6d7834c75e2950a0` |
| `daemon-linux-amd64` | `fc7ba96b40f4da9d33c02b7c67f8617d26b0982166df515e429d94c97cba1433` |
| `daemon-linux-arm64` | `e21cec4ba1f0411022a2d22061b1d27ac80d439606529ddc9cabec3060ca118b` |

ZIP 原位置：
`D:/AM6B-Project/AM6B-review-ui-anirss-20261018/ui-redesign/review-evidence/juku-20261019/research/juku080/plugin.video.juku-0.80-linux-{x64,arm64}/`。

采用已有 Ghidra **12.1.4** 分析工程及 JDK **21.0.12.1+1**，`-readOnly -noanalysis`
打开；首轮每架构 4 worker、每函数 60 秒，失败以 2 worker、180 秒上限重试一次。
重试开启 syntax tree；AMD64 SQLite VM 的首轮超时恢复成功，7 个底层失败没有改善。
最后以不重试失败的模式复跑，两个架构均 `attempted_this_run=0`，验证续跑跳过机制。

工具位于仓库 `tools/`：

- `ExportJukuFull.java`：枚举全部内部/外部函数、全符号表、函数 body 地址段；
  逐函数输出 `.c`、`.asm`、`.calls.tsv` 和持久化 journal。
- `summarize_juku_full.py`：从函数清单而非输出文件数量计算覆盖，检查输出存在，
  汇总失败、正反直接调用图、模块计数及模块调用图。
- `crosscheck_juku_go_functions.py`：独立解析 ELF64 `.symtab`、Go `.gopclntab`，
  交叉核对入口地址，保留函数 body 外的 `.text` 地址范围及 SHA-256。
- `package_juku_full.py`：生成每文件哈希清单和架构 ZIP，重新读取 ZIP 每项并核对 SHA-256。

## 实际覆盖

| 项目 | AMD64 | ARM64 |
| --- | ---: | ---: |
| Ghidra 识别函数 / 本轮全部尝试 | 19,104 / 19,104 | 19,028 / 19,028 |
| 伪 C 输出成功 | 19,102 | 19,023 |
| 重试后失败 | 2 | 5 |
| 未尝试 | 0 | 0 |
| 符号记录 | 233,005 | 238,795 |
| 直接调用边 | 82,785 | 81,762 |
| Go pclntab 函数 | 19,092 | 19,019 |
| pclntab 入口未被 Ghidra 收录 | 0 | 0 |
| ELF 不同函数符号地址 | 19,093 | 19,020 |
| ELF 函数地址未被 Ghidra 收录 | 0 | 0 |
| Ghidra 额外候选（不在 pclntab） | 12 | 9 |

来源为两架构 [coverage.json](amd64/coverage.json)、
[ARM64 coverage.json](arm64/coverage.json) 及
[Go 交叉核对](amd64/go-coverage-crosscheck.json)、
[ARM64 Go 交叉核对](arm64/go-coverage-crosscheck.json)。
外部函数表为空；编入 ELF 的 runtime 和第三方函数已包含在内部函数全量中。

Go 表中 `pcHeader.textStart` 在文件里为 0，交叉脚本采用 ELF `.text` 起址；
逐条入口与 ELF 函数名对照，统一 `.abi0` 和中点局部类型名后 **19,092 / 19,019
条全部吻合**。这不是仅凭函数数量相近判定覆盖。原始名称差异保留在
`pclntab-elf-name-aliases.tsv`。

不能把入口覆盖说成“每个代码字节都已理解”。Ghidra 函数 body 外尚有：

| `.text` 范围核对 | AMD64 | ARM64 |
| --- | ---: | ---: |
| `.text` 总字节 | 9,877,169 | 8,572,244 |
| 函数 body 外字节 | 365,137 | 177,048 |
| 其中匹配常见填充字节模式 | 316,766 | 133,300 |
| 其余未分类字节 | 48,371 | 43,748 |
| body 外地址段 | 25,831 | 20,725 |
| pclntab 相邻入口跨度外的尾部字节 | 16 | 19 |

完整范围和每段哈希在 `text-unassigned-ranges.tsv`。填充模式只做字节模式分类；
其余可能含分支尾段、跳表或识别边界差异，未自动认定为新函数或无用数据。
Go 相邻入口跨度包含对齐填充，不能拿跨度代替指令反汇编覆盖。
Ghidra 额外候选也未强行当作 Go 源函数：ARM64 的两个候选位于 `.text` 外，
其中 `009d77e6` 出现非对齐指令告警；仍保留原始识别记录。

## 最终失败记录

| 架构 | 地址 | 函数 | 原因 |
| --- | --- | --- | --- |
| AMD64 | `0043cb40` | `runtime.(*mheap).reclaimChunk` | `Conditional execution: Illegal op in iblock` |
| AMD64 | `00b273c0` | `github.com/pion/dtls/v2.(*State).deserialize` | `Cannot properly adjust input varnodes` |
| ARM64 | `000129b0` | `internal/bytealg.Count` | `Unable to find unique hash for varnode` |
| ARM64 | `000129c0` | `internal/bytealg.CountString` | 同上 |
| ARM64 | `00012e00` | `internal/bytealg.IndexByte` | 同上 |
| ARM64 | `00012e10` | `internal/bytealg.IndexByteString` | 同上 |
| ARM64 | `00800bc0` | `crypto/internal/fips140/aes/gcm.gcmAesEnc.abi0` | 同上 |

详见 `amd64/failures.tsv` 和 `arm64/failures.tsv`。每条两次尝试记录均在 journals。
首轮 AMD64 `modernc.org/sqlite/lib._sqlite3VdbeExec` 在 60 秒超时，180 秒重试成功，
历史超时没有抹去。最终 Juku 自有命名空间每架构 **2,289 个函数均成功输出伪 C**。

## 目录与使用

```text
juku-full-20261019/
  README.md / DESIGN.md / ASSETS.md
  assets/                       原始资产索引与可安全保留的原文
  amd64/ 和 arm64/
    functions.tsv               全部识别函数（权威分母）
    index.tsv / failures.tsv    最新状态、尝试次数、伪C/asm路径
    symbols.tsv                 全符号表
    functions/地址前四位/       每函数 .c / .asm / .calls.tsv
    calls.tsv / callers.tsv     正向/反向静态直接调用边
    modules.tsv / module-calls.tsv
    journals/                   每次worker逐函数完成记录
    function-body-ranges.tsv
    go-pclntab-functions.tsv / elf-function-symbols.tsv
    go-coverage-crosscheck.json / text-unassigned-ranges.tsv
    artifact-manifest.tsv        每个证据文件的大小与SHA-256
  archives/                     两架构完整静态证据ZIP及校验JSON
```

`modules.tsv` 的模块名是基于 Go 限定符号的启发式分组，通用实例和编译器生成符号
单独归类；不把分组数当作准确依赖包数量。直接调用图不含所有接口分派、闭包调用、
HTTP 请求和远端服务关系。Go ABI 的寄存器、多返回值、指针类型恢复有误差，必要时
须看 `.asm`、原始 Python 和两个架构交叉证据。

大体积函数散文件和 ZIP 在本地保留，`.gitignore` 避免误将 11 万余散文件整体提交。
两个 ZIP 已作为[私库 Release 附件](https://github.com/2223M1/bobbi-tv/releases/tag/audit-20261019-private-ce1909)
上传并核对 GitHub SHA-256；网页审阅请用下表下载链接，不依赖 ignored 本地路径。
每架构 ZIP 含全部该架构静态导出和 manifest，不含原始安装包、ELF、账户状态或私钥。
校验结果见 `archives/amd64-archive.json` 与 `archives/arm64-archive.json`。

| 已逐项校验的证据包 | 字节 / 文件项 | SHA-256 |
| --- | --- | --- |
| [juku-0.80-amd64-full-static.zip](https://github.com/2223M1/bobbi-tv/releases/download/audit-20261019-private-ce1909/juku-0.80-amd64-full-static.zip) | 49,114,616 / 57,341 | `507afb7d91792188e285f89c2ef84b29aadea766833c0b52b405c43521bef7a9` |
| [juku-0.80-arm64-full-static.zip](https://github.com/2223M1/bobbi-tv/releases/download/audit-20261019-private-ce1909/juku-0.80-arm64-full-static.zip) | 51,980,628 / 57,113 | `20685353b7567a8eb1702881a24361a06e699a7fd7bc14c651d94cfd9dbc8100` |

收尾复核重新读取两个 ZIP 的 **114,454 个条目**，逐项核对 manifest 的长度与
SHA-256，并重新计算 ZIP 整体哈希；均一致。直接从归档内 `index.tsv` 复算成功/失败，
确认 7 个失败均有两次尝试及非空反汇编，两个架构的 2,289 个自有函数分别全部成功。
资产核验以只读方式重跑，结果与既有 `assets/verification.json` 完全一致；没有重新
生成归档或改写原始证据。这里验证的是交付完整性，不扩大源码恢复或实机保证。

## 续跑示例

已有工程目录：
`C:/Users/theon/AppData/Local/Temp/am6b-juku080-audit-c1d94364ca0449caac433205113d487c/ghidra-project`。
工具根目录：
`D:/AM6B-Project/AM6B-review-ui-anirss-20261018/ui-redesign/runtime/juku-research-20261019/tools`。

```text
analyzeHeadless <project-dir> juku080 -process daemon-linux-amd64
  -readOnly -noanalysis -scriptPath <repo>/tools
  -postScript ExportJukuFull.java <output>/amd64 4 60 false

# ARM64换工程名 juku080-arm64、程序 daemon-linux-arm64 和输出目录。
# 最后参数 true 才重新尝试历史失败；完成的函数不再反编译。
python tools/summarize_juku_full.py <output>/amd64
python tools/crosscheck_juku_go_functions.py <fixed-elf> <output>/amd64
python tools/package_juku_full.py <output>/amd64
```

Ghidra 工程、固定 ELF 和脚本都用于本地静态研究；只需执行分析器，不能把样本 daemon
当成分析步骤启动。若未来样本哈希改变，使用独立输出目录和新固定输入记录。
