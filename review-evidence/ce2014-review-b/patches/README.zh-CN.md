# 参考补丁范围

`0001-clear-retained-source-counts.diff` 只修G03的seeders/peers旧值残留，来自冻结renderer相应完整方法。用最终6个UI断言在临时方法副本重跑后，应为6项满足；满额焦点在真实session中原本就通过；实际结果见evidence/reference-patch.json。

没有对完整仓库做git apply检查（本轮没有完整源树副本）；文件混合行尾或后续改动可能需要按照精确锚点移植。不要因此改测试期望、旧Git blob或原始证据。先检查输入，再在候选工作树应用并运行完整回归。

G02已排除；不对G01给未经端到端验证的简单join补丁，也不伪称此一补丁使整包合格。source_populate.after.py.txt仅为方法级后像，绝不能当完整source_select.py覆盖。
