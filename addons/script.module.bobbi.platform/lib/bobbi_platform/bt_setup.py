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


def _configured(translate):
    """Existence/validation is local; it never constructs a network client."""
    try:
        path = Path(translate('special://profile/addon_data/'+ADAPTER_ID+'/backend.json'))
        if not path.is_absolute():
            return 'adapter_unavailable', None, None
        if not path.exists() and not path.is_symlink():
            return None, None, None
        backend = _backend_module()
    except (ImportError, AttributeError, OSError, RuntimeError, ValueError):
        return 'adapter_unavailable', None, None
    try:
        config = backend.load_config(path)
    except backend.BackendError as error:
        return (None if error.code == 'TORRENT_BACKEND_NOT_CONFIGURED' else 'adapter_invalid'), None, None
    except (OSError, ValueError):
        return 'adapter_invalid', None, None
    return 'adapter_configured', backend, config


def adapter_state(translate):
    """First-paint and mutation guards must not wait on optional BT connectivity."""
    return _configured(translate)[0]


def helper_state(translate, pairing_path):
    state = adapter_state(translate)
    if state is not None:
        return state
    from .pairing import load
    try:
        return 'paired' if load(pairing_path) is not None else 'not_paired'
    except (ValueError, OSError):
        return 'invalid'


def adapter_status(translate, cancelled=lambda: False):
    """Explicit read-only connection check, separate from configured ownership."""
    state, backend, config = _configured(translate)
    if backend is None:
        return state
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
        'adapter_ready': '已连接现有 BT 后台，可以选择片源试播，无需重新安装。',
        'adapter_offline': '无法连接现有 BT 后台，请确认它已启动后重试，无需另装后台。',
        'adapter_invalid': '已有 BT 配置无法读取，请检查配置。原设置保留。',
        'adapter_unavailable': 'BT 组件暂不可用，请重启 Kodi 后再试。原设置保留。',
        'adapter_configured': '已保存 BT 配置，尚未检查连接，无需重新配对。',
    }.get(state, 'BT 连接需要检查，原设置保留。')
