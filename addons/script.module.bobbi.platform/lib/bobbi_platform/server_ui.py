"""Media-server connection UI, intentionally separate from cloud QR/CD2."""
from .pan_accounts import SERVER_PROVIDERS, PanError
from .runtime import call

NAVIGATED = 'NAVIGATED'
CHANGED = 'CHANGED'
CANCELLED = 'CANCELLED'


def add(dialog, store, previous=None):
    import xbmcgui
    from .pan_ui import _failure
    if previous is None:
        choice = dialog.select(_t(32078, '媒体服务器 · 实验接入', 'Media Server · Experimental'), [name for _, name in SERVER_PROVIDERS])
        if not 0 <= choice < len(SERVER_PROVIDERS):
            return False
        provider, label = SERVER_PROVIDERS[choice]
        existing = [source for source in store.sources() if source.kind == 'media_server'
                    and source.metadata['provider'] == provider]
        if existing and provider != 'emby':
            if len(existing) != 1 or not dialog.yesno(_t(None, '此类型已有连接', 'Connection Already Exists'), _t(None, '首期每类支持一个连接。要明确更新当前连接吗？', 'Only one connection of this type is supported. Update the existing connection?')):
                return False
            previous = existing[0]
    else:
        provider = previous.metadata['provider']
        label = dict(SERVER_PROVIDERS)[provider]
    name = dialog.input(_t(32079, '服务器显示名称', 'Server Display Name'), defaultt=previous.name if previous else label)
    if not name:
        return False
    body = dict(provider=provider, name=name, expected_source=previous.id if previous else None)
    if provider == 'plex':
        if not dialog.yesno(_t(None, '使用已有 Plex 登录', 'Use Existing Plex Sign-In'),
                _t(None, '请先在原 Plex 设置中登录并选择服务器，然后重启插件服务。现在核验并登记该服务器？\n不另存 token；首次核验需要连接 plex.tv。',
                   'Sign in and select a server in Plex settings first, then restart the add-on service. Verify and register that server now?\nNo separate token copy is stored; initial verification contacts plex.tv.')):
            return False
    else:
        location = dialog.input(label + _t(None, ' HTTP(S) 地址（可含服务前缀）', ' HTTP(S) URL (optional path prefix)'),
                                defaultt=previous.location if previous else 'http://')
        if not location:
            return False
        mode = dialog.select(_t(None, 'Emby 登录方式', 'Emby Sign-In Method'), [_t(None, '用户名和密码', 'Username & Password'), _t(None, '高级：导入用户令牌', 'Advanced: Import User Token')]) if provider == 'emby' else 1
        if mode == 0:
            username = dialog.input(_t(None, 'Emby 用户名', 'Emby Username'))
            if not username:
                return False
            password = dialog.input(_t(None, 'Emby 密码（无密码账户可留空）', 'Emby Password (leave empty if none)'), option=xbmcgui.ALPHANUM_HIDE_INPUT)
            body.update(location=location, username=username, password=password)
        elif mode == 1:
            secret = dialog.input(_t(None, '当前用户访问令牌（不是管理员全局 API key）', 'User Access Token (not global admin API key)'), option=xbmcgui.ALPHANUM_HIDE_INPUT)
            if not secret:
                return False
            body.update(location=location, secret=secret)
        else:
            return False
        warn = _t(None, '\nHTTP 没有加密，请只在可信局域网使用。', '\nHTTP is unencrypted; use only on a trusted LAN.') if location.lower().startswith('http://') else ''
        switch = (_t(None, '\n保存后切换到此连接。私服原片由 Kodi 自动使用当前账号播放，可信遥控器和 Kodi 调试日志可能读到令牌，请勿分享原始日志。',
                     '\nSwitches to this connection on save. Direct playback uses the active account; trusted remotes and Kodi debug logs may see tokens — never share raw logs.')) if provider == 'emby' else ''
        if not dialog.yesno(_t(32080, '核验并保存服务器？', 'Verify and Save Server?'), _t(None, '仅向填写的服务器验证；本机保存用户令牌，不保存密码。', 'Verifies only with the specified server; stores a user token locally, never your password.') + warn + switch):
            return False
    try:
        # Bounded request, no background registration continuing after a
        # purported cancellation. The Host verifies IDs before its CAS save.
        call('pan_server_register', body, timeout=28)
    except (OSError, ValueError, RuntimeError) as error:
        note = (_t(None, '原连接保留。要连接另一个服务器或用户，请选择“添加服务器”。', 'Previous connection kept. Choose "Add Media Server" to add another server or user.') if provider == 'emby'
                else _t(None, '原连接保留。不同服务器或用户请先明确移除旧连接。', 'Previous connection kept. Remove the old connection explicitly before switching servers or users.'))
        dialog.ok(_t(None, '服务器未保存', 'Server Not Saved'), _failure(error) + '\n' + note)
        return False
    if provider == 'emby':
        dialog.ok(_t(None, 'Emby 已连接', 'Emby Connected'), _t(None, '打开“我的片库”即可浏览在线海报、电影和季集，无需扫描。可用的原片直链由 Kodi 播放。', 'Open "My Library" to browse posters, movies, and episodes online without scanning. Direct streams play in Kodi.'))
        return True
    dialog.ok(_t(None, '服务器已登记 · 待实机验证', 'Server Registered · Experimental'), _t(None, '可立即浏览服务器并播放；需要本地整理时再选择“将此目录加入片库”。\n仅原文件从头直放，历史进度仅供查看，不自动续播；HLS、转码与分卷串联尚未开放。',
              'Browse and play immediately, or add folders to your indexed library later.\nPlays original files from the start (history is reference-only; HLS, transcoding, and multi-part chaining are not enabled).'))
    return True


