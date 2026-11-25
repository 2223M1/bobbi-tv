# 波比 TV · TVBox / 小雅 T4 配置导入与桥接说明

## 1. 安全边界与支持范围

波比 TV 原生支持符合标准 HTTP JSON 契约的 **`type: 4`（T4）远端站点**，并提供三种面向客厅遥控器与手机端的导入方式：

1. **订阅网址导入（支持 Yatse 粘贴）**：在电视端「我的片库 → 添加来源 → 小雅 / TVBox（T4） → 输入订阅网址」粘贴 `https://...` 或家庭局域网私有 IP `http://192.168.x.x:...` 地址，自动保留基址以解析相对接口。禁止将手机端本地路径（如 `/storage/emulated/0/...`、`content://`、`file://`）当作电视订阅网址拉取。
2. **本机 / U盘 / 局域网共享 JSON 文件**：直接读取电视可见存储中的 `.json` 配置文件（最大 `2 MB`）。
3. **手机扫码受控分片上传（`/manage`）**：选择「手机扫码上传配置文件」，手机浏览器在配对会话下以 `4 KB` 分片上传并校验整包 `SHA-256`，正常关闭二维码仅撤销网络授权而保留同 profile 待确认交接，由电视端最终确认后保存。

### 为什么不直接运行 `type: 3` Spider（JAR / Dex / JS / Python）？

传统 TVBox 配置中的 `type: 3` 站点（如 `csp_AList`、`csp_WebDAV`、`csp_Emby` 或带 `./spider.jar;md5;...` 的爬虫壳）依赖外部 JVM 动态加载字节码或任意脚本。在 CoreELEC / Kodi 环境中直接运行未签名第三方爬虫会破坏播放所有权、沙箱与凭据隔离。因此：

- 当导入的 JSON 仅包含 `type: 3` Spider 而 `type: 4` 数量为 `0` 时（例如历史实测样本：`0` 个可用 `type: 4`、`50` 个 `type: 3` Spider、`7` 个 `lives` 直播订阅入口），波比 TV 会给出分类诊断报告，**绝不写入空白或无效片库记录**，也不提供将 `type: 3` 伪改为 `type: 4` 的假转换配置。
- `lives` 计数仅表示配置文件中的**直播订阅入口条数**（可另存为 `.m3u/.txt` 交由外部 IPTV 插件使用），**不代表已验证可用的电视频道数量**。
- 对于 `csp_AList` / `csp_WebDAV` / `csp_Emby` 等网盘与媒体服场景，可在「添加来源」中改用波比 TV 的 **WebDAV 目录浏览** 或 **Emby / Jellyfin 在线目录** 模式：支持受测子集内的在线目录分页、按选定版本直连字节流播放、本地精确历史记录，以及 Emby 会话进度回报与受控失效刷新；4K、HDR、Dolby Vision（含 Profile 7 FEL）、原盘目录/ISO 与音频直通取决于具体片源、硬件解码链、系统与 Kodi 支持，不作跨格式或全功能无条件承诺。

## 2. 将传统配置桥接为标准 T4 服务

如果你已有自建的小雅 AList、CatVodOpen Node 服务或 TVBox T4 转换桥接器，只需将桥接器输出的真实 `type: 4` HTTP JSON 地址导入波比 TV。每个可用站点须满足：

- `type` 为整数 `4`，`api` 为合法的远端 `https://` 或家庭内网私有 IP `http://` 地址（仅把 `csp_*` 名称改为 `type: 4` 无法替代真实 HTTP T4 协议）。
- 支持标准 T4 查询参数：`?filter=true`（首页分类与筛选）、`?ac=detail&t=<type_id>&pg=<page>`（分类列表）、`?ac=detail&ids=<vod_id>`（详情与线路分集）、`?play=<ep>&flag=<line>`（返回 `parse: 0` 的有限 HTTP(S) 媒体地址，且每跳重定向受同源/明确批准策略约束）。
- 若站点声明 `searchable: 1`，支持 `?wd=<keyword>&quick=false&pg=<page>` 搜索。
- 自定义站点请求头仅允许无凭据的安全白名单字段（`User-Agent`、同源 `Referer`、`Accept`、`Accept-Language`）。

## 3. 使用命令行工具自检配置与桥接连通性

维护者或高级用户可在导入前通过只读校验脚本检查本地 JSON 或远端订阅：

```bash
# 仅做离线结构与分类诊断（零网络请求；0 个可用 T4 时返回明确非 MEDIA_VERIFIED 状态）
python -B tools/check_t4_bridge.py --config path/to/config.json

# 指定订阅基址并按单站点共享 8 秒总预算实测 home/category/search/detail/play 五阶段与 Range 媒体探针
python -B tools/check_t4_bridge.py --config http://192.168.1.91:5678/tvbox/t4.json --probe-live
```
