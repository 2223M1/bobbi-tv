# bobbi TV 0.1.0-alpha.1 · 首个公开测试版

同一个库分发 CoreELEC / Kodi 仓库入口和通用 Android ARM32 / ARM64 APK；不选品牌，不刷机。

## 下载哪个

- **Android**：`bobbi-tv-0.1.0-alpha.1-android.apk`。安装与 BT 后台助手；影院仍在官方 Kodi 21 内运行。打开 APK 按「安装影院」向导操作。
- **CoreELEC / Kodi 21**：`repository.bobbi-0.1.0.zip`。从 ZIP 安装，再从 bobbi 仓库安装程序插件「bobbi 开始使用」，自动拉取组件。
- `bobbi-kodi-components-0.1.0-alpha.1.zip` 是维护 / 回退组件合集，不是直接给 Kodi 安装的单一插件。
- `TorrServer-source-MatriX.147.zip` 是随二进制提供的固定上游对应源码，不是影片。

## 本轮内容

新 UI 与有许可的近似字体；个人 115 本机二维码登录；原 / 腾讯补充 115 目录合并；多 NAS、WebDAV、U 盘与直链片库；手选片源；本机 BT 固定引擎；Android 六位码配对；Kodi 原生仓库更新与长期 APK 签名。无私人服务器或共享账号依赖。

## 必须知道

这是 **预发行，不是稳定版**。Android 及新的 CoreELEC 全新安装尚未实机验收；单元测试、构建成功不能替代播放验证。

自动找外部中文字幕与自动续播的私人后台流程没有完成通用移植；请用 Kodi 标准字幕菜单及手动选集。HDR / Dolby Vision / 音频直通由 Kodi 和设备决定，不承诺所有安卓盒子等价。

海报搜索需在首次设置填写自己的 TMDb API Key；自己的 NAS / 直链浏览不需要。115 使用安装者本人账号，失效分享不会自动变成可用资源。不转码、不降分辨率，不自动转存、创建云任务或打开公网控制端口。

建议 Kodi 更新方式选「通知，但不要安装更新」，停止播放后再升级。APK 覆盖安装保留数据，签名冲突时不要卸载旧应用或关闭系统防护。

详细安装、能力边界与许可证见仓库 README、`docs/INSTALLATION.md`、`docs/RELEASE_VALIDATION.md`。
