# 第三方组件与许可范围

插件原创部分采用 **GPL-2.0-or-later**，授权声明见 [NOTICE](NOTICE)，GPLv2 全文见 [LICENSE](LICENSE)。`addon.xml` 的许可字段描述插件原创部分，不表示安装包内所有文件都能按同一种许可证重新授权。

## 随包组件

| 组件 | 许可证与来源 |
| --- | --- |
| ampart 可执行文件、源码和构建文件 | 版权所有 7Ji，采用上游 GPLv3 授权。完整许可与原始声明保留在 [vendor/ampart](resources/emmc/vendor/ampart/README.md) 和 [LICENSE](resources/emmc/vendor/ampart/LICENSE)，另有 [许可副本](resources/emmc/LICENSE.ampart)。使用 v1.4.1 aarch64 静态发行文件，源码提交 `1539ff2f6fa73ef78dfde3ac585fb9c93244e85e`；下载地址、哈希见 [来源记录](resources/emmc/provenance.json)。 |
| `8852be.ko`、`rtkm.ko` | 来自 [CoreELEC/RTL8852BE-aml](https://github.com/CoreELEC/RTL8852BE-aml/tree/5da5adca92ac38a6c3a782147d45e48da577dce3)。Realtek 驱动源码声明 GPLv2，二进制模块标记 `GPL`；具体文件保留上游的版权与许可。插件的 “or later” 授权不扩展到这些第三方模块。 |
| `leds-tca6507.ko` | [CoreELEC/linux-amlogic](https://github.com/CoreELEC/linux-amlogic/blob/50c8e8154c5aba3c7cd8438d04dd5fdd51733e41/drivers/leds/leds-tca6507.c)，源文件声明 `GPL-2.0-only`，模块标记 `GPL v2`。GPLv2 全文随本插件 [LICENSE](LICENSE) 提供。 |
| 专用 DTB、`rtl8852bs_config` | 属于对上游设备树或配置的适配，沿用各自原始材料的权利和许可，不因本插件的许可声明而统一改为 GPL-2.0-or-later。蓝牙配置来源为 [CoreELEC/rtkbt-firmware-aml](https://github.com/CoreELEC/rtkbt-firmware-aml)；设备树与配置的具体分发条件应按对应源文件核对。 |
| `resources/logo/stock-logo.img.gz` | 从原厂固件提取的 Logo 资源，来源和哈希见 [素材说明](resources/logo/README.md)。未取得该素材的开源许可证，不属于本项目 GPL 授权范围；不能据此主张素材或商标的再授权权利。 |

ampart 通过独立进程、命令行和临时镜像调用，没有把它的 C 源码链接进插件 Python 程序。当前按独立组件分别保留许可证；这不意味着任意形式的 GPL 程序间交互都自动构成独立作品。可参阅 [GNU GPL FAQ：独立程序与聚合分发](https://www.gnu.org/licenses/gpl-faq.html#MereAggregation)。

发布 GPL 二进制时，应按对应许可证提供与所发布版本匹配的源码、修改及必要构建材料。此处列出的来源链接和模块许可标记不是对整个发行包已满足全部分发义务的证明。

## 系统依赖与实现参考

- **Pillow**：使用 CE 系统提供的库，不在插件中打包。其 HPND/MIT-CMU 等许可及第三方声明以 [Pillow 上游许可目录](https://github.com/python-pillow/Pillow/tree/main/LICENSE) 为准。
- **CoreELEC 系统驱动和工具**：包括系统提供的博通驱动、蓝牙服务及文件系统工具，继续适用各自许可证。
- **AOSP liblp / libsnapshot**：作为 Android 动态分区和 OTA 快照格式参考，本项目来源记录注明采用独立解析实现；没有把整个 AOSP 库打包进插件。原始文件许可仍属于上游。
- **AM9 Pro 安装器及 Logo 工具**：作为流程和资源格式参考，链接见 [README](README.md)。参考来源不代表其代码已获本项目重新授权；若引入具体代码，应同时保留并遵守该代码的原始许可。
