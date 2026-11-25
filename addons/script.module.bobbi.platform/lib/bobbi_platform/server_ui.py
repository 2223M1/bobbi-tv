"""Media-server connection UI, intentionally separate from cloud QR/CD2."""
from .pan_accounts import SERVER_PROVIDERS, PanError
from .runtime import call


def add(dialog, store, previous=None):
    import xbmcgui
    from .pan_ui import _failure
    if previous is None:
        choice = dialog.select('媒体服务器 · 实验接入', [name for _, name in SERVER_PROVIDERS])
        if not 0 <= choice < len(SERVER_PROVIDERS):
            return False
        provider, label = SERVER_PROVIDERS[choice]
        existing = [source for source in store.sources() if source.kind == 'media_server'
                    and source.metadata['provider'] == provider]
        if existing and provider != 'emby':
            if len(existing) != 1 or not dialog.yesno('此类型已有连接', '首期每类支持一个连接。要明确更新当前连接吗？'):
                return False
            previous = existing[0]
    else:
        provider = previous.metadata['provider']
        label = dict(SERVER_PROVIDERS)[provider]
    name = dialog.input('服务器显示名称', defaultt=previous.name if previous else label)
    if not name:
        return False
    body = dict(provider=provider, name=name, expected_source=previous.id if previous else None)
    if provider == 'plex':
        if not dialog.yesno('使用已有 Plex 登录',
                '请先在原 Plex 设置中登录并选择服务器，然后重启插件服务。现在核验并登记该服务器？'
                '\n不另存 token；首次核验需要连接 plex.tv。'):
            return False
    else:
        location = dialog.input(label + ' HTTP(S) 地址（可含服务前缀）',
                                defaultt=previous.location if previous else 'http://')
        if not location:
            return False
        mode = dialog.select('Emby 登录方式', ['用户名和密码', '高级：导入用户令牌']) if provider == 'emby' else 1
        if mode == 0:
            username = dialog.input('Emby 用户名')
            if not username:
                return False
            password = dialog.input('Emby 密码（无密码账户可留空）', option=xbmcgui.ALPHANUM_HIDE_INPUT)
            body.update(location=location, username=username, password=password)
        elif mode == 1:
            secret = dialog.input('当前用户访问令牌（不是管理员全局 API key）', option=xbmcgui.ALPHANUM_HIDE_INPUT)
            if not secret:
                return False
            body.update(location=location, secret=secret)
        else:
            return False
        warn = '\nHTTP 没有加密，请只在可信局域网使用。' if location.lower().startswith('http://') else ''
        switch = ('\n保存后切换到此连接。私服原片由 Kodi 自动使用当前账号播放，'
                  '可信遥控器和 Kodi 调试日志可能读到令牌，请勿分享原始日志。') if provider == 'emby' else ''
        if not dialog.yesno('核验并保存服务器？', '仅向填写的服务器验证；本机保存用户令牌，不保存密码。' + warn + switch):
            return False
    try:
        # Bounded request, no background registration continuing after a
        # purported cancellation. The Host verifies IDs before its CAS save.
        call('pan_server_register', body, timeout=28)
    except (OSError, ValueError, RuntimeError) as error:
        note = ('原连接保留。要连接另一个服务器或用户，请选择“添加服务器”。' if provider == 'emby'
                else '原连接保留。不同服务器或用户请先明确移除旧连接。')
        dialog.ok('服务器未保存', _failure(error) + '\n' + note)
        return False
    if provider == 'emby':
        dialog.ok('Emby 已连接', '打开“我的片库”即可浏览在线海报、电影和季集，无需扫描。可用的原片直链由 Kodi 播放。')
        return True
    dialog.ok('服务器已登记 · 待实机验证', '可立即浏览服务器并播放；需要本地整理时再选择“将此目录加入片库”。'
              '\n仅原文件从头直放，历史进度仅供查看，不自动续播；HLS、转码与分卷串联尚未开放。')
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
        dialog.ok('服务器连接未就绪', '请重新验证连接；Plex 设置变更后须重启服务再登记。')
        return False
    return open_directory(rows[0], dialog)


def activate_emby_account(dialog, store, source):
    """Switch the default browsing Emby account via existing CAS Host authority."""
    from .pan_ui import _failure, _status
    active, _ = store.emby_binding()
    if active is not None and active.id == source.id:
        dialog.ok('当前浏览账号', '“' + source.name + '”已是首页与默认片库的当前浏览账号。')
        return False
    try:
        target, generation = store.source_snapshot(source.id)
    except Exception as error:
        from .library_ui import message
        dialog.ok('未能切换账号', message(error))
        return False
    if target.kind != 'media_server' or target.metadata.get('provider') != 'emby':
        dialog.ok('未能切换账号', '此连接已变更，请返回刷新后再试。')
        return False
    try:
        rows = [row for row in _status(servers=True) if row['provider'] == 'emby']
        if len(rows) != 1:
            raise PanError('PAN_STATUS_INVALID')
        expected = rows[0]['account']
        if (expected.get('authenticated') and expected.get('source_id') == target.id
                and expected.get('generation') == generation):
            dialog.ok('当前浏览账号', '“' + target.name + '”已是当前浏览账号。')
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
            dialog.ok('已切换当前浏览账号', '核对确认当前浏览账号已切换为“' + target.name + '”。')
            return True
        current_label = ('当前仍为“' + current_active.name + '”。' if current_active is not None
                         else '当前没有启用的默认 Emby 浏览账号。')
        dialog.ok('未确认切换结果', _failure(error) + '\n' + current_label)
        return False
    dialog.ok('已切换当前浏览账号', '首页与默认片库已切换到“' + target.name + '”，正在播放的影片不受影响。')
    return True


def manage(dialog, store, source):
    is_emby = source.metadata.get('provider') == 'emby'
    active_emby = store.emby_binding()[0] if is_emby else None
    is_active_emby = is_emby and active_emby is not None and active_emby.id == source.id
    options = [
        '浏览在线片库' if is_emby else '浏览与选择扫描目录',
        '重新核验 / 更新连接',
        '移除服务器连接',
    ]
    if is_emby:
        uid = source.metadata.get('user_id', '')
        suffix = (' · 用户 ' + uid[:16]) if isinstance(uid, str) and uid else ''
        options.append(('当前浏览账号 · 已启用' if is_active_emby else '设为当前浏览账号') + suffix)
    heading = source.name + (' · 当前浏览账号' if is_active_emby else '') + ' · 媒体服务器'
    choice = dialog.select(heading, options)
    if choice == 0:
        return browse(dialog, source)
    if choice == 1:
        return add(dialog, store, source)
    if choice == 2 and dialog.yesno('移除服务器连接？', '移除本机连接并撤销相关播放权限；索引整理与历史保留，服务器媒体不变。'):
        store.remove(source.id)
        return True
    if is_emby and choice == 3:
        return activate_emby_account(dialog, store, source)
    return False
