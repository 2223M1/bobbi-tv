# 可重现架构图与边界审查

`tools/architecture_graph.py` 是离线静态证据工具。它不导入项目模块，不执行 ZIP、插件、原生代码或构建脚本，不连接设备。输出不是“所有调用均已解析”的全程序调用图。

## 使用

使用 Python 3.10+ 和 Git，无第三方依赖。在仓库根运行，产物目录必须在仓库外。

```powershell
python -B tools/architecture_graph.py --revision 6cd23ee --output D:/AM6B-Project/architecture-baseline-6cd23ee
python -B tools/architecture_graph.py --output D:/AM6B-Project/architecture-working
python -B -m pytest -q -p no:cacheprovider tests/test_architecture_graph.py
```

`--revision` 将输入解析为完整 commit，直接读取该树的 Git blob，不 checkout，完全忽略当前产品改动。默认模式读取全部 tracked 文件和非 ignored 的新增源码/配置文件（Python、JS/TS、XML、JSON、C/C++、patch）；tracked 非源码、删除项、子模块和符号链接仍保留在 inventory。不会递归子模块或跟随符号链接。解析单文件上限为 8 MiB，跳过和解析失败会保留原因。

外部目录产生 `graph.json`、`overview.md`、`overview.mmd`。默认拒绝覆盖，明确重复生成时可加 `--overwrite`。输出含完整 commit/tree、输入 fingerprint、逐文件 SHA256或Git对象ID、工具SHA256、manifest身份；无时间戳。同一不可变输入及工具版本产生相同图。工作树模式是逐文件读取，不是假装原子快照；变更检测发现并发修改时会记录 diagnostic。需要冻结证据时使用 commit。

## 图协议

- `confirmed`：静态文本或显式声明唯一指向某目标。只证明绑定证据，不证明分支执行、运行时可达或真机能力。
- `candidate`：Python调用候选、协议分派、JS/XML/C++词法匹配。方法动态分派、对象注入、猴子补丁、条件、编译配置均未被证明。
- `external`：不在当前库存中解析的模块/目标或绝对HTTP地址。可包括标准库、第三方依赖、运行时注入；不等于已连接成功。
- `unresolved`：计算式、未知导出、重复模块或缺少上下文；`candidates`可列出候选，绝不任选一个冒充已解析。

文件节点使用`file:<仓库相对路径>`，Python符号包含文件、限定名称和定义行号；每条边有类型、状态、证据路径/行号。Python调用另保留caller。import根包括仓库、tools/tests、addon根/lib及addon.xml声明的module library；同addon上下文优先，其余同名模块保持歧义。真实`sys.path`修改、运行时插件发现需人工审查。

字面量动态import与相对package可解析，计算式保留为unresolved。`sys.modules[__name__] = import_module(...)`另记`compatibility_alias`及`duplicate_implementation:false`，不因同名文件自动判定重复实现。未知package属性不冒充已解析函数。

JS/TS识别字面量HTTP端点、rpc/invoke/call及action对象值，动态fetch保留未解析边；无完整JS AST或控制流。XML识别addon入口和plugin action URL；Python action/path比较提供分派候选。C++识别JSONRPC方法表及注册文本；patch只读取新增/上下文行，标记`patch_only`，不将旧快照或补丁文本算作已安装二进制。正则提取不是编译器，缺少的路由可以通过manifest补充。

SCC仅根据可指向文件的静态import/call/alias边构建，报告为候选，不能据此声称运行时死锁或依赖方向已完全符合架构。概览Mermaid按模块组聚合，最多显示120个跨组边桶；完整图均在JSON中，截断数量在概览中明确列出。

## 显式协议、状态、存储、生命周期与测试映射

可重复传入`--manifest 路径`。仓库相对路径必须存在于选定快照；绝对路径为显式外部输入并单独记录SHA256。扩展manifest只作审阅者声明，不推断所有权，也不冒充测试执行结果。

