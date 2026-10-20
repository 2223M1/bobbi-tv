# PR #1 / CE2006 审查整改

> 历史阶段记录：本文件的“不合并/不操作盒子”和 F9-only 新装结论已由用户本轮
> “通用 CE，执行、测试、然后合并”替代。当前入口与边界见
> [通用 CE 安装](CE-CLEAN-INSTALL-20261020.md)；R01/R02 和旧测试证据仍有效，
> 不把它们重新标成新版本或新硬件通过。

## 范围与结论

本轮以 `c62e816607f3ef13d6763950bcdd4175bde6044c` 为产品基准，独立工作区
`bobbi-tv-ce-pr1-20261020`，仅 CE；未使用子代理。用户另行授权更新 PR #1 并运行 CI，
保持草稿、不合并 main、不发布、不重启或升级盒子。

最新设备交接仍是 **2026102006 / core 0.1.11**。本轮 **2007 / core 0.1.12 /
BT 适配器 0.1.3** 只是本地离线候选，不能把构建或远端 CI 成功写成已经安装、实播通过。
原 F9、UI、字体、画质、block 默认、CD2、挂载和用户账号均未修改。

审查输入原件保留于 `review-evidence/ce-pr1-20261020/web-review-input.zip`。
包内操作建议作为审查资料，不作为新增设备或远端授权。

## 逐项处置

| 项目 | 本轮处理 | 证据边界 |
| --- | --- | --- |
| R01 范围末端修订号 | 接受最小中央语法修复：消费 `02v2/02v10` 后再判断边界；不回滚统一语法或重写旧版本键 | Web 原样 18+14 场景通过；另测真实 selector、准备意图、手选 resolver 和播放 owner |
| R02 浮点速度 | 后端读取响应时将有界非负 int/float 归一为整数 B/s；拒绝 bool、NaN/Inf、负数、字符串及超限值 | 实际 JSON → Backend → Resolver → 日志/等待提示；0.0 保留为 0，未知缺失，仍是种子总速率而非所选文件准备证明 |
| D01 集成/CI | 在独立工作树合入固定 main；仅 README 冲突，保留双方内容并纠正历史状态标注 | 合并提交 `285746f`；不强推或改动 main；远端执行结果另记 |
| F01 启动缓冲 | 保持开放；不调全局缓存、超时、原生或默认传输，不降画质换源 | 未新增实播；此前 ODDTAXI 启动缓冲仍有效 |
| F02 字幕裁切 | 保持“7.5% 安全边距缓解，待电视确认”，不再修改用户偏好 | 未获得电视端画面，不声称 ASS/PGS 或字体外观全部解决 |
| F03 新机/第二账号/音画 | 保持未验收 | 不清空唯一设备或借用别人账号模拟验收 |

### R01 实际链路

新的范围文件不能通过有/无 hash 绑定的自动单集选择，不能生成自动当前/下一集准备意图。
当前正确单集后接一个范围文件时，仅保留当前准备，不误准备后继，也不取消当前。
用户仍可在真实文件列表显式选择合集，但结果保持 `USER_CONFIRMED_FILE`，不发布自动准备目标，
不能重绑成 `AUTO_VERIFIED_FILE`，自然结束后也不授予自动续播。
单集 v2/v10、像素、CRC、`-1080p` 和原有精确版本键控制均保留。

### CI 补充修复

实际本地复跑 CI 的三进程结构后发现两个此前未显现的阻断：

1. `test_ce_subtitle_font_compat` 从另一隔离测试组导入夹具，在主测试单独运行时收集失败。
   改为直接调用相同的产品 `video_identity`，不引入另一组 Kodi stub、不减少断言。
2. 默认组件构建要求本机 TMDb 应用配置，干净 CI 没有该文件。新增显式 `--source-check`：
   仍校验真实清单、组件及两次构建，但完全不读取或封装本地 Key。
   清单标记 `channel=source-check, installable=false`，签名器拒绝此类产物。
   默认私用构建继续要求真实配置，不生成假 Key，不把 CI 检查包装成可安装包。

工作流增加只读 `codex/**` push；PR 仍检查正常合并引用，不使用 `pull_request_target`。
日志记录实际 checkout commit/tree/parents，分支 head 与 PR 合并结果分开。
三组测试保持独立进程，保存各自 JUnit；只上传测试回执，不上传 CI 检查组件作为安装包。

