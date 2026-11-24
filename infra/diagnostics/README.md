# Bobbi 系统优化回传

电视入口：影院设置 → 检查与诊断 → 系统优化。默认开，按 Kodi profile 保存。关闭即停止新记录、清空待发队列；不能撤回正在传输或已送达的记录。搜索诊断原有的本地记录、预览和手动导出保持独立。

一次 HTTPS POST 只包含版本、枚举步骤、枚举结果、耗时档位和一次性回执编号。首次安装使用启动器版本；Emby 使用平台组件版本。`handoff` 仅表示交给 Kodi，不等于成功起播。盒子不上传 kodi.log、文件名、搜索词、URL、标识设备的 ID 或账号材料。连接所需的 IP 会被 Cloudflare 用于限流，不写入诊断表。离线队列最多 100 条/7 天，失败退避，重试不换编号；接收端最多每天新增 10,000 条，按 UTC 日保留约 14 天。

Bobbi 独占 Worker 和 D1。公网只有 `POST /v1/diagnostics`，没有读日志接口。维护者通过 Cloudflare 控制台或已授权的 Wrangler 查询 **bobbi-tv-diagnostics** 的 `receipts` 表，按 `day,build,stage,outcome,elapsed` 分组即可。维护者凭据不放在客户端，不需玩家注册。请勿绑定 NinjaSlayer 的数据库或改动它的域名。

本地运行：`npm ci`、`npx wrangler d1 migrations apply bobbi-tv-diagnostics --local`、`npm run dev -- --port 18744`。另开终端设置 `BOBBI_TEST_LOCAL=1` 后执行 `npm test` 即验证实际本地 Worker + D1；不设置时只运行 SQLite 合同测试。发布前核对账号、数据库及域名，先做 dry-run，再对指定数据库应用迁移、发布和验证回执。
