# 原版插件与波比组件的维护边界

本轮最初按已有代码、固定包和前轮研究进行本机审计，后续追加主代理提供的 CE 只读证据
及作者仓库受控安装/停用记录；本子任务仅维护文档，没有操作设备。
本页不能作为真实播放或官方更新已验收的证明。

**最终活动系统已恢复原深度定制，1909 候选停用，全部测试暂停。**
定制 JackTorr `1.2.2+am6b.317` 已从设备备份核对恢复，旧 F9、皮肤及准备 owner 已恢复；
13 个 bobbi 自有组件停用，profile 哨兵未变。详见[最终恢复记录](CE-LEGACY-RESTORE-20261019.md)。

下文 1908“作者原版 JackTorr 1.2.2 已恢复”及 1907“未恢复”都是各自历史阶段，
不能当作最终设备现况。候选采用原版依赖的设计成果保留用于审查，不再继续操作设备。

## 22 个候选组件的分类

`release/source-inventory.json` 中有 22 个组件；其中 9 个上游依赖保留原 ID。
重新核对 `release/kodi-vendors.json` 中全部 214 个文件的 SHA-256，无不一致。
`jurialmunkey` 和 `infotagger` 的 `LICENSE.bobbi-supplement` 是补充许可文件，
不是行为修改。固定包用于重建和审计，不代表必须让波比继续接管其更新。

| 上游原 ID | 本机固定版本 | 现状 / 维护方 |
| --- | --- | --- |
| `script.module.certifi` | 2023.5.7 | 原样 Kodi 包；Kodi 原仓库管理 |
| `script.module.chardet` | 5.1.0 | 原样 Kodi 包；Kodi 原仓库管理 |
| `script.module.idna` | 3.10.0 | 原样 Kodi 包；Kodi 原仓库管理 |
| `script.module.requests` | 2.31.0 | 原样 Kodi 包；Kodi 原仓库管理 |
| `script.module.routing` | 0.2.3+matrix.1 | 原样 Kodi 包；Kodi 原仓库管理 |
| `script.module.urllib3` | 2.2.3 | 原样 Kodi 包；Kodi 原仓库管理 |
| `script.module.infotagger` | 0.1.0 | 原样 jurialmunkey 源码；保留作者来源 |
| `script.module.jurialmunkey` | 0.2.35 | 原样 jurialmunkey 源码；保留作者来源 |
| `script.skinvariables` | 2.2.9 | 原样 jurialmunkey 源码；保留作者来源 |

来源 URL、固定 commit、原始包与逐文件哈希见 `release/kodi-vendors.json`。
保留 ID 并不自动证明设备已关联正确的原仓库；更新可用性仍取决于设备的仓库、
来源、兼容版本及用户设置，不能宣传为“已经全部恢复一键更新”。

主代理的 CE 只读证据 `review-evidence/ce-upstream-readonly-20261019.json` 已确认：
9 个上游插件均 enabled；除 `script.module.jurialmunkey`、`script.skinvariables`
关联 `repository.jurialmunkey` 外，其余 7 个均关联 `repository.xbmc.org`，
这两个原仓库均已启用。该证据验证了设备现有来源关系，不等于执行过更新往返测试。

| 波比 ID | 实际性质 | 能否直接用原版覆盖 |
| --- | --- | --- |
| `plugin.video.bobbi` | Jacktook 深度派生；统一检索、选源、续播和播放所有权 | 不能，会丢失业务契约 |
| `skin.bobbi.cinema` | 多皮肤素材及新版影院交互的定制皮肤 | 不能，会失去用户确认的新 UI |
| `script.module.bobbi.core` | 独立抽出的 AM6B 播放、字幕、字体、准备及续播策略 | 无对应原版产品 |
| `script.module.bobbi.platform` | 波比宿主、账号、安装及升级适配 | 无对应原版产品 |
| `script.module.bobbi.catalog` | QQDocs / 115 / Juku 目录适配 | 不是作者官方插件的改名 |
| `script.module.bobbi.mdsub` | 漫迪目录适配 | 不是漫迪官方 Kodi 插件 |
| `plugin.video.bobbi.torrent` | 对现有 TorrServer 的薄 HTTP 播放适配 | 不等于完整 JackTorr；需保留播放绑定 |
| `script.bobbi.opensubtitles` | 自有 REST 客户端和手动字幕保护 UI | 不是官方原版，不能仅换 ID |
| `resource.uisounds.bobbi-modern` | 用户提供音效主题，统一 -10 dB PCM 增益 | 数据派生，不是独立插件逻辑 fork |
| `plugin.video.bobbi.library` | Kodi VFS 与个人片库登记入口 | 无独立上游可恢复 |
| `script.bobbi.setup` | 自有配置、账号和配对入口 | 无独立上游可恢复 |
| `script.bobbi.start` | 到设置页的极薄转发脚本 | 可后续合并入口，不是主要复杂度来源 |
| `repository.bobbi` | 旧仓库迁移告知脚本，不是在线仓库 | 可在迁移结束后从新装中省略 |

