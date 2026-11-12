"""Explicit one-level extra ownership using the original review/receipt workflow."""
from bobbi_core.catalog_supplements import KINDS

LABELS = dict(bonus='花絮', interview='访谈', deleted='删减片段', trailer='预告', other='其他补充内容')


def select_page(dialog, expected, query, rpc, title, optional=False):
    from lib.utils.views.personal_catalog import query_page
    cursor = None
    while True:
        page = query_page(rpc, expected, query=query, cursor=cursor, limit=20)
        rows = page['items']
        labels = (['整个作品（不限某个版本）'] if optional else []) + [row['display_title'] for row in rows]
        if page.get('next_cursor'):
            labels.append('下一页')
        if not labels:
            dialog.ok('尚无可选主作品', '请先把主作品整理为电影、剧集或人工自建名称，再关联补充文件。')
            return None
        choice = dialog.select(title, labels)
        if not 0 <= choice < len(labels):
            return None
        if optional and choice == 0:
            return {}
        number = choice - int(optional)
        if number < len(rows):
            return rows[number]
        cursor = page['next_cursor']


def edit(dialog, expected, item, rpc, context=None):
    from bobbi_platform.catalog_ui import _review_context, review_entries
    binding, invoke = context or _review_context(expected)
    binding.require_current()
    original_rpc = rpc

    def rpc(action, body):
        binding.require_current()
        result = original_rpc(action, body)
        binding.require_current()
        return result
    current = item.get('supplement')
    choice = dialog.select('个人补充内容关系', ['关联 / 修改主作品与版本', '移除补充内容关联', '撤回上次修改'])
    if choice not in (0, 1, 2):
        return
    action, relation = ('supplement', 'detach_supplement', 'undo')[choice], None
    if choice == 0:
        text = dialog.input('查找主作品或自建名称（可留空）').strip()
        work = select_page(dialog, expected, dict(view='works', text=text), rpc, '选择主作品')
        if not work:
            return
        if work.get('metadata_key'):
            parent = select_page(dialog, expected, dict(view='files', parent_entity_id=work['entity_id']),
                                 rpc, '关联整个作品或指定文件版本', optional=True)
        else:
            # A custom title is not a public/group identity. Bind exactly this
            # manually named file and recheck its revision/observation on apply.
            from lib.utils.views.personal_catalog import TYPED_KINDS, typed_action
            if expected.get('reference_kind') in TYPED_KINDS:
                record = rpc(typed_action(expected, 'item'), dict(source_id=expected['source_id'],
                    namespace=expected['namespace'], file_id=work['entity_id']))
            else:
                record = rpc('catalog_item', dict(expected=expected, file_id=work['entity_id']))
            from bobbi_core.catalog_supplements import custom_parent
            if not custom_parent(record) or record.get('supplement'):
                dialog.ok('请先整理主作品', '未整理的原文件不能当作主作品；请先填写人工自建名称，或确认为电影、剧集。')
                return
            parent = dict(entity_id=record['file']['id'], review_revision=record['revision'],
                          observation_key=record['file']['observation_key'])
        if parent is None:
            return
        kind = dialog.select('补充内容类型', [LABELS[key] for key in KINDS])
        if not 0 <= kind < len(KINDS):
            return
        title = dialog.input('补充内容名称（最多 160 字）', defaultt=(current or {}).get('title') or item['file']['name']).strip()
        if not title:
            return
        relation = dict(metadata_key=work.get('metadata_key'), parent_file_id=parent.get('entity_id'),
                        kind=KINDS[kind], title=title, parent_revision=parent.get('review_revision'),
                        parent_evidence=parent.get('observation_key'))
    return review_entries(dialog, expected, [dict(name=item['file']['name'], command=dict(
        file_id=item['file']['id'], expected_revision=item['revision'], action=action, mapping=relation))],
        invoke=invoke, scope_check=binding.require_current, profile_root=binding.root())