```json
{
  "schema": 1,
  "nodes": [
    {"id": "state:example", "kind": "state", "label": "人工审核状态"},
    {"id": "storage:example", "kind": "storage", "label": "索引数据库"},
    {"id": "lifecycle:example", "kind": "lifecycle", "label": "Host持有并关闭"}
  ],
  "edges": [
    {
      "source": "file:core/example.py",
      "target": "state:example",
      "kind": "owns_state",
      "status": "confirmed",
      "evidence": {"path": "core/example.py", "line": 12},
      "note": "审阅者核对的写入权威；不是自动推断"
    }
  ],
  "boundaries": [
    {
      "id": "core-to-platform",
      "source_prefixes": ["core/"],
      "target_prefixes": ["platform/"],
      "kinds": ["python_import", "python_dynamic_import"],
      "note": "需要审查反向依赖",
      "allow": [
        {"source": "core/legacy.py", "target": "platform/paths.py", "reason": "明确的临时兼容例外"}
      ]
    }
  ]
}
```

上面是结构示例，文件名和行号必须替换为实际快照内证据，否则工具拒绝。允许声明的节点kind为`state/storage/lifecycle/protocol/responsibility`；既有文件/符号节点不能覆盖。边的kind可扩展，例如`persists_to`、`owned_lifecycle`、`drains`、`covered_by`、`protocol_handler`。测试映射可直接指向`file:tests/test_example.py`，note应说明“静态覆盖声明，未执行”。

每条manifest边必须有存在的端点、有效证据行和note，输出标记`origin:manifest_assertion`。检查证据位置并不验证声明的语义真实性。边界规则使用路径前缀与边类型，不把函数名字符串当路径；例外必须给出精确source/target和reason。命中报告`review_required`或`allowed`；无规则不代表通过边界检查。`--fail-on-boundary`在写出报告后对未豁免命中返回2，普通成功返回0，输入/输出错误返回1。

本次新增的 A/B/C、profile 与 poll 映射是 `55b4f9b` 冻结后的文档补充。该 commit 的冻结图使用其 Git 对象内的旧 manifest，不含这些后补边；工作树或后续文档 commit 的图必须保留自己的 manifest/input 身份，不能回标成 `55b4f9b` 图。

## 验证范围

最小fixture覆盖相对import、import别名及caller、同名模块、动态import、兼容alias、未知导出/对象方法、XML→Kodi路由、JS→HTTP、C++RPC注册、SCC、显式所有权/存储/生命周期/测试映射、边界规则、Git对象与工作树隔离、只写仓库外、语法错误报告。fixture模块包含不可执行哨兵，扫描仅处理源码文本。

这些测试证明提取合同，不证明Bobbi整体调用可达、设备稳定性或所有协议边已穷尽。全仓输出用于后续逐条核对与显式补图，不替代运行时回执。

## 精确文件人工片段切片

MediaIndex 的存储版本 4 在同一数据库增加 `file_segments` 与 `segment_changes`，沿用既有 review 修订、事务、preview/apply/receipt/undo；不创建第二索引或新写入 API。版本 1、2、3 升级前保留经过核验的独占恢复副本；失败回滚 DDL，已有备份不覆盖。旧代码若不支持版本 4，不能直接打开新数据库，也不能靠降低 `user_version` 回退。

TV 的单文件整理菜单提供“编辑本文件片段（人工观察）”及“查看本文件片段与证据”。支持 `intro`、`recap`、`outro`、`credits_scene`，每种最多一段，整数毫秒，区间必须落在用户明确填写的时长内且互不重叠。时长标明人工来源，未知不猜测；这不是探测事实、seek 授权、EOF 证明或自动跳过策略，片尾标注不能跳过彩蛋。

