"""Conservative cached episode identity; never contact a provider while resolving."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re


def _number(value):
    if isinstance(value, bool) or not str(value).isdigit():
        return None
    result = int(value)
    return result if 1 <= result <= 999999999999 else None


def _range(value):
    match = re.fullmatch(r'([1-9][0-9]*)(?:-([1-9][0-9]*)?)?', value)
    if not match:
        return None
    start = int(match[1])
    # The provider defines a lone x as open-ended, not a singleton.
    end = int(match[2]) if match[2] else None
    return (start, end) if end is None or end >= start else None


def mapped_episode(mapping, tmdb_id, season, episode):
    """Accept only an unambiguous 1:1 regular AniDB mapping.

    Split/combined episodes, specials and competing identities fail closed.
    Unsupported ranges are not silently replaced with S1 assumptions.
    """
    tmdb_id, season, episode = map(_number, (tmdb_id, season, episode))
    if None in (tmdb_id, season, episode) or season > 100000 or episode > 100000 or not isinstance(mapping, dict):
        return None
    targets = mapping.get('tmdb_show:{}:s{}'.format(tmdb_id, season))
    if not isinstance(targets, dict):
        return None
    matches = set()
    for target, ranges in targets.items():
        if not re.fullmatch(r'anidb:[1-9][0-9]*:R', target) or not isinstance(ranges, dict):
            continue
        for source_range, target_range in ranges.items():
            source = _range(source_range) if isinstance(source_range, str) else None
            if not source or episode < source[0] or (source[1] is not None and episode > source[1]):
                continue
            destination = _range(target_range) if isinstance(target_range, str) else None
            if not destination:
                return None
            if (source[1] is None) != (destination[1] is None):
                return None
            if source[1] is not None and source[1] - source[0] != destination[1] - destination[0]:
                return None
            matches.add((target, destination[0] + episode - source[0]))
    return next(iter(matches))[1] if len(matches) == 1 else None


@lru_cache(maxsize=1)
def load_mappings():
    path = Path(__file__).resolve().parents[2] / 'resources/cinema/episode-mappings.json'
    try:
        if path.stat().st_size > 2 * 1024 * 1024:
            return {}
        document = json.loads(path.read_text(encoding='utf-8'))
        if document.get('schema') != 1 or document.get('source_schema') != 'anibridge-v3':
            return {}
        return document.get('mappings', {})
    except (OSError, ValueError, AttributeError):
        return {}


def _mapped_identity(ids, tv_data, mappings=None):
    if not isinstance(ids, dict) or not isinstance(tv_data, dict):
        return None
    tmdb_id, season, episode = map(_number, (ids.get('tmdb_id'), tv_data.get('season'), tv_data.get('episode')))
    if None in (tmdb_id, season, episode):
        return None
    mapping = load_mappings() if mappings is None else mappings
    targets = mapping.get('tmdb_show:{}:s{}'.format(tmdb_id, season), {})
    absolute = mapped_episode(mapping, tmdb_id, season, episode)
    # A database mapping alone does not prove that an arbitrary release hash
    # belongs to a later cour. Keep offsets and multi-cour sources closed until
    # the preparation ledger also verifies the release's specific anime ID.
    if absolute is None or absolute != episode or season != 1 or len(targets) != 1:
        return None
    return {'media_id': 'tmdb:' + str(tmdb_id), 'season': season, 'episode': episode,
            'absolute_episode': absolute, 'provenance': 'anibridge-v3-anidb-regular'}


def bind_selected_episode(ids, tv_data, info_hash, mappings=None):
    if not isinstance(info_hash, str) or not re.fullmatch(r'[0-9a-fA-F]{40}', info_hash):
        return None
    proof = _mapped_identity(ids, tv_data, mappings)
    return dict(proof, source_info_hash=info_hash.lower()) if proof else None


def catalog_identity(details, tmdb_id):
    """Extract title evidence only from an independently ID-checked TV detail."""
    if (not isinstance(details, dict) or _number(details.get('id')) != _number(tmdb_id)
            or _number(tmdb_id) is None):
        return None
    names = [details.get('name'), details.get('original_name')]
    translations = details.get('translations') or {}
    translations = translations.get('translations') if isinstance(translations, dict) else []
    translated = []
    for row in translations[:128] if isinstance(translations, list) else []:
        if isinstance(row, dict) and isinstance(row.get('data'), dict):
            translated.append(row['data'].get('name'))
    alternate = details.get('alternative_titles') or {}
    alternate = alternate.get('results') if isinstance(alternate, dict) else []
    alternatives = []
    for row in alternate[:128] if isinstance(alternate, list) else []:
        if isinstance(row, dict):
            kind = row.get('type')
            # Release basenames often use a catalogue's romanization instead
            # of any localized translation. Preserve that independent ID-bound
            # evidence before the 16-alias / downstream 2048-byte handoff caps.
            if isinstance(kind, str) and kind.casefold() in (
                    'romaji', 'romanized', 'romanised', 'romanization', 'romanisation', 'transliteration'):
                names.append(row.get('title'))
            else:
                alternatives.append(row.get('title'))
    # Neither a long translation list nor a long alternative-title list owns
    # every remaining slot. No provider/release title is admitted as evidence.
    for index in range(max(len(alternatives), len(translated))):
        if index < len(alternatives):
            names.append(alternatives[index])
        if index < len(translated):
            names.append(translated[index])
    aliases = list(dict.fromkeys(name.strip() for name in names
        if isinstance(name, str) and 2 <= len(name.strip()) <= 128))[:16]
    if not aliases:
        return None
    date = details.get('first_air_date')
    year = int(date[:4]) if isinstance(date, str) and re.fullmatch(r'[12][0-9]{3}-[0-9]{2}-[0-9]{2}', date) else None
    return dict(tmdb_id=_number(tmdb_id), aliases=aliases, year=year)


def _transport_proof(ids, tv_data, request_id, selection_identity, mappings, catalog, candidate_scope=None):
    proof = _mapped_identity(ids, tv_data, mappings)
    if proof is None:
        return None
    if (not isinstance(catalog, dict) or catalog.get('tmdb_id') != _number(ids.get('tmdb_id'))
            or type(catalog.get('aliases')) is not list or not 1 <= len(catalog['aliases']) <= 16
            or any(not isinstance(name, str) or not 2 <= len(name) <= 128 or name.strip() != name
                   for name in catalog['aliases'])
            or len(set(catalog['aliases'])) != len(catalog['aliases'])
            or (catalog.get('year') is not None
                and (type(catalog['year']) is not int or not 1000 <= catalog['year'] <= 2999))):
        return None
    if candidate_scope not in (None, 'unscoped-range-v1'):
        raise ValueError('Unknown episode candidate scope')
    if candidate_scope and type(catalog.get('year')) is not int:
        return None
    identity_pattern = ('(?:transport:[0-9a-f]{64}|bt:[0-9a-f]{40})'
                        if candidate_scope else 'transport:[0-9a-f]{64}')
    if (not isinstance(request_id, str) or not re.fullmatch('[0-9a-f]{32}', request_id)
            or not isinstance(selection_identity, str)
            or not re.fullmatch(identity_pattern, selection_identity)):
        raise ValueError('Current request and selected transport required')
    key = 'tmdb_show:{}:s{}'.format(proof['media_id'].split(':')[1], proof['season'])
    evidence = json.dumps([key, mappings[key]], sort_keys=True, separators=(',', ':'))
    value = dict(proof, version=1, request_id=request_id, selection_identity=selection_identity,
                 mapping_sha256=hashlib.sha256(evidence.encode('utf-8')).hexdigest(),
                 catalog_aliases=list(catalog['aliases']), catalog_year=catalog.get('year'))
    if candidate_scope:
        value['candidate_scope'] = candidate_scope
    while len(json.dumps(value, ensure_ascii=False).encode('utf-8')) > 2048:
        value['catalog_aliases'].pop()
    return value if value['catalog_aliases'] else None


def bind_transport_episode(ids, tv_data, request_id, selection_identity, locator, mappings=None, catalog=None):
    """Carry a cached same-ID mapping until this selected URL yields its hash.

    This is not a hash-bound selector proof and cannot select a file on its own.
    The consumer must first verify torrent bytes and current playback ownership.
    """
    mapping = load_mappings() if mappings is None else mappings
    proof = _transport_proof(ids, tv_data, request_id, selection_identity, mapping, catalog)
    if proof is not None and (not isinstance(locator, str) or not locator
            or selection_identity != 'transport:' + hashlib.sha256(locator.encode('utf-8')).hexdigest()):
        raise ValueError('Episode handoff does not belong to the selected transport')
    return proof


def bind_catalog_range_episode(ids, tv_data, request_id, selection_identity, locator, info_hash,
                               mappings=None, catalog=None):
    """Restricted trusted-producer handoff, not a signed catalogue authority.

    Native ownership and verified content are independently checked by the
    consumer. Catalogue aliases/year come from the producer's checked cache.
    Missing evidence never produces a legacy or empty fallback for this route.
    """
    mapping = load_mappings() if mappings is None else mappings
    proof = _transport_proof(ids, tv_data, request_id, selection_identity, mapping, catalog,
                             candidate_scope='unscoped-range-v1')
    if proof is None:
        raise ValueError('Catalogue, year and regular episode mapping required for this range')
    if selection_identity.startswith('bt:'):
        if (not isinstance(info_hash, str) or not re.fullmatch('[0-9a-fA-F]{40}', info_hash)
                or selection_identity != 'bt:' + info_hash.lower()):
            raise ValueError('Range handoff must belong to the selected torrent hash')
    elif (not isinstance(locator, str) or not locator
            or selection_identity != 'transport:' + hashlib.sha256(locator.encode('utf-8')).hexdigest()):
        raise ValueError('Range handoff must belong to the selected transport')
    return proof


def _unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError('Duplicate episode handoff field')
        value[key] = item
    return value


def resolve_episode_binding(raw, request_id, selection_identity, info_hash, season, episode, mappings=None):
    """Convert only a verified transport handoff to the existing hash proof.

    Callers must obtain selection_identity from validate_torrent_resolution,
    never from URL parameters. Legacy hash proofs remain checked by the selector.
    """
    if raw in ('', None):
        return raw
    if not isinstance(raw, str) or len(raw.encode('utf-8')) > 2048:
        raise ValueError('Bounded episode handoff required')
    try:
        value = json.loads(raw, object_pairs_hook=_unique_object)
    except (ValueError, RecursionError):
        raise ValueError('Malformed episode handoff') from None
    if not isinstance(value, dict) or 'version' not in value:
        return raw
    if (type(value.get('version')) is not int or value['version'] != 1
            or not isinstance(value.get('media_id'), str)
            or not re.fullmatch('tmdb:[1-9][0-9]{0,11}', value['media_id'])
            or any(type(value.get(key)) is not int for key in ('season', 'episode', 'absolute_episode'))
            or value['season'] != _number(season) or value['episode'] != _number(episode)):
        raise ValueError('Invalid episode transport handoff')
    ids = {'tmdb_id': value['media_id'].split(':')[1]}
    tv_data = {'season': season, 'episode': episode}
    mapping = load_mappings() if mappings is None else mappings
    catalog = dict(tmdb_id=_number(ids['tmdb_id']), aliases=value.get('catalog_aliases'), year=value.get('catalog_year'))
    candidate_scope = value.get('candidate_scope')
    if candidate_scope not in (None, 'unscoped-range-v1'):
        raise ValueError('Unknown episode candidate scope')
    if candidate_scope and not isinstance(selection_identity, str):
        raise ValueError('Current selected transport required for this range')
    if candidate_scope and selection_identity.startswith('bt:') and (
            not isinstance(info_hash, str) or not re.fullmatch('[0-9a-fA-F]{40}', info_hash)
            or selection_identity != 'bt:' + info_hash.lower()):
        raise ValueError('Range handoff differs from the verified torrent hash')
    expected = _transport_proof(ids, tv_data, request_id, selection_identity, mapping, catalog,
                                 candidate_scope=candidate_scope)
    if expected is None or value != expected:
        raise ValueError('Episode handoff changed or belongs to another request')
    proof = bind_selected_episode(ids, tv_data, info_hash, mapping)
    if proof is None:
        raise ValueError('Verified torrent content hash required')
    return json.dumps(proof, ensure_ascii=False, separators=(',', ':'))


def check_transport_episode_file(raw, path):
    """Check the actual basename after transport proof validation and selection.

    Directory names, provider labels and technical tags cannot hide another work.
    Hash-bound legacy proofs keep their existing behavior outside this new path.
    """
    if raw in ('', None):
        return
    value = json.loads(raw, object_pairs_hook=_unique_object)
    if not isinstance(value, dict) or 'version' not in value:
        return
    from .catalog_identity import normalized, release_title
    if not isinstance(path, str):
        raise ValueError('Actual selected episode filename required')
    basename = re.split(r'[/\\]', path)[-1]
    name, year = release_title(basename, 'tv')
    if name not in {normalized(alias) for alias in value['catalog_aliases']}:
        raise ValueError('Actual episode title differs from the selected catalog work')
    if year is not None and year != value['catalog_year']:
        raise ValueError('Actual episode year differs from the selected catalog work')
    if 'candidate_scope' in value:
        if value['candidate_scope'] != 'unscoped-range-v1':
            raise ValueError('Unknown episode candidate scope')
        from .anime_range_candidates import check_file_tail
        check_file_tail(path, value['catalog_year'])
