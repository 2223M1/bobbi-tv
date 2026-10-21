# Bobbi TV CE2021 clean 独立审查交付包

固定对象：`b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2`，分支 `codex/ce2021-clean-delivery-20261021`。审查日期：2026-10-21。

## 先读什么

1. `CE2021-REVIEW.zh-CN.md`：主审查结论、3 项发现、证据边界与后续规划。
2. `CODEX-EXECUTION-PACK.zh-CN.md`：可直接交给 Codex 的任务书，含依赖、行为契约、命令与关闭条件。
3. `FINDINGS.json`、`evidence/SOURCE-IDENTITY.json`：机器可读结论及固定来源。
4. `reviews/`：安装/停机、播放/UI、构建/发布的完整分报告与播放专项指导。
5. `checks/`：4 份独立反例脚本；`evidence/` 保留本轮结果、当前 CI 原始 ZIP/日志和元数据。

## 核心结论

要求修改：真实修复源码没有进入当前分支；当前 CI 和构建/入口审计契约未闭环；专用重签器允许更早合法输入并写错原代次。当前 Git 的失败不等同于未取得的 CE2021 release ZIP 失败。

当前 CI：2679 通过 / 5 失败 / 5 跳过 / 0 errors。四组独立反例合计：17 项，11 通过 / 6 失败 / 0 errors；它们与 CI 分开记账。没有执行设备变更或真实 release ZIP 验签。

## 使用与校验

在项目声明测试依赖可用的环境中，按任务书对指定完整源码运行 `checks/`。脚本退出 1 代表契约失败，2 代表执行错误。原始结果包含夹具边界和实际源文件摘要；参考 commit 标签不是未来候选的真实身份。

`MANIFEST.json` 列出除 MANIFEST、SHA256SUMS 本身以外全部文件的 bytes/SHA-256；`SHA256SUMS.txt` 包含 MANIFEST 与所有非自身文件的摘要。本包包含审查产物和证据，不复制整个 Git 仓库，不含签名私钥、设备账号或临时下载凭据。

完整主报告和任务书已包含可审查的事实与下一步，不需要依赖聊天中间进度才能使用。
