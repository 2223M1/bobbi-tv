from lib.gui.qr_progress_dialog import QRProgressDialog
from lib.services.webserver import StremioWebServer, get_local_ip
from lib.utils.debrid.qrcode_utils import make_qrcode
from lib.utils.kodi.utils import ADDON_PATH, kodilog, translation

_SERVER_PORT = 8081


def catalog_manage_phone(expected):
    """Explicit optional TV approval; close QR dialog to revoke the session."""
    import xbmcgui
    from lib.services.phone_management import PhoneManagement, SCOPES
    dialog = xbmcgui.Dialog()
    mounted = expected.get('reference_kind') == 'mounted_path'
    description = ('仅授权此已登记本地来源及其 namespace，不授权其他挂载或网盘账号。\n'
                   '来源：%s\n范围：%s\n' % (expected['source_id'], expected['namespace'])) if mounted else '仅授权当前原生网盘账号。\n'
    if not dialog.yesno('允许手机管理当前片库？',
            description + '仅在可信局域网使用。扫码者可查看所选片库的本地索引、整理作品和取消扫描，不能播放或读取网盘登录。'
            '授权最多 15 分钟，关闭此二维码窗口立即撤销；后台扫描不会被取消。'):
        return False
    # Local/mounted grants identify a catalog namespace, not a playback account.
    # Do not advertise a command scope that the existing owner cannot execute.
    permission = 0 if mounted else dialog.select('手机权限（仅本次授权）', ['仅整理片库', '片库 + 查看当前播放', '片库 + 查看并控制当前播放'])
    if permission < 0:
        return False
    scopes = SCOPES | (frozenset(('playback_read',)) if permission >= 1 else frozenset())
    if permission == 2:
        if not dialog.yesno('允许手机控制当前播放？',
                '扫码者可查看当前音轨和字幕，并拖动进度、切换音轨或字幕。仅对当前授权账号的已确认播放生效；'
                '旧内核不支持时不会开放控制。关闭二维码窗口立即撤销。'):
            return False
        scopes |= frozenset(('playback_control',))
    origin = 'http://%s:%d' % (get_local_ip(), _SERVER_PORT)
    manager = PhoneManagement(expected, origin, scopes=scopes)
    server = StremioWebServer(port=_SERVER_PORT, phone_management=manager)
    server.start()
    if not server.is_running:
        manager.revoke()
        dialog.ok('手机管理暂不可用', '端口可能已被使用，请关闭原手机管理窗口后重试。')
        return False
    try:
        # Fragment never reaches HTTP access logs. Do not log pairing URL.
        qr_path = make_qrcode(manager.pairing_url)
        qr = QRProgressDialog('qr_dialog.xml', ADDON_PATH)
        qr.setup(title='手机片库管理 · 关闭即撤销', qr_code=qr_path or '',
                 url=manager.pairing_url, user_code='', is_debrid=False, url_label_id=90670)
        qr.doModal()
        return True
    finally:
        server.stop()


def stremio_manage_phone(params):
    local_ip = get_local_ip()
    url = f"http://{local_ip}:{_SERVER_PORT}/"

    server = StremioWebServer(port=_SERVER_PORT)
    server.start()

    if not server.is_running:
        from lib.utils.kodi.utils import notification

        notification(translation(90560))
        return

    try:
        kodilog(f"Server started at {url}")

        # Generate QR code image
        qr_path = make_qrcode(url)

        # Show blocking QR dialog
        dialog = QRProgressDialog("qr_dialog.xml", ADDON_PATH)
        dialog.setup(
            title=translation(90162),
            qr_code=qr_path or "",
            url=url,
            user_code="",
            is_debrid=False,
            url_label_id=90670,
        )
        dialog.doModal()
    finally:
        server.stop()
        kodilog("Server stopped")
