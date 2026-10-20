# CE：原版插件维护与 Juku 账号流程收敛

**最终状态：原深度定制已恢复；1909 候选与其 13 个自有组件停用，全部测试暂停。**
设备运行旧 `skin.am6b.cinema`、F9 `8962740e…`、定制 JackTorr `1.2.2+am6b.317`；
旧准备服务 active/enabled，恢复时 profile 哨兵未变，恢复后没有试播。见
[最终恢复记录](CE-LEGACY-RESTORE-20261019.md)及
[回执](../review-evidence/ce-legacy-restore-1792418552005660600.json)。

下文 1907/1908 为历史检查点；1908 的作者原版恢复不是最终设备状态。1909 已部署但
BT/启动回归仍有失败，随后按用户要求恢复旧系统。真实换号仍未认证。
用户要求能直接复用的插件保留原版及原仓库更新，不为切账号重命名整套组件。

## 1908 历史检查点（非当前活动系统）

- 冻结 run `20261019-205008` 已实际升级 1908，不重新迁移账号/profile；完整验证
  22 个组件，仅维护 13 个自有组件。9 个上游依赖保留原件/来源。
- JackTorr 已从旧 fork 恢复为作者原版 **1.2.2**，enabled、origin 为
  `repository.jacktook`；作者仓库 0.0.5 也启用。恢复证据见
  [ce-upstream-restored1908.json](../review-evidence/ce-upstream-restored1908.json)。
  TorrServer 仍是独立 `bobitv-torrserver.service`、当次 PID 4025，未交给插件启动。
- 已应用精确候选 native SHA-256
  `d750a88c3dc041d17ea34d06e2b2ddadcf4db0f9fffdaaa727c8a6b7427f21d3`：
  只修 `Directory.cpp` 重入时 shared_ptr 生命周期，不改音画源码或刷固件。
  旧二进制及配置保留供回退；构建/LTO限制和分层恢复见[原生审查](CE-NATIVE-REVIEW-20261019.md)。
- 新电影《窃听风暴》所选 115 片源有界实播通过，德语音轨和简中已启用。
  《东京教父》启动后出现缓冲，验收不通过，不能用后续恢复覆盖失败。
  新动漫《灰羽联盟》BT 已取得资料但首段缓冲超时，未进入 AV。
  《Flip Flappers》回归已定位实际文件 `HEVC-yuv420p10 AAC` 技术尾缀被通用规则误拒绝，
  待 1909 修复及部署验证，不算已经修复或新增作品验收。

对应 trace、音轨/字幕和日志链接集中在[1908 发布检查点](PRIVATE-RELEASE-20261019.md)。
1909 部署及最终恢复见[安装记录](PRIVATE-RELEASE-20261019.md)。1909 像素后缀修复
没有带来该 BT 回归的开播确认；全部失败保留。官方依赖未来版本更新、真实换号、完整
音画/字幕/续播或断电恢复均不能据维护回执视为已认证。

## 已实施的源码边界

- 九个原样上游依赖保持原 ID、代码及作者/Kodi 更新渠道，不再由波比程序更新或回退覆盖。
- 完整包仍验证全部 22 个组件；只有 13 个波比定制组件进入程序替换、备份和回退事务。
- 上游依赖缺失、过旧或禁用时先明确报错，让 Kodi 管理，不伪造仓库来源，不自动降级。
- 历史完整备份仍完整核验，恢复只投影至波比自有组件。未完成的旧完整事务必须先由其冻结控制器恢复。
- 设置页提供 Kodi 原生插件/依赖管理入口，不另造插件下载器，不执行批量更新或自动刷新仓库。
- 账号仍只有一个当前凭据入口。扫码确认才替换，退出确认后清除凭据，成功后刷新目录；取消不更换当前登录。
- 保留已有原子保存、写盘失败反馈和防迟到提交检查；没有新增账号后台、切换皮肤或重启播放器。

## Juku 证据

此前仅有 Python 入口及其他功能的定向反编译，不能声称已经完整理解退出后台。
本轮补出 85 个函数记录，ARM64/AMD64 交叉核对登录、退出、保存，以及关联缓存和播放链。
这仍不是完整原 Go 源码恢复，但账号核心路径已有直接证据。

Juku 的退出会删除对应 provider 凭据，扫码确认则覆盖同一项；没有要求换插件 ID。
缓存也会用当前凭据验证文件是否存在。波比采用这些简洁行为，不照搬已观察到的保存错误未检查分支。
详见 [反编译记录](research/juku-account-protocol/README.md)。

