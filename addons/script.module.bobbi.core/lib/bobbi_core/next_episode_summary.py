"""Read-only projection of existing continuation results, never a play permit."""
from copy import deepcopy
from hashlib import sha256
import json
import re

STATES = {'unavailable', 'preparing', 'ready', 'needs_selection', 'complete', 'error'}
REASONS = {'IDENTITY_UNAVAILABLE', 'NOT_PREPARED', 'FINAL_CHECK_REQUIRED',
           'SAME_RELEASE_PREPARED', 'MANUAL_SOURCE_REQUIRED', 'PREPARATION_FAILED',
           'SEQUENCE_COMPLETE'}
FIELDS = {'schema', 'state', 'reason_code', 'current_media_ref', 'next_media_ref', 'release_family_ref'}


def media(data):
    if type(data) is not dict or data.get('mode') not in ('tv', 'anime', 'episode'):
        return None
    # Playback accepts some legacy metadata shapes. This optional projection
    # only describes an already structured identity; unknown shapes stay quiet.
    ids, tv_data = data.get('ids'), data.get('tv_data')
    if type(ids) is not dict or type(tv_data) is not dict:
        return None
    try:
        values = [ids.get('tmdb_id'), tv_data.get('season'), tv_data.get('episode')]
        if any(type(value) not in (str, int) or not str(value).isdecimal() for value in values):
            return None
        tmdb, season, episode = map(int, values)
        if not (0 < tmdb <= 2147483647 and 0 <= season <= 999 and 0 < episode <= 99999):
            return None
        return 'tmdb:tv:%d:s%d:e%d' % (tmdb, season, episode)
    except (ValueError, TypeError):
        return None


def project(current, candidate=None, *, preparing=False, failed=False, selection=None):
    """Only existing verified adapter results enter candidate/selection.

    No filename, title, adjacent array entry or user mapping is identity proof.
    An unresolved candidate is deliberately not advertised as ready.
    """
    current_ref = media(current)
    result = dict(schema=1, state='unavailable', reason_code='IDENTITY_UNAVAILABLE',
                  current_media_ref=None, next_media_ref=None, release_family_ref=None)
    if (not current_ref or current.get('selection_policy') != 'exact'
            or current.get('file_evidence') == 'USER_CONFIRMED_FILE' or current.get('_pan_file')):
        return result
    result['current_media_ref'] = current_ref
    result.update(state='preparing' if preparing else 'unavailable', reason_code='NOT_PREPARED')
    if failed:
        result.update(state='error', reason_code='PREPARATION_FAILED')
    if selection and media(selection) and media(selection) != current_ref:
        result.update(state='needs_selection', reason_code='MANUAL_SOURCE_REQUIRED', next_media_ref=media(selection))
    if candidate and media(candidate) and media(candidate) != current_ref:
        family = candidate.get('prepared_version_key')
        result.update(state='preparing', reason_code='FINAL_CHECK_REQUIRED', next_media_ref=media(candidate))
        if type(family) is str and re.fullmatch('[0-9a-f]{64}', family):
            result['release_family_ref'] = family
        # Existing prepared/direct routes revalidate on final submit. BT remains
        # provisional, even if metadata already proved the family.
        if (result['release_family_ref'] and candidate.get('_next_cloud_verified') is True
                and not candidate.get('_next_cloud_pending') and candidate.get('_next_transport') != 'bt'):
            result.update(state='ready', reason_code='SAME_RELEASE_PREPARED')
    return result


def checked(value):
    if (type(value) is not dict or set(value) != FIELDS or type(value['schema']) is not int
            or value['schema'] != 1 or value['state'] not in STATES or value['reason_code'] not in REASONS):
        raise ValueError('NEXT_SUMMARY_INVALID')
    for key in ('current_media_ref', 'next_media_ref'):
        if value[key] is not None and (type(value[key]) is not str or not re.fullmatch(
                r'tmdb:tv:[1-9][0-9]{0,9}:s[0-9]{1,3}:e[1-9][0-9]{0,4}', value[key])):
            raise ValueError('NEXT_SUMMARY_INVALID')
    family = value['release_family_ref']
    if family is not None and (type(family) is not str or not re.fullmatch('[0-9a-f]{64}', family)):
        raise ValueError('NEXT_SUMMARY_INVALID')
    if value['state'] == 'ready' and (not family or not value['next_media_ref']
                                    or not value['current_media_ref']):
        raise ValueError('NEXT_SUMMARY_INVALID')
    return deepcopy(value)


def envelope(summary, adapter, identity, account, generation):
    value = checked(summary)
    value.update(adapter=adapter, owner_identity=deepcopy(identity), generation=generation,
        account_ref=sha256(json.dumps(account, sort_keys=True).encode()).hexdigest() if account else None,
        account_epoch=(account or {}).get('epoch'), allowed_actions=[])
    return value


def label(summary):
    value = checked({key: summary[key] for key in FIELDS})
    labels = {'unavailable': '', 'preparing': '正在准备同版下一集',
        'ready': '同版下一集已就绪 · 播放前仍核验', 'needs_selection': '下一集需手动选源',
        'complete': '已到当前播放序列末尾', 'error': '下一集准备失败 · 可手动选源'}
    text = labels[value['state']]
    if value['state'] == 'preparing' and value['next_media_ref']:
        text = '下一集候选已确认 · 播放前仍需检查'
    if text and value['next_media_ref']:
        match = re.search(r':s([0-9]+):e([0-9]+)$', value['next_media_ref'])
        text += ' · S%02dE%02d' % tuple(map(int, match.groups()))
    return text
