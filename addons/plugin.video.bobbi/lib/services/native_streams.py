"""Read-only observations for stock Kodi track picks. Never serializes the file locator."""
from hashlib import sha256
import json

PROPERTIES = {'audio': ('audiostreams', 'currentaudiostream'), 'subtitle': ('subtitles', 'currentsubtitle')}
TRACK_FIELDS = ('index', 'language', 'name', 'codec', 'channels', 'isforced', 'isdefault', 'isoriginal', 'isimpaired')


def snapshot(rpc, kind, mode):
    """An index is meaningful only in the observed file and track table."""
    listing, selected = PROPERTIES[kind]
    players = [p['playerid'] for p in rpc('Player.GetActivePlayers', {}) if p.get('type') == 'video']
    if len(players) != 1 or type(players[0]) is not int:
        raise ValueError('NO_CURRENT_VIDEO')
    player = players[0]
    def file_key():
        item = rpc('Player.GetItem', dict(playerid=player, properties=['file']))['item']
        locator = item.get('file')
        if not isinstance(locator, str) or not locator or len(locator) > 32768:
            raise ValueError('VIDEO_FILE_UNKNOWN')
        return (item.get('type'), item.get('id'), locator)
    before = file_key()
    fields = [listing, selected] + (['subtitleenabled'] if kind == 'subtitle' else [])
    props = rpc('Player.GetProperties', dict(playerid=player, properties=fields))
    rows = props.get(listing)
    visible = props.get('subtitleenabled') if kind == 'subtitle' else None
    if (file_key() != before or type(rows) is not list or len(rows) > 256
            or (kind == 'subtitle' and type(visible) is not bool)):
        raise ValueError('VIDEO_STREAMS_CHANGED')
    tracks, indices = [], set()
    for row in rows:
        i = row.get('index') if type(row) is dict else None
        if type(i) is not int or not 0 <= i <= 255 or i in indices:
            raise ValueError('INVALID_STREAM_INDEX')
        indices.add(i)
        tracks.append([row.get(key) for key in TRACK_FIELDS])
    current = (props.get(selected) or {}).get('index')
    raw = json.dumps([mode, player, before, kind, tracks, current, visible], separators=(',', ':')).encode()
    return dict(player=player, rows=rows, current=current, visible=visible, proof=sha256(raw).hexdigest())
