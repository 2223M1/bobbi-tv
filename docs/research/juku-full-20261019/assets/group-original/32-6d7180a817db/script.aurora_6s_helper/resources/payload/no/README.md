# NO 自定义 DTB 启动优化

NO 的 6S、4 Pro / RTL8852、4 Pro / AP6275P 硬件修复均安装
`/flash/post-sysroot.sh`。CoreELEC initramfs 在挂载 SYSTEM 后加载该脚本，
随后才执行 `check_amlogic_dtb`。

CE 的检查在自带 `device_trees` 中查找 DTB 名称；插件使用的 `_hs400` 自定义
标识不在此目录中，因此官方 NO 系统会提示 DTB 过旧并等待 30 秒。
脚本只在 NO 系统、存在 CoreELEC DT 标记且当前 DT ID 精确匹配插件三种
自定义标识时替换该名称检查函数，不更改 DTB 或硬件参数。

安装器备份原脚本，保留其中其他内容，仅添加或更新
`BEGIN/END Aurora NO DTB check` 标记之间的片段。恢复本次修复的备份时，
还原原脚本；原先没有脚本则删除新增文件。旧版本备份的恢复文件清单保持不变。

更新插件后，在 NO 系统重新执行“修复硬件”并重启即可应用。
安装到 eMMC 时，此脚本随 `/flash` 文件一起复制。
