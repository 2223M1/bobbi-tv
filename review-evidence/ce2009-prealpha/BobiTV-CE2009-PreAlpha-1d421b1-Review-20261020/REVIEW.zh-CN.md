# 波比TV CE2009：合并后、内测前审查

## 结论

**保留已经合并的通用 CE 实现；不要把当前 CE2009 入口 ZIP 直接发给朋友。先完成三项 P1 的小范围修复，并同批处理一项 P2，再重新打包。** 这不是要求机型白名单、未知设备风险提示或预先完成其它盒子认证。当前问题在普通路径的确定性状态与恢复逻辑，AM6B/F9 已有成功不能覆盖。

main `1d421b101bdc3b940bdd5870caaac49a5fc49394`，tree `f013b350c62352ad2ac03c7fde94932d0c408344`；前次冻结基准 `da279d45ecf84133f9ac15ddb21a2f18a5f37ba8`。PR 已合并，标题与旧正文仍写2007/Draft不反映最终状态；代码与最新交接以本冻结点为准。我们没有合并/推送、连接盒子或改变账号。

## 已成立的进展

实际单 ZIP 入口为 `script.bobbi.start-0.2.1-ce2009.zip`。其 `default.py` 优先加载内附 bootstrap；入口声明 Python 和适配 ABI 的 pycryptodome，由 Kodi 解析。新的通用安装器不以型号或 F9 哈希作准入，能力判断已去掉 Kodi major==21 的静态限制。普通播放链已加入驻留观察，而不是旧的单次 URL 手动演示。

合并后 main CI run `39410984018` 成功。本轮真实下载 43,779 字节 JUnit 工件，SHA-256 与 GitHub摘要一致、CRC通过：primary 1641 passed/5 skipped，baseline 757 passed，preparation 177 passed，合计 **2575 passed/5 skipped**，0failure/0error。见 evidence/CI-RECEIPTS-VERIFIED.json。未独立重跑全套。

已读取的真实标准 Kodi fixture 有2次AV和2次Ended，通过常规链；但后继是固定测试输入，不能证明异常/跨应用切片/安装恢复。现场影院电影/动漫主试播仍在现有 F9 上，不能与下面的普通路径反例混为一谈。

## A01 / P1：安装与恢复提前宣布结束

`addons/script.module.bobbi.platform/lib/bobbi_platform/ce_installer.py` 83–95、152–158。

恢复中先写 restored，再 `host.restore()`；安装中先写 complete，再 `host.activate()`。`recover()` 却跳过 complete/restored。真文件恢复与启用向量/皮肤恢复是不同步骤，当前日志把它们混成一个终态。

实际生产 Installer 的故障实验：

| 场景 | 结果 |
|---|---|
| 正常安装/正常回退 | 正常；控制例通过 |
| 文件回退后，第一次恢复启用/皮肤 RPC 抛错 | journal=restored，blocked=false；重开 recover=false，插件仍停用、界面Estuary |
| 写 complete 后进程立即退出 | 0/12组件启用，重开不恢复 |
| 激活第一组件后进程退出 | 1/12组件启用，重开不恢复 |

临时文件、目录改名、落盘和子进程退出均真实执行；签名/解包、互斥和 Kodi RPC 为明确替身。没有证明签名漏洞或用户数据丢失，也不是电视实机断电实验。

修复必须把“整套程序已核验，可准入”与“宿主激活/恢复还未完成”分开。**不可只把 complete 移到 activate 后**：新服务入口还受 boot gate 约束，可能在启用时直接退出。保持可启动的已验证代次，同时持久化待完成操作；恢复幂等读回启用状态和皮肤，确认后终结事务。测试每个新状态边界，不只复用旧完整写点。

入口使用自带 bootstrap，因此必须同时刷新内附 bootstrap、signed payload、入口版本和清单。仅更新安装后的 platform 模块不足以修复用户手中的旧入口。

## A02 / P1：用户已播放别的视频，旧续集仍能复活

`addons/plugin.video.bobbi/lib/services/standard_playback.py` 240–251；`addons/script.module.bobbi.platform/lib/bobbi_platform/standard_session.py` 155–163。

观察到无关播放器条目时只把 `bound` 清空；旧 session 仍为 ended，next_data 未撤销。`20秒`期限只在没有候选的 elif 分支执行，并被 playing 条件绕开。

受控真实控制流：A自然结束 → 有已就绪续集 → 0.1秒后用户开始播放非波比视频 → 旧session仍ended → 60秒后停止用户视频 → 旧A的续集被自动打开。不是一次被取消的云请求，也不是两个实例同时播放的猜测。

修复针对已有明确关联的旧会话和其后继任务：新无关播放已被观察到时撤销旧自动交接资格；撤销时清候选/取消工作，不控制无关影片。不能把“开播期间短暂读不到条目”也误当外部接管，不能停掉用户影片，不能因标准接口没有原子API就关闭所有普通设备的续播。后继的有效期不应因已有 next_data 而无限延长。

## A03 / P1：一个后继开播异常，退出整个普通宿主

