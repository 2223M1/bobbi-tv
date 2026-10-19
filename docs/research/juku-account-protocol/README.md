# Juku 0.80：账号退出、登录替换及关联生命周期

2026-10-19，本地静态定向反编译。结论基于 **0.80**，不是旧 0.20。
未启动 Juku daemon、未登录/退出任何真实账号、未联网或操作盒子，未改业务代码。

## 结论先行

Juku 已有完整的本地网盘登录入口和凭据替换机制，不需要为了“能换账号”
另建一套插件身份。其核心是 **每个 provider 一份当前凭据**：

1. 退出：`TokenStore.Save(provider, "")` 删除此 provider 的内存项并重写加密令牌文件。
2. 扫码：确认成功且凭据非空后，`Save(provider, token)` 覆盖同一项。
3. 手工输入：检查 provider 后也走同一 `Save`，没有额外账号注册系统。
4. 请求读取当前凭据；部分播放续期闭包持有先前取到的非空凭据。
5. 离线缓存并非完全不验证：完成态缓存可用当前凭据检查文件存在性，明确不存在则删除本地缓存。

**不能把这些事实扩大成“Juku 已有/没有完整跨账号并发隔离”。** 已还原的
保存/退出/确认链没有账号代际比较、任务取消或播放停止通知；但这不等于
全程序、远端服务及所有接口分派都已穷尽验证。没有进行 A→B 并发实测。

## 固定样本与导出边界

- ARM64 官方包 SHA-256：`850414fb4829512b44086245e1889f4e9bb9ae44b9f42b3f6d7834c75e2950a0`
- AMD64 官方包 SHA-256：`0a384785f3cb9182513b0ea9f387675438217136df0ca751f6011c45ddeea9ca`
- ARM64 ELF SHA-256（本轮重新核对）：`e21cec4ba1f0411022a2d22061b1d27ac80d439606529ddc9cabec3060ca118b`
- AMD64 ELF SHA-256（本轮重新核对）：`fc7ba96b40f4da9d33c02b7c67f8617d26b0982166df515e429d94c97cba1433`

源码入口来自先前保存的官方包可读 Python：
`plugin.video.juku/resources/lib/router.py:4212–4259`、
`api_client.py:251–326`。其 `logout_pan` 请求 `/api/pan/logout`，
扫码请求 `/api/qrcode`、`/api/qrcode/status`。

本轮导出 85 个函数记录：ARM64 核心 18、AMD64 核心 18、AMD64 生命周期 36、
代理注册 1、缓存 11、文件存在性检查 1。每个目录有 `index.tsv`、直接调用及
调用者索引、符号清单、`.c` 和 `.asm`。所有记录的反编译完成标记均为 true。

**true 只表示该函数伪代码导出完成，不表示原 Go 源码完整恢复。** Ghidra
的部分 Go 寄存器参数、指针/整数类型不精确；接口调用不会完整出现在静态直接
调用索引中。本文交叉核对两个架构的核心路径，并在退出错误处理处核对指令。
没有恢复全部第三方库、全部后台任务、全部代理 HTTP handler 或完整源工程。

## 1. 退出与凭据保存：已恢复

核心地址：

- `main.handlePanLogout`：ARM64 `007694b0`，AMD64 `00c58fc0`。
- `(*TokenStore).Save`：ARM64 `005baf30`，AMD64 `00a63a60`。
- `(*TokenStore).Get`：ARM64 `005bb260`，AMD64 `00a63de0`。
- `(*TokenStore).load`：ARM64 `005bad00`，AMD64 `00a63880`。

退出 handler 读取 `provider`，检查 `main.providers`，调用
`Save(provider, "")`，然后返回 `success`。准确字面量分别保存在
`arm64/009d9f87-8.bin`、`arm64/009d739b-7.bin` 及 AMD64 对应文件。

`Save` 的已恢复顺序：

1. 互斥锁保护；必要时创建 `map[string]string`。
2. `TrimSpace(token)` 为空则按 provider 删除，否则覆盖该 provider 的字符串。
3. 序列化整个 map → `GetEncryptionKey` → `EncryptGCM` → `os.WriteFile(..., 0600)`。
4. 返回序列化/加密/写入错误，释放锁。

