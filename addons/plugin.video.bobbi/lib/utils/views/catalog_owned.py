"""One page-level local ownership overlay; public discovery remains the default."""
import re


def annotate(cards, rpc=None):
    from bobbi_platform.runtime import call
    from lib.utils.views.personal_catalog import route, scope_params, variants_target, card_target
    rpc = rpc or call
    identities = [key for _, key in cards if re.fullmatch(r'tmdb:(movie|tv):[1-9]\d{0,8}', key)]
    if not identities or len(identities) > 20:
        return
    try:
        page = rpc('catalog_public_holdings', dict(identities=identities))
        found = {row['metadata_key']: row for row in page.get('items', [])}
    except (ValueError, OSError, RuntimeError, KeyError, TypeError):
        page, found = {}, {}
    for item, key in cards:
        target = route(action='personal_catalog', mode='owned', metadata_key=key)
        label = '查看我的片库版本'
        row = found.get(key)
        if row and row.get('state') == 'observed' and page.get('expected'):
            expected = page['expected']
            target = (variants_target(row, expected) if row['media_kind'] == 'movie' else
                      card_target(row, expected)[0])
            label = '我的片库 · %d 个文件' % row['file_count']
            item.setProperty('Bobi.Catalog.OwnedCount', str(row['file_count']))
        elif row and row.get('state') == 'not_indexed':
            label = '当前片库未收录 · 查看其他来源'
        elif page.get('state') == 'choose_scope':
            label = '我的版本 · 选择账号或来源'
        else:
            label = '我的版本 · 收录状态未知'
        item.setProperty('Bobi.Catalog.Owned', target)
        if hasattr(item, 'addContextMenuItems'):
            item.addContextMenuItems([(label, 'ActivateWindow(Videos,"' + target + '",return)')])
