# CE2043 双审查复核与窄修（2026-10-22）

本轮按用户要求独立执行，不调用子代理。附件是待核实证据和建议，不是额外操作授权。

## 可信性结论

- 两包都固定 `24c1ec23915c690924388a7e6ca9fbee95826582` / tree `fa94e168076d58d745cbcba9aa5e464e85fbf891`，与本轮起点完全相同。包内清单分别39、111项，校验零差异。
- 独立从 GitHub 下载旧 run 39700107157 的原始 CI artifact：唯一失败确为 `test_actual_ce2039_receipt_is_bound_and_read_only` 的维护机绝对路径；两包此结论可信。不是播放器故障，也不是第二个产品失败。
- README 过期、两处同一失效链接属实。实时 GitHub 查询为 PUBLIC；用户确认保留公开源码且安装包允许自由分发。上轮文档的私库描述保留其历史时间点，当前政策已更新。
- 两包均承认没有 CE2043 安装包/ELF 实物、没有重新控制盒子；其设备结论是对已有回执的复核，不冒称独立实机验收。不会把重叠通过数相加，也不因某审查环境缺少外部 ELF 就认定强制 CI 多一个失败。
- 对旧缺陷关闭结论，按具体作用域保留防回归，不推倒已完成实现。P1/P2 分级不同不改变这轮可复现的修复目标。

## CI 与交付入口

把原诊断回执缩成有固定 digest、明确来源和白名单字段的仓库相对路径夹具；保留真实 binding/只读消费者和错误身份负例。没有删除失败断言或改成 skip/xfail。原始原件另由 `check_diagnostic_receipt.py` 显式路径核验，缺输入为 not_run，不算设备通过。相关67项回归通过，原始回执实读验证成功且字节不变。

用户随后指定 `D:/daily/download/README.md` 原文作为首页。已先按原始字节替换并验证SHA256 `9811d1ce2c77f7541f012c7d19e0dff719357173e0888651d227595310bd544c`；随后按用户最新明确文案，将自愿致谢改成“感谢波比梓狸伟大的构想与实现。”，保留“各组件与素材沿用各自的许可说明”。其余首页文案不改。机器状态记录放在 `release/current-delivery.json`，构建/测试说明在下节。不恢复旧独立文档，不把仍继承的实现改名冒充自写，不发布账号/私钥。

### 开发与完整安装包的边界

```sh
python -m pip install -r requirements-test.txt
python -m pytest tests --ignore=tests/private_baseline --ignore=tests/preparation_regression -q
python -m pytest tests/private_baseline -q
python -m pytest tests/preparation_regression -q
python tools/build_release.py --source-check --output dist/source-check
python tools/build_release.py --source-check --output dist/source-check-repeat
python tools/check_repository.py dist/source-check dist/source-check-repeat
```

三套测试使用独立进程。source-check 无需维护者项目配置或签名私钥，但其输出不是完整安装包，签名器拒绝把它冒充可安装载荷。完整构建保留配置输入摘要、同代签名、精确inventory和既有信任钥。历史CE2024 ZIP不重命名成新包；历史门禁文件不代表当前验收。

## 个人概览

空闲盒子现有 CE2043 再进入“我的”后，连续10秒六次实读均得到隐藏列表9130有一条“夜行者”、进度2%、IsUpdating=false。说明列表能完成加载，不能认定历史丢失或永久隐藏失效。先前即时截图把尚未完成的空列表直接写成“没有在看”，是未区分加载状态的呈现问题；精确启动时延尚未单独量化。

另用真实历史读取模块的坏文件反例确认：原 `_reload` 保存原文件但吞掉读取失败，初始空字典可被呈现成确认空。本轮增加只读 checked accessor，原写入、合并、删除和其他旧接口行为不改。

同一继续观看路由增加 `resume_preview=true`：共享原历史去重/排序/完成过滤，只渲染第一条，不为概览处理十条元数据或翻页条目。状态随本次目录条目返回 ready/empty/error，避免新的全局窗口状态、并行历史库和迟到请求覆盖。皮肤加载/未知状态只显示读取提示，只有明确 empty 才宣称没有在看；焦点按 ready 可达，外观不重设计。

修前7项需求反例失败已保存；其中包含新增 preview/checked API 的缺失，并非声称存在7个独立产品事故。修后与历史时间/焦点/旧危险探针禁用回归合计33项通过。旧可能崩溃的 personal probe 保持禁用，现场只使用普通 RPC 和受控 idle 导航。

## 当前边界

CE2044 已安装，真实中途接力、当前代EOF、线上字幕与双语cue验证依旧分别列为未验收，不用本轮UI或测试修复冒充解决。不开新性能路线，不改固件、CD2、挂载、账号、Yatse或代理。用户已决定不做旧兼容层替换，本轮未删改兼容实现或原版依赖。

## 冻结、安装与实机结果

- 入口0.2.34、影院0.1.28、皮肤0.1.7，core0.1.29与native ba0327保持不变。读取到旧高水位2043后分配2026102044，没有覆盖旧代包。
- 主套3465 passed / 6 skipped / 1 xfailed，基础1020 passed，准备254 passed，合计4739 passed；另有既有JUnit warning。跳过为Windows symlink环境限制，独立子集不重复累加。
- 两次完整构建63文件一致；22组件签名、同代bootstrap和隔离入口导入通过。入口96,026,655字节，SHA256 `3101e9a427d44da3317086164de83c7d2e5b2d2ce7aee3a663dc765cdd55d458`。
- 真实入口事务 `903f2688bb8d45cdbdc108d36c2654e2` complete，sequence/highwater 2026102044；1164自有文件全部匹配。第一次25秒等待处于switching，未重复安装；后续只读确认完成。
- 闲置重启指令后工具最后一次RPC遇到URLError，原回执保留；未重复重启。随后真实RPC、个人页/首页导航和截图均正常，证明服务已恢复。不会把丢失的即时观察伪写成首轮工具成功。
- 首张本代个人页截图实际显示“正在读取观看记录”；随后 ready 卡片显示“夜行者、2%”。RPC对比Personal与Home第一项的TMDb 242582、movies、空季集和进度2%完全一致。Home计数11只作为容器条目数，不声称有11条媒体历史。
- 真实右键进入9110卡片、左键回到9100，再返回首页，均成功；无播放器启动、无历史写入。已实际查看加载和ready截图，不仅依赖文字标签。
- 真空历史、读取失败、完成/移除后快照变化为本地真实渲染函数/历史模块测试，没有为了现场验收清空真实历史、损坏数据库或换账号。没有真实第二账号验收主张。
- 本轮未调用子代理；自审及回归不冒称另一AI独立复审。最终main CI须看本轮新提交，旧run 39700107157的失败原件保留。

## 恢复

新入口及完整载荷位于 `CE2044-Delivery-20261022`；旧CE2043包和安装事务备份均保留。若需要恢复，通过“波比TV·开始使用”中现有已核验程序回退入口操作，不手改journal或高水位，不回滚账号/媒体/观看数据。本轮没有新增native overlay，无需改SYSTEM或eMMC。
