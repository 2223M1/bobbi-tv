# Claude UI 联调交接（CE2027 候选）

本轮在独立候选 `D:/AM6B-Project/bobbi-tv-ce2025-review-20261021` 修改。
用户确认的 UI 分支是 `codex/ce2024-reviewed-delivery-20261021`，对应
`D:/AM6B-Project/bobbi-tv-ui-ce2024`。未改写该 dirty 工作树。
2026-10-21 15:23 的 14 个 UI 文件快照已经实机部署、回滚、再次部署，
并导入本候选；以后 Claude 的新改动不会自动进入本候选或正式安装包。
预览记录保存精确的逐文件 SHA-256；以记录为准，不以工作区分支名猜版本。

## 预览工具

在本候选工作区执行（也可用工具绝对路径）：

```powershell
$py = 'D:/AM6B-Project/bobbi-tv-ce2023-closure-20261021/.venv-closure/Scripts/python.exe'
$transport = 'D:/AM6B-Project/AM6B/.claude/worktrees/bobi-tv-redesign'
$out = 'D:/AM6B-Project/ce2025-results-20261021/ui-preview'
& $py tools/ce_ui_preview.py deploy --source-root D:/AM6B-Project/bobbi-tv-ui-ce2024 --transport-source $transport --output $out
& $py tools/ce_ui_preview.py screenshot --transaction <deploy返回的transaction> --transport-source $transport --output $out
& $py tools/ce_ui_preview.py rollback --transaction <deploy返回的transaction> --transport-source $transport --output $out
```

`--scope skin|dialogs|both`，默认 both。目标固定为当前 `skin.bobbi.cinema`
以及 `plugin.video.bobbi/resources/skins`，不使用旧 skin.am6b.cinema/jacktook。
可复制 1080p XML、媒体/字体/声音/颜色及已存在的 `cinema_keyboard.py`；
不复制 addon.xml、业务 Python、账号、userdata、安装事务或更新凭据。
此为 UI 预览，不是升级包或 Kodi ZIP 安装认证。

流程：校验 XML/哈希和范围 → 备份并暂存完整组件 → journal → 切换 →
ReloadSkin → 截取实际显示的 framebuffer → 保存提交记录。
异常尝试恢复；进程退出后可用同 transaction 的 rollback 恢复。
回滚前完整检查双方组件，存在并发改动时拒绝回滚，不覆盖其他人的新工作。
备份保存在设备 `/storage/.bobbi-ui-preview/<transaction>/backup`。
不要与安装器、另一个部署者并行使用；工具内有预览互斥锁，且拒绝播放中操作。
所有截图只含 GUI 平面，不代表硬件视频平面的画面或解码质量。

已实机验证的事务：

- `preview-20261021T072045Z-34d34cf6`：14 文件提交成功，随后回滚成功。
- `preview-20261021T072348Z-c3d1cdc6`：同一 UI 再次提交成功。

## 片库数据契约

- 根来源 Label2：`SMB · nas.local`、`NFS · nas.local`、`WebDAV · nas.local`、`目录 · N 项`。
- 原生 Kodi 文件窗口会重新应用 `%D` 次标签格式，把上述 Label2 清空。
  因此同步提供 `Bobi.Library.Location`，皮肤 `BobiLibraryLocation` 优先读此属性、再回退 Label2。
  这是实机发现的兼容要求；不借用片名/制作编号等无关字段、不改原生内核。
- `Bobi.Library.Kind`：smb / nfs / webdav / catalog；本机路径另用 local，不能伪装成网盘。
- 管理入口：`Bobi.Library.Manage=true`。
- 文件：Kodi 原生 `ListItem.Size` / `ListItem.Date`；本机目录一次 scandir 读取，网络目录使用一次 Files.GetDirectory 的 size/lastmodified。
  不对一页 200 文件分别 Stat；目录不支持元数据时回退普通列表，不伪造大小/日期。
  未登记为 Kodi 可共享源的远端路径可能被该 API 拒绝；不会擅自改 sources.xml 或开放目录。
  此时文件仍能浏览/手选播放，但大小和日期保持未知，不能把本机测试当作真实 NAS 通过。
- 导入目录 schema 不变，支持可选 `size`（非负字节整数）、`modified`（ISO 日期或日期时间）。
  老目录继续可用；没有这些值就保持未知，不向全部媒体 URL 发 HEAD。
- URL、账号、密码、签名参数不进入 Label2，也不写入 UI 路由或诊断。

## 翻页契约

所有自有插件翻页入口统一 `Label=下一页`、`Bobi.NextPage=true`。
覆盖公共 add_next_button、继续观看、标题历史、动漫目录、MDBList、下载列表和片库。
保留原分页路由、查询条件及 legacy anime 的“当前页/目标页”区别。
不修改独立上游插件的原始更新代码。

## 中文拼音实机结果

使用上述 Claude UI，中文拼音布局，自动启动候选脚本。
逐个真实聚焦/点击可见按钮 500–509，XML 再发送 400–409，10/10 写入成功：
是、使、十、时、事、室、市、石、师、试。最后点击完成，返回文本“试”。
未用 setText 或 JSON-RPC Input.SendText 绕过原生选字路径；未改变账号或键盘布局设置。

证据目录：
`D:/AM6B-Project/ce2025-results-20261021/keyboard/bobbi-keyboard-1792567368931001500`。
首轮探针在异步 setFocus 后立即断言而失败，原失败保留；探针改为等待实际焦点后通过。

本地定向测试 133 项已通过；最终整包/实播状态见本轮交付报告，不能由本文件推断。
