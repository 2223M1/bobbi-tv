"""TVBox type-4 adapter. The shared Registry and stream owner retain all authority."""
from urllib.parse import urlsplit
from uuid import uuid4

from bobbi_core import t4
from bobbi_core.library_contract import LibraryError, MAX_CATALOG_BYTES, _text
from .t4_http import read, selection
from .source_media_http import MESSAGES


def _pick(dialog, title, entries):
    if not entries:
        return None
    i = dialog.select(title, [label for label, value in entries])
    return entries[i][1] if 0 <= i < len(entries) else None


def add(dialog, vfs, store, previous=None):
    from .paths import ProfileBinding
    from .source_library_ui import operation
    binding = ProfileBinding()
    expected = store.source_snapshot(previous.id) if previous else (None, None)
    method = _pick(dialog, '小雅 / TVBox（T4）', [('输入订阅网址', 'url'), ('选择配置文件', 'file')])
    if not method:
        return False
    if method == 'url':
        location = dialog.input('输入 T4 配置网址（仅本机保存）')
        if not location:
            return False
        location = t4.endpoint(location.strip())
        if previous is None:
            previous = next((s for s in store.sources() if s.kind == 't4' and s.location == location), None)
            if previous:
                expected = store.source_snapshot(previous.id)
        parsed = operation(lambda end, stop: t4.preview(read(location, end, stop), location))
    else:
        location = ''
        path = dialog.browse(1, '选择 T4 配置文件', 'files', mask='.json')
        if not path:
            return False
        fh = vfs.File(path)
        try:
            parsed = t4.preview(bytes(fh.readBytes(MAX_CATALOG_BYTES + 1)))
        finally:
            fh.close()
    if parsed is None:
        return False
    summary = '可用 %d 个 · 不支持的类型 %d 个 · 无效 %d 个' % (
        len(parsed.sites), parsed.unsupported, parsed.invalid)
    if not parsed.sites:
        dialog.ok('未导入 T4 站点', summary + '\n' + MESSAGES['T4_NO_SITES'])
        return False
    # Show the actual origins (never path/query credentials), including explicitly
    # opt-in third-party site origins declared by a local or remote config.
    origins = sorted({urlsplit(s['api']).scheme + '://' + urlsplit(s['api']).netloc for s in parsed.sites})
    if not dialog.yesno('确认导入 T4 站点？', summary + '\n允许按需连接：\n' + '\n'.join(origins)):
        return False
    binding.require_current()
    store.save(parsed.source(location, previous), expected_snapshot=expected)
    dialog.ok('T4 站点已保存', '打开“我的片库”可按站点浏览与搜索。')
    return True


def manage(dialog, vfs, store, source):
    action = _pick(dialog, source.name, [('重新导入配置', 'edit'), ('移除来源', 'remove')])
    if action == 'edit':
        return add(dialog, vfs, store, source)
    if action == 'remove' and dialog.yesno('移除 T4 来源？', '不会修改远端配置或媒体。'):
        if store.get(source.id) != source:
            raise LibraryError('T4_CHANGED')
        store.remove(source.id)
        return True
    return False


def _rows(value, key, id_key, label_key):
    rows = value.get(key, [])
    if not isinstance(rows, list) or len(rows) > t4.MAX_ROWS:
        raise LibraryError('INVALID_DOCUMENT')
    out, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise LibraryError('INVALID_DOCUMENT')
        ident = t4.identifier(row.get(id_key))
        if ident in seen:
            raise LibraryError('T4_CHANGED')
        seen.add(ident)
        out.append((_text(row.get(label_key), 240), ident))
    return out


def _filter_options(home, category):
    cfg = home.get('filters')
    filters = cfg.get(category) if isinstance(cfg, dict) else None
    for spec in filters[:16] if isinstance(filters, list) else ():
        if (not isinstance(spec, dict) or not isinstance(spec.get('value'), list)
                or not isinstance(spec.get('name'), str) or not isinstance(spec.get('key'), str)):
            continue
        values = [(v['n'], v['v']) for v in spec['value'][:128] if isinstance(v, dict)
                  and isinstance(v.get('v'), str) and isinstance(v.get('n'), str)]
        if values:
            yield spec['name'], spec['key'], values


