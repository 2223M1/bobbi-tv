"""Validated provider episode orders; catalog IDs never become release offsets."""
import hashlib
import json
import re


def _int(value, minimum=1, maximum=100000):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError('Invalid episode order number')
    return value


def validate_group(tmdb_id, listing, document):
    """Accept a listed production/TV season order with unique real episode IDs.

    A story-arc order is not a broadcast season. Specials remain separate.
    Group order numbers alone are not season evidence; require season labels.
    """
    _int(tmdb_id, maximum=999999999)
    if (not isinstance(listing, dict) or listing.get('id') != tmdb_id
            or not isinstance(document, dict) or document.get('type') not in (6, 7)):
        raise ValueError('Unbound/non-season episode group')
    group_id = document.get('id')
    if not isinstance(group_id, str) or not re.fullmatch('[0-9a-f]{24}', group_id):
        raise ValueError('Invalid group identity')
    summaries = [row for row in listing.get('results', []) if row.get('id') == group_id]
    if len(summaries) != 1 or summaries[0].get('type') != document.get('type'):
        raise ValueError('Episode group is not listed for this show')
    groups = document.get('groups')
    if not isinstance(groups, list) or not 2 <= len(groups) <= 100:
        raise ValueError('No bounded seasonal grouping')
    seasons, seen_ids, seen_catalog, seen_seasons = [], set(), set(), set()
    for group in groups:
        number = _int(group.get('order'), 0, 99)
        if number == 0:
            continue
        name = str(group.get('name', ''))
        match = re.fullmatch(r'(?i)season\s+0*([1-9]\d?)', name.strip())
        if not match or int(match[1]) != number or number in seen_seasons:
            raise ValueError('Ambiguous/non-season group label')
        seen_seasons.add(number)
        rows = group.get('episodes')
        if not isinstance(rows, list) or not 1 <= len(rows) <= 1000:
            raise ValueError('Unbounded/empty episode group')
        episodes, orders = [], set()
        for row in rows:
            if row.get('show_id') != tmdb_id:
                raise ValueError('Foreign show in episode group')
            ep_id = _int(row.get('id'), maximum=999999999)
            pair = (_int(row.get('season_number')), _int(row.get('episode_number')))
            order = _int(row.get('order'), 0, 999)
            if ep_id in seen_ids or pair in seen_catalog or order in orders:
                raise ValueError('Duplicate/split episode mapping')
            seen_ids.add(ep_id); seen_catalog.add(pair); orders.add(order)
            episodes.append(dict(season=number, episode=order + 1, catalog_season=pair[0],
                catalog_episode=pair[1], episode_id=ep_id,
                name=str(row.get('name') or ''), air_date=str(row.get('air_date') or ''),
                overview=str(row.get('overview') or '')[:4096], still_path=str(row.get('still_path') or '')))
        if orders != set(range(len(rows))):
            raise ValueError('Noncontiguous episode order')
        seasons.append(dict(season=number, episodes=sorted(episodes, key=lambda row: row['episode'])))
    if len(seasons) < 2 or len(seen_ids) > 2000:
        raise ValueError('Not a bounded multi-season order')
    seasons.sort(key=lambda row: row['season'])
    identities = [(e['catalog_season'], e['catalog_episode'], e['episode_id'], e['season'], e['episode'])
                  for season in seasons for e in season['episodes']]
    digest = hashlib.sha256(json.dumps(identities, separators=(',', ':')).encode()).hexdigest()
    return dict(schema=1, tmdb_id=tmdb_id, provider_group=group_id, digest=digest, seasons=seasons)


def lookup(order, catalog_season, catalog_episode):
    """Return a provider-mapped pair, never modify catalog/history numbering."""
    if not isinstance(order, dict) or order.get('schema') != 1:
        return None
    found = [row for season in order.get('seasons', []) for row in season['episodes']
             if (row['catalog_season'], row['catalog_episode']) == (catalog_season, catalog_episode)]
    return dict(found[0], order_digest=order['digest'], provider_group=order['provider_group']) if len(found) == 1 else None


def continuous_episode(order, target):
    """Prove a complete, ordered single-season sequence, not an assumed offset."""
    if not isinstance(order, dict) or not isinstance(target, dict):
        return None
    rows = [row for season in order.get('seasons', []) for row in season['episodes']]
    if not rows or [(row['catalog_season'], row['catalog_episode']) for row in rows] != [
            (1, number) for number in range(1, len(rows) + 1)]:
        return None
    found = [number for number, row in enumerate(rows, 1)
             if (row['episode_id'], row['season'], row['episode']) ==
                (target['episode_id'], target['season'], target['episode'])]
    return found[0] if len(found) == 1 else None
