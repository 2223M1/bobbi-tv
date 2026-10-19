# CE 设备本地迁移与回退 · 2026-10-19

本文件描述 `tools/deploy_ce_candidate.py`、`tools/deploy_ce_remote.py` 与
`tools/ce_state_migration.py` 的真实行为，不是已经完成设备验收的声明。
它面向当前已核对原生二进制和账号范围的 AM6B，**不是通用 CE 刷机脚本**。
不改固件、SYSTEM/eMMC、CD2 挂载或账号，不影响远端 newapi/代理，不主动播放影片。

## 输入代次与运行不可复用

当前候选为 `2026101903`。调用维护驱动必须显式传入对应 **coreelec** 的完整签名包，
不要依赖脚本历史默认文件名。首次 `stage` 使用全新 `YYYYMMDD-HHMMSS` run ID：

- 本机以独占创建记录该 run 的 candidate/controller/migration SHA-256。
- 设备新建 `/storage/.local/share/bobbi-private-deploy/<run-id>`；已存在即拒绝覆盖。
- 后续 deploy/rollback/status 都读取同一已冻结记录，并核对上传字节。
- bootstrap 树逐文件核验，签名包检查平台、序号、21 个完整成员及 SHA-256。
  修改源码后须新建 run；不能把新 controller 偷换进已执行的 run。

`stage` 只上传、解包并验证暂存树，不停止服务、不切换正在运行的 addons。
远端传输超时写 `unconfirmed`：连接断开不代表操作失败，**先查原 run 的 deployment.json
和实际状态，不重放 deploy**。同一已有部署收据的 run 再 deploy 会被拒绝。

## 停止唯一 owner 后才迁移

控制器先核对现运行 Kodi 的精确 F9 哈希，并用 CD2 实际数字 UID 与本机 115 Linux
登录状态交叉确认账号；只比昵称或缓存摘要不够。
原生哈希针对打开的 `/proc/PID/exe` 对象；不能先 resolve 再重开路径，后者在 CE
不同 mount namespace 下可能是另一份二进制。适配范围仍限定精确 F9 pin。
保存 `kodi.service` 和 `bobitv-preparation.service` 的活动/启用状态，拒绝已有未知 runtime override。

事务期间对这两个 service 加**运行时 mask**并停止；每个迁移检查点要求 mask 指向
`/dev/null` 且 MainPID 为 0。签名组件事务还持有 CE 生命周期锁。
旧 Kodi、旧准备服务与新宿主不能同时操作账本。原生播放器、CD2、TorrServer、外部代理本身
不由状态迁移重建或替换。

## 旧状态不动，在新 profile 中建立账号代次

`deploy` 是首次迁移：新的 plugin/platform profile 已存在会拒绝继续，不合并未知旧候选。
旧 `plugin.video.jacktook` profile 和旧准备状态目录不改名、不清空。
下列内容只在设备本地读取/复制，不进入仓库、安装包或本机审查证据：

1. 将本机同账号 115 登录装入新的账号管理器，产生新 account epoch；开始与结束都核对
   CD2 身份、本机登录字节和账号代次没有变化。
2. 用 SQLite backup API 在停止状态下复制准备账本；检查大小、白名单 schema、外键、
   resource/task 的账号与目标目录。保留 ready 文件绑定和已提交任务的历史。
3. 字幕/字体内容按账本列出的 SHA-256、大小、扩展名逐件复制，拒绝符号链接和复制中变动；
   元数据缓存经现有解析器重建。same-release 字幕必须保留能重新证明同包选择的元数据，
   不能只拷 ASS 字节却丢失对应关系。成功后以新 epoch 目录原子发布。
4. 复制明确列出的用户历史/片库配置；插件 settings 只保留新组件声明的键，`auto_play`
   强制为 false，以保持点选影片后手动选源。旧 socket、控制授权、临时播放 URL 不复制。
5. Assrt Token 本地复制至新 profile 的 `assrt-token`。Juku 仅复制同设备自己的
   `device.pem`、`session.json` 及经 SQLite backup 的目录缓存，不采用其他人的身份。
6. 保留旧皮肤 settings/record。新的 private `preparation.json` 只承接白名单配置，
   包括已有 ffprobe、font tool、字体目录、CD2 私有文件路径和显式 TMDb 代理。
   这些都是当前设备配置，不是安装器默认值或对外分发的账号材料。

迁移模块不发出云端新增/删除操作。不能因为复制成功就声称每条 ready 映射重新实播通过。

## 不重放未发送任务

只修改**新复制的账本**，不修写旧数据库：

- `queued` / `space_blocked` → `suppressed`，未发送直接任务 → `failed`；
- `submitting` → `uncertain`，保留不确定提交供核对，不盲目再提交；
- `checking` → `mapping`，已提交任务只进入查询/资格复核路径；
- 未完成准备意图与发现任务取消或明确失败；清除复制来的临时 lease/protection，结束旧会话。

新用户操作可以走正常的新任务准入，但不会借“迁移”补发旧的待提交意图。
已经发送给云端的任务不声称被本机迁移撤回或取消。

## 已迁移安装的程序升级

`upgrade` 复用同样的签名、停机、备份、代际和失败回退边界，但不会再次调用账号/账本迁移。
它要求已有非空的已安装代次、新 profile 和精确 F9 字幕 ABI；在停止 owner 后验证现有账号
代次与身份一致。程序切换前后比较明确列出的账号、设置、历史、个人 Token、皮肤配置哨兵，
任何变动都会回退程序并记录失败。该比较不是整库逐文件审计，不声称覆盖全部媒体数据。

