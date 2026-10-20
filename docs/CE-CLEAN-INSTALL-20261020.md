# CE 私人候选：干净安装与更新

本轮只支持已经装有受认证 F9 Kodi 21.3 的 AM6B Plus / CoreELEC。
这不是固件刷写包，不把普通 CE、其他 ABI 或没有原生播放协议的系统宣称为已认证。
全新机器的真实安装验收尚未完成；现用机器使用 `upgrade`，不能清理 profile 来冒充新机。

## 离线材料

同代签名包为 `dist/private-releases/bobbi-private-2026102006-coreelec.bobbi-update.zip`。
各原版依赖安装 ZIP 位于 `dist/private-components-2026102006/<原版ID>/`。
所有素材及来源说明都随组件保留；不含用户115登录态、CD2配置、观看记录或签名私钥。
TMDb为波比专用应用配置；安装者不用申请个人Key。

## 新装流程（维护者操作）

1. 在 Kodi 中先安装/启用官方 `script.module.pycryptodome`（必须适配 Kodi 进程 ABI）。
   原版依赖用 Kodi 自己的“从 ZIP 文件安装”功能安装，或直接从其官方仓库安装。
   离线顺序：certifi、chardet、idna、urllib3、requests、routing、infotagger、
   jurialmunkey、skinvariables。ZIP 完整保留各自 ID、作者和许可证。
   保留/添加它们原有的 Kodi 官方或作者仓库以获得后续更新；波比不接管这些插件。
2. 确认已启用 SSH 并建立设备主机信任。设备上的 Kodi 保持运行，安装器会核验真实
   进程 ABI/版本、依赖是否启用及其版本。不得复制维护者的SSH凭据到安装包。
3. 用 `tools/deploy_ce_candidate.py` 对新时间戳 `--run-id` 执行 `--mode stage`
   和 `--bundle <同代签名包>`；成功后对同一 run 执行 `--mode clean-install`。
   `--transport-source` 指向这台设备已核验的传输适配目录，不使用别人的私有设备地址。
   若检测到旧波比或旧影院程序/profile，拒绝新装；使用现有升级或明确迁移流程。
4. 安装器只临时停止/屏蔽 Kodi，备份原插件启用状态与皮肤配置，用签名事务安装
   13 个波比组件。9 个原版依赖由 Kodi 保管；安装器不覆盖、不改来源、不擅自启用。
   不读取旧115/CD2账号，不复制旧片库，不创建云任务，不安装BT后台。
5. Kodi恢复后打开“波比影院设置”，用自己的手机扫码登录115，查看TMDb来源说明。
   基础目录、分享播放、字幕无需CD2/Jackett/ffprobe。BT是可选项，可稍后配置。
   首次启动按当前F9字幕ABI创建空的字幕导出目录，不要求旧Jacktook账号或配置。

## 现用设备升级和回退

现用机器保留账号、观看、字体、语言和音画配置，用 `stage → upgrade`，不执行新装。
失败时依照该run冻结的控制器执行 `--mode rollback`。仅回退程序、启用状态及皮肤入口，
不会覆盖账号/媒体/观看数据库。旧控制器不能跨代回滚新的安装。

程序升级与原生播放器试验分开进行。本轮首先保留原F9，再比较整块与渐进传输；
“波比影院设置 → 115播放传输”可切回整块，下次安全重启Kodi后生效。
离线安装、构建通过、单元测试和真实播放分别记账，不能互相代替。
