# 4 Pro / RTL8852 / NO

A4111 / S905X4 rev D 使用与 6S NO 相同的修复方案，包含 DTB、Realtek config18 和 V12 输入规则。
DTB 以 `no/6s/dtb.img` 为基础，仅更改 `model` 和 `coreelec-dt-id`：
`sc2_s905x4_tencent_aurora_4pro_rtl8852_hs400`。

与 6S 共用同分支的 RTL8852 修复实现，仅保留机型专属名称和设备树标识。

自 1.6.1 起，默认启用 eMMC HS400，`tx_delay=16`；dt-id 使用 `_hs400` 后缀，区别于官方标识。4 Pro/AP6275P 已通过本机基础读写测试，其他硬件版本仍需实机确认。

1.9.1 纳入与 6S 共用的蓝牙心跳、动态唤醒名单（排除 RC173）及可选有线待机处理。NO 使用已验证的 hciconfig 关闭/重新打开恢复接口，不安装 NG 恢复模块或 PCIe 启动参数。
