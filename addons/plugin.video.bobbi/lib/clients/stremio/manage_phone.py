from bobbi_core.typed_ref import KINDS as PATH_KINDS
from lib.gui.qr_progress_dialog import QRProgressDialog
from lib.services.webserver import StremioWebServer, get_local_ip
from lib.utils.debrid.qrcode_utils import make_qrcode
from lib.utils.kodi.utils import ADDON_PATH, kodilog, translation

_SERVER_PORT = 8081


def _tr(po_id, zh_text):
    val = translation(po_id)
    return val if isinstance(val, str) and val else zh_text


def catalog_manage_phone(expected):
    """Explicit optional TV approval; close QR dialog to revoke the session."""
    import xbmcgui
    from lib.services.phone_management import PhoneManagement, SCOPES
    dialog = xbmcgui.Dialog()
    mounted = expected.get('reference_kind') in PATH_KINDS
    description = (
        _tr(91269, '仅授权此已登记本地来源及其 namespace，不授权其他挂载或网盘账号。\n来源：%s\n范围：%s\n')
        % (expected['source_id'], expected['namespace'])
    ) if mounted else _tr(91270, '仅授权当前原生网盘账号。\n')
    if not dialog.yesno(
        _tr(91271, '允许手机管理当前片库？'),
        description + _tr(
            91272,
            '仅在可信局域网使用。扫码者可查看所选片库的本地索引、整理作品和取消扫描，不能播放或读取网盘登录。'
            '授权最多 15 分钟，关闭此二维码窗口立即撤销；后台扫描不会被取消。',
        ),
    ):
        return False
    # Local/mounted grants identify a catalog namespace, not a playback account.
    # Do not advertise a command scope that the existing owner cannot execute.
    permission = 0 if mounted else dialog.select(
        _tr(91273, '手机权限（仅本次授权）'),
        [
            _tr(91274, '仅整理片库'),
            _tr(91275, '片库 + 查看当前播放'),
            _tr(91276, '片库 + 查看并控制当前播放'),
        ],
    )
    if permission < 0:
        return False
    scopes = SCOPES | (frozenset(('playback_read',)) if permission >= 1 else frozenset())
    if permission == 2:
        if not dialog.yesno(
            _tr(91277, '允许手机控制当前播放？'),
            _tr(
                91278,
                '扫码者可查看当前音轨和字幕，并拖动进度、切换音轨或字幕。仅对当前授权账号的已确认播放生效；'
                '旧内核不支持时不会开放控制。关闭二维码窗口立即撤销。',
            ),
        ):
            return False
        scopes |= frozenset(('playback_control',))
    origin = 'http://%s:%d' % (get_local_ip(), _SERVER_PORT)
    manager = PhoneManagement(expected, origin, scopes=scopes)
    server = StremioWebServer(port=_SERVER_PORT, phone_management=manager)
    server.start()
    if not server.is_running:
        manager.revoke()
        dialog.ok(
            _tr(91279, '手机管理暂不可用'),
            _tr(91280, '端口可能已被使用，请关闭原手机管理窗口后重试。'),
        )
        return False
    try:
        # Fragment never reaches HTTP access logs. Do not log pairing URL.
        qr_path = make_qrcode(manager.pairing_url)
        qr = QRProgressDialog('qr_dialog.xml', ADDON_PATH)
        qr.setup(title=_tr(91281, '手机片库管理 · 关闭即撤销'), qr_code=qr_path or '',
                 url=manager.pairing_url, user_code='', is_debrid=False, url_label_id=90670)
        qr.doModal()
        return True
    finally:
        server.stop()


def stremio_manage_phone(params):
    import xbmcgui
    from lib.services.phone_management import PhoneManagement, STREMIO_SCOPES
    from lib.utils.kodi.utils import notification

    dialog = xbmcgui.Dialog()
    if not dialog.yesno(
        _tr(91282, '允许手机管理 Stremio 插件源？'),
        _tr(
            91283,
            '仅在可信局域网使用。扫码者可在当前配置下查看、添加、启用/停用或移除自定义 Stremio 插件源，不会回显已保存 URL 中的完整凭据。'
            '授权最多 15 分钟，关闭此二维码窗口立即撤销。',
        ),
    ):
        return False

    origin = 'http://%s:%d' % (get_local_ip(), _SERVER_PORT)
    manager = PhoneManagement({'local_scope': 'stremio_addons'}, origin, scopes=STREMIO_SCOPES)
    server = StremioWebServer(port=_SERVER_PORT, phone_management=manager)
    server.start()

    if not server.is_running:
        manager.revoke()
        notification(translation(90560))
        return False

    try:
        qr_path = make_qrcode(manager.pairing_url)
        qr = QRProgressDialog('qr_dialog.xml', ADDON_PATH)
        qr.setup(
            title=translation(90162),
            qr_code=qr_path or '',
            url=manager.pairing_url,
            user_code='',
            is_debrid=False,
            url_label_id=90670,
        )
        qr.doModal()
        return True
    finally:
        server.stop()
        kodilog('Paired Stremio phone management stopped')


