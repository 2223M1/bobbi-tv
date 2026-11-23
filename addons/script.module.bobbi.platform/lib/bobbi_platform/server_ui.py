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
        if existing:
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
        secret = dialog.input('当前用户访问令牌（不是管理员全局 API key）', option=xbmcgui.ALPHANUM_HIDE_INPUT)
        if not secret:
            return False
        body.update(location=location, secret=secret)
        if not dialog.yesno('核验并保存服务器？', '仅向填写的服务器发送令牌，保存在本机私有来源中。媒体文件不会改变。'):
            return False
    try:
        # Bounded request, no background registration continuing after a
        # purported cancellation. The Host verifies IDs before its CAS save.
        call('pan_server_register', body, timeout=28)
    except (OSError, ValueError, RuntimeError) as error:
        dialog.ok('服务器未保存', _failure(error) + '\n原连接保留。不同服务器或用户请先明确移除旧连接。')
        return False
    dialog.ok('服务器已登记 · 待实机验证', '打开服务器目录，选择“将此目录加入片库”后扫描。'
              '\n仅原文件从头直放，历史进度仅供查看，不自动续播；HLS、转码与分卷串联尚未开放。')
    return True


def browse(dialog, source):
    from .pan_ui import _status, browse as open_directory
    rows = [row for row in _status(servers=True) if row['provider'] == source.metadata['provider']]
    if len(rows) != 1 or rows[0]['account'].get('source_id') != source.id:
        dialog.ok('服务器连接未就绪', '请重新验证连接；Plex 设置变更后须重启服务再登记。')
        return False
    return open_directory(rows[0], dialog)


def manage(dialog, store, source):
    choice = dialog.select(source.name + ' · 媒体服务器',
        ['浏览与选择扫描目录', '重新核验 / 更新连接', '移除服务器连接'])
    if choice == 0:
        return browse(dialog, source)
    if choice == 1:
        return add(dialog, store, source)
    if choice == 2 and dialog.yesno('移除服务器连接？', '移除本机连接并撤销相关播放权限；索引整理与历史保留，服务器媒体不变。'):
        store.remove(source.id)
        return True
    return False
