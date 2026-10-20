# 私库审阅附件索引 · 2026-10-19

这些是停用候选和历史研究成果，不是安装或继续测试的授权。盒子已恢复原深度定制。
源码冻结标签为 `audit-20261019-private-ce1909`，提交为
`cdf0c487c3640228cfe5844a3af2813e5367aa3b`；后续文档提交不改变该源码快照。

[Release 下载入口](https://github.com/2223M1/bobbi-tv/releases/tag/audit-20261019-private-ce1909)
需要私库访问权限。7 个附件均已完成上传，远端状态与大小见
[交付状态回执](../review-evidence/web-delivery-20261019.json)。按用户要求，本次收尾
不做哈希核验；下表是既有打包清单的哈希，不代表本轮重新校验。

## 覆盖范围

共覆盖 **509 个原始路径、5,625,140,589 原始字节**。507 个路径按 SHA-256 去重为
184 个对象，放入四个独立 ZIP；另外两个 Juku ZIP 直接附加。四份 ZIP 不是分卷压缩，
可以独立打开，不能顺序拼接。本次白名单的 509 个路径没有遗漏或待隔离项；
这不是整个工作区所有缓存和私人状态均已上传的声明。

| 类别 | 原路径数量 | 说明 |
| --- | ---: | --- |
| 完整签名候选包 | 17 | CE 与历史代次，不能绕过高水位重放 |
| 冻结组件及清单 | 422 | 各代完整组件与版本、签名关系 |
| 原生平台实际产物 | 32 | Windows / Android 历史候选，不等于实机认证 |
| CE 原生源码与隔离构建输出 | 30 | 基线、控制、候选及对应中间证据 |
| 原生构建日志 | 6 | 保留构建结果和失败上下文 |
| Juku 全量静态归档 | 2 | 两架构全函数伪 C、汇编、索引与失败记录 |

所有源码、小型证据和文档仍直接保留在审查分支。真实账号/profile、私钥、会话和
可重新取得的 SDK/工具链缓存不在附件内；本机原件没有被删除。边界见
[审阅交接](WEB-REVIEW-HANDOFF-20261019.md)。

## 下载与整体哈希

| 文件 | 字节 | SHA-256 |
| --- | ---: | --- |
| [成果 01](https://github.com/2223M1/bobbi-tv/releases/download/audit-20261019-private-ce1909/bobbi-web-artifacts-20261019-01.zip) | 1,449,992,354 | `34e9991eabb43fa3afd931375bf6dce9c4dd279a390d892f8476ea08c3e21731` |
| [成果 02](https://github.com/2223M1/bobbi-tv/releases/download/audit-20261019-private-ce1909/bobbi-web-artifacts-20261019-02.zip) | 1,449,990,466 | `5ec8043bf2a900b3b1f7125d7a14cf0889aba6ac10e7b710b72612500f102f1a` |
| [成果 03](https://github.com/2223M1/bobbi-tv/releases/download/audit-20261019-private-ce1909/bobbi-web-artifacts-20261019-03.zip) | 1,449,989,981 | `d961ba272419182b76cd912f850563c351c72b24f17412636432b11e8d68ca00` |
| [成果 04](https://github.com/2223M1/bobbi-tv/releases/download/audit-20261019-private-ce1909/bobbi-web-artifacts-20261019-04.zip) | 444,894,642 | `a0ca5b6dfb4d6f04f7d865c5a13223eb51852f288e506d1d2b3d9f39e92b6868` |
| [Juku AMD64](https://github.com/2223M1/bobbi-tv/releases/download/audit-20261019-private-ce1909/juku-0.80-amd64-full-static.zip) | 49,114,616 | `507afb7d91792188e285f89c2ef84b29aadea766833c0b52b405c43521bef7a9` |
| [Juku ARM64](https://github.com/2223M1/bobbi-tv/releases/download/audit-20261019-private-ce1909/juku-0.80-arm64-full-static.zip) | 51,980,628 | `20685353b7567a8eb1702881a24361a06e699a7fd7bc14c651d94cfd9dbc8100` |
| [完整产物清单](https://github.com/2223M1/bobbi-tv/releases/download/audit-20261019-private-ce1909/web-artifact-manifest-20261019.json) | 37,771,745 | `a58ae6a6f7393c50a97a2ae12bcb801dde5fa7584bb1e0a4f5cb65f72ee0b6d1` |

## 按原路径取证

完整清单较大，包含 73 个 ZIP/APK 及嵌套组件的逐成员审计。网页无法展开时下载 JSON：

1. 在顶层 `files` 中按 `path` 查原始相对路径，核对 `bytes` 与 `sha256`。
2. `status=packaged`：下载 `attachment` 所指文件，在该 ZIP 中取出 `member` 对象。
   对象成员以内容哈希命名，不带原扩展名；需要阅读或解包时复制为原文件名。
3. `status=existing_attachment`：直接下载同名 Juku ZIP，没有第二层对象映射。
4. 对取出的内容核对大小与 SHA-256。一个对象可以对应多个原路径，这是去重，非遗漏。

四份内容寻址 ZIP 只保存对象，路径映射在单独的完整产物清单中，请一并下载。
该清单的 `objects` 保留全部 `original_paths`，`archive_audits` 保留嵌套文件的
成员哈希和检查结果。只读解包，不执行附件内程序。

在保留全部原始工作区的维护端，可用 `python tools/package_web_artifacts.py --verify-only`
复核原文件、附件及成员一致性；仅下载附件的审查端不具备这条命令所需的所有原路径。
`tools/verify_web_delivery.ps1` 则查询 GitHub 元数据并重算本地附件哈希；它保留供后续
自选复核，本轮按用户要求未运行。两者都不是播放测试。
