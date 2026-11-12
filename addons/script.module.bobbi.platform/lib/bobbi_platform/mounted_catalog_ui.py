"""Compatibility URLs; one personal-catalog renderer and playback selector.

Keep these aliases for saved Kodi favourites; they own no scan, page or player.
"""
from urllib.parse import urlencode


def target(params):
    action = params.get('action')
    values = {key: params[key] for key in ('namespace', 'scope', 'view', 'text', 'cursor', 'task')
              if params.get(key)}
    if params.get('source'):
        values['source'] = params['source']
    if params.get('parent'):
        values['parent_entity_id'] = params['parent']
    if action in ('mounted_root', 'mounted_browse', 'mounted_search'):
        values['action'] = 'personal_catalog'
        if action == 'mounted_search':
            values['search'] = 'true'
        elif action == 'mounted_browse':
            values.setdefault('view', 'works')
    elif action == 'mounted_play':
        values.update(action='personal_catalog_play', object_id=params.get('object', ''))
    elif action in ('mounted_jobs', 'mounted_scan', 'mounted_cancel'):
        values.update(action='personal_catalog_manage', mode=action[len('mounted_'):])
    else:
        raise ValueError('CATALOG_ACTION_INVALID')
    return 'plugin://plugin.video.bobbi/?' + urlencode(values)


def execute(handle, params, _item=None):
    import xbmc
    import xbmcplugin
    url = target(params)
    if handle >= 0:
        xbmcplugin.endOfDirectory(handle, succeeded=False, cacheToDisc=False)
    command = 'RunPlugin' if params.get('action') in (
        'mounted_play', 'mounted_jobs', 'mounted_scan', 'mounted_cancel') else 'Container.Update'
    xbmc.executebuiltin(command + '(' + url + ')')