`plugin.video.bobbi/lib/cinema` 中一些模块只是到共享 core 的兼容重定向，
不是两套业务逻辑；不能只因两个目录有同名文件就删除。

## 实质精简的正确边界

1. 上述 9 个依赖不 fork、不重命名，日常维护交给 Kodi / 作者原仓库。
   完整发行包仍须验签，但波比升级和回退不应覆盖用户独立升级过的原版依赖。
   13 个定制组件则作为同代签名事务维护，不能把它们整体换成原版。
2. 原版 JackTorr 可保留独立管理和手动回退入口；波比增强播放使用独立 HTTP
   适配器访问同一个已有 TorrServer。这样有机会移除整份旧定制 JackTorr，
   而不是长期维护两个增强 fork。
3. `script.bobbi.opensubtitles` 的自有 REST 层是后续真正可减少的维护面。
   应先做一次通用的标准字幕下载回调适配，让官方字幕服务可原样使用；必须保留
   当前影片和手动字幕意图保护。尚不能声称直接换成官方插件即等价。
4. 保留字幕字体、原声优先、手动选源、同版本续播；不得为“原版化”删除这些能力。

## JackTorr 原包和恢复证据

原始缓存目录：

```text
D:/AM6B-Maintainable/20260912-133935/snapshots/AM6B-before-final-refresh-r3/AM6B-Maintenance/windows-services/downloads/
```

| 文件 | SHA-256 |
| --- | --- |
| `plugin.video.jacktorr-1.2.2.zip` | `bd8b3851bf4f887b9e60c95187402ec4510eea37695e709c8ba444881e40b280` |
| `repository.jacktook-0.0.5.zip` | `2ab25bbed089accf3d837d8de68ff0113358ba71c4d6a28430ceda24acac4e78` |

原版作者为 Sam-Max，ID 为 `plugin.video.jacktorr`。仓库包指定的索引为：

```text
https://raw.githubusercontent.com/Sam-Max/repository.jacktook/master/repo/zips/addons.xml
https://raw.githubusercontent.com/Sam-Max/repository.jacktook/master/repo/zips/addons.xml.md5
https://raw.githubusercontent.com/Sam-Max/repository.jacktook/master/repo/zips/
```

原版 README 指向 `https://github.com/Sam-Max/plugin.video.jacktorr/releases/latest`。
主代理后续已从电脑取到作者索引及 1.2.2 原包，包哈希与上述缓存完全一致。
这不表示盒子能访问同一仓库，也不等于已经验证或安装了任何更高版本。

与 `D:/AM6B-Maintainable/20260912-133935/execution/release317/source/addons/plugin.video.jacktorr`
对比，排除测试和缓存：34 文件原样，变化或新增为 `addon.xml`、`AGENTS.md`、
`lib/bobi_owner.py`、`lib/episode_matching.py`、`lib/exact_selection.py`、
`lib/navigation.py`、`lib/player.py`、`lib/subtitles.py`、
`lib/torrent_identity.py`、`lib/torrserver/api.py`。

`service.py`、`lib/service.py`、`lib/settings.py`、`lib/os_platform.py` 均与原包一致。
原版后台服务监控设置，并可按用户偏好写入 TorrServer 设置；它不负责启动或停止
TorrServer 引擎。原版 README 也明确要求外部 TorrServer。
因此不能用“旧 fork 拥有引擎进程”作为保留整份 fork 的理由。

新 `plugin.video.bobbi.torrent` 的 Python import 审计未发现对旧 JackTorr 私有模块、
旧插件路由或旧 profile 的运行依赖；它使用自己的 `backend.json`。
主插件仍有 `xbmcaddon.Addon(...).getSetting(...)` 的公开配置兼容桥，
不等于导入旧插件私有 Python 代码。主插件独立 TorrServer 文件浏览/手动字幕路径
还会调用 JackTorr 公开 `buffer_and_play` 路由；只有增强选源走上述薄适配器，
不能把局部 import 审计泛化为“波比已完全没有 JackTorr 路由依赖”。
薄适配器没有新增守护服务或另一份引擎。

原版不能直接代替波比增强播放路由：它没有当前请求 / 文件身份、原语言提示和
同包字幕上下文的绑定，部分取消和超时路径还会删除 TorrServer 中的任务。
恢复前须保留原 profile、连接、设置同步偏好并确认外部引擎所有权；
`1.2.2+am6b.317` 的版本关系也不能假定会被原版 1.2.2 自动覆盖。
1907 该阶段没有替换旧插件或声明原版恢复后的 BT 实播通过。

初始 CE 只读证据显示 `plugin.video.jacktorr` 为 `1.2.2+am6b.317`，origin 为空，
当时 `repository.jacktook` 尚未安装。后续状态已改变：主代理通过 Kodi 原生从 ZIP
成功安装 `repository.jacktook` 0.0.5，仓库 origin 由 Kodi 自然写入，没有直接改插件库。
但盒子打开 `addons://repository.jacktook/` 返回“无法连接插件库”，日志两次读取
作者索引 MD5 URL 失败，另一次独立直连 5 秒超时。随后通过原生
`Addons.SetAddonEnabled` 仅停用该次新增且不可达的仓库。**1907 当时是已安装但停用，
不是尚未安装；旧 JackTorr 当时没有替换。后续 1908 原版恢复见下节。**