证据：`amd64/00a63a60.c:58–136`；ARM64 对应
`arm64/005baf30.c:100–178`。这是网盘 TokenStore，不应与 Juku 主站的
设备注册会话混为一谈；这里只复用加密密钥获取函数。

此保存链没有账户 UID 比较、epoch、订阅通知或 `CloseAll`。map 修改发生在
持久化之前，保存函数本身不是临时文件+原子替换事务。

退出 handler **未依据 Save 返回错误选择失败响应**：
`amd64/00c58fc0.asm:72–83` 的 `CALL 0x00a63a60` 之后立即装载
ResponseWriter 数据，没有检查 Save 的返回错误。这是本地静态错误路径事实，
不是声称实际用户已遭遇磁盘写失败。

## 2. 扫码与手工替换：已恢复

`main.handleQrCodeStatus`（ARM64 `0075dcf0`、AMD64 `00c4afc0`）：

- 读取 provider、key，走 `getRealProvider`。
- key 为 `manual` 时，读取 TokenStore 判断是否已有凭据。
- 普通 key 调用 provider 的 PollQrLogin。
- 返回状态为 `confirmed` 且 token 非空时调用同一个 `Save(provider, token)`。
- 此 handler 的成功提交路径未比较扫码开始时的旧凭据/账号代际；
  Save 的返回错误在该路径也未单独转换为失败响应。

证据：`amd64/00c4afc0.c:84–153`，ARM64 `0075dcf0.c:102–233`。
`confirmed` 的准确九字节另存于 `amd64/00f059ff-9.bin`。

115 provider 的 `StartQrLoginWithType` 与 `PollQrLogin` 也已导出：
ARM64 `00538530` / `00539120`，AMD64 `009b9260` / `009ba1e0`。
后者获取授权结果、整理 Cookie 字段并拼成返回字符串，实际本地持久化由
上层 handler 完成。本文不从服务端二维码协议推测多窗口并发保证。

手工输入 handler（ARM64 `0075d780`、AMD64 `00c4a980`）限定 POST，
解码 provider/token，检查 provider，再调用 Save。
**此分支会检查 Save 错误并返回 500**，与退出和扫码分支不相同。
证据：`amd64/00c4a980.c:145–155`。

“不同账号替换”在以上本地链中就是覆盖该网盘的一份当前凭据；没有要求
改变 Kodi addon ID、换 skin ID、创建另一个插件目录或重置整个 profile。

## 3. 播放连接：已恢复到注册及续期闭包

- 新分享播放 handler 在进入解析流程时调用 `ProxyManager.CloseAll`：
  `amd64-lifecycle/00c4bea0.c:167`。
- 如请求未带 token，则读取当前 TokenStore，再交给 Cloud115Provider 解析：
  同文件 `:338–352`。
- 注册 ProxyManager 时传入续期闭包：同文件 `:542–608`；
  `amd64-proxy/00aa4980.c` 可见 `Downloader.SetRefresher`。
- 闭包保存先前的凭据；只有捕获的凭据为空才再次读取 TokenStore：
  `amd64-lifecycle/00c4d320.c:35–46`。
- 个人网盘播放有相似续期分支：`amd64-lifecycle/00c50a60.c:29–39`。

`amd64-cache/callers.tsv` 里 `CloseAll` 的已识别直接调用者是新分享播放、
个人播放和 fast-play handler，不是退出/登录 handler。

因此可确定**退出提交本身没有沿上述已还原链关闭代理连接**。不能据此保证
“退出后必定持续播放”或“必定立即停止”：尚未实测已发出的 CDN 链接、
远端凭据撤销、Kodi 当前播放及所有间接回调的最终行为。

## 4. 离线任务缓存：存在按当前凭据校验，不能说完全不管账号

离线 Add、Status、Tasks、Delete、Resolve handler 已导出到
`amd64-lifecycle/`。常规请求没有显式 token 时从 TokenStore 取当前凭据，
无凭据时拒绝受限操作，例如 `00c515a0.c:270–279`、`00c53a00.c:228–237`。

