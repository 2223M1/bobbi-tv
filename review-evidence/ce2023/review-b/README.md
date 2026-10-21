# CE2021 审查与 Codex 执行包

本包用于审查与指导后续整改，不是 Kodi 安装包。

## 阅读顺序

1. [完整审查](01-REVIEW.md)
2. [Codex 下一轮任务](02-CODEX-NEXT-TASK.md)
3. [验收矩阵](03-ACCEPTANCE-MATRIX.md)
4. evidence/ 中的事实、CI 摘录、路径检查与复现结果

冻结对象是 GitHub commit b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2。最终复查时分支仍指向它，CI run 39525777378 仍为 failure。

本次完成源码与交付链审查。Release 附件下载被 Chrome 拦截，未取得包字节；没有执行设备操作。完整报告对这些范围有明确标记。

## 诊断脚本

三个脚本均要求显式 --repo，读取本机已有源码树，不下载仓库或连接 AM6B。它们不包含产品源码、不带维护密钥，也不会修改项目源码。

这些脚本用于定位冻结旧源码中的已知问题。新实现改变接口后，应按行为契约迁移夹具；不要把这些脚本原样作为未来CI或发布门禁。

在项目已有 Python 测试环境中运行，示例中的源码目录需替换为实际路径：

```text
python probes/probe_lifecycle.py --repo /path/to/bobbi-tv --expected-head b20e972da6efd25eeeb19f8dcb8fae38eed1dfb2
python probes/probe_ui_monitor.py --repo /path/to/bobbi-tv
python probes/probe_entry_builder.py --repo /path/to/bobbi-tv
```

| 脚本 | 方法与范围 |
|---|---|
| probe_lifecycle.py | 导入完整真实生命周期模块，临时profile与真实OS锁；需要本机127.0.0.1监听权限，无外部服务访问 |
| probe_ui_monitor.py | AST提取原方法，使用明确的Kodi消息队列/IPC替身；不等于完整插件或设备测试 |
| probe_entry_builder.py | 将所需原源码复制到临时目录，用临时RSA密钥构造两组件签名包；实际build和验签保持，需cryptography依赖 |

统一退出码：

- 1：观察到目标历史问题。这是问题复现，不是产品通过。
- 0：在兼容的限定夹具中没有复现。不能单独据此关闭缺陷。
- 2：源码/接口/依赖/权限不适配，或其他运行故障。不能计为修复通过。

生命周期脚本额外支持 --source-label 标记非Git导出目录；标签不是独立验证的源码身份。三个脚本不会修改生产信任根、账号、设备或现有profile。

## 本包包含的回执

- review_facts.json：冻结对象、实际CI、版本与资产元数据、审查限制。
- ci_excerpt.txt：GitHub原始CI日志的关键摘录，保留UTC时间和原行号。
- inventory_missing_paths.json：Git树与显式源码清单的路径成员差异，非全库文件摘要复算。
- report_links.json：报告26个相对证据链接的Git树存在性核对。
- lifecycle_observed.json、ui_monitor_observed.json、entry_builder_observed.json：审查阶段实际取得的最小复现结果。

回执属于当前冻结源码或临时夹具，不属于清理重签后的Release包实测。本包不带目标项目源码副本；GitHub源码引用均指向固定commit。

## 文件完整性

SHA256SUMS.txt 仅用于核对本审查包内部文件，不是应用包签名、发布认证或设备验证。