## 1907 历史：原版与定制不能混称

CE 只读证据已确认九个依赖 enabled、来源正确且对应仓库启用。没有执行官方升级往返，
不能把仓库关联正确说成最新版兼容性已实测。

1907 当时 JackTorr 仍是 `1.2.2+am6b.317`，不是原版。该阶段尝试通过 Kodi 原生 ZIP 安装
作者仓库 `repository.jacktook 0.0.5` 已成功，来源由 Kodi 正常写入，未手改数据库；
但盒子访问其 GitHub 索引超时，打开仓库显示“无法连接插件库”，因此未继续替换。
电脑端实际取得作者的 1.2.2 原包，SHA-256 与此前审计缓存相同。

仓库浏览过程中发生一次原生 SIGSEGV / 139，堆栈为
`CVariant::operator[] → IDirectory::ProcessRequirements → AddonBrowser`。
这证明崩溃发生于原生目录要求处理，不足以直接断言网络超时就是根因；未更换 F9。
Kodi 服务当时自动恢复并回到首页；已停用该次新增的不可达仓库，避免继续刷新它。
JackTorr 旧插件、profile 设置和 TorrServer PID 均未改变。
现有 TorrServer 由独立 `bobitv-torrserver.service` 拥有，不是 JackTorr 启动。
原版 JackTorr 可作为独立管理入口，但不能直接替换波比增强播放的薄适配路径。
主插件独立文件浏览/手动字幕路径还使用 JackTorr 的公开 `buffer_and_play` 路由。
该历史检查点没有完成旧 fork 恢复或原生修复；后续 1908 状态以上节为准。完整分类见
[原版插件清单](UPSTREAM-ADDONS-20261019.md)。

## 1907 历史：部署与验收边界

CE `2026101907` 已通过冻结 run `20261019-211907` 实际升级；回执为 `upgraded`。
Kodi、新宿主和准备功能已恢复运行，账号仍登录且 epoch 为 1；14 部/58 条准备来源及
3 条直连记录保持。九个原版依赖的全部非字节码文件哈希、启用状态和仓库来源前后相同，
TorrServer PID 4025 未更换。设置插件为 0.1.1，平台模块为 0.1.2。

1907 当时最终本机回归：primary 1,225 通过/6 跳过（132.04 秒），baseline 741 通过，
preparation 177 通过。六项跳过为本机符号链接权限，不算通过。
第一轮 primary 的 45 个失败记录仍保留：历史 21→22 测试必须显式使用历史完整组件
事务模型；修正 fixture 后保留全部旧断点，另覆盖新 13 组件事务及旧 journal 拒绝。
未为迁就旧断言放宽产品边界或删掉测试。

1907 包验证全部 22 组件/1,371 文件，程序状态记录 13 个自有组件。
未进行 1907 实机回退、媒体试播、真实换号或原版依赖升级往返。
不得把本机回归及启动检查当作这些验收的替代。
1906 已知 BT `target_unresolved`、部分 Assrt 493、未完成的字幕/续播实播验收仍保留，
不因该阶段账号与插件维护调整而宣称已解决；1908 后续实播失败也保留为失败。

证据：`review-evidence/ce-20261019-211907-upgrade.json`、对应 `inspect.json`、
`ce-runtime-upgraded-1907.json`、`ce-upstream-content-pre1907.json` /
`ce-upstream-content-post1907.json`、`ce1907-unit-primary-final.xml`、
`private-artifact-boundaries-ce1907.json`。

仓库尝试及恢复证据：`ce-upstream-repo-installed.json`、
`ce-upstream-ui-*.json`（含原生界面结果、安装、停用、日志和崩溃栈）、
`ce-runtime-1907-after-upstream-recovery.json`。后者确认首页、宿主 ready、
准备服务 RUNNING、账号 epoch 1 及原准备/直连记录均保留，无新增 Python 失败记录；
不代表完成影片验收。原插件和 profile 的恢复备份仅在设备
`/storage/.local/share/bobbi-upstream-restore/20261019-jacktorr`，不进入安装包或 Git。

1907 当时未更换 F9；1908 的最小原生 overlay 另有精确哈希与应用收据。
不改 CD2 1.0.19、挂载、Yatse、VPS newapi 或代理。
