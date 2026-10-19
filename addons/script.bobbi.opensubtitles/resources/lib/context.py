# Modified for bobbi portability and explicit credentials, 2026-10-19.
"""Read-only playback context; no snapshot grants permission to change playback."""
import math
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlsplit


class ContextUnavailable(RuntimeError):
    pass


def _integer(value, minimum=0, maximum=99999):
    if type(value) is str and re.fullmatch(r"[0-9]{1,12}", value):
        value = int(value)
    return value if type(value) is int and minimum <= value <= maximum else None


def text(value, limit=256):
    """Display/search text only, not Kodi markup or a transport URL."""
    if not isinstance(value, str) or "://" in value:
        return ""
    return " ".join(re.sub(r"[\x00-\x1f\x7f]", " ", value).split())[:limit]


def playback_key(rpc):
    result = rpc("Player.BobiState", {})
    row = result.get("playback") if isinstance(result, dict) else None
    if (not isinstance(result, dict) or type(result.get("protocol")) is not int
            or result["protocol"] != 1 or not isinstance(row, dict)
            or type(row.get("protocol")) is not int or row["protocol"] != 1
            or row.get("phase") != "AV_STARTED"):
        raise ContextUnavailable("NO_ACTIVE_PLAYBACK")
    if (not re.fullmatch(r"[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}",
                         str(row.get("native_instance", "")))
            or not re.fullmatch(r"[0-9a-f]{64}", str(row.get("url_sha256", "")))
            or not re.fullmatch(r"(?:[0-9a-f]{32})?", str(row.get("request_id", "")))
            or not isinstance(row.get("file_identity"), str)
            or len(row["file_identity"]) > 1024):
        raise ContextUnavailable("PLAYBACK_IDENTITY_UNAVAILABLE")
    for key in ("open_epoch", "subtitle_intent"):
        if type(row.get(key)) is not int or row[key] < 0:
            raise ContextUnavailable("PLAYBACK_IDENTITY_UNAVAILABLE")
    if (type(result.get("selection_epoch")) is not int
            or result["selection_epoch"] != row["open_epoch"]):
        raise ContextUnavailable("PLAYBACK_CHANGED")
    return tuple(row[key] for key in ("native_instance", "request_id", "file_identity",
                                      "url_sha256", "open_epoch", "subtitle_intent"))


@dataclass(frozen=True)
class Snapshot:
    context: dict
    key: tuple
    account: object = None
    account_reader: object = None

    def current(self, rpc):
        try:
            return (playback_key(rpc) == self.key and
                    _account(self.account_reader) == self.account)
        except (ContextUnavailable, RuntimeError, ValueError, TypeError, OSError):
            return False


def _duration(properties):
    total = properties.get("totaltime") if isinstance(properties, dict) else None
    if not isinstance(total, dict):
        raise ContextUnavailable("DURATION_UNAVAILABLE")
    values = [_integer(total.get(key), maximum=maximum) for key, maximum in
              (("hours", 6), ("minutes", 59), ("seconds", 59), ("milliseconds", 999))]
    if None in values:
        raise ContextUnavailable("DURATION_UNAVAILABLE")
    hours, minutes, seconds, millis = values
    value = hours * 3600 + minutes * 60 + seconds + millis / 1000.0
    if not math.isfinite(value) or not 60 <= value <= 21600:
        raise ContextUnavailable("DURATION_UNAVAILABLE")
    return value


def _imdb(value):
    return value if isinstance(value, str) and re.fullmatch(r"tt[0-9]{5,12}", value) else None


def _release(path):
    if not isinstance(path, str) or len(path) > 16384:
        return ""
    try:
        parsed = urlsplit(path.split("|", 1)[0])
        if parsed.scheme.lower() in {"plugin", "stack"}:
            return ""
        return text(unquote(parsed.path.replace("\\", "/").rsplit("/", 1)[-1]), 256)
    except ValueError:
        return ""


