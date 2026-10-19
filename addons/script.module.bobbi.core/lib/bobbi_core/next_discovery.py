"""Bounded headless discovery IO; it never writes the ledger or submits to 115.

Search titles are hints only. Current anchor, actual candidate file metadata,
exact episode selector, catalog identity and release family must all agree.
"""
import hashlib
import json
import re
import time

from bobbi_core.jackett_protocol import AbsoluteEpisodeQuery
from bobbi_core.next_release import verified_anchor, verified_next
from bobbi_core.release_identity import bound_family
from bobbi_core.candidate_titles import matches as matches_catalog_title
from bobbi_core.catalog_identity import release_context, release_binding
from bobbi_core.episode_identity import bind_selected_episode, load_mappings

BUDGET = 16.0  # One search <=8 s, remaining metadata lane <=8 s per call.
MAX_PROBES = 3


def _groups(name):
    """Exact shared co-release tags are probe hints, never version proof."""
    match = re.match(r'^\[([^\[\]]{1,80})\]', name)
    if not match:
        return set()
    return {re.sub(r'[\W_]+', '', part.casefold())
            for part in re.split(r'[&+×]', match[1]) if len(part.strip()) >= 3}


def candidate_priority(candidate, family, anchor_name, catalog, season, episode, absolute=None):
    """Order bounded metadata probes without accepting any search label.

    Bilingual aliases and translated co-group labels differ from actual file
    basenames. An exact shared group plus the requested title/episode gets a
    probe before unrelated versions; verified_next still proves the full file.
    """
    try:
        same_release = bound_family(candidate.title, season, episode, absolute) == family
    except ValueError:
        same_release = False
    if not same_release:
        from bobbi_core.episode_revision import continuation_family
        try:
            same_release = (continuation_family(candidate.title, season, episode)
                            == continuation_family(anchor_name, season, episode - 1))
        except ValueError:
            pass  # Only probe ordering; actual metadata must still prove E+1.
    try:
        # Search titles may use slash-separated aliases; only this *hint*
        # removes separators. Actual paths/families are never transformed.
        bound_family(candidate.title.replace('/', ' ').replace('\\', ' '), season, episode, absolute)
        episode_hint = True
    except ValueError:
        episode_hint = False
    title_hint = matches_catalog_title(candidate.title, catalog['aliases'], 'tv', release_season=season)
    group_hint = bool(_groups(anchor_name) & _groups(candidate.title))
    return (not same_release, not (title_hint and episode_hint and group_hint),
            not (title_hint and episode_hint), not title_hint)