def browse(dialog, store, source):
    import xbmc
    from .source_library_ui import operation
    from .paths import ProfileBinding
    from .runtime import bind_call
    from .source_streams import local_media_url
    from .kodi import standard_handoff
    from .playback import selected_identity
    binding = ProfileBinding()
    snapshot = store.source_snapshot(source.id)
    if snapshot[0] != source:
        raise LibraryError('T4_CHANGED')
    generation = snapshot[1]
    call = bind_call(binding.root() / 'runtime.json')

    def current():
        return binding.is_current() and not xbmc.Monitor().abortRequested() and store.source_snapshot(source.id) == snapshot

    def fetch(url):
        if not current():
            raise LibraryError('T4_CHANGED')
        raw = operation(lambda end, stop: read(url, end, stop))
        if raw is None:
            raise LibraryError('T4_CANCELLED')
        if not current():
            raise LibraryError('T4_CHANGED')
        return raw

    sites = source.metadata['sites']
    site = sites[0] if len(sites) == 1 else _pick(dialog, source.name, [(s['name'], s) for s in sites])
    if not site:
        return
    client = t4.Client(site, fetch)
    home = client.home()
    categories = _rows(home, 'class', 'type_id', 'type_name')
    recommendations = _rows(home, 'list', 'vod_id', 'vod_name')
    while current():
        first = ([('搜索本站', ('search', ''))] if site['searchable'] else [])
        first.extend((name, ('category', ident)) for name, ident in categories)
        first.extend((name, ('detail', (name, ident))) for name, ident in recommendations)
        action = _pick(dialog, site['name'], first)
        if not action:
            return
        op, key = action
        filters = {}
        if op == 'search':
            key = dialog.input('搜索本站')
            if not key:
                continue
        page = 1
        while current():
            if op == 'detail':
                chosen = key
            else:
                data = client.search(key, page) if op == 'search' else client.category(key, page, filters)
                rows = _rows(data, 'list', 'vod_id', 'vod_name')
                choices = [(name, (name, ident)) for name, ident in rows]
                facets = list(_filter_options(home, key)) if op == 'category' else []
                if facets:
                    choices.append(('筛选条件', 'filters'))
                try:
                    last = int(data.get('pagecount', page))
                except (TypeError, ValueError):
                    raise LibraryError('INVALID_DOCUMENT') from None
                if page < min(10000, last):
                    choices.append(('下一页', 1))
                if page > 1:
                    choices.append(('上一页', -1))
                if not choices:
                    dialog.ok(site['name'], '没有结果。')
                chosen = _pick(dialog, '%s · 第 %d 页' % (site['name'], page), choices)
                if chosen == 'filters':
                    facet = _pick(dialog, '选择筛选条件', [(n, (n, k, v)) for n, k, v in facets])
                    if facet:
                        val = _pick(dialog, facet[0], facet[2])
                        if val is not None:
                            filters[facet[1]] = val
                            page = 1
                    continue
                if isinstance(chosen, int):
                    page += chosen
                    continue
            if chosen is None:
                break
            title, ident = chosen
            lines = client.detail(ident)
            line = lines[0] if len(lines) == 1 else _pick(dialog, title + ' · 选线路', [(n, (n, e)) for n, e in lines])
            if line:
                name, episodes = line
                episode = episodes[0] if len(episodes) == 1 else _pick(dialog, title + ' · 选集', [(n, (n, i)) for n, i in episodes])
                if episode:
                    choice = selection(site, ident, name, episode[1])
                    request = uuid4().hex
                    if not current():
                        raise LibraryError('T4_CHANGED')
                    result = operation(lambda end, stop: None if stop() else call('source_stream_open', dict(
                        source_id=source.id, generation=generation, request_id=request, selection=choice), timeout=18))
                    if result is None:
                        return
                    url = local_media_url(result)
                    identity = selected_identity(t4.compact([source.id, generation, choice]))
                    standard_handoff(identity, -1, current).submit(identity, {
                        'url': url, 'title': title + ' · ' + episode[0], '_bobbi_start_over': True})
                    return
            if op == 'detail':
                break
