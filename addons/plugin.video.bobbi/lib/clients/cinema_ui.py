"""UI-only local metadata rows. Never mistake this preview for ready resources."""
import json
from pathlib import Path
import re
import sys
from urllib.parse import parse_qs, urlencode, urlsplit


ROWS = {"weekly": "本周值得看", "anime": "热门番剧", "movies": "热门电影", "series": "热门剧集", "anime_movies": "热门动漫电影"}


def catalog_playable_property():
    # Source-picker actions never fulfill a Kodi media resolver callback.
    # This is a route contract, not a skin-specific presentation setting.
    return 'false'


def is_ui_action():
    try:
        return int(sys.argv[1]) < 0
    except (IndexError, TypeError, ValueError):
        return False


def search_prompt(params):
    import xbmc
    headings = {'multi': '搜索影视', 'tv': '搜索电视剧', 'movie': '搜索电影',
                'anime_tv': '搜索动漫', 'anime_movie': '搜索动漫电影'}
    section = params.get('section', 'multi')
    if section not in headings:
        return
    from lib.utils.kodi.utils import get_property, set_property
    memory_key = 'bobitv.search.last.' + section
    previous = get_property(memory_key) or ''
    initial = params.get('query', previous)
    if not isinstance(initial, str):
        initial = previous if isinstance(previous, str) else ''
    keyboard = xbmc.Keyboard(initial, headings[section])
    keyboard.doModal()
    query = str(keyboard.getText() or '').strip() if keyboard.isConfirmed() else ''
    if query:
        set_property(memory_key, query)
        url = 'plugin://plugin.video.bobbi/?' + urlencode({
            'action': 'am6b_streaming_search', 'section': section, 'query': query, 'page': 1})
        xbmc.executebuiltin('ActivateWindow(Videos,"' + url + '",return)')


def load_preview(path):
    path = Path(path)
    if path.stat().st_size > 512 * 1024:
        raise ValueError("UI snapshot budget")
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema") != 1 or data.get("status") != "CATALOG_UI_PREVIEW_NOT_READY_RECOMMENDATIONS":
        raise ValueError("Explicit preview contract required")
    if set(data.get("rows", {})) != set(ROWS):
        raise ValueError("Five bounded preview rows required")
    for rows in data["rows"].values():
        if not isinstance(rows, list) or len(rows) > 8:
            raise ValueError("Eight-item row limit")
        for item in rows:
            url = urlsplit(item["file"])
            if url.scheme != "plugin" or url.netloc != "plugin.video.bobbi" or parse_qs(url.query).get("action") != ["am6b_open_streaming_item"]:
                raise ValueError("Preview cannot open files or a player")
    return data


def handle(params):
    import xbmcgui
    import xbmcplugin
    handle_id = int(sys.argv[1])
    section = params.get("section", "weekly")
    if section not in ROWS:
        raise ValueError("Unknown presentation row")
    path = Path(__file__).resolve().parents[2] / "resources/cinema/ui-catalog-preview.json"
    try:
        data = load_preview(path)
        items = []
        for entry in data["rows"][section]:
            label = re.sub(r"\[/?(?:COLOR[^\]]*|B|I|UPPERCASE)\]", "", entry.get("label", ""), flags=re.I)
            title = entry.get("title") or label
            item = xbmcgui.ListItem(label=title, label2=entry.get("originaltitle", ""))
            item.setInfo("video", {key: entry[key] for key in ("title", "originaltitle", "year", "genre", "plot") if key in entry})
            item.setArt(entry.get("art", {}))
            item.setProperty("Bobi.Preview", "true")
            item.setProperty("Bobi.SnapshotDate", data["captured_at"][:10])
            plot = re.sub(r"\s+", " ", entry.get("plot", "")).strip()
            item.setProperty("Bobi.ShortPlot", plot[:90].rstrip("，,。 ") + "…" if len(plot) > 90 else plot)
            item.setContentLookup(False)
            # Follow the catalog's folder/playable semantics and actual route;
            # no ready-resource claim, guessed media or second play entry point.
            folder = entry.get("filetype") == "directory"
            item.setProperty("IsPlayable", "false" if folder else catalog_playable_property())
            route = parse_qs(urlsplit(entry['file']).query)
            if folder and route.get('mode') == ['tv']:
                from lib.clients.tmdb.season_cards import apply
                apply(item, (route.get('id') or [''])[0], title)
            items.append((entry["file"], item, folder))
        xbmcplugin.setContent(handle_id, "movies")
        xbmcplugin.setPluginCategory(handle_id, ROWS[section] + " · 片单预览")
        xbmcplugin.addDirectoryItems(handle_id, items)
        xbmcplugin.endOfDirectory(handle_id, cacheToDisc=False)
        from lib.clients.tmdb.season_cards import enqueue_directory
        enqueue_directory(items, home=True)
    except (OSError, ValueError, KeyError):
        xbmcplugin.endOfDirectory(handle_id, succeeded=True, cacheToDisc=False)