def browse(dialog, source):
    if source.metadata['provider'] == 'emby':
        from .emby_dynamic import link
        import xbmc
        xbmc.executebuiltin('ActivateWindow(Videos,' + link(action='browse', source=source.id) + ',return)')
        return True
    from .pan_ui import _status, browse as open_directory
    rows = [row for row in _status(servers=True) if row['provider'] == source.metadata['provider']]
    if len(rows) != 1 or rows[0]['account'].get('source_id') != source.id:
        dialog.ok(_t(None, '服务器连接未就绪', 'Server Connection Not Ready'), _t(None, '请重新验证连接；Plex 设置变更后须重启服务再登记。', 'Re-verify the connection; restart the service and re-register after changing Plex settings.'))
        return False
    return open_directory(rows[0], dialog)


def activate_emby_account(dialog, store, source):
    """Switch the default browsing Emby account via existing CAS Host authority."""
    from .pan_ui import _failure, _status
    active, _ = store.emby_binding()
    if active is not None and active.id == source.id:
        dialog.ok(_t(None, '当前浏览账号', 'Active Browsing Account'), _q(source.name) + _t(None, '已是首页与默认片库的当前浏览账号。', ' is already the active browsing account for Home and My Library.'))
        return False
    try:
        target, generation = store.source_snapshot(source.id)
    except Exception as error:
        from .library_ui import message
        dialog.ok(_t(None, '未能切换账号', 'Could Not Switch Account'), message(error))
        return False
    if target.kind != 'media_server' or target.metadata.get('provider') != 'emby':
        dialog.ok(_t(None, '未能切换账号', 'Could Not Switch Account'), _t(None, '此连接已变更，请返回刷新后再试。', 'This connection changed; go back to refresh and try again.'))
        return False
    try:
        rows = [row for row in _status(servers=True) if row['provider'] == 'emby']
        if len(rows) != 1:
            raise PanError('PAN_STATUS_INVALID')
        expected = rows[0]['account']
        if (expected.get('authenticated') and expected.get('source_id') == target.id
                and expected.get('generation') == generation):
            dialog.ok(_t(None, '当前浏览账号', 'Active Browsing Account'), _q(target.name) + _t(None, '已是当前浏览账号。', ' is already the active browsing account.'))
            return False
        call('pan_server_activate_emby', {
            'source_id': target.id,
            'generation': generation,
            'expected': expected,
        }, timeout=8)
    except (ValueError, OSError, RuntimeError, KeyError, TypeError) as error:
        try:
            current_active, _ = store.emby_binding()
        except Exception:
            current_active = None
        if current_active is not None and current_active.id == target.id:
            dialog.ok(_t(None, '已切换当前浏览账号', 'Switched Active Browsing Account'), _t(None, '核对确认当前浏览账号已切换为', 'Confirmed active browsing account switched to ') + _q(target.name) + (_t(None, '。', '.')))
            return True
        current_label = ((_t(None, '当前仍为', 'Still using ') + _q(current_active.name) + _t(None, '。', '.')) if current_active is not None
                         else _t(None, '当前没有启用的默认 Emby 浏览账号。', 'No default Emby browsing account is currently active.'))
        dialog.ok(_t(None, '未确认切换结果', 'Switch Outcome Unconfirmed'), _failure(error) + '\n' + current_label)
        return False
    try:
        import xbmc
        import xbmcgui
        xbmcgui.Window(10000).setProperty('Bobbi.Emby.ActiveSource', target.id)
        xbmc.executebuiltin('Container.Refresh')
    except Exception:
        pass
    dialog.ok(_t(None, '已切换当前浏览账号', 'Switched Active Browsing Account'), _t(None, '首页与默认片库已切换到', 'Home and My Library switched to ') + _q(target.name) + _t(None, '，正在播放的影片不受影响。', '; active playback is unaffected.'))
    return True


