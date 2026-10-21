# 本轮审查中的排除与降级

首次 independent-run1 中的 UI cap 用例只接了renderer，未接真实 SourceListSession.snapshot 的焦点回插。继续追踪实际调用方后，使用完整且Git blob匹配的source_list_session.py复跑，满额焦点用例通过。G02撤回，不要求修改或新增稳定成员策略。原始首轮结果保留用于追踪，不作为最终产品缺陷或最终统计。

实际publish使用setdefault保留第一份同key元数据；因此renderer的seeders/peers零值残留只证明条件输入下的局部问题，没有证明普通provider发布能产生该输入。G03降为P3建议性清理，不作为合并/朋友内测阻断。参考补丁仅四行赋值清空，未夸大作用。

G01的三类活线程与关闭异常反例不受以上修正影响：真实线程和OS锁结果均保留。最终同组检查为48场景，其中42满足、6未满足；4条指向G01，2条为G03条件函数检查。