记录保留 manual 来源、记录时间及完整 FileRef/typed observation 的不透明证据键。状态 matched 只表示与当前已保存观察匹配，不声称实时文件仍相同；读/整理不会额外 stat 文件。扫描或点核验发现替换、尺寸、签名或其他观察变化后显示 verification_required。旧记录保留；清空、修改及撤销共用 CAS。撤销恢复原证据，不刷新为新文件。重新填写失效标注不会自动沿用其他旧片段。

人工描述导出保留 v1 读兼容，无片段及花絮时仍使用 v1；含片段使用 `bobbi-catalog-manual-v2`，含花絮关系使用 v3。v2/v3 复用 `restore_description`，元数据、片段和花絮共享一次修订与撤销；每项有 SQLite savepoint，描述写入后的领域拒绝不会提交半套状态。请求回执仍保留失败结果，不能通过重发补写。

片段保留原观察键、manual 来源与时间，旧观察不会因导入自动获得新时间轴。花絮导出同时保留精确父文件观察和关联状态；目标父作品须先已整理，原观察必须相同，再将父修订替换为目标当前修订。提交时再核对父观察、修订及单层关系。已失效的源关联保留在导出文件，但只列为待复核，不静默重新确认。共有花絮仍使用作品级关系，不伪造精确父版本。不同人工状态或补充关系冲突不覆盖，重复导入不新增修订。

同一份文件中尚未导入父作品的关系需要先导入父作品，再由用户重新预览关联；不预先假定用户必定选择父项。跨来源/账号重映射、typed/path 描述迁移与播放时自动消费片段仍未完成，不能据此宣称阶段 3/4 全部闭环或设备能力已验证。

## Preparation composition boundary

`Host._tick_preparation` supplies the session factory, installation-owned lock, pairing loader, Android font decoder factory, and an `owner_call` bound to that actual resident Host. `PreparationHost` has no implicit session default; `Session` cannot import platform capabilities as a fallback. Its root/config are captured before the owner starts, and optional pairing/decoder lookup remains lazy within session initialization. Required missing capabilities fail closed before resources open; an Android decoder returning no callable cannot fall back to the CE helper.

`Session._owner_read` checks the captured account lease before and after the resident owner queue. `ProtectionLane` requires an explicit callable reader; failed or missing observation is unknown, not idle. Font owner observations run outside account CAS to avoid waiting on the actor while holding its account lock. Only the final SQLite COMMIT is passed through `Lease.commit`, inside the existing SQL and font-link rollback scopes. Post-commit invalidation cannot return ready and does not claim to undo an already committed transaction.

The existing account-generation fence and resource order are unchanged. The process lock is acquired before SQLite opens and retained until admitted IO drains and all session resources close; shutdown does not hold account CAS while waiting for font IO. Lock acquire/close errors are not converted to success. These local ordering contracts do not certify process-kill, power-loss or device behavior.

Request-owned `PreparedSession` is distinct from the resident preparation `Session` and the independent playback `Client`. The latter fixes transport for its entry and continuations without becoming a second playback owner or requiring optional preparation/cloud login. Core preparation/playback IPC now requires explicit transport and no longer imports platform runtime as a fallback. Plugin compatibility wrappers perform bounded entry composition. `pan_playback.py` also captures transport at entry and passes that same call/Client through standard select/cancel and continuations; it no longer uses the old dynamic `runtime.call` path. These changes remove those specific debts, not every dependency exception listed in `dependency-debt.json`. Local binding contracts do not replace standard full-chain device acceptance.

## Catalog presentation composition boundary

`personal_catalog.manage` supplies the existing metadata candidate adapter and a lazy phone launcher to the shared `catalog_ui` invocation. The platform UI no longer imports the plugin's candidate, renderer or phone modules. Missing candidate capability affects only candidate search/group review; manual mapping and ordinary browsing remain available. Missing phone capability is reported without granting access. The existing profile binding, CAS, receipts, scan worker and renderer remain their sole owners; no global capability registry or second review implementation is introduced.