def _am6b_tagged(key):
    """Only AM6B's bound playback uses make_listing's parent-series ID contract."""
    request, identity = key[1], key[2]
    selected = r"(?:bt:[0-9a-f]{40}|(?:prepared|transport):[0-9a-f]{64})"
    exact = (r"(?:bt:[0-9a-f]{40}\|[0-9a-f]{64}"
             r"|transport:[0-9a-f]{64}\|bt:[0-9a-f]{40}\|[0-9a-f]{64}"
             r"|" + selected + r"\|transport:[0-9a-f]{64})")
    return bool(re.fullmatch(r"[0-9a-f]{32}", request) and re.fullmatch(exact, identity))


def _account(reader):
    if reader is None:
        return None
    from bobbi_platform.account_manager import validate_snapshot
    return validate_snapshot(reader())


def capture(rpc, account_reader=None):
    """Sandwich all metadata reads between exact native-instance/intent reads."""
    account = _account(account_reader)
    before = playback_key(rpc)
    players = rpc("Player.GetActivePlayers", {})
    video = [p for p in players if isinstance(p, dict) and p.get("type") == "video"
             and type(p.get("playerid")) is int] if isinstance(players, list) else []
    if len(video) != 1:
        raise ContextUnavailable("NO_ACTIVE_PLAYBACK")
    player_id = video[0]["playerid"]
    result = rpc("Player.GetItem", {"playerid": player_id, "properties": [
        "title", "originaltitle", "showtitle", "year", "season", "episode",
        "uniqueid", "imdbnumber", "file"]})
    properties = rpc("Player.GetProperties", {"playerid": player_id, "properties": ["totaltime"]})
    after = playback_key(rpc)
    if before != after or _account(account_reader) != account:
        raise ContextUnavailable("PLAYBACK_CHANGED")
    item = result.get("item") if isinstance(result, dict) else None
    if not isinstance(item, dict):
        raise ContextUnavailable("MEDIA_CONTEXT_UNAVAILABLE")
    show = text(item.get("showtitle"))
    series = item.get("type") == "episode" or bool(show)
    title = show if series else text(item.get("originaltitle") or item.get("title"))
    if not title:
        raise ContextUnavailable("MEDIA_CONTEXT_UNAVAILABLE")
    year = _integer(item.get("year"), 1888, 2100)
    season, episode = _integer(item.get("season"), 0, 999), _integer(item.get("episode"), 1, 99999)
    if (series and (season is None or episode is None)) or (not series and year is None):
        raise ContextUnavailable("MEDIA_CONTEXT_UNAVAILABLE")
    ids = item.get("uniqueid") if isinstance(item.get("uniqueid"), dict) else {}
    if series:
        # Kodi's episode uniqueid may identify the episode OR its show. Use
        # explicit parent IDs, or the tightly scoped AM6B contract below.
        # Without either, fail clearly rather than promise a title fallback.
        tmdb = _integer(ids.get("tmdb.tv") or ids.get("tvshow.tmdb"), 1, 999999999)
        imdb = _imdb(ids.get("imdb.tv") or ids.get("tvshow.imdb"))
        explicit_episode = any(ids.get(k) for k in (
            "tmdb.episode", "episode.tmdb", "tmdb_episode",
            "imdb.episode", "episode.imdb", "imdb_episode"))
        if _am6b_tagged(before) and not explicit_episode:
            # AM6B make_listing explicitly places data.ids.tmdb_id/imdb_id
            # (parent series) into generic uniqueids and sets S/E separately.
            # This contract is not inherited by untagged external players.
            tmdb = tmdb or _integer(ids.get("tmdb"), 1, 999999999)
            imdb = imdb or _imdb(ids.get("imdb")) or _imdb(item.get("imdbnumber"))
    else:
        tmdb = _integer(ids.get("tmdb"), 1, 999999999)
        imdb = _imdb(ids.get("imdb")) or _imdb(item.get("imdbnumber"))
    if tmdb is None and imdb is None:
        raise ContextUnavailable("MEDIA_CONTEXT_UNAVAILABLE")
    context = dict(mode="tv" if series else "movie", title=title, showtitle=show,
                   year=year, season=season if series else None, episode=episode if series else None,
                   tmdb=tmdb, imdb=imdb, release=_release(item.get("file")),
                   duration=_duration(properties))
    return Snapshot(context, before, account, account_reader)
