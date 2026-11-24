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
    raw_url = url.partition('|')[0]
    item = xbmcgui.ListItem(label=data.get('title', 'bobbi'), path=url)
    item.setProperty('IsPlayable', 'true')
    if isinstance(data.get('mime'), str) and data['mime']:
        item.setContentLookup(False)
        item.setMimeType(data['mime'])
    video_info = dict(data.get('video_info') or {})
    if data.get('title') and 'title' not in video_info:
        video_info['title'] = data['title']
    if video_info:
        item.setInfo('video', video_info)
    tag = item.getVideoInfoTag()
    if data.get('title'):
        tag.setTitle(data['title'])
    tv = data.get('tv_data') or {}
    for key, setter in (('season', 'setSeason'), ('episode', 'setEpisode')):
        value = tv.get(key)
        if type(value) is int and value >= 0 and hasattr(tag, setter):
            getattr(tag, setter)(value)
    art = {key: data[key] for key in ('poster', 'fanart', 'thumb')
           if isinstance(data.get(key), str) and data[key]}
    if art:
        item.setArt(art)
    subtitles = data.get('subtitles_path') or []
    if isinstance(subtitles, list) and subtitles and hasattr(item, 'setSubtitles'):
        item.setSubtitles(subtitles)
    request = data.get('request_id')
    if request:
        item.setProperty('bobbi.standard.request', request)
        if hasattr(tag, 'setUniqueID'):
            tag.setUniqueID(request, 'bobbi_request')
    resume_pos = data.get('_resume_offset_seconds')
    if data.get('_pan_file') and resume_pos is None:
        resume_pos = data.get('_file_resume_position', 0)
    if data.get('_mounted_path') or data.get('_bobbi_start_over') is True:
        # Mounted stat is not a strong resume identity. Do not inherit Kodi's
        # old same-path offset after remount/replacement.
        item.setProperty('StartOffset', '0')
    elif type(resume_pos) in (int, float) and 0 < resume_pos <= 864000:
        item.setProperty('StartOffset', str(resume_pos))
    # Do not override global audio/HDR/codec/refresh-rate/OSD settings. Original
    # language and Chinese preference are a first-run user-confirmed setting.
    _ = raw_url
    return item


def standard_handoff(identity, handle, ready=lambda: True):
    import xbmc
    import xbmcplugin
    from .playback import Handoff
    return Handoff(identity, handle, xbmcplugin.setResolvedUrl, xbmc.Player().play, make_item, ready)