## 本地验证

全部输出在 `review-evidence/ce-pr1-20261020/`，保留第一次失败而非覆盖：

- Web 冻结原件：**33/40 满足、7 未满足，退出 1**（`web-frozen-before/`）。
- 新产品测试首次收集失败：测试模块导入次序不完整（`product-before.*`），已修测试导入。
- 修复前实际产品路径：**27 failed / 33 passed**（`product-before-collected.*`）。
- 修复后新增路径与构建边界：**63 passed**（`targeted-after.xml`）。这包含重复子集，不另加到总数。
- 原样 Web 旧 18、新 14 身份场景：**32/32**，直接指向实际候选模块（`web-identity-after.json`）。
  原包速度摘录仍是冻结旧代码；速度改善由完整产品链测试证明，不改旧摘录冒充通过。
- CI 同结构主测试首轮收集失败保留（`primary-full.*`）；修复跨组夹具后：
  **1598 passed / 6 skipped**（`primary-second.*`），退出 0。
- 独立旧 Kodi 测试：**757 passed**（`baseline-full.*`），退出 0。
- 独立准备回归：**177 passed**（`preparation-full.*`），退出 0。
- 既有打包/bootstrap 单元回归：**41 passed / 4 subtests passed**（`packaging-local.*`），退出 0。
  仅本地共享打包合同检查，不恢复 Android/Windows 构建或实机工作。
- 合计 **2573 passed / 6 skipped / 4 subtests passed**。一个 JUnit `record_property`
  格式警告保留。6 个跳过均是 Windows 宿主无法创建符号链接夹具，不计作安全能力已验证：
  `test_ce_state_migration` 1、`test_ce_torrent_migration` 3、`test_updates` 1、`test_upstream_addons` 1。
- 无 Key 的 source-check 两次均构建 **22 组件**，**63 个输出文件逐字节一致**。
- 私用 2007 离线候选已使用原信任钥签名并实际解包检查：**22 组件 / 1384 文件**；
  错平台、签名篡改、组件篡改、缺成员四项负例均被拒绝（`artifact-boundaries-2007.json`）。
  本地产物：`dist/private-releases/bobbi-private-2026102007-coreelec.bobbi-update.zip`。
  该包没有部署、上传发行页或被标记为稳定版本。

## GitHub 交付

目标 PR #1 的原 head 是 `c62e816`，main 在开始时仍为 `71ea558`。
仅将本独立集成候选以普通快进方式更新 PR head；不强推、不合并 main。
远端 head/合并结果检查及原始 run 链接在 PR 评论中补充，不能以本地通过代替 Actions。
源代码提交不含本地应用 Key、签名私钥或个人账号资料。安装包只留本机。

首次远端执行（head `e4efaed`）的 push `39395832037` 与 PR `39395840729` 均实际运行，
主测试 **2 failed / 1597 passed / 5 skipped**，其余两组测试及双构建通过。
失败是两个模拟 CE 的路径测试在 Linux 上尝试创建真实 `/storage`，不是产品播放错误。
修复测试隔离：将模拟 F9 导出根映射到各自临时目录，新增真实 ABI 字面量断言，
并对该组所有 mkdir 加“不能逃出临时目录”检查；不 sudo、不创建 `/storage`、不跳过测试，
不改生产路径或已封存 2007 包。首败输出保留在 `ci-first-push-failed.txt`。
Linux 的 5 个跳过为真实 Windows inherited-pipe API 测试；Windows 上此前跳过的
6 个符号链接用例在此次 Linux 执行中已经运行，不再用 Windows skip 冒充其结论。

## 设备验证与回退边界

本轮没有设备更改，因此无需回退盒子；已安装 2006 的回退仍按原冻结部署回执执行。
2007 离线候选没有部署回执，不得重放 2006 的 run-id 冒充安装。

后续若授权验证缓冲：仅对同一 file_id/hash、账号、码流、输出与 F9 做 block/progressive
交错重复比较，记录首分钟 caching、真实解码/呈现进度、上游交付间隙、队列及取消时延；
单次缓存命中收益不能决定默认值。
字幕裁切则先只读分类普通文本/ASS/PGS、分辨率/overscan、ASS PlayRes/MarginV/pos 与实际字体
fallback，并结合电视拍屏，每次只调整一个变量；不 flatten 特效字幕或缩小整幅画面。
