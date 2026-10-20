"""Read a bounded Kodi selection snapshot before the assistant takes focus."""
import re
import time


LABELS = ('ListItem.Label', 'ListItem.Title', 'ListItem.DBID', 'ListItem.DBTYPE',
          'ListItem.Year', 'ListItem.TVShowTitle', 'ListItem.Season', 'ListItem.Episode',
          'Container.Content', 'Container.FolderName', 'Container.PluginName')
SENSITIVE = re.compile(r'api[\s_-]*key|access[\s_-]*token|refresh[\s_-]*token|authorization|'
                       r'password|secret|密码|密钥|令牌', re.I)
URL = re.compile(r'\b[a-z][a-z0-9+.-]*://\S+', re.I)
SECRET = re.compile(r'\b(?:sk-[a-z0-9_-]{12,}|eyJ[a-z0-9_-]+\.[a-z0-9_-]+\.[a-z0-9_-]+)', re.I)
KINDS = {'movie': ('VideoLibrary.GetMovieDetails', 'moviedetails'),
         'tvshow': ('VideoLibrary.GetTVShowDetails', 'tvshowdetails'),
         'episode': ('VideoLibrary.GetEpisodeDetails', 'episodedetails')}


def plain(value):
    if not isinstance(value, str):
        return ''
    value = re.sub(r'\[/?(?:COLOR(?: [^\]]+)?|B|I|LIGHT|UPPERCASE|LOWERCASE|CAPITALIZE)\]', '', value,
                   flags=re.I)
    return ' '.join(value.replace('[CR]', ' ').split())


def text(value, limit=240, sensitive=False):
    value = plain(value)
    if sensitive and SENSITIVE.search(value):
        return '[敏感输入项]'
    return SECRET.sub('[private]', URL.sub('[地址已省略]', value))[:limit]


def number(value, minimum=0, maximum=2147483647):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    try:
        result = int(value)
    except (ValueError, TypeError, OverflowError):
        return None
    return result if minimum <= result <= maximum else None


def capture(rpc):
    """Best effort only: an unavailable GUI label must never block recording.

    Do not query paths, edit values, artwork URLs, or an entire directory. A
    library lookup admits a selection to playback tools only when ID and title
    agree; plugin-supplied IDs are never treated as Kodi library IDs.
    """
    result = {'captured_at': time.time(), 'source': 'before_assistant',
              'window': {}, 'focus': {}, 'container': {}, 'selected': None}
    try:
        gui = rpc('GUI.GetProperties', {'properties': ['currentwindow', 'currentcontrol']})
        window = gui.get('currentwindow') or {}
        result['window'] = {'id': number(window.get('id')), 'label': text(window.get('label'))}
        result['focus'] = {'label': text((gui.get('currentcontrol') or {}).get('label'), sensitive=True)}
        labels = rpc('XBMC.GetInfoLabels', {'labels': list(LABELS)})
        result['container'] = {key: text(labels.get(label)) for key, label in (
            ('content', 'Container.Content'), ('label', 'Container.FolderName'), ('plugin', 'Container.PluginName'))}
        label, title = text(labels.get('ListItem.Label')), text(labels.get('ListItem.Title'))
        if not label and not title:
            return result
        selected = {'label': label, 'title': title, 'type': text(labels.get('ListItem.DBTYPE'))}
        for key, field in (('year', 'Year'), ('season', 'Season'), ('episode', 'Episode')):
            value = number(labels.get('ListItem.' + field), maximum=9999)
            if value is not None:
                selected[key] = value
        show = text(labels.get('ListItem.TVShowTitle'))
        if show:
            selected['showtitle'] = show
        result['selected'] = selected
        kind = selected['type']
        identifier = number(labels.get('ListItem.DBID'), minimum=1)
        if kind in KINDS and identifier is not None and not result['container']['plugin']:
            method, field = KINDS[kind]
            try:
                row = rpc(method, {kind + 'id': identifier, 'properties': ['title']})[field]
                actual_title = plain(row.get('title') or row.get('label'))
                visible_title = plain(labels.get('ListItem.Title') or labels.get('ListItem.Label'))
                if row.get(kind + 'id') == identifier and actual_title and actual_title.casefold() == visible_title.casefold():
                    selected['media'] = {'kind': kind, 'id': identifier, 'title': text(actual_title)}
            except Exception:
                pass  # Keep the visible selection even if its library entry vanished.
    except Exception:
        result['incomplete'] = True
    return result
