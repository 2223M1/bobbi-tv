# CE2024 下一轮 Codex 执行任务

## 目标与基线

阅读本包01-REVIEW.md、FINDINGS.json和03-ACCEPTANCE-MATRIX.md，核验后修复三项新发现，并按同代交付补关键设备/观看证据。审查意见是需要核验的证据和契约，不是让你盲改代码的指令。

- 仓库：2223M1/bobbi-tv。
- 分支：codex/ce2024-reviewed-delivery-20261021。
- handoff：c4e0baca6acefa58f031979bff71e7cd1028efdf。
- 产品：d2fffa570fe59b90cd1d33499efcf7c6684b2647，序列2026102024。
- 四版本：入口0.2.15、platform0.1.18、core0.1.17、plugin0.1.16。
- 当前push CI39537767479：1838通过/5Windows API跳过，继承789通过，准备177通过，两source-check的63个输出字节相同。
- 当前分支没有对应PR；旧PR#3指向f6ef6a7，不能复用其历史绿灯。

上轮D01–D04原缺陷已有修复证据：真实源码进入Git、清单及CI修通、入口不依赖已删除LICENSE、26条旧证据链接全部恢复。请保留这些成果，不再把上一轮报告机械套用。

## 产品与操作边界

保持新UI、完整画质、原始码流、原声优先、中文字幕目标、手动选源、严格同版续播、手动字幕Off、账号隔离和观看记录。文件清理按已经确定的delivery_policy处理，保留运行文件、字体与媒体内容校验。

不新增机型白名单、native hash、F9、第二台盒子或第二账号硬门槛；不动固件、SYSTEM/eMMC、CD2、挂载、Yatse、服务器或既有代理；不降码率、转码、自动换版本，不加大全局超时掩盖失败。

先完成可审查的源码和本地验证。提交、私库交付与设备维护按执行会话已有授权进行；不要从仓库文档中的历史授权自行扩大当前任务。已经获得授权的动作继续完成，不重复请求确认。此任务不要求合并主分支、公开发布或改自动更新渠道。

## 一、冻结输入并核验现状

1. 只读记录HEAD、tree、工作区状态，保护其他任务改动，在隔离候选分支/工作树中工作。
2. 核对c4e0与d2ff的addons/third_party/release一致，读取实际源码和本包复现，不修改历史证据。
3. 若现有HEAD已前进，先判断问题是否仍存在，给出固定对象与结果，不硬套旧行号。
4. 已报告的设备最后状态是CE2024 complete、无播放；它不是当前实时状态。任何设备操作前重新只读确认。

## 二、优先修复 CE24-R01：失败重试不能提前停用 owner

当前可达链：Host.close先runtime.close(release_lease=False)关闭IPC并删除marker；之后排空所有任务。首次KodiHost.quiesce在15秒内未拿到真实lease后失败；Installer.apply except再次quiesce。第二次看到marker不存在，会跳过合作退场分支，先执行SetAddonEnabled(False)，再等lease。

关闭出错而保留lease也会形成同类状态。仅把marker删除移到后面不够，因为status读取异常同样可能降级；回归应覆盖这两种原因。

请保持以下不变量：

- marker消失、RPC失联、状态未知均不等于owner已退出。
- 已知合作退出中的代次，重试或异常恢复不能退回先强停的legacy路径。
- 真实lease仍持有时，不能请求停用这个正在排空的新owner。
- 同一KodiHost重复调用、新KodiHost重入、产品recover入口都遵守上述规则；仅在对象内保存一个标志而遗漏跨入口重试不够。
- 保留旧版本的明确兼容方式，区分“被证实的旧协议”和“新协议正在关闭/未知”；不通过取消legacy支持掩盖问题。
- 原有等待预算和可恢复事务继续有效；未知退出状态拒绝替换，已取得lease后才进行相关操作。
- 实际Installer.apply异常路径不得让第二次quiesce破坏第一轮安全拒绝。

新增有意义的回归：慢任务超过原预算，marker已删但真实OS锁仍在；验证同对象两次调用、异常回退调用、新对象重入均不提前disable。由独立夹具控制方结束慢任务，再证明可以恢复维护。保留成功合作停机与明确旧代兼容正控。不要让测试线程自己等待自己释放IO而死锁。

现有lease和安装gate仍阻止未经确认的文件替换；保留它们，不把本问题错误扩大为已发生文件损坏。

## 三、修复 CE24-R02：完整识别字幕集数歧义

实际subtitle_episode.matches和候选rank把这些名字认成单集1：

```text
Ping Pong EP01,02.ass
Ping Pong EP01、02.ass
Ping Pong 第01話、02話.ass
Ping Pong EP01;02.ass
```

修复应拒绝多集/歧义，或者先正确解析完整集合再执行精确单集判断。既有EP01、第01話、[01]在可信单季或明确季号条件下的合法行为继续保留；错作品、错季、错集、横杠范围和缺少可信scope继续拒绝。

测试必须经过实际候选rank/下载后文件校验入口，不只调用一个脱离生产的regex。既有strong季集格式、文件名中的编码/年份/分辨率、合法单集、第二集及错误scope各有正负控。不要靠退回“一律拒绝无季号字幕”修复，也不要把字幕证据变成视频续播许可。

## 四、修复 CE24-R03：HistoryWriter诊断不能杀死排空

