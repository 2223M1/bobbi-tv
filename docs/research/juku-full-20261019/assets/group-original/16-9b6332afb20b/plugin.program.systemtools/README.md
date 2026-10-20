# Kodi 系统工具箱 (plugin.program.systemtools)

专为 Kodi (Matrix 19 / Nexus 20 / Omega 21 / Piers 22) 及各类嵌入式机顶盒系统（CoreELEC、LibreELEC、Android、外贸电视盒子、Linux、Windows）设计的全功能系统工具箱插件。

## 主要功能

### 1. CoreELEC 多版本管理与切换 (CoreELEC Version Switcher)
- **从 .tar 升级包导入新版本**：支持选择任意版本的 CoreELEC `.tar` 升级包（如不同大版本、测试版、Nightly 构建等），纯 Python `tarfile` 流式解包自动提取 `KERNEL.img`、`SYSTEM` (SquashFS) 及对应 MD5 校验文件。
- **解包后按需删除原始 TAR 文件**：解包提取完成后，弹窗询问是否删除原始 `.tar` 安装包（释放约 250MB~350MB 存储空间，亦可在设置中开启自动删除），防止重复占用宝贵磁盘空间。
- **持久化版本池 (/storage/.ce_versions/)**：版本池存储在容量充足的 ext4 数据分区，彻底避免 `/flash` FAT 引导分区（通常仅 512MB）因多镜像存储而溢出损坏。
- **配置隔离与开机自动恢复**：各版本独立保存配套的 `guisettings.xml`。通过 `/storage/.config/autostart.sh` 开机钩子，在系统引导、Kodi 启动前精准还原对应版本的设置；切换时使用 `sync && reboot -f` 极速重启，避免 Kodi 退出时内存设置反向覆盖目标配置。
- **当前系统一键备份**：支持将当前正在运行的 `/flash` 镜像与 Kodi 运行配置备份为新的独立版本槽位，随时可一键回退。
- **已保存版本管理**：随时查看所有版本、一键切换已保存版本、或删除不需要的历史版本释放存储空间。

### 2. DTB 设备树防覆盖保护与管理 (DTB Protection & Management)
- **一键开关防自动覆盖保护**：管理 `/storage/.config/dtb-autoupdate.conf`（`ENABLE=no` / `ENABLE=yes`）。开启后，无论是 CoreELEC 官方在线升级、本地更新，还是通过本工具箱切换版本，均**绝对禁止覆盖设备的 `dtb.img`**，彻底保全定制设备树（如千兆网卡补丁、蓝牙WiFi补丁等）。
- **定制 DTB 一键备份与还原**：支持将当前正常运行的 `/flash/dtb.img` 备份至 `/storage/.config/custom_dtb.img`，即使误刷亦可随时一键写回 `/flash` 分区。
- **实时设备硬件树检测**：读取 `/proc/device-tree/model` 直观查看当前盒子型号与设备树载入状态。

### 3. 一键释放系统内存 RAM (Free System RAM)
- **深层内核缓存回收 (Drop Caches)**：安全执行 `sync` 将脏数据刷写回存储后，向 `/proc/sys/vm/drop_caches` 写入 `3`，强制内核立即释放 PageCache、目录项 (dentries) 与 inode 索引节点占用的内存。
- **Kodi 内部渲染与纹理缓存清理**：调用 Kodi 原生 `ClearCache` 清除积压的海报海量纹理与媒体流缓存，并触发 Python 堆垃圾回收 (`gc.collect`)。
- **清理前后详细对比看板**：直观展示清理前后内存总计、已用、可用容量与释放的体积（MB/GB），极大缓解 2GB/4GB 内存电视盒子长时间运行后的卡顿与闪退。

