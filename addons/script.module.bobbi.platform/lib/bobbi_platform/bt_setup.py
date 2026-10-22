"""Read-only setup view of the cinema's existing optional torrent adapter.

No persisted setup state, service startup, torrent operation or pairing copy.
The adapter is loaded lazily from its own installed package, without adding an
optional addon or its entrypoint to the setup script's startup dependencies.
"""
from pathlib import Path

ADAPTER_ID = 'plugin.video.bobbi.torrent'


class _CheckCancelled(Exception):
    pass


def _backend_module():
    import importlib.util
    import sys
    import xbmcaddon
    import xbmcvfs

    addon = xbmcaddon.Addon(ADAPTER_ID)
    root = Path(xbmcvfs.translatePath(addon.getAddonInfo('path')))
    if not root.is_absolute():
        raise ValueError('Adapter path unavailable')
    package = root/'lib/bobbi_torrent'
    namespace = '_bobbi_setup_existing_torrent'
    missing = object()
    previous = {name: sys.modules.get(name, missing) for name in
                (namespace, namespace+'.backend', namespace+'.http_io')}
    try:
        # Only the addon ID, backend and its inert IO guard are loaded. Do not run the
        # plugin entry, resolver, player owner or an engine installer.
        spec = importlib.util.spec_from_file_location(namespace, package/'__init__.py',
                                                     submodule_search_locations=[str(package)])
        parent = importlib.util.module_from_spec(spec)
        sys.modules[namespace] = parent
        spec.loader.exec_module(parent)
        spec = importlib.util.spec_from_file_location(namespace+'.backend', package/'backend.py')
        backend = importlib.util.module_from_spec(spec)
        sys.modules[namespace+'.backend'] = backend
        spec.loader.exec_module(backend)
        return backend
    finally:
        for name, value in previous.items():
            if value is missing:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def adapter_status(translate, cancelled=lambda: False):
    """Return one existing-adapter state, or None to use the legacy helper UI."""
    try:
        path = Path(translate('special://profile/addon_data/'+ADAPTER_ID+'/backend.json'))
        if not path.is_absolute():
            return 'adapter_unavailable'
        if not path.exists() and not path.is_symlink():
            return None
        backend = _backend_module()
    except (ImportError, AttributeError, OSError, RuntimeError, ValueError):
        return 'adapter_unavailable'
    try:
        config = backend.load_config(path)
    except backend.BackendError as error:
        return None if error.code == 'TORRENT_BACKEND_NOT_CONFIGURED' else 'adapter_invalid'
    except (OSError, ValueError):
        return 'adapter_invalid'
    client = None
    def active():
        if cancelled():
            raise _CheckCancelled()
    try:
        active()
        client = backend.Backend(config)
        # The adapter's bounded ready() performs only GET /echo and validates
        # exactly the same supported engine versions used by cinema playback.
        client.ready(active)
        return 'adapter_ready'
    except _CheckCancelled:
        return 'adapter_configured'
    except backend.BackendError:
        return 'adapter_offline'
    except (ImportError, OSError, RuntimeError, ValueError):
        return 'adapter_unavailable'
    finally:
        if client is not None:
            try:
                client.close()
            except (OSError, RuntimeError):
                pass


def adapter_message(state):
    return {
        'adapter_ready': '影院已接入现有 BT 后台，连接检查通过。\n'
                         '无需重新配对或安装其他后台；实际播放效果仍需试播检验。',
        'adapter_offline': '影院已有 BT 接入，本次连接检查未通过。\n'
                           '请检查现有后台的运行状态后重试。已有接入保持不变，无需另装后台。',
        'adapter_invalid': '影院已有 BT 配置，但当前无法验证这份配置。\n'
                           '本次未更改现有接入，也不会安装另一个后台。',
        'adapter_unavailable': '影院已有 BT 配置，当前接入组件暂不可用。\n'
                               '本次未更改现有接入，也不会安装另一个后台。',
        'adapter_configured': '影院已有 BT 接入，本次未完成连接检查。\n'
                              '已有接入保持不变，无需重新配对或安装其他后台。',
    }.get(state, '现有 BT 接入需要检查。本次没有更改配置。')
