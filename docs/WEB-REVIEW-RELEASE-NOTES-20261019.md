# 私库审阅快照：CE1909 候选与原深度定制恢复

这是供 Web 独立审阅的成果归档，不是稳定发行或重新部署授权。

用户已要求停止验证。AM6B 已在 `20261019-220212` 恢复原深度定制：
旧 F9、`skin.am6b.cinema`、定制 JackTorr `1.2.2+am6b.317` 和原准备服务；
13 个新候选组件停用，账号及新旧 profile 保留。仅确认启动到首页，未继续试播。

阅读入口：

- [审查交接](https://github.com/2223M1/bobbi-tv/blob/codex/private-three-platform-20261019/docs/WEB-REVIEW-HANDOFF-20261019.md)
- [恢复说明](https://github.com/2223M1/bobbi-tv/blob/codex/private-three-platform-20261019/docs/CE-LEGACY-RESTORE-20261019.md)
- [发行门禁](https://github.com/2223M1/bobbi-tv/blob/codex/private-three-platform-20261019/release/gates.json)
- [Juku 全量结论](https://github.com/2223M1/bobbi-tv/blob/codex/private-three-platform-20261019/docs/research/juku-full-20261019/SUMMARY.zh-CN.md)

保留全部源码、部署/回退工具、测试结果及失败记录。1909 不能称为完整播放认证：
BT 首段缓冲、115 首播停顿、准备链路身份疑点和未验收项均在交接文档中列出。
Windows/Android 为暂停前的历史候选，并非当前 CE 同代认证。

Juku 0.80 AMD64/ARM64 的全部 38,132 个已识别函数均尝试反编译，
38,125 个伪 C 成功，7 个失败保留汇编和原因；不等于恢复原始 Go 工程。
两个完整静态 ZIP 与哈希直接附在本 Release。

其他大型成果以内容寻址归档交付：`manifest.json`/仓库附件清单记录每个原始路径、
字节数及 SHA-256；同字节文件仅保存一份，但全部原路径均可还原。
它们包含各代完整签名组件包、历史 Windows/Android 成品及原生构建证据。
重复构建目录、可重新取得的 SDK/工具链缓存、真实账户 profile 和签名私钥不作为源码成果上传。

私库仅限制访问范围，不改变第三方素材的许可证；来源与原始说明保持。
审阅时请区分“候选代码”“历史验证”“当前运行旧深度定制”，不要自动安装附件。