### 4. Kodi 性能与渲染优化 (Kodi Performance Optimizer)
- **SQLite 媒体数据库 WAL 并发加速**：遍历 `/storage/.kodi/userdata/Database/` 下的所有媒体数据库，自动开启 `PRAGMA journal_mode = WAL` 与 `PRAGMA synchronous = NORMAL`，使读写操作并行不锁库，彻底消灭上万部影视库浏览时的卡死与等待。
- **Mali GPU 渲染管线与防掉帧调优**：
  - 自动禁用异步纹理上传 (`<asynctextureupload>false</asynctextureupload>`)，杜绝多线程 EGL 上下文竞争引发的 `glFinish()` 阻塞与 GPU 驱动死锁卡死。
  - 禁用运行时动态多级贴图生成 (`<minifiedmipmapping>false</minifiedmipmapping>`)，杜绝主渲染线程执行昂贵的 `glGenerateMipmap()` 造成海报列表滚动丢帧。
  - 开启代价减少脏区域局部重绘 (`<algorithmdirtyregions>2</algorithmdirtyregions>`)，避免全视口重绘。
  - 缩略图分辨率智能限制（海报限制 540p、背景图限制 720p），释放高达 50% 显存与内存占用。
  - 为 SQLite 视频数据库分配 32MB 内存页缓存 (`<cache_size>-32768</cache_size>`)，海量媒体索引瞬间常驻 RAM。
- **安全备份与一键还原**：修改前自动为数据库和 `advancedsettings.xml` 生成 `.bak` 备份，支持一键无损还原。

### 5. R10/F10 固件高级设置 (Firmware Advanced Settings)
- **底层硬件专项深度调优**：专门针对 CoreELEC CPM R10、F10 等定制固件和晶晨芯片提供 35+ 项核心优化。
  - **音频引擎与 ALSA 输出**：PCM 最大位深限制（解决外部 DAC 握手 32bit 异常与爆音）、音频输出初始化静音保持时间（切格式切采样率防噼啪爆音）。
  - **视频播放与硬件解码**：蓝光菜单缓冲队列、无缝分段边界排空、异步字幕解析（消除 ASS/PGS 特效字幕加载掉帧）、全屏 OSD 异步渲染（解耦进度条与视频主帧率）、异步视频图层渲染、片尾最小 Seek 距离保护、Dolby Vision VSVDB V1 兼容模式、隔行扫描反交错延迟补偿、视频场频保持、VC-1 硬件解码三项优化（自动向驱动注入逐行/隔行模式、坏帧丢弃机制、时间戳自动校准）。
  - **GUI 渲染与 Mali 绘图管线**：基于 EGL Buffer Age 局部重绘（大幅降低 Mali GPU 负载与发热）、最大脏区跟踪矩形数、按键交互后跳过休眠活动窗口时间、菜单静止空闲帧率上限（极度降温省电）、皮肤 HDR FBO 宽色域渲染、客制化合成与脏区调试、各向异性过滤、Front-to-Back 渲染排序减少 Overdraw、几何缓冲清空、VSync 与 GPU 帧交换等待同步、sRGB HDR 色彩校正混合（防 SDR 皮肤覆盖在 HDR 视频上刺眼过饱和）、界面合成抖动抗色带处理、异步材质上传 PBO（快速滚动海报不卡顿）、皮肤 Mipmapping 渐远贴图与负向 LOD 锐化偏差。
  - **媒体库管理**：本地同名封面/海报是否区分大小写（NAS 挂载混有大写后缀时不漏图）。
  - **局域网协议**：NFS 连接超时时间与自动重试次数。
  - **远程数据库超时保护**：Video/Music/TV/EPG 远程 MySQL/MariaDB 5 秒超时保护，防止断网时开机卡死在黑屏。
- **分类呈现与原理解析**：不提供死板的预设大礼包，而是按 6 大核心模块清晰罗列，点击即可查阅原汁原味的原理解析说明长文本，明明白白调优。
- **实时安全合并与备份还原**：数值修改后立即安全增量更新 `advancedsettings.xml`，绝不触碰或破坏已有其他非冲突配置；首次写入自动备份 `.bak`，支持一键还原；退出时若检测到配置变更，贴心询问是否重启 Kodi 生效。