`catalog_routes` owns only the existing URL and scope-hash value helpers. `personal_catalog` re-exports them for compatibility, while the independent platform library entry uses them directly and keeps the same synchronous `ActivateWindow` navigation. Native/mounted/local/network saved-route values, including network generation, retain their prior encoding; they are neither playback authority nor live account discovery. `catalog_navigation` remains the separate read-only descriptive join and is not merged with this value contract. This source-local debt removal does not regenerate historical frozen graphs or establish device acceptance.

## Runtime path and search ownership boundary

Entry composition supplies concrete profile roots, one sticky binding, search/HTTP admission and subtitle exporter capabilities. Core `ProfilePath` no longer discovers Kodi, a home directory or a process-global profile. The verified CE native ABI selector remains for independent subtitle interpreters; this does not change the native binary or grant a stale profile access to the shared legacy export root. The manual subtitle script captures its own state separately from the plugin export root and retains its original Host transport.

The progressive search owns one instance of the existing `HybridCache` for its captured profile, including a distinct L1 namespace. It keeps this backend for user retries and closes it after final cancellation and actual coordinator/provider callback drainage. Shutdown does not hold the lifecycle lock while entering executor shutdown. Configuration SQL/decode/shape failures stop reconciliation instead of writing defaults; optional acceleration-cache failures retain their separate semantics. SQLite publication rechecks revocation inside its real write boundaries. Settings are read once from captured profile XML plus installed defaults; discovery, title-fallback screening and ordinary result filters receive that same getter.

Scoped debrid checking uses those entry settings and the current search round's sticky owner/deadline. Each checker receives its own deep-copied rows and explicit owned cleanup; the outer provider callback retains its lease until all child checks and cleanup drain. This path bypasses the legacy aggregate row cache without creating another cache. Existing `SearchResults` / `SearchCompletion` carries factory, check and cleanup failures through the ordinary transform and retry path, preserving usable rows. A receipt-bearing transform returns the complete receipt, not a delta; raw provider caches keep only the upstream receipt so downstream failures are checked again rather than counted twice. These counts describe work units, not HTTP request counts.

This is not whole-search or all-account isolation. Legacy debrid helper authentication, account refresh and public-IP discovery still use ambient dependencies; independent standalone calls retain their old aggregate cache. RD OAuth and Debrider's IP behavior remain. Base-client construction closes only a session it created; Torbox's pre-base session construction failure is not fully covered. Cancellation suppresses publication but does not interrupt a blocking network call. Selected catalog adapters retain their own quality-filter calls, metadata helpers retain module cache/settings, skin selection remains live, Stremio projection still observes current YouTube availability, and arbitrary external scraper internals are not controlled by Bobbi's snapshot. Empty core/platform dependency exceptions mean only that the forbidden-import scanner has no remaining listed exceptions, not that dynamic ownership or the entire convergence plan is complete. New manifest edges are static mappings for the new source, never additions to historical frozen execution records.

## Cancellation timing scope

The opt-in `block_timing` diagnostic separates consumer cancellation, its live account guard, and its socket probe into cumulative wall/own-thread CPU counters. It preserves the ordinary guard/socket order, half-close handling, range policy, deadlines and revocation; no extra worker or cache is introduced. These nested counters include measurement overhead and overlap fetch/write time. Neither their sum nor wall-minus-CPU is proof of pure network or account-lock wait. Only account checks reached through `Handler.cancelled` are measured, not all checks in grants or the service lifecycle.

Missing CPU clocks omit CPU fields. `cancel_timing_failures > 0` means accumulated timings are incomplete; outer/inner inequalities cannot then establish complete accounting. Optional clock reads, overflow or clock rollback cannot replace the original cancellation result or exception. These offline policy/real-loopback contracts do not demonstrate a fix for the 115 device stall. The 629597c device receipts predate these new counters and cannot certify them.
