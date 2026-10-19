# 4 Pro / AP6275P / NO

`dtb.img` 对应 A4111、AP6275P / BCM43752（PCI ID `14e4:449d`）。
来源：本工作区 `output/aurora4pro-ap6275p-no-20260924/`，该目录保留 DTS、差异和验证记录。
设备树标识：`sc2_s905x4_tencent_aurora_4pro_ap6275p_hs400`。

已在 CoreELEC 22.0-Piers_nightly_20260920 / Amlogic-no / Linux 5.15.196 验证
Wi-Fi、蓝牙和 RGB 灯条正常，连续两次暖重启自动加载成功。
随后仅更改 dt-id；插件识别检查已确认新标识在实机生效，最终版本尚未单独验证断电冷启动。

使用 CE 自带 `dhdpci`、Broadcom 固件及蓝牙初始化服务；不需要 Realtek 蓝牙配置、
NG 外置模块。插件已接入该版本的识别、DTB 安装与灯控入口。

与所有 NO 修复包一样，附带 `99-zidoo-v12-keyboard.rules`，用于纠正 Remote-V12
键盘接口被误标为 tablet/tablet-pad 的问题。只匹配蓝牙 VID/PID `5a44:5a44` 的
`Remote-V12 Keyboard`，不修改独立的鼠标接口；该修复与无线芯片型号无关。

自 1.6.1 起，默认启用 eMMC HS400，`tx_delay=16`；dt-id 使用 `_hs400` 后缀，区别于官方标识。4 Pro/AP6275P 已通过本机基础读写测试，其他硬件版本仍需实机确认。
