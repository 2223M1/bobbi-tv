"""Thin TV workflows over CatalogViews and the existing directory renderer."""
from bobbi_core.typed_ref import KINDS as PATH_KINDS, request_scope
from lib.db.catalog_views import CatalogViews, owner


def _tr(po_id, zh_text):
    try:
        from bobbi_platform.i18n import tr
        return tr(po_id, zh_text, '', addon_id='plugin.video.bobbi')
    except Exception:
        return zh_text


def resolve(record, rpc):
    from bobbi_platform.pan_accounts import scope
    belonging = record['owner']
    if belonging.get('reference_kind') in PATH_KINDS:
        from lib.utils.views.personal_catalog import typed_action
        expected = rpc(typed_action(belonging, 'scope'), dict(source_id=belonging['source_id']))
        if owner(expected) != belonging:
            raise ValueError('CATALOG_VIEW_SCOPE_CHANGED')
    else:
        matches = [scope(row['account'], authenticated=True) for row in rpc('pan_status', {})['providers']
            if row['provider'] == belonging['provider'] and row['account'].get('authenticated')
            and row['account'].get('account_id') == belonging['account_id']]
        if len(matches) != 1:
            raise ValueError('CATALOG_VIEW_SCOPE_CHANGED')
        expected = matches[0]
        source = record['query'].get('source_id')
        if source and source not in {row['id'] for row in rpc('catalog_sources', dict(expected=expected))['items']}:
            raise ValueError('CATALOG_VIEW_SOURCE_REMOVED')
    query = dict(record['query'])
    if record['parent'] is not None:
        descriptor = parent_descriptor(expected, query['parent_entity_id'], rpc)
        if descriptor != record['parent']:
            raise ValueError('CATALOG_PARENT_CHANGED')
    return expected, query


def parent_descriptor(expected, parent_id, rpc):
    if expected.get('reference_kind') in PATH_KINDS:
        from lib.utils.views.personal_catalog import typed_action
        return rpc(typed_action(expected, 'parent'), dict(request_scope(expected), parent_id=parent_id))
    return rpc('catalog_parent', dict(expected=expected, parent_id=parent_id))


def changed():
    import xbmcgui
    from lib.cinema.focus_anchor import bump
    bump(xbmcgui.Window(10000), 'personal_library')


def entries(entry, store=None):
    from .personal_catalog import route
    _, snapshot = (store or CatalogViews()).snapshot()
    for record in snapshot['items']:
        target = route(action='personal_catalog', mode='saved', view_id=record['id'])
        item = entry(record['title'], target, detail=_tr(91230, '首页我的片库视图') if snapshot['active'] == record['id'] else '',
                     properties={'Bobbi.CardKey': 'catalog-view:' + record['id']})
        item.addContextMenuItems([(_tr(91231, '管理这个常用视图'), 'RunPlugin(' + route(
            action='personal_catalog_manage', mode='view_edit', view_id=record['id']) + ')')])
    if not snapshot['items']:
        entry(_tr(91232, '尚无常用视图'), route(action='personal_catalog'),
              detail=_tr(91233, '先进入片库筛选，再选择“保存为常用视图”'))
    entry(_tr(91234, '恢复默认首页片库'), route(action='personal_catalog_manage', mode='view_default'), False)


def current(view_id=None, store=None):
    _, snapshot = (store or CatalogViews()).snapshot()
    identifier = view_id or snapshot['active']
    if identifier is None:
        return None
    row = next((item for item in snapshot['items'] if item['id'] == identifier), None)
    if row is None:
        raise ValueError('CATALOG_VIEW_CHANGED')
    return row


def save(dialog, params, expected, origin, rpc, store=None):
    from bobbi_core.catalog_query import parameters
    from .personal_catalog import FILTER_FIELDS, origin_is_current
    store = store or CatalogViews()
    query = parameters({key: value for key, value in params.items()
        if key in FILTER_FIELDS + ('view', 'parent_entity_id') and value is not None})
    descriptor = parent_descriptor(expected, query['parent_entity_id'], rpc) if query['parent_entity_id'] else None
    snapshot = store.snapshot()
    options = [_tr(91235, '保存为新的常用视图')] + [_tr(91236, '更新：%s') % row['title'] for row in snapshot[1]['items']]
    choice = dialog.select(_tr(91237, '保存当前筛选'), options)
    if choice < 0 or choice >= len(options):
        return
    identifier, title = None, None
    if choice == 0:
        title = dialog.input(_tr(91238, '常用视图名称（最多 80 字）')).strip()
        if not title:
            return
    else:
        row = snapshot[1]['items'][choice - 1]
        identifier = row['id']
        if not dialog.yesno(_tr(91239, '更新常用视图？'),
                            _tr(91240, '用当前来源和筛选替换“%s”。原文件与观看记录不变。') % row['title']):
            return
    if not origin_is_current(params, expected, origin, rpc):
        raise ValueError('CATALOG_VIEW_SCOPE_CHANGED')
    store.change(snapshot, 'create' if choice == 0 else 'update', identifier=identifier, title=title,
                 expected=expected, query=query, descriptor=descriptor)
    changed()
    dialog.notification(_tr(91241, '已保存常用视图'), title or row['title'])


def manage(params, rpc, store=None):
    import xbmc
    import xbmcgui
    store, dialog = store or CatalogViews(), xbmcgui.Dialog()
    snapshot = store.snapshot()
    if params['mode'] == 'view_default':
        store.change(snapshot, 'default')
    else:
        identifier = params.get('view_id')
        row = next((item for item in snapshot[1]['items'] if item['id'] == identifier), None)
        if row is None:
            raise ValueError('CATALOG_VIEW_CHANGED')
        actions = ['home', 'rename', 'up', 'down', 'delete']
        choice = dialog.select(row['title'], [
            _tr(91242, '设为首页我的片库视图'),
            _tr(91243, '重命名'),
            _tr(91244, '上移'),
            _tr(91245, '下移'),
            _tr(91246, '删除常用视图'),
        ])
        if not 0 <= choice < len(actions):
            return
        action, title = actions[choice], None
        if action == 'home':
            resolve(row, rpc)  # A stale account/root is not a new default.
        elif action == 'rename':
            title = dialog.input(_tr(91238, '常用视图名称（最多 80 字）'), defaultt=row['title']).strip()
            if not title:
                return
        elif action == 'delete' and not dialog.yesno(
                _tr(91247, '删除常用视图？'),
                _tr(91248, '只删除筛选描述，原文件与观看记录均保留。')):
            return
        store.change(snapshot, action, identifier=identifier, title=title)
    changed()
    xbmc.executebuiltin('Container.Refresh')
