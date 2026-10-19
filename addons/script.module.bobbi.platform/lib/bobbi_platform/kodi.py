"""Runtime adapters. Kodi modules are imported only inside the Kodi entrypoint."""
import json


def rpc(method, params=None):
    import xbmc
    response = json.loads(xbmc.executeJSONRPC(json.dumps({
        'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {},
    })))
    if 'error' in response or 'result' not in response:
        raise RuntimeError('Kodi RPC failed: ' + method)
    return response['result']


def make_item(url, data):
    import xbmcgui
    item = xbmcgui.ListItem(label=data.get('title', 'bobbi'), path=url)
    item.setProperty('IsPlayable', 'true')
    if data.get('title'):
        item.getVideoInfoTag().setTitle(data['title'])
    # Do not override global audio/HDR/codec/refresh-rate/OSD settings. Original
    # language and Chinese preference are a first-run user-confirmed setting.
    return item


def standard_handoff(identity, handle, ready=lambda: True):
    import xbmc
    import xbmcplugin
    from .playback import Handoff
    return Handoff(identity, handle, xbmcplugin.setResolvedUrl, xbmc.Player().play, make_item, ready)
