# 极光 6S / 4 Pro 助手

适用于腾讯极光 **6S（A4112）** 和 **4 Pro（A4111）**，支持 CoreELEC **NG 21.x / NO 22.x**，兼容 RTL8852 和 AP6275P 无线版本。

## 功能介绍

- **硬件修复**：修复 Wi-Fi、蓝牙和灯条，支持恢复修复前的配置；NO 支持芝杜 V12 遥控器输入修复，并跳过插件自带 DTB 引起的 30 秒开机等待，蓝牙开机初始化失败时自动重试一次。
- **6S / 4 Pro RTL8852 待机唤醒（NG / NO）**：初始化后和每次待机前，自动选取当前已配对且受支持的蓝牙遥控器（已连接优先，最多 10 只），新增或取消配对无需重做硬件修复，唤醒后自动恢复蓝牙；可选择待机前关闭有线网卡、醒后恢复。RC173 排除在动态名单外，保留原有电源键唤醒；其他加入名单的遥控器可能由方向键等唤醒，不保证仅电源键。
- **灯光控制**：调节颜色、亮度和呼吸速度，支持常亮、呼吸、关闭，可分别设置日常与播放时的灯效，开机自动应用。
- **安装 Android / CE 双系统**：将外置盘上的 CE、插件和设置迁入 eMMC，自选 Android 用户数据容量，其余可分配空间用于 CE。
- **移除内置 CE**：移除 eMMC 中的 CE，将其空间归还 Android。
- **修复双系统启动/布局**：处理已支持的启动异常和 Android OTA 后的布局问题，符合条件时恢复 OTA 目标系统启动。
- **eMMC 备份与还原**：手动完整备份 eMMC，支持在原机校验并还原备份。
- **eMMC 健康度**：查看芯片型号、容量、寿命估计和备用块状态。
- **启动第一屏**：预览和更换开机 Logo，支持 PNG、JPG、BMP 图片，也可恢复内置原厂第一屏。

安装、移除双系统会重置 Android 应用和用户数据，且不会自动备份。相关写盘操作请从外置 CE 发起，并按界面提示操作；插件作者不对刷双系统造成的损失负责。

## 源码与素材来源

| 组件 | 源码来源 |
| --- | --- |
| RTL8852BE Wi-Fi 驱动及内存模块（`8852be.ko`、`rtkm.ko`） | [CoreELEC/RTL8852BE-aml](https://github.com/CoreELEC/RTL8852BE-aml/tree/5da5adca92ac38a6c3a782147d45e48da577dce3) |
| TCA6507 灯条驱动（`leds-tca6507.ko`） | [CoreELEC/linux-amlogic — leds-tca6507.c](https://github.com/CoreELEC/linux-amlogic/blob/50c8e8154c5aba3c7cd8438d04dd5fdd51733e41/drivers/leds/leds-tca6507.c) |
| Realtek 蓝牙配置（`rtl8852bs_config`） | 基于 [CoreELEC/rtkbt-firmware-aml](https://github.com/CoreELEC/rtkbt-firmware-aml) 的配置进行修复 |
| AP6275P / BCM43752 Wi-Fi（NG/NO 系统自带博通驱动，插件不附带模块） | [CoreELEC/ap6xxx-aml](https://github.com/CoreELEC/ap6xxx-aml/tree/f0130717e2cdfc0d339a10e5b430ef15ee6b0c29) |

插件打包的 NG 驱动模块编译自上述固定提交。蓝牙使用 CoreELEC 自带的驱动和启动服务，RTL8852 使用插件提供的修复配置，AP6275P 使用系统博通固件。

| 组件或参考 | 来源 |
| --- | --- |
| eMMC 分区工具 ampart | [7Ji/ampart](https://github.com/7Ji/ampart/tree/1539ff2f6fa73ef78dfde3ac585fb9c93244e85e)，使用上游 v1.4.1 的 aarch64 静态可执行文件，GPL-3.0 |
| eMMC 安装流程参考 | [AM9 Pro 开源安装器](https://github.com/dangerouslaser/ugoos-am9-pro-coreelec-emmc/blob/581ca4f7a441461b957d814cc9beb1a1cca6cfe5/ce-emmc-install.sh)，本插件后端由本项目 `CE_android/tools` 研究流程整理 |
| Android 动态分区与 OTA 快照格式 | AOSP Android 11：[liblp](https://android.googlesource.com/platform/system/core/+/refs/heads/android11-release/fs_mgr/liblp/include/liblp/metadata_format.h)、[libsnapshot](https://android.googlesource.com/platform/system/core/+/refs/heads/android11-release/fs_mgr/libsnapshot/snapshot.proto)，用于本项目解析实现的格式参考 |
| Amlogic Logo 资源格式参考 | [AM9 Pro aml-logo-tool](https://github.com/dangerouslaser/ugoos-am9-pro-coreelec-emmc/blob/main/img-tools/aml-logo-tool.py) |
| 图片处理 | [Pillow](https://github.com/python-pillow/Pillow)，使用 CE 系统提供的库 |
| 原厂第一屏素材 | 从极光 6S 原厂 Logo 分区提取，详见 [素材说明](resources/logo/README.md) |

ampart 的可执行文件、源码、构建文件、许可证和来源记录随插件一并提供，源码位于 `resources/emmc/vendor/ampart`


## 开源许可

插件原创代码采用 **GPL-2.0-or-later**（GPL 第 2 版或更新版本），见 [授权声明](NOTICE) 和 [许可证全文](LICENSE)。可按许可证使用、修改和再分发；分发修改版时须保留相关声明，并按 GPL 提供对应源码。

ampart、驱动、设备树和原厂 Logo 等第三方组件保留各自许可与权利，不统一重新授权；详见 [第三方说明](THIRD_PARTY_NOTICES.md)。
