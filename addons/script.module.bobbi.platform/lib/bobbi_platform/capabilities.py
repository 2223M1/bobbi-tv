"""Probe actual Kodi methods; never emulate private native receipts.

Availability is NOT successful playback or certified HDR/audio passthrough.
The custom protocol keeps its historical name for interoperability only.
"""
NATIVE_METHODS = frozenset({
    'Player.BobiState', 'Player.BobiControl', 'Player.BobiIntent',
    'Player.BobiFullscreen', 'Player.BobiSubtitles', 'Player.BobiSubtitle',
    'Player.BobiSubtitleFile',
})
STANDARD_METHODS = frozenset({'Player.Open', 'Player.GetActivePlayers',
                               'Player.GetProperties', 'Player.GetItem'})


def probe(rpc, os_name='unknown'):
    errors = []
    try:
        app = rpc('Application.GetProperties', {'properties': ['version']})
        version = app.get('version', {})
        major = version.get('major', 0)
        if type(major) is not int:
            major = 0
    except (ValueError, TypeError, OSError, RuntimeError):
        major = 0
        errors.append('KODI_VERSION_UNAVAILABLE')
    try:
        reply = rpc('JSONRPC.Introspect', {'getdescriptions': False, 'getmetadata': False})
        methods = reply.get('methods', {})
        if not isinstance(methods, dict):
            raise ValueError('Invalid introspection')
    except (ValueError, TypeError, OSError, RuntimeError):
        methods = {}
        errors.append('RPC_INTROSPECTION_UNAVAILABLE')
    standard = major == 21 and STANDARD_METHODS.issubset(methods)
    native = standard and NATIVE_METHODS.issubset(methods)
    return {
        'schema': 1, 'platform': os_name, 'kodi_major': major,
        'standard_playback': standard, 'native_contract_available': native,
        'native_contract_healthy': False,
        'automatic_continuation': False, 'zidoo_player_verified': False,
        'bt_backend_ready': False, 'cloud_account_ready': False,
        'errors': errors,
    }


def require(capabilities, name):
    if capabilities.get(name) is not True:
        raise RuntimeError('BOBBI_CAPABILITY_UNAVAILABLE:' + name)