def source_import_manage_phone(params):
    """Paired phone chunked upload for TVBox / T4 JSON configs with TV-side final confirmation (R19)."""
    from urllib.parse import urlsplit
    import xbmc
    import xbmcgui
    import xbmcvfs
    from bobbi_core import t4
    from bobbi_platform import library_ui, server_ui
    from bobbi_platform.paths import ProfileBinding
    from lib.services.phone_management import PhoneManagement, SOURCE_IMPORT_SCOPES

    dialog = xbmcgui.Dialog()
    if not dialog.yesno(
        _tr(91284, '允许手机扫码上传配置文件？'),
        _tr(
            91285,
            '仅在可信局域网使用。扫码者可分片上传一份最多 2 MB 的 JSON 配置文件进行诊断；'
            '写入片库前仍须在电视上确认。关闭此二维码窗口立即撤销授权并清理临时分片。',
        ),
    ):
        return False

    binding = ProfileBinding()
    origin = 'http://%s:%d' % (get_local_ip(), _SERVER_PORT)
    manager = PhoneManagement(
        {'local_scope': 'source_import'},
        origin,
        scopes=SOURCE_IMPORT_SCOPES,
        profile_binding=binding,
    )
    server = StremioWebServer(port=_SERVER_PORT, phone_management=manager)
    server.start()
    if not server.is_running:
        manager.revoke()
        dialog.ok(
            _tr(91286, '手机上传暂不可用'),
            _tr(91280, '端口可能已被使用，请关闭原手机管理窗口后重试。'),
        )
        return False

    try:
        qr_path = make_qrcode(manager.pairing_url)
        qr = QRProgressDialog('qr_dialog.xml', ADDON_PATH)
        qr.setup(
            title=_tr(91287, '手机上传配置 · 上传完成后按返回确认'),
            qr_code=qr_path or '',
            url=manager.pairing_url,
            user_code='',
            is_debrid=False,
            url_label_id=90670,
        )
        qr.doModal()
    finally:
        server.stop()
        kodilog('Paired source_import phone session stopped')

    committed = manager.committed_import
    if not committed:
        return False

    diag = committed['diagnosis']
    if not diag.get('can_save_t4') or not committed.get('raw_bytes'):
        dialog.ok(
            _tr(91288, '配置文件诊断（未修改片库）'),
            diag.get('summary_zh') or _tr(91289, '没有可用的 type-4 站点。'),
        )
        if (diag.get('counts') or {}).get('type3', 0) > 0:
            nxt = dialog.select(
                _tr(91290, '后续操作建议'),
                [
                    _tr(91291, '暂不添加（保持原片库不变）'),
                    _tr(91292, '改连原生 WebDAV / AList 网盘'),
                    _tr(91293, '改连原生 Emby / Jellyfin 媒体服'),
                ],
            )
            if nxt in (1, 2):
                store = library_ui.registry(xbmcvfs.translatePath)
                try:
                    if nxt == 1:
                        src = library_ui._network(dialog, 'webdav')
                        if src is not None and dialog.yesno(
                                _tr(91294, '添加“%s”') % src.name,
                                _tr(91295, '%s\n仅保存到本机。') % src.location):
                            store.save(src)
                            xbmc.executebuiltin('Container.Refresh')
                            return True
                    else:
                        if server_ui.add(dialog, store):
                            xbmc.executebuiltin('Container.Refresh')
                            return True
                finally:
                    store.close()
        return False

    binding.require_current()
    base_url = committed.get('base_url') or ''
    parsed = t4.preview(committed['raw_bytes'], base_url)
    origins = sorted({urlsplit(s['api']).scheme + '://' + urlsplit(s['api']).netloc for s in parsed.sites})
    summary = diag.get('summary_zh') or (_tr(91296, '可用 %d 个站点') % len(parsed.sites))
    if not dialog.yesno(
        _tr(91297, '确认导入手机上传的 T4 站点？'),
        _tr(91298, '%s\n允许按需连接：\n%s') % (summary, '\n'.join(origins)),
    ):
        return False

    store = library_ui.registry(xbmcvfs.translatePath)
    try:
        previous = (
            next((s for s in store.sources() if s.kind == 't4' and s.location == base_url), None)
            if base_url
            else None
        )
        expected = store.source_snapshot(previous.id) if previous else (None, None)
        binding.require_current()
        store.save(parsed.source(base_url, previous), expected_snapshot=expected)
    finally:
        store.close()
    xbmc.executebuiltin('Container.Refresh')
    dialog.ok(_tr(91299, 'T4 站点已保存'), _tr(91550, '打开“我的片库”可按站点浏览与搜索。'))
    return True
