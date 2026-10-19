# CE 原深度定制恢复 · 2026-10-19

**已按用户要求停止候选验证并恢复原深度定制。所有后续设备操作和测试暂停。**
本次恢复不是把候选退到 1907，也没有刷固件、SYSTEM 或 eMMC。

## 最终状态

恢复 run `/storage/.local/share/bobbi-legacy-restore/20261019-220212` 返回
`legacy_restored`、退出码 0、无诊断错误。原始回执：
[ce-legacy-restore-1792418552005660600.json](../review-evidence/ce-legacy-restore-1792418552005660600.json)。

- `skin.am6b.cinema`（波比TV）已在首页，恢复完成时没有活动播放器。
- 旧 F9 原生程序 SHA-256：
  `8962740e718a7978acadbf2ae7ad55b0cd0742f6d0db162e9c1a1d8645ef834b`。
- 定制 JackTorr `1.2.2+am6b.317` 已从设备原备份核对恢复；不再是候选阶段的作者原版 1.2.2。
- 13 个 bobbi 自有候选组件已停用；旧准备服务 `bobitv-preparation.service` active/enabled。
  Kodi active，保持原 `UnitFileState=disabled`；这不是 Kodi 未运行。
- profile 保留且已列出的哨兵未变；这不是逐字节验证所有媒体/云端数据。
- `playback_tested=false`：恢复后没有试播，不宣称全部片源、字幕、续播或历史问题已修复。

原生先回到旧 F9，再执行旧入口/定制插件/服务恢复；原生回退回执为
[ce-native1908-rollback-1792418205919813100.json](../review-evidence/ce-native1908-rollback-1792418205919813100.json)。
回执保留之前应用、回退与重新应用的历史，没有用最新成功删除中间状态。

## 留下的候选成果

1909 源码、22 组件签名包、原生生命周期候选、全部实播失败和静态研究均保留供私库
Web 独立审查；它们不是当前活动系统。Git 交接见
[WEB-REVIEW-HANDOFF-20261019.md](WEB-REVIEW-HANDOFF-20261019.md)。
Juku 目录/共享库/字幕协议及群资源研究继续保留，不因恢复设备而删除成果。

## 下一轮注意事项

1. 用户未重新授权前，不重启、试播、切回候选或运行账户/续播验证。
2. 旧系统与候选各有 profile/准备账本，不能互相覆盖，也不能同时启动两套准备 owner。
   恢复不是把新候选的观看进度、任务和缓存自动反向迁回旧账本。
3. 不整库恢复旧 Addons33/guisettings，不删除候选更新状态、不降低防重放高水位。
   旧 run 的普通 rollback 不是跨多个代次恢复旧深度定制的通用入口。
4. 再次使用原生候选前需核对实际活动插件、原生 pin、配置与既有回执；不能盲目重放
   历史安装包或在旧插件下直接启用不匹配的原生补丁。
5. 候选 BT preload、启动缓冲、字幕缺失/493、续播不确定及准备意图 NxM 语法发现仍
   保留为待审问题；本地复现与设备真实根因、单元测试与实播认证必须分开。