### 6. 全协议视频流测速与网络测速 (Network Speed Test)
- **局域网 / 网盘全协议测速**：
  - 基于 Kodi 原生 `xbmcvfs`，全面覆盖 `smb://`、`nfs://`、`webdav://`、`dav://`、`http://`、`https://`、`ftp://` 及本地挂载路径。
  - 选择任意大文件视频（建议 ≥1GB），采用 1MB 分块读取，**随读随弃，零内存缓存**。
  - 引入 **前 2 秒传输连接稳定期机制**，排除建立握手初期的低速波动，精准统计稳定期后的最高速度、最低速度。
  - 智能计算 **网络稳定度 (Stability Rate)**，提供 4K 蓝光原盘流畅度评级（卡顿风险预警 / 蓝光全速评估）。
  - 测速完成后自动调用垃圾回收与 Kodi 缓存清理 (`ClearCache`)。
- **互联网外网宽带测速**：
  - 测试 TCP 延迟 (Ping)、公网 CDN 多线程下载带宽与上传带宽。

### 7. 存储读写测速 (Disk Benchmark)
- 支持测试机顶盒内置存储 (eMMC)、SD 卡、U盘、外置移动硬盘或 NAS 挂载路径。
- **顺序写入与读取** (MB/s)。
- **4K 随机写入与读取** (MB/s 及 IOPS 吞吐量)。
- 强制同步 (`fsync` / `O_SYNC` / `O_BINARY`) 并通过内核 `drop_caches` 与 `posix_fadvise` 彻底消除内存缓存干扰，测得真实物理闪存性能。
- 退出与异常时通过 `finally` 安全自动清理临时测试文件。

### 8. 系统网络配置 (Network Configuration)
- 查看网卡接口（eth0、wlan0）、当前 IP、子网掩码、网关、DNS。
- 支持一键切换 DHCP 自动获取或配置静态 IP / 网关 / DNS。
- 针对 CoreELEC / LibreELEC 的 ConnMan 服务及通用 Linux `ip` 指令无缝集成。

### 9. 遥控器自动适配工具 (Remote Control Auto-Adapter)
- **11 款主流遥控器开箱即用适配**：包含 AM6B Plus 原厂 UR02、UR02 社区定制版、芝杜 V12 / V10 Mini、DUNE 杜恩、华为 R22、G20 Pro 语音飞鼠、MX3 2.4G 飞鼠、中国移动 2.4G / 蓝牙遥控器、腾讯极光 4 Pro 等。
- **用户自建 Keymaps 绝对保护**：分发的按键映射均采用 `remote_adapter_` 专属前缀，严禁触碰或删除用户已有的 `gen.xml`（Keymap Editor）或手写 `keyboard.xml`。
- **全量配置自动快照与一键无损撤销**：适配新遥控器前，自动将现存的 Keymaps、hwdb 硬件映射以及 `/flash/remote.conf` 完整快照备份至 `/storage/.remote_backup/`，支持随时一键无损还原。
- **出厂红外码安全保护**：切换至无需 `remote.conf` 的纯蓝牙遥控器时，原始出厂红外码文件自动重命名为 `remote.conf.factory` 妥善保存，杜绝出厂红外码永久丢失。

### 10. Kodi 日志管理与一键清理 (Kodi Log Cleaner)
- 自动定位 Kodi 日志目录 (`special://logpath/`)。
- 一键查看最近运行日志 (Tail Viewer)。
- 一键清空 `kodi.log`，清理 `kodi.old.log` 及崩溃日志 (`kodi_crashlog*`)。
- 支持清理前自动备份 (`.bak`)。

