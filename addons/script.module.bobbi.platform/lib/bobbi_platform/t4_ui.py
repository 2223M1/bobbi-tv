"""TVBox type-4 adapter with native Kodi directory navigation and persistent opaque tokens."""
import re
from urllib.parse import urlencode, urlsplit

from bobbi_core import t4
from bobbi_core.library_contract import LibraryError, MAX_CATALOG_BYTES, _text
from bobbi_core.playback_request import SelectionChanged
from bobbi_core.source_endpoint import endpoint
from .source_media_http import MESSAGES
from .t4_http import _opaque, read, selection, selection_with_play_token, selection_with_token
from .t4_tokens import T4TokenStore

BASE_ROUTE = 'plugin://plugin.video.bobbi.library/?'
DETAIL_PAGE_SIZE = 200


def _route(**params):
    return BASE_ROUTE + urlencode(params)


def _clean_label(value, limit=240, fallback=''):
    if not isinstance(value, str):
        return fallback
    return (
        ''.join(c if ord(c) >= 32 else ' ' for c in value[:limit])
        .strip()
        .replace('[', '［')
        .replace(']', '］')
        or fallback
    )


def _safe_poster(raw_pic) -> str:
    if not isinstance(raw_pic, str) or not raw_pic.strip():
        return ''
    try:
        return endpoint(raw_pic.strip())
    except LibraryError:
        return ''


def _pick(dialog, title, entries):
    if not entries:
        return None
    i = dialog.select(title, [label for label, value in entries])
    return entries[i][1] if 0 <= i < len(entries) else None