缓存查询 SQL 的原始 231 字节见 `amd64-check/00f67ee5-231.bin`：

```sql
SELECT info_hash, url_key, url, title, vod_title, vod_id, file_id, pick_code,
       file_name, file_size, is_dir, sub_files_json, status, updated_at
FROM offline_tasks
WHERE info_hash = ? OR url_key = ? OR url = ?
LIMIT 1
```

此查询没有账号谓词；这不单独证明所有部署都共享同一数据库路径。

`OfflineCacheStore.GetValid` 不只是按下载键返回：完成状态、有 file_id 或
pick_code、有当前 token 及 provider 时，会调用 `Check115FileExists`。
明确无错误且文件不存在时删除此缓存以及关联 URL/info-hash 键。
存在性检查出错时，不走这个“明确不存在”的删除分支。
证据：`amd64-cache/00a142e0.c:33–61`；被调函数完整导出于
`amd64-check/00a119c0.c`。删除的是本地缓存记录，不是云端影片文件。

这是可借鉴的“使用时验证”机制，不能描述为已有账号代际分区，更不能
描述为“Juku 从来不验证跨账号文件是否可用”。并发任务返回后的账号一致性
及整个异步生命周期仍没有完成实测证明。

## 5. 目录缓存与后台同步：仅对实际调用作结论

`ClearAll115DirCache` 遍历并删除 lifeAncestorCache 项，已有直接调用者为
LifeSyncManager 的 oncePoll / handleEventForDir，不在 TokenStore.Save 或退出链。

`amd64-lifecycle/00a03580.c:205–221` 表明每轮 oncePoll 读取当前 CLOUD115
凭据，凭据为空则返回；`:408–412` 的清缓存调用处于目录事件处理，不能
冒充账号切换清理钩子。完整函数保留供后续核对，但本次没有研究全部
启动条件、轮询周期、事件持久化、并发导入及远端同步策略。

## 对波比的具体建议（建议，不是假称上游行为）

- 采用 Juku 已证明的简洁交互：一个网盘账号入口，扫码确认才提交，取消不另建账号。
- 优先复用原插件及可更新依赖。不要为了切号改掉整套 addon ID，
  也不要把 TokenStore、代理、下载器和同步任务整体复制成第二套常驻服务。
- 保留一处当前凭据所有者；波比现有后台选源/字幕/准备任务若已有代际守卫，
  可作为薄边界继续使用，不需要对外暴露“多账号系统”。
- 可以借鉴“缓存使用时校验”，不必把所有缓存都全量清掉。
- 不照抄忽略持久化错误或先改内存再直接写文件的部分；现有原子保存若已正常，
  保留它比倒退更合理。
- 不能把 Juku 未证实的并发保证作为删除现有防迟到结果措施的依据。
  若要进一步精简，应针对真实任务生命周期做有界测试，再决定删除什么。

## 复现导出

使用 `tools/ExportJukuAccountProtocol.java`、Ghidra 12.1.4、JDK 21，
对已有工程执行 `-readOnly -noanalysis`。`fn:` 选择名称子串，`at:` 选择
确切地址，`bytes:` 按调用处长度导出字面量。每次运行输出至独立目录。

```text
analyzeHeadless <project-dir> juku080-arm64 -process daemon-linux-arm64
  -readOnly -noanalysis -scriptPath <repo>/tools
  -postScript ExportJukuAccountProtocol.java <output>/arm64
  fn:main.handlePanLogout fn:TokenStore fn:main.handleQrCode
  fn:main.handleManualInput fn:ClearAll115DirCache fn:main.getRealProvider
  at:00538530 at:00539120 bytes:009d9f87:8 bytes:009d739b:7
```

AMD64 工程为 `juku080`，程序为 `daemon-linux-amd64`。核心 QR 地址换为
`009b9260`、`009ba1e0`；各补充目录的确切选择可由 `index.tsv` 重放。
研究代码和生成证据可独立审查；没有把伪代码当作可直接执行的 Go 源码加入产品。