过程中 Kodi 于日志时间 20:06:19 出现一次原生 `segfault / exit 139`，服务自动恢复，
后续状态为 `MainPID=21453`、`NRestarts=1`。时间先后不足以证明仓库超时导致崩溃，
该次 1907 维护未改 F9。旧 JackTorr profile 设置 SHA 前后相同，TorrServer `PID=4025` 未变，
已回到主界面；未进行影片播放、真实换号或循环回退试验。
崩溃线程 1 的调用栈为 `CVariant::operator[]` →
`XFILE::IDirectory::ProcessRequirements` → `CDirectory` → `AddonBrowser` →
`ActivateWindow`。这是原生目录/窗口交互路径证据，不是网络超时因果结论。
最终健康检查显示宿主 ready、preparation RUNNING、账号 epoch 1，14 部/58 条准备来源
及 3 条直连状态保持，无 Python 失败。

同时 TorrServer 进程父 PID 为 1，cgroup 为
`system.slice/bobitv-torrserver.service`，证明当前盒子的引擎确由独立系统服务拥有，
不依赖 JackTorr 启动；恢复插件仍不能重置或停止这个共享服务。

记录：[安装后的仓库与插件状态](../review-evidence/ce-upstream-repo-installed.json)、
[连接失败与原生崩溃诊断](../review-evidence/ce-upstream-ui-1792411693451227800.json)、
[崩溃线程调用栈](../review-evidence/ce-upstream-ui-1792411741018097300.json)、
[停用不可达仓库并回首页](../review-evidence/ce-upstream-ui-1792411661889469900.json)、
[恢复后健康状态](../review-evidence/ce-runtime-1907-after-upstream-recovery.json)。

### 1908 原版恢复历史检查点（最终已恢复旧定制）

[恢复后只读清单](../review-evidence/ce-upstream-restored1908.json) 已记录：

- `plugin.video.jacktorr` 为作者原版 **1.2.2**、enabled、origin=`repository.jacktook`。
  已安装非字节码内容指纹为
  `0ebf826d60701144a86e3f9ddc8e5d8ed27d4d3fde3ef1bac1693b0cb9a4b5ff`，51 个文件。
- `repository.jacktook` **0.0.5** 已启用，origin 保留作者仓库；9 个依赖保留原 ID/来源。
- 当次 TorrServer 仍为 PID 4025、父 PID 1、独立 `bobitv-torrserver.service`。
  原版恢复没有让插件接管或重置这个共享后台。
- 波比增强选源继续由自己的薄适配器负责；独立浏览仍可使用原版的公开路由。
  JackTorr 及作者仓库不在波比 22 组件名单或旧影院禁用名单，因此自有程序回退不会
  用旧 fork 或整个 Addons33 备份覆盖它们，也不会回滚其用户 profile。
  最终恢复旧定制是用户另行要求的独立恢复事务，不是上述自有程序 rollback 的隐式行为。

1908 同时应用目录对象生命周期原生候选 `d750a88c…`，详见
[原生审查及回退顺序](CE-NATIVE-REVIEW-20261019.md)。这不把 1907 的崩溃历史删除，
也不表示已证明其所有诱因或完成断电认证。

原版恢复不等于 BT 实播已全面通过：1908《灰羽联盟》首段缓冲超时，
《Flip Flappers》实际 `yuv420p10` 技术尾缀误拒绝待 1909 修复；《窃听风暴》115
有界实播通过，《东京教父》启动缓冲失败。具体证据见
[1908 发布检查点](PRIVATE-RELEASE-20261019.md)。未完成官方依赖版本更新往返、真实换号
或全部播放验收，不宣称“恢复原版即全部解决”。

## 本轮菜单改动

设置的“更新与恢复”分为原版依赖、已装插件、波比定制组件签名包说明。
前两项仅使用 Kodi 标准 `ActivateWindow(addonbrowser,...,return)` 打开
`addons://dependencies/` 和 `addons://user/all/`，不创建下载器，
不调用 UpdateAll、InstallAddon、EnableAddon、UpdateAddonRepos 或虚构的 Addon.OpenInfo，
不改仓库 / 自动更新设置。播放中不打开这些操作页；等待用户选择期间若开始播放，
再次检查并停止打开操作页，不停止影片。打开原生页面后退出设置循环，避免遮住该页。

本机 `tests/test_onboarding.py` 的 18 项测试通过，覆盖两个原生入口、取消、仅说明、
播放中及菜单等待期间开始播放。
上述 18 项是本机菜单测试，不等于新增菜单入口在盒子上的专项验收。
后续作者仓库原生 UI 安装/停用记录见上节；仍未完成官方插件更新往返。