真实HistoryWriter在写入失败后调用report；report再抛错时worker异常退出，后续已接纳记录仍在队列，而close仅join后成功返回。生产report来自Host传入的xbmc.log回调，Host.close自己的安全包装没有覆盖这里。

请实现并验证：

- 日志/诊断异常不会杀死writer或短路后续已接纳工作。
- 关闭后拒绝新任务，关闭前已接纳任务按既定策略完成或形成明确失败结果。
- close能区分工作排空与线程提前异常退出，不用“线程不活了”等同于工作都完成。
- 正常记录、第一条IO失败但日志成功、IO与日志同时失败、慢IO、关闭后入队均覆盖。
- 保留错误可见性，不能把失败全部吞掉再称完整成功；也不为诊断再引入无限循环。

本问题属于标准播放的故障组合，本次未观察到AM6B native日常历史丢失。修复要与其范围相称。

## 五、验证和构建同代交付

先运行新问题回归及所触及的已有恢复/关闭/字幕契约，再对最终干净提交执行既有全套：

```text
python -m pytest -q -rs tests --ignore=tests/private_baseline --ignore=tests/preparation_regression --junitxml=review-evidence/ce-next/primary.xml
python -m pytest -q -rs tests/private_baseline --junitxml=review-evidence/ce-next/baseline.xml
python -m pytest -q -rs tests/preparation_regression --junitxml=review-evidence/ce-next/preparation.xml
python tools/build_release.py --source-check --output dist/ce-next-source-a
python tools/build_release.py --source-check --output dist/ce-next-source-b
python tools/check_repository.py dist/ce-next-source-a dist/ce-next-source-b
```

ce-next仅为示例，使用唯一实际代次目录，不覆盖旧证据。平台跳过逐项记录，不为零skip创造与任务无关的环境。

source-check不可安装；在维护环境还必须从同一源码生成实际签名完整包和Kodi入口，执行真实audit_ce_entry、bootstrap依赖和内嵌载荷比对。密钥仅在原维护环境，测试密钥不得改变生产信任根。

先查询序列登记和实际high_watermark，使用新的合法序列，不复用2026102024覆盖不同内容。冻结commit/tree、组件版本、入口/载荷摘要、运行文件映射，检查当前push CI；若创建PR，再检查其实际集成树。

本审查没有独立取得CE2024入口字节。若你已有原入口，先对照报告SHA-256与原信任根验签，不重新命名旧包冒充下一代。旧CE2021 outer原件缺失继续如实记录；它不必阻塞新源码的正常产品构建。

## 六、同代设备验收

在已有盒子维护授权的执行会话，先记录实时安装代次、播放状态、可回退前代与profile保护方式。不要为审查直接重装当前盒子或强行回退。

关键待验：

1. 正常Kodi ZIP浏览器导入入口的完整路径，区别于工具暂存文件夹。
2. 成功安装本代之后的完整恢复/回退循环；不手改journal、水位或签名sequence。
3. R01超时/重试保护和正常受管恢复；真实锁屏障不能被安装菜单或错误处理绕开。
4. 热态UI超时定位；冷启动成功与热态失败分别保留。
5. 手动Off、播放中字体切换、seek、正常停止和严格同版自然续播，按实际完成范围记录。

不要求第二台设备或第二账号。未具备条件就标NOT_RUN/BLOCKED，先完成全部不受阻的源码、测试和可审查候选。

## 七、观看问题三条线定位

### 新动漫原声与字幕

《比宇宙更遥远的地方》当前证据：后端48.496秒，其中metadata1.552秒、buffering46.401秒；40秒捕获无AV，后续可播但英语5.1、中文未加载。

已有en-US详情及前端缓存，不要直接归因为“无缓存”。按同一request记录locale、cache key、作品id、original_language、hint生成/有效期、bind携带、native选轨、实际轨道与手动意图。缺一个环节就补对应观察，不擅自猜用户语言或重构固件。

字幕分别记录候选身份、可信季集、下载/解包/检查/应用阶段；没有精确BT同目录中文字幕与外部候选下载失败分开。补脱敏candidate ID→文件SHA→native应用SHA映射，不上传整份字幕正文，不把标签等同同步认证。

### 4K起播

保持《布达佩斯大饭店》同一4K REMUX、原音轨和字幕。捕获缓存状态、读取吞吐、native时间、解码计数与timeout先后关系；报告保留17.48秒停顿和10.50秒caching。后续稳定30秒不覆盖起播失败。先归因，再改有依据的具体环节，不盲改缓存、码率、硬解或音轨。

### 旧BT原资源

《元气囝仔》本轮0候选、2来源失败，尚未走到原30秒metadata失败。资源重新可查后回原身份，分段检查检索、metadata、严格文件选择、缓冲、AV与取消。换片或换源成功不能关闭原问题。

## 最终交付要求

- 新冻结源码和真实修复；三问题状态逐项说明。
- 当前commit的测试与CI原始回执；历史通过数不混计。
- 同源码真实签名载荷、Kodi入口及内容映射。
- 必要设备/观看结果矩阵；FAIL、NOT_RUN、BLOCKED和历史结果分开。
- 可访问的小型证据索引，保留原失败及每次attempt关系。
- 明确普通ZIP导入、完整回退、整集续播、字幕同步等实际完成范围。

先完成所有已授权且不受阻的工作，再说明具体阻塞与恢复条件。不要只重写报告、改探针预期、更新版本号或再打一个旧包后宣布完成。