每次改动组件必须提升对应 addon 版本，且完整签名包序号高于历史高水位。相同版本向量
不能用于该控制器的升级，因为回退后高水位不降，无法仅靠该向量区分程序状态。
实际回退后再次安装候选，也须签发更高序号，禁止重放旧包或降低高水位。

## 程序切换与失败回退

停机后先备份 Kodi Addons33 数据库和 guisettings 文件，再保存涉及组件的启用标志及
skin/soundskin 选择。迁移完成后安装已验签的完整代次，启用候选组件，关闭旧影院/
字幕入口，切换新 UI。部署成功后禁用旧外部准备 service，由新宿主接管可选准备能力。

自动失败恢复及显式 rollback 的边界是：

- 恢复上一程序代次；序号高水位不倒退。
- 恢复本轮涉及的插件启用/disabledReason，以及原 skin/soundskin 两项，不用旧数据库
  全量覆盖后来所有 Kodi 状态。
- 按保存的服务状态解除本轮 runtime mask、恢复需要运行的旧 owner。
- **不回滚或删除账号、云盘、媒体、用户数据和新 profile**。失败的新 profile / migration
  stage 保留供诊断，因此再次首次迁移会拒绝，必须先审查再制定新的恢复动作，不能自动清空。

若程序/flags/gui恢复不完整，保持 owner 停止并记录 recovery_required，不启动未知混合态。
解除 mask/重启失败也记录独立错误，不把部分恢复写成全部成功。控制器记录
`cd2_and_mount_untouched`，但始终返回 `playback_verified: false`，实播另行验收。

## 验证及后续

离线测试覆盖 SQLite 复制、账号边界、资产和元数据保真、未知 schema、unsent 抑制、
复制预算和失败情形。Windows 符号链接夹具受限的跳过仍保留为未执行项，不折算通过。
真实 CE 预检确认 pycryptodome 3.4.3 可用；经能力探针选择一致 Crypto 命名空间并完成
P-256 实际签验，ffprobe / 7zzs 为可执行 ARM32 文件。

1903 已通过 run `20261019-174118` 实际部署。`ce-runtime-health.json` 记录新 UI、
精确 F9 subtitle ABI、宿主 ready/native owner、准备 RUNNING/current account，旧准备
service inactive；快照包含 14 部/58 来源及 3 条 direct 状态。部署/启动和账本迁移
仍不能替代每个 ready 映射实播、字幕/字体、续播、实际回退和真正新作品验收。
当前执行收据位于本机 `review-evidence/ce-<run-id>-<mode>.json`，设备完整回退收据位于
该 run 的 `deployment.json`；不要在文档中嵌入 Token 或 Cookie。

### 1904 实际升级与回退

run `20261019-181420` 已从 1903 程序升级到 1904，随后实际回退到 1903 的组件版本向量。
这是 `upgrade`，`migration.performed=false`，没有再次迁移账号或准备账本。
前后精确 F9 hash 未变，账号 epoch=1，14 部/58 条准备来源与 3 条直连记录保留，
新宿主与准备服务正常，旧准备 service 仍 inactive。程序、账号和设置哨兵核对通过。

回退收据中的 `sequence=2026101904` 是防重放高水位；`versions` 已恢复 1903 的
plugin/core 0.1.0。不能误读为 1904 程序仍在运行，更不能降低高水位重放 1904。
最终候选必须使用更高代次。该健康往返没有模拟断电，也不替代续播/字幕实播。
原始回执：`ce-20261019-181420-upgrade.json`、`-rollback.json`、`-inspect.json`，
运行快照：`ce-runtime-upgraded-1904.json`、`ce-runtime-rollback-to-1903.json`。

### 1906：21 → 22 组件的受控迁移

run `20261019-190604` 已实际升级到 1906。新增的唯一组件是
`plugin.video.bobbi.torrent`；公钥与冻结 1905 一致。维护端先完整验签，再生成
`transition-baseline.json`，与包、控制器和迁移脚本一起固定哈希。仍按完整精确
组件名单校验，旧 21 组件客户端不能直接接受新 22 包。

新事务开始前必须没有未完成的 `journal.json`。旧事务若未结束，应使用旧 run 的
冻结控制器恢复，不能删除 journal 或修改名单来绕过。在 22 → 21 回退后，保留的
22 组件控制器仍是该事务的恢复权威；若提交后清理中断，不让已恢复的旧更新器猜测处理。
43 个升级移动中断、回退提交后清理中断及高水位/重放均有本地回归，不能替代断电实机认证。

只在 owner 停止后，将原 JackTorr 的七个连接/预算字段一次性迁入新组件的
`backend.json`。已有有效新配置保留，旧配置、引擎设置和旧 service 不改。
缺旧配置可保持未配置，基础 115/NAS 影院仍启动；非法或符号链接配置拒绝覆盖。
新连接配置加入程序升级前后哨兵，并作为用户数据在程序回退时保留。

1906 健康回执确认原 MatriX.144.1、F9 字幕 ABI、账号 epoch=1、14 部/58 条准备来源和
3 条直连记录保持。该代首次 BT 实播已正常快速报告目标选择失败，而非旧协议长等待；
尚未据此确认 BT 开播、字幕或续播通过。详见
`ce-runtime-upgraded-1906.json`、`ce-runtime-flip-1906-failed.json`。