### 11. 每日自动重启 (Daily Auto Reboot)
- **systemd Timer 守护定时维护**：通过 Linux 原生 systemd 定时器服务每天在指定时间（支持 Kodi 原生时间拨盘输入）自动重启设备，彻底释放长时间运行的内存碎片与缓存泄漏。
- **系统开机时长防死循环校验**：内置 `UPTIME > 600s` 严格校验，若开机不足 10 分钟自动跳过重启，彻底杜绝因开机时钟偏差或整点刚启动引发的重启死循环。
- **一键启用与无残留彻底停用**：支持随时停用，自动卸载定时器、清除配置文件并重新载入 systemd 状态。

---

## 安装与打包

### 打包为 Kodi 安装包 (ZIP)
```bash
python scripts/package.py
```
生成安装包位于 `dist/plugin.program.systemtools-1.0.8.zip`。

### 在 Kodi 中安装
1. 打开 Kodi -> **设置 (Settings)** -> **插件 (Add-ons)**。
2. 开启 **未知来源 (Unknown sources)**。
3. 选择 **从 Zip 文件安装 (Install from zip file)**。
4. 浏览并选择 `dist/plugin.program.systemtools-1.0.8.zip` 即可完成安装。

---

## 开发者指令

### 安装开发依赖
```bash
pip install -r requirements-dev.txt
```

### 运行单元测试
```bash
python -m pytest tests/
```

### 运行单项测试
```bash
python -m pytest tests/test_os_switcher.py
python -m pytest tests/test_net_speedtest.py
```

### 运行测试覆盖率
```bash
python -m pytest --cov=resources.lib tests/
```

### 代码检查
```bash
flake8 resources/ addon.py tests/
```

---

## 全皮肤兼容统一 UI 架构 (v1.0.3+)

### 为什么选择原生详细选择对话框？
* **传统目录的皮肤缺陷**：原先通过 `xbmcplugin` 生成的 `plugin://` 目录列表，必须由**激活皮肤提供的媒体窗口**（`MyPrograms.xml`）来承载渲染。Kodi **不会跨皮肤回退** 窗口 XML 文件。如果第三方皮肤裁减了程序列表或插件视图失效，用户点击插件时就会出现无反应、黑屏或卡死。
* **原生详细对话框的优势**：
  1. **100% 皮肤无关**：由 Kodi 核心 C++ 直接渲染，任何皮肤、任何嵌入式设备均绝不闪退、不白屏、不卡死。
  2. **高颜值与风格原生自适应**：通过 `useDetails=True`，每个工具选项同时显示专属图标、主标题与独立副标题说明；且自适应继承当前皮肤的原生字体、半透明磨砂背景、高亮光标与音效。
  3. **杜绝外置贴图崩溃**：避免了自定义 `WindowXMLDialog` 在低配 Mali/GLES 驱动盒子上因纹理未加载导致的黑屏或文字悬浮现象。

### 启动方式与容器生命周期管理

| 启动方式 | Kodi 行为 | 工具箱处理策略 |
|---|---|---|
| **程序插件列表点击** | `RunAddon` 触发并附带容器句柄 (`handle >= 0`) | 调用 `endOfDirectory(succeeded=False)` 立即释放容器，消除媒体窗口的转圈等待，平滑弹出工具箱 |
| **收藏夹 / 皮肤快捷键** | `RunPlugin` 或快捷方式触发，无容器 (`handle = -1`) | 直接弹出工具箱原生详细对话框 |

### 快捷调用与收藏夹配置
在 `userdata/favourites.xml` 中可直接添加如下命令一键唤起工具箱：
```xml
<favourite name="系统工具箱">RunPlugin(plugin://plugin.program.systemtools/?action=menu)</favourite>
```
*注：URL 结尾不要带斜杠 `/`，以便 Kodi 识别为执行脚本而非目录。*

---

## 更新日志