def discover(job, catalog, searcher, metadata_provider, selector, cancelled=lambda: False,
             clock=time.monotonic, mappings=None):
    """Service-only IO callback. Return a proposal, never a ready-file flag."""
    started = clock()
    evidence = dict(searched=False, candidate_count=0, probes=[], search_complete=False)
    def remaining():
        return max(0, BUDGET - (clock() - started))
    def unavailable(reason):
        return dict(state='UNAVAILABLE', reason=reason, evidence=evidence)
    if cancelled(): return unavailable('CANCELLED')
    anchor, selection = job['payload']['anchor'], job['payload']['selection']
    media, family, proof = verified_anchor(anchor, selection, catalog)
    next_media = 'tmdb:tv:{}:s{}:e{}'.format(media['tmdb_id'], media['season'], media['episode'] + 1)
    if job['media_id'] != next_media or job['version_key'] != hashlib.sha256(family.encode()).hexdigest():
        raise ValueError('Discovery job no longer matches its current-source anchor')
    season, episode = media['season'], media['episode'] + 1
    next_context = dict(media, episode=episode)
    current_pair = release_context(media, catalog)
    try:
        pair = release_context(next_context, catalog)
    except ValueError:
        return unavailable('NO_NEXT_CATALOG_EPISODE')
    if current_pair and (not pair or pair['season'] != current_pair['season']):
        return unavailable('RELEASE_SEASON_END')
    if pair:
        season, episode = pair['season'], pair['episode']
    mapping = load_mappings() if mappings is None else mappings
    binding = bind_selected_episode({'tmdb_id': media['tmdb_id']}, {'season': season, 'episode': episode},
                                    anchor['selected']['source_info_hash'], mapping) if media['anime'] else None
    absolute = None
    if pair:
        binding = release_binding(next_context, catalog, anchor['selected']['source_info_hash'])
        absolute = AbsoluteEpisodeQuery(title=proof['matched_title'], **binding,
                                        mapping_sha256=pair['order_digest'])
    elif binding:
        raw = json.dumps(mapping.get('tmdb_show:{}:s{}'.format(media['tmdb_id'], season)), sort_keys=True, separators=(',', ':')).encode()
        absolute = AbsoluteEpisodeQuery(title=proof['matched_title'], **binding, mapping_sha256=hashlib.sha256(raw).hexdigest())
    if remaining() <= 0 or cancelled(): return unavailable('CANCELLED_OR_DEADLINE')
    def priority(candidate):
        return candidate_priority(candidate, family, anchor['selected']['torrent_path'].rsplit('/', 1)[-1],
                                  catalog, season, episode, pair['absolute_episode'] if pair else None)
    found = searcher.search_tv(proof['matched_title'], media['tmdb_id'], season, episode,
        absolute_query=absolute, cancelled=cancelled, budget=min(8.0, remaining()), candidate_priority=priority)
    evidence.update(searched=True, candidate_count=len(found.candidates), search_complete=found.complete)
    # Preserve bounded diagnostic codes, never provider exception strings/URLs.
    evidence['search_errors'] = [list(row) for row in found.errors[:64]
        if isinstance(row, (tuple, list)) and len(row) == 2
        and isinstance(row[0], str) and re.fullmatch('[A-Za-z0-9_-]{0,64}', row[0])
        and isinstance(row[1], str) and re.fullmatch('[a-z_]{1,64}', row[1])]
    if len(found.candidates) > 64 or found.state != 'CANDIDATES_ONLY_NOT_READY':
        raise ValueError('Unbounded/unrecognized search result')
    if cancelled(): return unavailable('CANCELLED')
    candidates, seen = [], set()
    for candidate in found.candidates:
        source = candidate.info_hash
        if (not isinstance(source, str) or not re.fullmatch('[0-9a-f]{40}', source)
                or source == anchor['selected']['source_info_hash'] or source in seen):
            continue
        seen.add(source)
        # This only orders metadata probes. It cannot establish identity or
        # discard a differently labelled pack that may contain the exact file.
        candidates.append((priority(candidate), candidate))
    candidates.sort(key=lambda pair: (pair[0], pair[1].key))
    # Rotate each bounded retry within rank tiers so one offline magnet cannot
    # permanently starve another exact candidate. The chosen release is still
    # proved from files; no quality/group fallback can be silently accepted.
    ordered = []
    for rank in sorted({rank for rank, _ in candidates}):
        tier = [c for score, c in candidates if score == rank]
        if tier:
            offset = max(0, job['attempts'] - 1) % len(tier)
            ordered.extend(tier[offset:] + tier[:offset])
    for candidate in ordered[:MAX_PROBES]:
        if cancelled() or remaining() <= 0:
            return unavailable('CANCELLED_OR_DEADLINE')
        row = dict(source_info_hash=candidate.info_hash, state='CHECKING')
        evidence['probes'].append(row)
        try:
            metadata = metadata_provider(candidate.info_hash, cancelled=cancelled, budget=min(8.0, remaining()))
        except (ValueError, OSError, TimeoutError):
            row['state'] = 'METADATA_UNAVAILABLE'
            continue
        if cancelled() or remaining() <= 0:
            return unavailable('CANCELLED_OR_DEADLINE')
        if metadata.get('hash') != candidate.info_hash:
            row['state'] = 'METADATA_HASH_MISMATCH'
            continue
        try:
            request, selection = verified_next(anchor, job['payload']['selection'], metadata,
                job['account'], job['destination'], selector, catalog)
        except (ValueError, KeyError, TypeError):
            row['state'] = 'FILE_OR_RELEASE_PROOF_REJECTED'
            continue
        if cancelled() or remaining() <= 0:
            return unavailable('CANCELLED_OR_DEADLINE')
        row['state'] = 'SOURCE_PROVED_NOT_CLOUD_READY'
        return dict(state='SOURCE_PROVED_NOT_CLOUD_READY', request=request, selection=selection, evidence=evidence)
    return unavailable('NO_VERIFIED_SAME_RELEASE')
