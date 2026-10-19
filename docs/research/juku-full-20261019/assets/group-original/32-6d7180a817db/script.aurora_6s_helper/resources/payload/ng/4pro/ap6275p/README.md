# 4 Pro / AP6275P / NG

对应 A4111、S905X4 rev A/B/C、AP6275P / BCM43752（PCI ID `14e4:449d`）。
设备树标识：`sc2_s905x4_tencent_aurora_4pro_ap6275p_ng`。

DTS及编译产物保存在工作区 `output/aurora4pro-ap6275p-ng-20260924/`，
生成脚本为 `work/build_4pro_ap6275p_ng.py`。基于已在本4Pro运行的6S NG设备树，
仅改变model及dt-id，保留NG的PCIe供电域、GPIOX_3复位、GPIOX_6无线电源、
UART蓝牙和TCA6507三通道配置；不能与NO设备树混用。默认蓝色，sys_led保持使能。

- Wi-Fi使用CE自带Broadcom驱动，蓝牙由原有80-brcmfmac_pci.rules启动
  brcmfmac_sdio-firmware-aml.service，加载BCM4362A2.hcd。
- 只附带NG TCA6507模块、LED加载脚本和独立systemd服务。
  模块要求4.9.269及匹配内核ABI；服务名和路径保留aurora6s-ng前缀以兼容旧部署。
- 不部署Realtek模块/配置或V12规则，不新增无线加载服务。
- 安装前备份旧文件和链接，清理已知8852be.ko、rtkm.ko、rtl8852bs_config、
  aurora6s-ng-wifi.service及旧Wi-Fi/Realtek蓝牙启动链接。
  有旧bt-uart-keepalive服务时停用并记录原启用/运行状态。未知文件不会递归清除。
- 需要重启完成驱动和设备树切换；失败可通过备份restore.sh恢复（恢复后也需重启）。

当前基础配置已在CE21.3 mephis NG验证Wi-Fi、蓝牙扫描连接及按键。
本专用版本已部署并暖重启，确认博通Wi-Fi/蓝牙与灯控自动运行、Realtek模块未加载。
用户确认Wi-Fi扫描、蓝牙遥控连续按键和灯条均正常；断电冷启动尚未另行验证。
详细记录见工作区work/aurora4pro-ng-repair/。
