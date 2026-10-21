# CE2029 架构精简审查

阶段边界：CE2029 为非 UI 本地候选，不覆盖 Claude 工作树。用户随后授权
整合、部署 Claude 完整新皮肤，并要求日常完整回归全部收口后再推送；后续整合另记。
第一阶段故障修复冻结于 `4dedbc8b66364c6bd3c492656eba1e8d67f2774f`，
tree `42bc34110084d1450837db27e85b157a5fd16eb2`。其独立干净回归为
2069 + 789 + 177 = **3035 passed / 6 skipped / 1 strict xfailed**，
不能直接充当随后精简代码的最终验收。

## 结论

存在可删的旧实现，也存在不能因“看起来重复”就合并的边界。采用删除无调用实现、
复用已有实现及提前跳过无工作轮询，不新增 manager，不重新设计一套框架。

| 职责 | 保留的唯一当前路径 | 精简方向 |
| --- | --- | --- |
| 字幕下载、文本检查与落盘 | `subtitle_fallback → fetch_candidate → subtitle_io / inspect_text / publish` | 删除同包字幕遗留的第二套下载、校验和缓存淘汰函数 |
| Stremio 字幕 | `submanager → opensubstremio` | 移除没有实例化或配置入口的旧 `StremioSubtitleProvider`，不移除在用 provider |
| 准备服务与字幕查询 IPC | `subtitle_lookup_portable → preparation_client → runtime → Host → PreparationHost/Session` | 删除已无服务端的 Unix socket 收发与旧查询状态机；旧 import 路径指向同一 portable 类 |
| 播放期间准备重试 | 原生播放器先看本地 sent/inflight/due/attempts，再询问 owner | 已耗尽或未到期时跳过不产生工作的 owner IPC；真正提交前后检查保留 |

## 为什么这些旧实现可以移除

- `torrent_subtitles.cache_chinese_sidecar` 与私有文本校验无生产调用；现有准备队列仍使用
  同文件的 `matching_chinese_sidecars` / `MATCHER_POLICY`，两者必须保留。
- 旧 `bobbi_core.subtitle_provider` 只剩定义和一份空转兼容别名，未接 Host 配置。
  在用的手动 Stremio 字幕入口是另一个模块，不是按名称相似一并删除。
- 旧 Unix 查询连接地址已为 `None`，请求不带现行协议和账号字段；当前产品配置和
  preparation 服务端没有这条通道。回退旧安装包使用旧代完整载荷，不依赖新包保留失效实现。
- `socket_path` 参数仍应显式拒绝非 None，不能把旧调用静默改走当前账号。

不删除任何用户字幕缓存、账号、观看记录或旧版本备份。代码删除可从 Git 的第一阶段
冻结提交恢复；真实当前功能必须由保留的生产入口回归证明，而不是只统计删了多少行。

## 刻意不做的“精简”

- `lib.cinema` 多数短模块通过 `sys.modules` 指向 `bobbi_core` 同一个模块对象，
  不是两份业务或两份状态；它们承接旧 import，不能为了减少文件数引入隐式导入魔法。
- 原生 Kodi 与普通 Kodi 是不同宿主适配，不是两个播放器竞争一个实例；不删普通 CE 支持。
- Host 入队检查、Session Lease 和结果发布前账号校验分别位于不同异步边界，
  中途可换号，不能只留最前面一次检查。
- 候选卡筛选、精确视频文件匹配和字幕季集匹配的证据强度不同；强行合成一个“大匹配器”
  会放宽自动播放，或误伤本来可手选的资源。
- 旧字幕 schema、历史 timing 读取及字体迁移仍被持久数据使用，不是死代码。
- 安装 journal/OS lease/最终 quiesce 分别保护崩溃恢复、进程排空和并发播放，不合并掉恢复状态。

## 证据与交付要求

引用扫描、无操作 tick 反例和精简后回归分别保存在
`D:/AM6B-Project/ce2029-results-20261021/architecture-subtitles` 与
`architecture-lifecycle`。最终应记录实际减少的产品行数、100 次无操作调用的 owner 查询数，
以及精简后新冻结 commit/tree 的全量测试；不复用第一阶段绿色结果冒充最终通过。

## 已落实的精简与定向结果

- 字幕旧路径净删 249 行；保留同包匹配、现用 Stremio、字体及旧状态迁移。
  联合回归 710 passed / 1 skipped（本机符号链接能力限制）。
- 准备 IPC 与轮询净删 125 行；旧字幕 import 重导出 portable 同一类。
  新组合回归 343 passed；原字幕/字体/续播账号/监测回归 162 passed（不同集合有重叠，不累加）。
- 四种状态（BT/漫迪各自重试耗尽或未到期），每 100 次无操作调用的 owner 查询
  从 100 次变成 0 次。真正到期工作、迟到取消/替代/换号仍执行原有守卫。
- 合计产品代码净减少 374 行（6 个产品文件，25 行新增、399 行删除），未新增运行期管理层。
  用户缓存与媒体文件未删除；源码删除可从 `4dedbc8` 恢复。