### 1.0.8
* **新增遥控器自动适配工具（Remote Control Auto-Adapter）**：
  - 内置 11 款主流外贸与品牌遥控器（UR02、芝杜 V12/V10、DUNE、华为 R22、G20 Pro、MX3、移动蓝牙/2.4G 等）全套硬件驱动与按键映射。
  - **用户已有 Keymaps 绝对保护**：分发 XML 自动采用安全隔离前缀，严禁触碰或删除用户原有的 `gen.xml`（Keymap Editor）或手写 `keyboard.xml`。
  - **全量快照备份与一键撤销**：适配前全量快照备份旧配置至 `/storage/.remote_backup/`，支持一键无损还原。
  - **出厂红外码安全保护**：切换至纯蓝牙遥控器时自动将原出厂 `/flash/remote.conf` 重命名为 `.factory` 妥善保存，杜绝出厂红外码永久丢失。
* **新增每日定时自动重启工具（Daily Auto Reboot）**：
  - 基于 Linux systemd 定时器实现每日无人值守定时维护重启，集成 Kodi 原生时间拨盘输入。
  - **开机时长防死循环保护**：内置 `UPTIME > 600s` 校验，刚开机不足 10 分钟自动跳过重启，杜绝因开机时钟偏差或整点刚启动引发的重启死循环。
* **CoreELEC 多版本切换工具（OS Switcher）重启可靠性与文件系统安全增强**：
  - **彻底解决切回系统版本后偶发不自动重启问题**：分析定位到原位覆写 250MB 系统镜像触发内存回收导致外部命令（如 `systemctl` / `reboot -f`）因 SquashFS 缺页报段错误（SIGSEGV 139）崩溃。重构为常驻内存的内核级 Magic SysRq 安全重启序列（`s` 脏页全量刷盘 -> `u` 紧急设为只读以消除 FAT32 脏标记 -> `b` 硬件直接复位），100% 绕过用户态文件系统与外部二进制，彻底杜绝切系统后盒子卡死无响应。
  - **多级硬件与系统调用兜底体系**：按优先级串联 Magic SysRq、libc `reboot(0x01234567)` 系统调用与常规命令，确保在任何异常缺页状态下均能平滑自驱复位。
  - **前置落盘与安全保护**：在复位硬件前显式调用 `os.sync()` 并主动将 `/flash` 分区重新挂载为只读模式，完全消除文件系统未落盘隐患。

### 1.0.7
* **SQLite 媒体库复合覆盖索引极速优化（Widget 加速 7 ~ 26 倍）**：
  - 针对 Kodi 官方默认皮肤（Estuary）及流行第三方皮肤（AH2 / Nimbus / Titan）首页 Widgets 查询，自动检测注入定制复合与覆盖索引。
  - `idx_files_unwatched_recent`：针对“最近添加未观看影视”Widget，彻底消除内存临时 B-Tree 排序（`TEMP B-TREE FOR ORDER BY`），查询耗时由 1.86ms 骤降至 0.26ms。
  - `idx_art_covering`：针对海报与艺术图加载，建立涵盖所有检索列与 URL 的覆盖索引，消除主数据页二次回表读取，100 张封面连续加载耗时提速 3.3 倍。
  - `idx_bookmark_resume`：加速“继续观看 / 在播电影”断点进度检索，毫秒级即刻返回。
  - `idx_vv_lookup`：加速 Kodi 20/21 新增的多版本视频（videoversion）关联检索。
* **4K Page Size 块对齐与智能 VACUUM 碎片整理**：
  - 实现平滑安全的 `page_size = 4096` 块大小对齐逻辑，与 Linux ext4 文件系统及底层 eMMC / Flash 物理块 1:1 严格对齐，降低 B-Tree 树高。
  - 引入磁盘空间安全防御机制，可用空间不足 1.5 倍数据库体积时安全跳过 VACUUM，杜绝 `Disk Full` 风险。
  - 执行全量 `ANALYZE` 统计直方图更新，确保 SQLite 成本估算器始终选取最优索引扫描路径。
