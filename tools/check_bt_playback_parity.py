"""Grade paired AM6B trials from the exported, redacted JSON records."""
from pathlib import Path
import argparse, json, math, re


def read(root, name):
    if not isinstance(name,str) or Path(name).name!=name or not name.endswith('.json'):
        raise ValueError('A local JSON receipt filename is required')
    return json.loads((root / name).read_text(encoding='utf8'))


def contiguous(rows):
    best = 0.0
    first = last = last_move = None
    for row in rows:
        at, clock = row['at'], row['s']
        if any(type(v) not in (float, int) or not math.isfinite(v) for v in (at, clock)):
            raise ValueError('Invalid observation')
        if first is None or at <= last['at'] or at-last['at'] > 3.5 or clock < last['s']-.2 or clock-last['s'] > at-last['at']+2.5:
            first, last_move = row, at
        elif clock > last['s']+.1:
            if at-last_move > 3.8:
                first = row
            last_move = at
        best = max(best, clock-first['s'])
        last = row
    return round(best, 3)


def _case(root, spec):
    case = spec['name']
    product = read(root,spec['product'])
    if product.get('case') != case:
        raise ValueError('Public receipt belongs to a different case')
    identity = product.get('file_fingerprint')
    target = product.get('target', {})
    if 'selected' in spec:
        selected = read(root,spec['selected'])
        proven = selected.get('matched_active_request') is True or all(selected.get(k) is True
                for k in ('only_matching_engine_file','selected_tail_requested','prior_verified_identity_matched'))
        if not proven:
            raise ValueError('Selected input has no on-device evidence')
        if ((identity and identity != selected['file_fingerprint']) or
                (target and (target['id'],target['bytes']) != (selected['id'],selected['bytes']))):
            raise ValueError('Selected and played file differ')
        identity = selected['file_fingerprint']
        target = selected
    if not isinstance(identity,str) or not re.fullmatch('[a-f0-9]{64}', identity):
        raise ValueError('No selected-file fingerprint')
    if any(type(target.get(k)) is not int or target[k] < 1 for k in ('id','bytes')):
        raise ValueError('No selected file ID and size')
    if not read(root,spec['cold_before'])['exact_torrent_absent']:
        raise ValueError('Cold public comparison required')
    a = product['av']
    if a and not any(window == 12005 for _, window in product.get('windows', [])):
        raise ValueError('No observed fullscreen public playback')
    if any(not r.get('actual') or r.get('speed')!=1 or not r.get('w') or not r.get('h') for r in a):
        raise ValueError('Selected input and decoded stream must match')
    dimensions = (a[-1]['w'],a[-1]['h']) if a else None
    result = {'selected_id':target['id'], 'selected_bytes':target['bytes'],
              'cold_first_confirmed_fullscreen_wall_s':a[0]['at'] if a else None,
              'cold_longest_contiguous_s':contiguous(a), 'file_dialogs':product['file_dialogs'],
              'manual_waits':product['slow_waits'], 'skins':{}}
    result['cold_start_passed'] = result['cold_longest_contiguous_s']>=6 and result['file_dialogs']==spec['file_dialogs']
    result['cold_endurance_passed'] = result['cold_longest_contiguous_s']>=50
    passed = []
    seen = set()
    cache_state = None
    own_skin = 'skin.bobbi.cinema'
    if own_skin not in {v['skin'] for v in spec['views']} or len(spec['views']) < 2:
        raise ValueError('The household skin and a distinct reference skin are required')
    for view in spec['views']:
        skin = view['skin']
        if skin in seen:
            raise ValueError('Distinct actual skins are required')
        seen.add(skin)
        comp = read(root,view['receipt'])
        if not comp.get('cache') or (cache_state is not None and comp['cache'] != cache_state):
            raise ValueError('Cache conditions differ between skins')
        cache_state = comp['cache']
        if (comp.get('case') != case or comp['skin'] != skin or comp['file_fingerprint'] != identity or
                comp['file_id']!=result['selected_id'] or comp['bytes']!=result['selected_bytes'] or
                not comp['trigger'].startswith('remote Select')):
            raise ValueError('Controls do not represent the same file and playback action')
        rows = comp['observations']
        if rows and dimensions is None:
            dimensions = (rows[0].get('w'),rows[0].get('h'))
        valid = all(r.get('w') and r.get('h') and r.get('exact_file') and r.get('speed') == 1 and r.get('window') == 12005
                    and (r.get('w'),r.get('h'))==dimensions for r in rows)
        advance = contiguous(rows) if valid else 0
        result['skins'][skin] = {'confirmed_clock_s':advance,'passed':advance>=20}
        passed.append(advance>=20)
    result['same_path_parity_passed'] = len(passed)>=2 and all(passed)
    reference_opens = any(v['passed'] for skin,v in result['skins'].items() if skin != own_skin)
    result['reference_opens_household_does_not'] = reference_opens and not result['skins'][own_skin]['passed']
    result['reference_opens_product_does_not'] = reference_opens and not result['cold_start_passed']
    return result


def evaluate(manifest, *, report_incomplete=False):
    cases = {}
    for spec in read(manifest.parent,manifest.name)['cases']:
        case = spec['name']
        if not isinstance(case,str) or not case or case in cases:
            raise ValueError('Missing or duplicate comparison case')
        try:
            cases[case] = _case(manifest.parent, spec)
        except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
            if not report_incomplete:
                raise
            if isinstance(error, FileNotFoundError):
                reason = 'Missing receipt: ' + Path(error.filename).name
            elif isinstance(error, ValueError):
                reason = str(error)
            else:
                reason = 'Invalid receipt (' + type(error).__name__ + ')'
            cases[case] = {'incomplete':reason}
    if not cases:
        raise ValueError('No cases supplied')
    return cases


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    result = evaluate(parser.parse_args().manifest, report_incomplete=True)
    print(json.dumps(result,indent=2,ensure_ascii=False))
    raise SystemExit(0 if all(r.get('cold_start_passed') and r.get('cold_endurance_passed') and
                              r['same_path_parity_passed'] for r in result.values()) else 1)