def export_probed_lives_playlist(raw_config: bytes, export_dir, *, index: int = 0, fetch_fn=None) -> dict:
    """Format-probed standalone M3U8 export for TVBox lives entries; NEVER touches PVR settings (R19-09, R19-10)."""
    import hashlib
    from pathlib import Path
    import time

    doc = t4.document(raw_config)
    lives = doc.get('lives')
    if not isinstance(lives, list) or not (0 <= index < len(lives)) or not isinstance(lives[index], dict):
        raise LibraryError('INVALID_DOCUMENT')
    entry = lives[index]
    raw_url = str(entry.get('url') or '').strip()
    checked_url = t4.endpoint(raw_url)
    end = time.monotonic() + 8.0
    raw_body = (fetch_fn(checked_url) if fetch_fn is not None else read(checked_url, end, lambda: False))
    if not isinstance(raw_body, (bytes, bytearray)) or not (1 <= len(raw_body) <= 512 * 1024):
        raise LibraryError('T4_LIMIT')
    try:
        text_body = bytes(raw_body).decode('utf-8-sig')
    except UnicodeError:
        raise LibraryError('INVALID_DOCUMENT') from None
    stripped = text_body.lstrip()
    if not stripped or stripped.startswith(('<', '{', '[')):
        raise LibraryError('INVALID_DOCUMENT')

    lines = [ln.strip() for ln in stripped.splitlines() if ln.strip()]
    m3u_lines = ['#EXTM3U']
    channel_count = 0
    if lines[0].upper().startswith('#EXTM3U'):
        for ln in lines[1:]:
            if ln.upper().startswith('#EXTINF:'):
                m3u_lines.append(ln)
            elif ln.startswith(('http://', 'https://')) and ' ' not in ln:
                m3u_lines.append(ln)
                channel_count += 1
    else:
        current_group = '直播'
        for ln in lines:
            if ln.endswith(',#genre#'):
                current_group = _clean_label(ln[:-8], 60, '直播')
                continue
            cname, sep, curl = ln.partition(',')
            curl = curl.strip()
            if sep and cname.strip() and curl.startswith(('http://', 'https://')) and ' ' not in curl:
                safe_name = _clean_label(cname, 120, '频道')
                m3u_lines.append(f'#EXTINF:-1 group-title="{current_group}",{safe_name}')
                m3u_lines.append(curl)
                channel_count += 1

    if channel_count == 0:
        raise LibraryError('INVALID_DOCUMENT')

    out_dir = Path(export_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(checked_url.encode('utf-8')).hexdigest()[:8]
    out_path = out_dir / f'bobbi-lives-{digest}.m3u8'
    out_path.write_text('\n'.join(m3u_lines) + '\n', encoding='utf-8')
    return {
        'path': str(out_path),
        'channel_count': channel_count,
        'name': str(entry.get('name') or f'live_{index + 1}')[:80],
    }


def offer_lives_export(dialog, raw_bytes: bytes, diag: dict, export_dir, *, operation_fn=None) -> dict | None:
    """User-reachable import preview action for TVBox lives playlist export (SRC-GAP-02)."""
    lives_subs = diag.get('lives_subscriptions') or []
    lives_cnt = (diag.get('counts') or {}).get('lives', 0)
    if lives_cnt <= 0 or not lives_subs:
        return None
    if not dialog.yesno(
        '导出直播订阅列表？',
        f'检测到 {lives_cnt} 个直播入口（仅代表入口数，非频道数）。是否探测格式并导出独立 M3U8 文件（不自动修改 PVR 设置）？',
    ):
        return None
    idx = 0
    if len(lives_subs) > 1:
        picked = _pick(
            dialog,
            '选择要导出的直播入口',
            [(_clean_label(s.get('name'), 80, f'直播 {i + 1}'), i) for i, s in enumerate(lives_subs)],
        )
        if picked is None:
            return None
        idx = picked
    if operation_fn is not None:
        exported = operation_fn(
            lambda end, stop: export_probed_lives_playlist(
                raw_bytes,
                export_dir,
                index=idx,
                fetch_fn=lambda u: read(u, end, stop),
            )
        )
    else:
        exported = export_probed_lives_playlist(raw_bytes, export_dir, index=idx)
    if exported:
        dialog.ok(
            '直播列表已导出',
            f"已探测到 {exported['channel_count']} 个频道条目，已保存至：\n{exported['path']}",
        )
    return exported


def add(dialog, vfs, store, previous=None):
    from .paths import ProfileBinding
    from .source_library_ui import operation
    binding = ProfileBinding()
    expected = store.source_snapshot(previous.id) if previous else (None, None)
    method = _pick(
        dialog,
        '小雅 / TVBox（T4）',
        [
            ('输入订阅网址（支持 Yatse 粘贴）', 'url'),
            ('选择本机 / U盘 / 共享 JSON 文件', 'file'),
            ('手机扫码上传配置文件（支持大文件分片）', 'phone'),
            ('改连原生 WebDAV / AList 或 Emby 媒体服', 'native_handoff'),
        ],
    )
    if not method:
        return False
    if method == 'phone':
        import xbmc
        xbmc.executebuiltin('RunPlugin(plugin://plugin.video.bobbi/?action=source_import_manage_phone)')
        return False
    if method == 'native_handoff':
        from . import library_ui, server_ui
        target = _pick(
            dialog,
            '选择原生连接方式',
            [('WebDAV / AList 网盘', 'webdav'), ('Emby / Jellyfin 媒体服务器', 'server')],
        )
        if target == 'webdav':
            src = library_ui._network(dialog, 'webdav')
            if src is not None and dialog.yesno('添加“' + src.name + '”', src.location + '\n仅保存到本机。'):
                store.save(src)
                return True
        elif target == 'server':
            return bool(server_ui.add(dialog, store))
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
        raw_bytes = operation(lambda end, stop: read(location, end, stop))
        if raw_bytes is None:
            return False
    else:
        location = ''
        path = dialog.browse(1, '选择 T4 配置文件', 'files', mask='.json')
        if not path:
            return False
        fh = vfs.File(path)
        try:
            raw_bytes = bytes(fh.readBytes(MAX_CATALOG_BYTES + 1))
        finally:
            fh.close()
    diag = t4.diagnose_config(raw_bytes, location)
    parsed = t4.preview(raw_bytes, location)
    summary = diag.get('summary_zh') or (
        '可用 %d 个 · 不支持的类型 %d 个 · 无效 %d 个' % (len(parsed.sites), parsed.unsupported, parsed.invalid)
    )
    lives_cnt = (diag.get('counts') or {}).get('lives', 0)
    if not parsed.sites:
        dialog.ok('未导入 T4 站点', summary + '\n' + MESSAGES['T4_NO_SITES'])
        if lives_cnt > 0:
            export_root = binding.root() / 'exports' if hasattr(binding, 'root') else store.path.parent / 'exports'
            offer_lives_export(dialog, raw_bytes, diag, export_root, operation_fn=operation)
        return False
    # Show the actual origins (never path/query credentials), including explicitly
    # opt-in third-party site origins declared by a local or remote config.
    origins = sorted({urlsplit(s['api']).scheme + '://' + urlsplit(s['api']).netloc for s in parsed.sites})
    if not dialog.yesno('确认导入 T4 站点？', summary + '\n允许按需连接：\n' + '\n'.join(origins)):
        return False
    binding.require_current()
    store.save(parsed.source(location, previous), expected_snapshot=expected)
    dialog.ok('T4 站点已保存', '打开“我的片库”可按站点浏览与搜索。')
    if lives_cnt > 0:
        export_root = binding.root() / 'exports' if hasattr(binding, 'root') else store.path.parent / 'exports'
        offer_lives_export(dialog, raw_bytes, diag, export_root, operation_fn=operation)
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


def _vod_cards(value, key='list'):
    rows = value.get(key, [])
    if not isinstance(rows, list) or len(rows) > t4.MAX_ROWS:
        raise LibraryError('INVALID_DOCUMENT')
    out, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            raise LibraryError('INVALID_DOCUMENT')
        ident = t4.identifier(row.get('vod_id'))
        if ident in seen:
            raise LibraryError('T4_CHANGED')
        seen.add(ident)
        title = _clean_label(row.get('vod_name'), 240)
        if not title:
            raise LibraryError('INVALID_DOCUMENT')
        remarks = _clean_label(row.get('vod_remarks'), 120)
        poster = _safe_poster(row.get('vod_pic'))
        out.append((title, ident, remarks, poster))
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


def _fetch_site_url(site, url, end, stop):
    site_headers = site.get('headers')
    if site_headers:
        return read(url, end, stop, headers=site_headers, expected_origin=site['api'])
    return read(url, end, stop)


def _positive_int(raw_val: str, maximum: int) -> int:
    if not isinstance(raw_val, str) or not re.fullmatch(r'[0-9]{1,5}', raw_val):
        raise LibraryError('INVALID_VALUE')
    val = int(raw_val)
    if not 1 <= val <= maximum:
        raise LibraryError('INVALID_VALUE')
    return val


def execute_directory(handle, params, store, item):
    """Native Kodi directory views for T4 sites (posters, plots, filters, bounded pagination, owned playback)."""
    import time
    import xbmc
    import xbmcgui
    import xbmcplugin
    from .owned_playback import library_source_scope, reserve_playback
    from .paths import ProfileBinding
    from .source_streams import local_media_url

    binding = ProfileBinding()
    dialog = xbmcgui.Dialog()
    action = params.get('action', 'browse')
    is_play = action == 't4_play'
    submitted = False

    def finish(ok=False):
        nonlocal submitted
        if not submitted:
            submitted = True
            if is_play:
                xbmcplugin.setResolvedUrl(handle, False, xbmcgui.ListItem())
            elif handle >= 0:
                xbmcplugin.endOfDirectory(handle, succeeded=ok, cacheToDisc=False)

    try:
        root = binding.root()
        source, generation = store.source_snapshot(params.get('source', ''))
        if source.kind != 't4':
            raise LibraryError('T4_CHANGED')
        if action == 'browse':
            if set(params) != {'action', 'source'}:
                raise LibraryError('INVALID_VALUE')
        elif params.get('rev') != generation:
            raise LibraryError('T4_CHANGED')

        sites = source.metadata['sites']

        def is_current():
            if xbmc.Monitor().abortRequested() or not binding.is_current():
                return False
            try:
                return store.source_snapshot(source.id) == (source, generation)
            except LibraryError:
                return False

        def require_current():
            if not is_current():
                raise LibraryError('T4_CHANGED')

        if action == 'browse' and len(sites) > 1:
            rows = []
            for idx, s in enumerate(sites):
                rows.append(item(
                    _clean_label(s['name'], 120, f'站点 {idx + 1}'),
                    _route(action='t4_site', source=source.id, rev=generation, site=str(idx)),
                    True,
                    label2='支持搜索' if s.get('searchable') else '分类浏览',
                ))
            require_current()
            xbmcplugin.setPluginCategory(handle, source.name)
            xbmcplugin.setContent(handle, 'files')
            xbmcplugin.addDirectoryItems(handle, rows, len(rows))
            finish(True)
            return

        site_idx_str = '0' if action == 'browse' else params.get('site', '')
        if not re.fullmatch(r'[0-9]{1,3}', site_idx_str) or int(site_idx_str) >= len(sites):
            raise LibraryError('INVALID_VALUE')
        site_idx = int(site_idx_str)
        site = sites[site_idx]
        site_hash = _opaque(site['key'])

        def fetch(url):
            require_current()
            end = time.monotonic() + 12.0
            raw = _fetch_site_url(site, url, end, lambda: not is_current())
            require_current()
            return raw

        client = t4.Client(site, fetch)

        if is_play:
            if set(params) != {'action', 'source', 'rev', 'site', 'ptok'}:
                raise LibraryError('INVALID_VALUE')
            with T4TokenStore(root / 't4-tokens.sqlite3', read_only=True) as tstore:
                play_meta = tstore.get_play(source.id, generation, site_hash, params['ptok'])
            choice = selection_with_play_token(site, params['ptok'])
            scope = library_source_scope(source.id, generation)
            with reserve_playback(
                f"t4://{source.id}/{params['ptok']}",
                scope,
                binding=binding,
                allow_starting=True,
            ) as reservation:
                result = None
                for _hop_prompt in range(5):
                    try:
                        result = reservation.host_call('source_stream_open', {
                            'source_id': source.id,
                            'generation': generation,
                            'request_id': reservation.request_id,
                            'selection': choice,
                        }, timeout=18)
                        break
                    except LibraryError as err:
                        if err.code != 'T4_MEDIA_ORIGIN':
                            raise
                        cand_origin = getattr(err, 'blocked_origin', None)
                        if not cand_origin:
                            with T4TokenStore(root / 't4-tokens.sqlite3') as tstore:
                                cand_origin = tstore.pop_blocked_origin(
                                    source.id,
                                    generation,
                                    reservation.request_id,
                                )
                        if not cand_origin:
                            raw_vid = play_meta.get('vod_id') or ''
                            if not raw_vid:
                                with T4TokenStore(root / 't4-tokens.sqlite3', read_only=True) as tstore:
                                    raw_vid = tstore.get_item(source.id, generation, site_hash, play_meta['item_token'])
                            for lname, eps in client.detail(raw_vid):
                                if _opaque(lname) == play_meta['line']:
                                    for _, ep_id in eps:
                                        if _opaque(ep_id) == play_meta['episode']:
                                            m_url, _ = client.play(lname, ep_id)
                                            u_m = urlsplit(m_url)
                                            cand_origin = f'{u_m.scheme.lower()}://{u_m.netloc.lower()}'
                        if not cand_origin or not dialog.yesno(
                            '允许连接外部媒体域名？',
                            f'此片源位于 {cand_origin}，是否允许当前来源按需读取（不会发送站点凭据）？',
                        ):
                            return
                        require_current()
                        reservation.require_current()
                        with T4TokenStore(root / 't4-tokens.sqlite3') as tstore:
                            tstore.approve_origin(source.id, generation, cand_origin)
                if result is None:
                    raise LibraryError('MEDIA_REDIRECT')

                media_url = local_media_url(result)
                reservation.submit(
                    handle,
                    media_url,
                    title=play_meta['title'] or site['name'],
                    source_meta={
                        'provider': 't4',
                        'source_id': source.id,
                        'source_generation': generation,
                        'item_id': params['ptok'],
                        'identity_mode': str(result.get('identity_mode', 'strong_etag')),
                    },
                    start_over=True,
                    ready=is_current,
                )
                submitted = True
                return

        rows = []
        content = 'videos'
        category_label = f"{source.name} · {site['name']}"

        def _render_cards(tstore, cards, *, pinned=()):
            if not cards:
                return
            itoks = tstore.put_item_batch(
                source.id,
                generation,
                site_hash,
                [vid for _, vid, _, _ in cards],
                pinned_tokens=pinned,
            )
            for (vtitle, _vid, remarks, poster), itok in zip(cards, itoks):
                li_row = item(
                    vtitle,
                    _route(action='t4_detail', source=source.id, rev=generation, site=site_idx_str, tok=itok),
                    True,
                    label2=remarks,
                )
                li_row[1].setInfo('video', {'title': vtitle, 'mediatype': 'tvshow'})
                if poster:
                    li_row[1].setArt({'poster': poster, 'thumb': poster})
                rows.append(li_row)

        try:
            with T4TokenStore(root / 't4-tokens.sqlite3') as tstore:
                if action in ('browse', 't4_site'):
                    if action == 't4_site' and set(params) != {'action', 'source', 'rev', 'site'}:
                        raise LibraryError('INVALID_VALUE')
                    home = client.home()
                    if site.get('searchable'):
                        rows.append(item(
                            '搜索本站',
                            _route(action='t4_search', source=source.id, rev=generation, site=site_idx_str),
                            True,
                            label2=f"在「{site['name']}」中搜索影视",
                        ))
                    cat_tokens = []
                    for cname, cid in _rows(home, 'class', 'type_id', 'type_name'):
                        facets = list(_filter_options(home, cid))
                        ctok = tstore.put_category(
                            source.id,
                            generation,
                            site_hash,
                            cid,
                            facets=facets,
                            name=cname,
                        )
                        cat_tokens.append(ctok)
                        rows.append(item(
                            _clean_label(cname, 120),
                            _route(action='t4_cat', source=source.id, rev=generation, site=site_idx_str, cat=ctok, pg='1'),
                            True,
                            label2='分类 · 可筛选' if facets else '分类',
                        ))
                    _render_cards(tstore, _vod_cards(home, 'list'), pinned=tuple(cat_tokens))

                elif action in ('t4_cat', 't4_search'):
                    if action == 't4_search':
                        if set(params) - {'action', 'source', 'rev', 'site', 'pg', 'q'}:
                            raise LibraryError('INVALID_VALUE')
                        page = _positive_int(params.get('pg', '1'), 10000)
                        term = params.get('q', '').strip()
                        if not term:
                            term = dialog.input(f"搜索 {site['name']}").strip()
                            if not term:
                                return
                        data = client.search(term, page)
                        category_label += f' · 搜索：{term}'
                        _render_cards(tstore, _vod_cards(data, 'list'))
                        try:
                            last_pg = int(data.get('pagecount', page))
                        except (TypeError, ValueError):
                            last_pg = page
                        if page > 1:
                            rows.append(item(
                                '上一页',
                                _route(action='t4_search', source=source.id, rev=generation, site=site_idx_str, pg=str(page - 1), q=term),
                                True,
                                properties={'Bobbi.PrevPage': 'true'},
                            ))
                        if page < min(10000, last_pg):
                            rows.append(item(
                                '下一页',
                                _route(action='t4_search', source=source.id, rev=generation, site=site_idx_str, pg=str(page + 1), q=term),
                                True,
                                properties={'Bobbi.NextPage': 'true'},
                            ))
                    else:
                        allowed = {'action', 'source', 'rev', 'site', 'cat', 'pg', 'flt', 'pick'}
                        if not {'action', 'source', 'rev', 'site', 'cat'} <= set(params) or set(params) - allowed:
                            raise LibraryError('INVALID_VALUE')
                        cat_meta = tstore.get_category_meta(source.id, generation, site_hash, params['cat'])
                        raw_cat = cat_meta['type_id']
                        facets = cat_meta['facets']
                        if facets is None:
                            facets = list(_filter_options(client.home(), raw_cat))
                        active_filters = (
                            tstore.get_filter(source.id, generation, site_hash, raw_cat, params['flt'])
                            if params.get('flt')
                            else {}
                        )
                        pinned = (params['cat'], *([params['flt']] if params.get('flt') else ()))
                        if 'pick' in params:
                            if 'pg' in params:
                                raise LibraryError('INVALID_VALUE')
                            content = 'files'
                            pick_mode = params['pick']
                            if pick_mode == 'all':
                                category_label += ' · 筛选条件'
                                if active_filters:
                                    rows.append(item(
                                        '清除全部筛选',
                                        _route(action='t4_cat', source=source.id, rev=generation, site=site_idx_str, cat=params['cat'], pg='1'),
                                        True,
                                        label2='恢复默认全部结果',
                                    ))
                                for f_idx, (fname, fkey, fvals) in enumerate(facets):
                                    cur_v = active_filters.get(fkey, '')
                                    cur_n = next((n for n, v in fvals if v == cur_v), '全部')
                                    f_route_kw = dict(
                                        action='t4_cat',
                                        source=source.id,
                                        rev=generation,
                                        site=site_idx_str,
                                        cat=params['cat'],
                                        pick=str(f_idx),
                                    )
                                    if params.get('flt'):
                                        f_route_kw['flt'] = params['flt']
                                    rows.append(item(
                                        f'{_clean_label(fname, 80, fkey)}：{_clean_label(cur_n, 80, "全部")}',
                                        _route(**f_route_kw),
                                        True,
                                        label2='选择筛选值',
                                    ))
                            else:
                                if not re.fullmatch(r'[0-9]{1,2}', pick_mode) or int(pick_mode) >= len(facets):
                                    raise LibraryError('INVALID_VALUE')
                                fname, fkey, fvals = facets[int(pick_mode)]
                                category_label += f' · 筛选：{_clean_label(fname, 80, fkey)}'
                                cur_v = active_filters.get(fkey, '')
                                for opt_n, opt_v in fvals:
                                    next_f = dict(active_filters)
                                    if opt_v == '':
                                        next_f.pop(fkey, None)
                                    else:
                                        next_f[fkey] = opt_v
                                    opt_kw = dict(
                                        action='t4_cat',
                                        source=source.id,
                                        rev=generation,
                                        site=site_idx_str,
                                        cat=params['cat'],
                                        pg='1',
                                    )
                                    if next_f:
                                        opt_kw['flt'] = tstore.put_filter(
                                            source.id,
                                            generation,
                                            site_hash,
                                            raw_cat,
                                            next_f,
                                            pinned_tokens=pinned,
                                        )
                                    selected_mark = '✓ ' if opt_v == cur_v else ''
                                    rows.append(item(
                                        selected_mark + _clean_label(opt_n, 120, opt_v or '全部'),
                                        _route(**opt_kw),
                                        True,
                                        label2='当前已选' if opt_v == cur_v else '',
                                    ))
                        else:
                            page = _positive_int(params.get('pg', '1'), 10000)
                            data = client.category(raw_cat, page, active_filters or None)
                            if cat_meta['name']:
                                category_label += f" · {_clean_label(cat_meta['name'], 80)}"
                            if facets:
                                summary_parts = []
                                for fname, fkey, fvals in facets:
                                    if fkey in active_filters:
                                        vn = next((n for n, v in fvals if v == active_filters[fkey]), active_filters[fkey])
                                        summary_parts.append(_clean_label(vn, 40))
                                flt_kw = dict(
                                    action='t4_cat',
                                    source=source.id,
                                    rev=generation,
                                    site=site_idx_str,
                                    cat=params['cat'],
                                    pick='all',
                                )
                                if params.get('flt'):
                                    flt_kw['flt'] = params['flt']
                                rows.append(item(
                                    '筛选条件' + (f"（{' · '.join(summary_parts)}）" if summary_parts else ''),
                                    _route(**flt_kw),
                                    True,
                                    label2='按条件过滤当前分类',
                                    properties={'Bobbi.FilterEntry': 'true'},
                                ))
                            _render_cards(tstore, _vod_cards(data, 'list'), pinned=pinned)
                            try:
                                last_pg = int(data.get('pagecount', page))
                            except (TypeError, ValueError):
                                last_pg = page
                            base_pg_kw = dict(
                                action='t4_cat',
                                source=source.id,
                                rev=generation,
                                site=site_idx_str,
                                cat=params['cat'],
                            )
                            if params.get('flt'):
                                base_pg_kw['flt'] = params['flt']
                            if page > 1:
                                rows.append(item(
                                    '上一页',
                                    _route(**base_pg_kw, pg=str(page - 1)),
                                    True,
                                    properties={'Bobbi.PrevPage': 'true'},
                                ))
                            if page < min(10000, last_pg):
                                rows.append(item(
                                    '下一页',
                                    _route(**base_pg_kw, pg=str(page + 1)),
                                    True,
                                    properties={'Bobbi.NextPage': 'true'},
                                ))

                elif action == 't4_detail':
                    allowed_detail = {'action', 'source', 'rev', 'site', 'tok', 'ln', 'pg'}
                    if not {'action', 'source', 'rev', 'site', 'tok'} <= set(params) or set(params) - allowed_detail:
                        raise LibraryError('INVALID_VALUE')
                    raw_vid = tstore.get_item(source.id, generation, site_hash, params['tok'])
                    detail = client.detail_record(raw_vid)
                    vtitle = _clean_label(detail['title'], 240, site['name'])
                    plot = _clean_label(detail.get('plot', ''), 4096)
                    poster = detail.get('poster', '')
                    lines = detail['lines']
                    total_eps = sum(len(eps) for _, eps in lines)
                    multi_line = len(lines) > 1
                    category_label = vtitle

                    def _append_episode_batch(batch_specs):
                        # batch_specs: list of (line_name, ep_id, full_title, disp, label2_text, ep_num)
                        ptoks = tstore.put_play_batch(
                            source.id,
                            generation,
                            site_hash,
                            params['tok'],
                            raw_vid,
                            [(ln_n, ep_i, f_title) for ln_n, ep_i, f_title, _, _, _ in batch_specs],
                            pinned_tokens=(params['tok'],),
                        )
                        for (_ln_n, _ep_i, _f_title, disp, lbl2, ep_num), ptok in zip(batch_specs, ptoks):
                            info = {
                                'title': disp,
                                'tvshowtitle': vtitle,
                                'mediatype': 'episode',
                                'episode': ep_num,
                            }
                            if plot:
                                info['plot'] = plot
                            li_row = item(
                                disp,
                                _route(action='t4_play', source=source.id, rev=generation, site=site_idx_str, ptok=ptok),
                                False,
                                label2=lbl2,
                                info=info,
                                playable=True,
                            )
                            if poster:
                                li_row[1].setArt({'poster': poster, 'thumb': poster})
                            rows.append(li_row)

                    if 'ln' not in params and 'pg' not in params and total_eps <= DETAIL_PAGE_SIZE:
                        content = 'episodes'
                        batch_specs = []
                        for line_name, episodes in lines:
                            clean_line = _clean_label(line_name, 80, '线路')
                            for idx, (ep_label, ep_id) in enumerate(episodes, start=1):
                                clean_ep = _clean_label(ep_label, 160, f'第 {idx} 集')
                                disp = f'{clean_line} · {clean_ep}' if multi_line else clean_ep
                                batch_specs.append((
                                    line_name,
                                    ep_id,
                                    f'{vtitle} · {clean_ep}',
                                    disp,
                                    clean_line if multi_line else detail.get('remarks', ''),
                                    idx,
                                ))
                        _append_episode_batch(batch_specs)
                    elif 'ln' not in params and multi_line:
                        if 'pg' in params:
                            raise LibraryError('INVALID_VALUE')
                        content = 'files'
                        for l_idx, (line_name, episodes) in enumerate(lines):
                            clean_line = _clean_label(line_name, 80, f'线路 {l_idx + 1}')
                            rows.append(item(
                                f'{clean_line}（共 {len(episodes)} 集）',
                                _route(
                                    action='t4_detail',
                                    source=source.id,
                                    rev=generation,
                                    site=site_idx_str,
                                    tok=params['tok'],
                                    ln=str(l_idx),
                                    pg='1',
                                ),
                                True,
                                label2=f'分页选集（每页 {DETAIL_PAGE_SIZE} 集）',
                            ))
                    else:
                        content = 'episodes'
                        if 'ln' in params:
                            if not re.fullmatch(r'[0-9]{1,3}', params['ln']) or int(params['ln']) >= len(lines):
                                raise LibraryError('INVALID_VALUE')
                            l_idx = int(params['ln'])
                        else:
                            l_idx = 0
                        page = _positive_int(params.get('pg', '1'), 1000)
                        line_name, episodes = lines[l_idx]
                        clean_line = _clean_label(line_name, 80, '线路')
                        start = (page - 1) * DETAIL_PAGE_SIZE
                        if start >= len(episodes) and episodes:
                            raise LibraryError('INVALID_VALUE')
                        end = min(page * DETAIL_PAGE_SIZE, len(episodes))
                        total_pages = max(1, (len(episodes) + DETAIL_PAGE_SIZE - 1) // DETAIL_PAGE_SIZE)
                        category_label = f'{vtitle} · {clean_line}（第 {page}/{total_pages} 页）'
                        batch_specs = []
                        for idx in range(start + 1, end + 1):
                            ep_label, ep_id = episodes[idx - 1]
                            clean_ep = _clean_label(ep_label, 160, f'第 {idx} 集')
                            disp = f'{clean_line} · {clean_ep}' if multi_line else clean_ep
                            batch_specs.append((
                                line_name,
                                ep_id,
                                f'{vtitle} · {clean_ep}',
                                disp,
                                clean_line if multi_line else detail.get('remarks', ''),
                                idx,
                            ))
                        _append_episode_batch(batch_specs)
                        nav_base = dict(
                            action='t4_detail',
                            source=source.id,
                            rev=generation,
                            site=site_idx_str,
                            tok=params['tok'],
                        )
                        if 'ln' in params or multi_line:
                            nav_base['ln'] = str(l_idx)
                        if page > 1:
                            rows.append(item(
                                '上一页',
                                _route(**nav_base, pg=str(page - 1)),
                                True,
                                properties={'Bobbi.PrevPage': 'true'},
                            ))
                        if end < len(episodes):
                            rows.append(item(
                                '下一页',
                                _route(**nav_base, pg=str(page + 1)),
                                True,
                                properties={'Bobbi.NextPage': 'true'},
                            ))
                else:
                    raise LibraryError('INVALID_VALUE')
        except LibraryError as tok_err:
            if tok_err.code != 'T4_TOKEN_EXPIRED' or action not in ('t4_cat', 't4_detail'):
                raise
            # Same-generation expired directory token provides an explicit refresh path back to site home (A08-03).
            content = 'files'
            rows = [
                item(
                    '页面令牌已过期 · 返回站点首页刷新',
                    _route(action='t4_site', source=source.id, rev=generation, site=site_idx_str),
                    True,
                    label2='重新获取最新目录令牌',
                    properties={'Bobbi.ExpiredRefresh': 'true'},
                )
            ]

        require_current()
        xbmcplugin.setPluginCategory(handle, category_label)
        xbmcplugin.setContent(handle, content)
        xbmcplugin.addDirectoryItems(handle, rows, len(rows))
        finish(True)
    except SelectionChanged:
        finish(False)
    finally:
        finish(False)