* **无损撤销与备份防遗漏安全增强**：
  - 新增“无损撤销自定义索引加速”功能，只需 0.01 秒即可安全 drop 自定义索引，无需覆盖还原整库，完整保留用户最新的观影历史与断点。
  - 备份 `.bak` 文件前强制执行 `wal_checkpoint(TRUNCATE)`，确保将 WAL 中的最新影视和进度完整刷入主库文件后再备份，杜绝备份丢失最新数据。

### 1.0.6
* **SQLite 媒体数据库 WAL 维护增强与一键日常瘦身**：
  - 新增“快速清理与收缩 WAL 日志”动作，使用 `PRAGMA wal_checkpoint(TRUNCATE)` 在线回写脏数据并将 WAL 物理文件截断归零，秒级完成且无需重启 Kodi。
  - 增加长事务读写锁冲突保护机制，遇到锁争用时自动优雅降级为 `PASSIVE` 模式，绝不阻塞卡死 Kodi UI。
  - 优化状态报告全面增强，直观展示各数据库主库体积与 WAL 体积，WAL 积压超过 16MB 阈值时自动给出预警提示。
* **优化与固件设置备份还原逻辑彻底修复与安全加固**：
  - 还原数据库时自动扫描并同步清理残留的 `.db-wal` 和 `.db-shm` 文件，彻底解决覆盖主库后旧 WAL 校验冲突导致 SQLite 报 `disk I/O error` 或文件损坏的严重隐患。
  - 在性能优化工具与 R10/F10 固件高级设置中同步引入缺席哨兵机制（`.not_exist`），彻底解决设备初始不存在 `advancedsettings.xml` 时修改配置后无法一键还原回无配置文件状态的缺陷。

### 1.0.5
* **存储测速全面对标 FIO 工业标准**：重构存储读写测试引擎，全面对标 FIO / CrystalDiskMark Q1T1 标准测试模型。
* **4K 随机读写页对齐直读直写**：引入 `mmap` 物理页对齐缓冲区与 `O_DIRECT`（直写闪存）及 `os.readv`（直读闪存），彻底解决写入数据被操作系统 PageCache 内存缓冲拦截导致写速度严重虚高的问题，测速结果与实机运行 FIO 3.37 误差在个位数百分比以内。
* **4K 自适应超时收敛机制**：增加单次测试 3.0s 耗时自动收敛机制，防止在低速 U 盘 / TF 卡测试时 Kodi 界面冻结卡死。
* **顺序写入动态指纹与全流程闭环落盘**：顺序写入动态注入数据块序号扰动，防止主控压缩与去重作弊，并加入全系统 `sync` 闭环计时。

### 1.0.4
* **新增 R10/F10 固件高级设置**：全面集成 Amlogic SoC 晶晨硬件解码注入、ALSA 音频驱动抗爆音、Mali GPU 局部脏区重绘管线、蓝光无缝分段排空等定制固件核心参数调优。
* **声明式 Schema 与原理级解析**：按 6 大功能模块分类展示，点击可查看详细原理解析长文本，支持布尔开关、枚举单选与数值输入微调。
* **无损增量 XML 合并与备份恢复**：实时增量更新 `advancedsettings.xml`，绝不覆盖已有非冲突配置，首次写入自动生成 `.bak`，支持一键还原并在退出时友好提示重启。

### 1.0.3
* **全皮肤兼容架构重构**：主菜单统一采用 Kodi 原生详细对话框（`useDetails=True`），彻底消除第三方皮肤缺失 `MyPrograms.xml` 导致的调不出界面或闪退问题。
* **完善容器生命周期调度**：有容器启动时自动以 `succeeded=False` 安全释放容器，无容器启动直接呼出，秒级响应。
* **独立副标题与 i18n 补全**：为各工具配置独立的 `description_id` 与中英文说明，主菜单展示丰富功能简介。
* **安全异常捕获与通知**：工具执行统一异常捕获并输出堆栈日志与 Kodi Toast 通知，杜绝静默失败。
* **配置规范性修正**：修正 `settings.xml` 中 `<allowempty>` 约束标签嵌套；`addon.xml` 增加语言声明与版本更新。


