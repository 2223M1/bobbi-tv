# 字幕别名召回独立审查

## 审查范围与当前状态

仅只读审查五文件候选、创建外部独立反例并运行本地测试；未修改产品/工具/原生源码，未操作设备。架构建议由本审查者提出，产品实现由另一 agent 完成。原作者527项通过不视为独立审查通过。

首次独立审查发现2类需要修复的小范围问题，已交回原实现者，现均完成最小修复。独立新增13项反例并复跑完整组合，**552 passed / 2.84 秒**；下节保留修前证据。**同意v2纳入同代候选，未发现尚需阻止这项接入的正确性问题。** 遵照最新要求，不追加冷启动/1 MiB性能实验，普通默认仍8 MiB；本审查只收口字幕别名。

## 修前冻结

| 文件 | SHA256 |
| --- | --- |
| subtitle_candidates.py | dbc097e0ab396d62fe48405e0e394c8760d1e0514c33fe6b2bcafe73f5ed939b |
| subtitle_episode.py | 21ad8f2d381a85cc6ff34eb9b03885efee7c42d251272edc7f28009d4af577a4 |
| subtitle_scope.py | 18756a3b867d01fbb754811fd2b4d5544f5855f78358eb939d7afdb915d48c07 |
| subtitle_fallback.py | 8728aefaeb070ed8c08262ffb05566ec176c4960c572a44bf4f52697ef7c0d63 |
| test_subtitle_alias_recall.py | ce54e59f5030b8a8cfe19733a1819538b693634b9f633dff99ba0e63d0efb078 |

## 独立反例与必要修复

外部测试：`test_independent_ce2042_subtitle_alias.py`。

### 1. 别名覆盖优先不能覆盖更新的季数事实

两个合法、同ID的int/string缓存：较旧记录别名完整且只有S1；较新记录别名较少但已明确有S1/S2。新代码按coverage→fetched选择旧记录，同时从它发出SingleSeason，因而无季号EP01会获得单季授权。相同时间、不同coverage的季信息冲突也有同样问题。

这不是要求别名选择改成按最新记录或混合所有详情；**标题证据可继续选完整coverage，单季资格必须被同时间/更新的有效矛盾季信息否定。** 可以保留别名，将scope退None，不必新加状态、网络请求或mapper。

原HEAD的 `cached_scope()` 按fetched选择最新，等时间不同详情退None；新实现把BT的别名coverage策略直接用在SingleSeason上造成语义差异。这项属于新候选引入的授权扩张，不应以其他527项通过掩盖。

### 2. 可选缓存的损坏时间戳应隔离

缓存 `fetched=±10**400` 是可由JSON表示的整数。真实 `time.time()` 为float，执行 `time.time()-fetched` 会抛OverflowError，不在现有异常处理列表中；可选缓存异常会使字幕发现变成不可用。

这项原cached_scope也存在，属于触及年龄校验时发现的旧缺口，不归因于本次别名功能新增。建议算差值前先做有界数/范围判断，或在每行有限验证处隔离；不要只对巨大int直接调用math.isfinite再重复溢出。坏int键不该阻止另一个有效string键被采用。

首次独立测试 `independent-ce2042-alias-before.xml` 为2fail/9pass，时间fixture沿用作者整数clock，未触发float溢出；审查者纠正为真实float clock后，`independent-ce2042-alias-before-v2.xml` 为**4fail/7pass**。两份均保留，未把第一轮漏检隐藏掉。

## 已核对设计边界

- SubtitleTitles为frozen dataclass，只接受tuple，ID/kind严格，最多16项、单项2–128字符、UTF8总2048字节；去重/控制符/URL/纯标点过滤。普通JSON和错kind/ID不能扩大accepted_titles。
- discover_candidate删除传入私有titles/years/scope，再用cache-only producer注入。native和standard继续共用入口，不改native/IPC/schema或媒体cache identity；未增加后台服务和账号所有者。
- query、search row、detail合并、最终文件、缓存candidate重验及candidate_rank均使用accepted_titles。电影declared_years共享标题集合；TV使用纯标题剥除规则并保持季集约束，没有硬接云准备/AUTO资格或字幕时间轴门槛。
- 标题最多3个，整体query_plan最多9；电影可用年份仍保留原最多4年，总9次封顶。多标题不是各自再给6详情，合并ID后全程最多6detail，每detail最多2文件。
- 原30秒deadline、20 API/分钟、有效候选改善保留、Late cancel/Off/换号守卫未从代码上被移除。实际正文下载失败仍保留前一轮candidate_failed局部状态修复；诊断不作为匹配权威。
- 查询/遍历诊断只含hash、cache/live、槽位、计数，不输出Token/URL/完整正文。

## v2修复与独立复核

实现者只修改 `subtitle_scope.py` 及其专属测试：

- title继续coverage→fetched选择，不混合不同detail；当同时间/更新的有效detail无法得出相同SingleSeason时，只否决scope，不丢已校验别名。既有明确SxxExx不受影响，没有添加mapper或网络调用。
- 把 `0 <= now-fetched <= STALE` 改为先有界比较 `now-STALE <= fetched <= now`，巨大JSON int不转float相减；NaN/无穷大/坏类型同样不能成为有效时间。独立增加坏int键+另一有效string键两个反例，证明不是“异常吞掉整个缓存读取”。

最终独立13项包括：较新/同时间多季否决旧rich单季、7类坏时间戳、2类坏键不屏蔽另一键、不同精度查询同ID只detail一次、全角alias规范化不隐藏明确错季。

回归：

- `independent-ce2042-alias-after-integrated.xml`：21 passed / 0.38 秒。该次脚本按XML classname过滤原测试列表时未适配作者的workspace前缀，实际只跑了外部两文件（8+13），**不是完整组合**；发现后立即补跑下项，没有冒称宽回归。
- `independent-ce2042-alias-full-integrated.xml`：明确列出作者10个测试文件 + 外部2个独立文件，**552 passed / 2.84 秒**。包含原作者527组合及新增作者12、独立13项。
- 修前2fail与4fail两份证据保持原样；没有改失败断言换取通过。
- 回归前后五文件hash一致，限定范围 `git diff --check` 通过。

v2最终冻结（相对前表仅两项改变）：

| 文件 | SHA256 |
| --- | --- |
| subtitle_candidates.py | dbc097e0ab396d62fe48405e0e394c8760d1e0514c33fe6b2bcafe73f5ed939b |
| subtitle_episode.py | 21ad8f2d381a85cc6ff34eb9b03885efee7c42d251272edc7f28009d4af577a4 |
| subtitle_scope.py | a7c93e921ed75d0a70a6cc5b422f6e7c54fe977d9d8bec89f5b7eadd84dc0ad9 |
| subtitle_fallback.py | 8728aefaeb070ed8c08262ffb05566ec176c4960c572a44bf4f52697ef7c0d63 |
| test_subtitle_alias_recall.py | 897cfe25137e84ad33d0d6a79d361bd0b3e035698e4cf42421577668bb24578f |

该实现保留现有字体、字幕格式、原质量、手动Off/延迟和账号/实例所有权，不因为这次扩大标题召回要求另做架构或播放器性能修改。实际中文字幕是否在线可得/加载成功及同步状态仍由主任务实机证据单独记录；作者和独立测试中的中文返回是离线合成响应，不能冒称线上成功。未证明任意电影/动漫都有字幕，也不因此将无限探索字幕上游作为本轮新硬门槛。
