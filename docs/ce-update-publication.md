# CoreELEC 更新发布

源码推送不会改变电视的稳定更新。要发布安装包，先冻结同一提交的两次可复现构建、依赖许可、受信签名整包、安装入口、组件附件和轨道。稳定包与预览包的签名轨道不能互换。

1. 上传不可变 Release 附件，保存指向确切提交的 GitHub Release 元数据。
2. 用 `tools/ce_release_gate.py prepare` 生成收据。默认必须准备 GitHub、Gitee 双镜像；只在 GitHub 发布时显式使用 `--mirror-policy github-only`，不传 `--gitee-feed`。此模式不宣称 Gitee 已同步。
3. 对所选镜像运行 `promote`，目标是各自仓库的 `repository/stable` 或 `repository/preview`。它先回读发布附件，拒绝较新或同序号不同内容的活动指针，再在本地准备新目录。保留旧版 ZIP，根目录的旧版 `current.json` 不动。
4. 按普通快进提交推送更改。若远端分支已前进，重新取回并检查，不要强推。随后用同一收据运行 `verify`，核对线上完整目录及附件；只有这份回读通过才能称为已上线。

用户端在两个镜像间选可用的新版本；提醒不下载或安装，安装和重启仍要确认。
