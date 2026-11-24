# CoreELEC 更新发布

源码推送不会改变电视的稳定更新。要发布安装包，先冻结同一提交的两次可复现构建、依赖许可、受信签名整包、安装入口和轨道。稳定包与预览包的签名轨道不能互换。

1. 将不可变附件（普通安装入口 `script.bobbi.start-*.zip` 与完整更新包 `BobbiTV-CE*.bobbi-update.zip`，不混放单组件压缩包以免干扰用户选择）上传到 GitHub `2223M1/bobbi-tv`（双镜像发布时同步上传 GitCode `BobbiZerri/bobbi-tv-updates`）的同名 `ceNNNN` Release；不复制签名密钥或账号数据，保存指向确切提交的 GitHub Release 元数据。
2. 用 `tools/ce_release_gate.py prepare` 生成收据。默认必须准备 GitHub、GitCode 双镜像；只在 GitHub 发布时显式使用 `--mirror-policy github-only`，不传 `--gitcode-feed`。此模式不宣称 GitCode 已同步。
3. 对所选镜像运行 `promote`，目标是各自仓库的 `repository/stable` 或 `repository/preview`。它先回读发布附件，拒绝较新或同序号不同内容的活动指针，再在本地准备新目录。保留旧版 ZIP，不在此步骤改动根目录旧入口。稳定版另运行 `python tools/ce_legacy_pointer.py --root repository --receipt <收据> --proof <promote报告>`，在同一次 GitHub 快进提交中同步旧客户端的六字段清单；预览不触碰它。
4. 按普通快进提交推送更改。若远端分支已前进，重新取回并检查，不要强推。随后用同一收据运行 `verify`，核对线上完整目录及附件；只有这份回读通过才能称为已上线。

CE2182 及更早的客户端经原有 GitHub 通道获取迁移版；不要把 GitHub 清单的下载地址改为 GitCode。新版优先 GitCode，无需登录或自建服务器。用户端在两个镜像间选可用的新版本；提醒不下载或安装，安装和重启仍要确认。

GitCode 的 `raw` 是源码预览服务，不能当任意 ZIP 的下载站。CE 读取其稳定 JSON、从 Release 下载完整包或组件；Kodi 自带的仓库插件继续从 GitHub 取索引和小启动器。验收分别核对真实 HTTP 入口和 GitCode 主分支中存档的目录文件，不把 Git 对象校验算作 HTTP 下载成功。