def manage(dialog, store, source):
    is_emby = source.metadata.get('provider') == 'emby'
    active_emby = store.emby_binding()[0] if is_emby else None
    is_active_emby = is_emby and active_emby is not None and active_emby.id == source.id
    options = [
        _t(None, '浏览在线片库', 'Browse Online Library') if is_emby else _t(None, '浏览与选择扫描目录', 'Browse & Select Folders to Scan'),
        _t(None, '重新核验 / 更新连接', 'Re-verify / Update Connection'),
        _t(None, '移除服务器连接', 'Remove Server Connection'),
    ]
    if is_emby:
        uid = source.metadata.get('user_id', '')
        suffix = ((_t(None, ' · 用户 ', ' · User ') + uid[:16]) if isinstance(uid, str) and uid else '')
        options.append((_t(None, '当前浏览账号 · 已启用', 'Active Browsing Account · Enabled') if is_active_emby else _t(None, '设为当前浏览账号', 'Set as Active Browsing Account')) + suffix)
    heading = source.name + (_t(None, ' · 当前浏览账号', ' · Active Account') if is_active_emby else '') + _t(None, ' · 媒体服务器', ' · Media Server')
    choice = dialog.select(heading, options)
    if choice == 0:
        return NAVIGATED if browse(dialog, source) else CANCELLED
    if choice == 1:
        return CHANGED if add(dialog, store, source) else CANCELLED
    if choice == 2 and dialog.yesno(_t(None, '移除服务器连接？', 'Remove Server Connection?'), _t(None, '移除本机连接并撤销相关播放权限；索引整理与历史保留，服务器媒体不变。', 'Removes this local connection and revokes its playback scope; organized catalog records, history, and server media are kept.')):
        store.remove(source.id)
        return CHANGED
    if is_emby and choice == 3:
        return CHANGED if activate_emby_account(dialog, store, source) else CANCELLED
    return CANCELLED


def _t(msg_id, zh_text, en_text):
    from .i18n import tr
    return tr(msg_id, zh_text, en_text)


def _q(text):
    from .i18n import is_english
    return f'"{text}"' if is_english() else f'“{text}”'