`addons/script.module.bobbi.platform/lib/bobbi_platform/standard_session.py` 155–160 → `addons/plugin.video.bobbi/lib/services/standard_playback.py` 217–229 → Handoff.submit；`addons/plugin.video.bobbi/lib/portable_runtime.py` 标准分支循环没有请求级隔离。

向真实后继交付路径的 Player.play 边界注入一次 RuntimeError，异常穿过 tick，触发 portable_runtime 的 standard.close 和 host.close。结果1次开播尝试、仅1次宿主tick、正常monitor尚未退出、整个宿主已关闭。

这不是 Kodi 主进程崩溃，而是波比驻留服务退出。修复应局限单请求开播边界，保留有界错误记录，继续处理宿主IPC和之后的用户操作。提交结果未知不能自动重发，不要用全局Stop、宽泛吞掉所有主循环异常或无限服务重启来掩盖。

## A04 / P2：续集只查一次

`addons/script.module.bobbi.platform/lib/bobbi_platform/standard_session.py` 142–154，第一次进入片尾120秒范围就设置 next_started；无结果和失败都不恢复发现资格。

当前同一请求内：第一次不可用，后续变为可用，连续观察到结束仍只有1次lookup、0次续集交付。初次就有候选控制正常；账号变化、新选择、停止和错误控制也正常。

支持已有目录/准备revision变化驱动的有界刷新，或退避+结束前最后一次机会。单worker，取消和账号代际保持；重查不等于重新add云任务、全局搜模糊片名或切换发行版本。

## 已知现场失败：保持开放，但不要错误归因

《这个男人来自地球》BeiTai 1080p：选中至观察AV约9.289s；原监测异常累计7.515s，其中有2.483s caching同时解码计数停滞，其它时钟停滞段存在解码进展。不能说整个7.5s都是画面冻结，也不能全抹成时钟误报。

《玲音》S1E1 Ghosty6464：选中至AV约9.019s；caching采样窗口7.964s，含约2.034s及3.995s的解码计数静止段；仅英文内嵌、自动中文未取得，中文字幕验收失败。后续30s正常观察不冲销首次失败。未取得足够证据将这些现象归于本轮 standard adapter；当前主试播为F9路径。

这两项可以继续作为内测体验反馈目标；不要将“没有第二台设备”当分发门槛。优先修复本轮确定的软件缺口后，即可继续通用CE小范围实测，不要求先完美覆盖所有来源/字幕/硬件。

## 修复顺序及范围

同一连续候选：A01安装状态收口；A02/A03/A04共用普通生命周期修复；真实产品回归；重打bootstrap入口和完整签名包；main/候选CI；再交内测。不回退整次合并，不同时改F9/音频/画质/缓存默认，不引入新后台或新语言。

现有研究证据与历史失败不改。机型未知不提示风险、不要求确认、不禁用业务；包损坏、空间不足和真实依赖失败仍正常处理。Android/Windows继续不纳入本次工作。

## 本轮覆盖边界

15个独立场景：9满足、6未满足，对应4项问题；6份完整源码逐Git blob校验一致。合并后远端CI回执已实际下载验证。现有安装ZIP仅核对draft release元数据与仓库回执，未取得其实际字节，未独立解包签名验收。未操作设备、VPS、网盘、远端仓库；没有重建整个产品或重新运行全仓测试。

不是声称所有问题已经修复，也不是对整个累计PR逐文件审完。包内没有产品补丁；它提供实证与修复边界，候选必须重新接实际代码验证。

## 主要源文件

- [通用交接](https://github.com/2223M1/bobbi-tv/blob/1d421b101bdc3b940bdd5870caaac49a5fc49394/docs/CE-GENERAL-2009-20261020.md)
- [安装器](https://github.com/2223M1/bobbi-tv/blob/1d421b101bdc3b940bdd5870caaac49a5fc49394/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_installer.py)
- [标准会话](https://github.com/2223M1/bobbi-tv/blob/1d421b101bdc3b940bdd5870caaac49a5fc49394/addons/script.module.bobbi.platform/lib/bobbi_platform/standard_session.py)
- [标准播放器](https://github.com/2223M1/bobbi-tv/blob/1d421b101bdc3b940bdd5870caaac49a5fc49394/addons/plugin.video.bobbi/lib/services/standard_playback.py)
- [宿主循环](https://github.com/2223M1/bobbi-tv/blob/1d421b101bdc3b940bdd5870caaac49a5fc49394/addons/plugin.video.bobbi/lib/portable_runtime.py)
- [安装UI](https://github.com/2223M1/bobbi-tv/blob/1d421b101bdc3b940bdd5870caaac49a5fc49394/addons/script.module.bobbi.platform/lib/bobbi_platform/ce_install_ui.py)
- [入口](https://github.com/2223M1/bobbi-tv/blob/1d421b101bdc3b940bdd5870caaac49a5fc49394/addons/script.bobbi.start/default.py)
- [主分支CI](https://github.com/2223M1/bobbi-tv/actions/runs/39410984018)
