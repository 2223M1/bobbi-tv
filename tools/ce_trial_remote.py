"""Real ordinary playback trials; no independent video/CDN reads or lower-quality fallback."""
import ast
import json
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.parse import urlencode, parse_qsl, urlsplit
import urllib.request

BASE=Path('/storage/.local/share/bobbi-private-trials/20261020')
BASE.mkdir(mode=0o700, parents=True, exist_ok=True)
TESTS={
    'grand_budapest': {'title': 'The Grand Budapest Hotel', 'tmdb_id': 120467, 'kind': 'movie', 'year': 2014},
    'further_universe': {'title': 'A Place Further Than the Universe', 'tmdb_id': 76059, 'kind': 'tv', 'year': 2018, 'season': 1, 'episode': 1, 'animation': True},
    'perfect_days': {'title': 'Perfect Days', 'tmdb_id': 976893, 'kind': 'movie', 'year': 2023},
    'eizouken': {'title': 'Keep Your Hands Off Eizouken!', 'tmdb_id': 92579, 'kind': 'tv', 'year': 2020, 'season': 1, 'episode': 1, 'animation': True},
    'ping_pong': {'title': 'Ping Pong the Animation', 'tmdb_id': 60811, 'kind': 'tv', 'year': 2014, 'season': 1, 'episode': 1},
    'amelie': {'title': 'Amelie', 'tmdb_id': 194, 'kind': 'movie', 'year': 2001},
    'barakamon': {'title': 'Barakamon', 'tmdb_id': 67048, 'kind': 'tv', 'year': 2014, 'season': 1, 'episode': 1},
    'rashomon': {'title': 'Rashomon', 'tmdb_id': 548, 'kind': 'movie', 'year': 1950},
    'cowboy_bebop': {'title': 'Cowboy Bebop', 'tmdb_id': 30991, 'kind': 'tv', 'year': 1998, 'season': 1, 'episode': 1},
    'twelve_angry_men': {'title': '12 Angry Men', 'tmdb_id': 389, 'kind': 'movie', 'year': 1957},
    'tatami_galaxy': {'title': 'The Tatami Galaxy', 'tmdb_id': 36243, 'kind': 'tv', 'year': 2010, 'season': 1, 'episode': 1},
    'man_from_earth': {'title': 'The Man from Earth', 'tmdb_id': 13363, 'kind': 'movie', 'year': 2007},
    'lain': {'title': 'Serial Experiments Lain', 'tmdb_id': 1087, 'kind': 'tv', 'year': 1998, 'season': 1, 'episode': 1},
    'coherence': {'title': 'Coherence', 'tmdb_id': 220289, 'kind': 'movie', 'year': 2014},
    'odd_taxi': {'title': 'ODDTAXI', 'tmdb_id': 116727, 'kind': 'tv', 'year': 2021, 'season': 1, 'episode': 1},
    'wild_tales': {'title': 'Wild Tales', 'tmdb_id': 265195, 'kind': 'movie', 'year': 2014},
    'girls_last_tour': {'title': "Girls' Last Tour", 'tmdb_id': 74185, 'kind': 'tv', 'year': 2017, 'season': 1, 'episode': 1},
    'burning': {'title': 'Burning', 'tmdb_id': 491584, 'kind': 'movie', 'year': 2018},
    'flip_flappers': {'title': 'Flip Flappers', 'tmdb_id': 68272, 'kind': 'tv', 'year': 2016, 'season': 1, 'episode': 1},
    'lives_of_others': {'title': 'The Lives of Others', 'tmdb_id': 582, 'kind': 'movie', 'year': 2006},
    'tokyo_godfathers': {'title': 'Tokyo Godfathers', 'tmdb_id': 13398, 'kind': 'movie', 'year': 2003},
    'haibane_renmei': {'title': 'Haibane Renmei', 'tmdb_id': 34164, 'kind': 'tv', 'year': 2002, 'season': 1, 'episode': 1},
}
assert NAME in TESTS and OP in ('start', 'requery', 'wait', 'picker_wait', 'observe', 'seek', 'stop', 'cancel', 'cards', 'select', 'manual_off', 'font_switch', 'inspect'), 'TRIAL_SCOPE'
attempt=globals().get('ATTEMPT',1)
assert type(attempt) is int and 1<=attempt<=10
record_path = BASE / ('trial-' + NAME + ('' if attempt==1 else '-'+str(attempt)) + '.json')
sys.path.insert(0, '/storage/.kodi/addons/script.module.bobbi.core/lib')
def call(message):
    # Real device-local host IPC; CLI probes have no xbmcvfs interpreter.
    config=json.loads(Path('/storage/.kodi/userdata/addon_data/script.module.bobbi.platform/runtime.json').read_text())
    request=urllib.request.Request('http://127.0.0.1:%d/control'%config['port'],
        data=json.dumps(dict(action='playback',body=message)).encode(),
        headers={'Authorization':'Bearer '+config['token'],'Content-Type':'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=.3) as response:
        result=json.load(response)
    if result.get('ok') is not True:raise RuntimeError('PLAYBACK_OWNER_UNAVAILABLE')
    return result['result']



def rpc(method, params=None):
    request = urllib.request.Request('http://127.0.0.1:8080/jsonrpc',
        data=json.dumps(dict(jsonrpc='2.0', id=300, method=method, params=params or {})).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=4) as response:
        result = json.load(response)
    assert 'error' not in result, 'RPC_FAILURE'
    return result['result']


def snapshot():
    for attempt in range(3):
        try: return call({'operation': 'snapshot'})
        except OSError:
            if attempt == 2: raise
            time.sleep(.1)


def save(record):
    record_path.write_text(json.dumps(record, ensure_ascii=True))


def state(record, require=False):
    authority = snapshot()
    desired = authority.get('desired') or {}
    native = rpc('Player.BobiState')
    row = native.get('playback') or {}
    rid = desired.get('request_id')
    if not record.get('request_id') and rid and rid != record.get('prior_request'):
        record['request_id'] = rid
        record['selection_identity'] = desired.get('selection_identity')
        save(record)
    if record.get('request_id'):
        assert rid == record['request_id'], 'USER_CHANGED_SELECTION'
    if row and row.get('phase') != 'TERMINAL':
        assert row.get('request_id') == record.get('request_id'), 'OTHER_PLAYBACK'
        if not record.get('native_instance'):
            record['native_instance'] = row['native_instance']
            save(record)
        assert record['native_instance'] == row['native_instance'], 'OTHER_INSTANCE'
    if row.get('phase') == 'AV_STARTED' and 'first_av_observed_at' not in record:
        record['first_av_observed_at'] = time.monotonic()
        if record.get('selected_at') is not None:
            record['select_to_av_observed_seconds'] = record['first_av_observed_at'] - record['selected_at']
        save(record)
    if require:
        assert row.get('phase') == 'AV_STARTED' and record.get('native_instance') == row.get('native_instance'), 'NOT_PLAYING'
    return authority, native, row


def unsupported_control_evidence(record, operation):
    """Read-only gap receipt, never a check-then-global-write substitute.

    Reviewed F9 BobiControl accepts only stop/pause/resume. BobiSubtitle
    selects an index >=0 and explicitly enables visibility; it cannot hide
    subtitles. Neither contract changes the font working set. Future protocol
    additions require native/source review, not automatic feature guessing.
    """
    assert operation in ('seek', 'manual_off', 'font_switch'), 'CONTROL_SCOPE'
    _, _, before = state(record, require=True)
    response = rpc('JSONRPC.Introspect', {'getdescriptions': False, 'getmetadata': False})
    methods = response.get('methods', {})
    assert isinstance(methods, dict), 'CONTROL_SCHEMA_UNAVAILABLE'
    evidence = {}
    for method in ('Player.BobiControl', 'Player.BobiSubtitle', 'Player.Seek',
                   'Player.SetSubtitle', 'Settings.SetSettingValue'):
        schema = methods.get(method, {})
        params = schema.get('params', []) if isinstance(schema, dict) else []
        assert isinstance(params, list) and len(params) <= 32, 'CONTROL_SCHEMA_UNAVAILABLE'
        fields = {}
        for row in params:
            if not isinstance(row, dict) or not isinstance(row.get('name'), str):
                raise AssertionError('CONTROL_SCHEMA_UNAVAILABLE')
            fields[row['name']] = {key: row[key] for key in ('type', 'minimum', 'maximum', 'enum') if key in row}
        evidence[method] = fields
    _, _, after = state(record, require=True)
    assert (before['native_instance'], before['request_id']) == (after['native_instance'], after['request_id']), 'OTHER_INSTANCE'
    return dict(state='not_tested', passed=None, operation=operation, mutation_performed=False,
        reason='NO_REVIEWED_EXPECTED_INSTANCE_' + operation.upper(),
        native_instance=after['native_instance'], request_id=after['request_id'],
        observed_protocol=evidence,
        note='Unconditional player-id/settings RPC and UI actions are intentionally not substituted; no playback or font setting was changed.')


def seconds(moment):
    return moment['hours'] * 3600 + moment['minutes'] * 60 + moment['seconds'] + moment['milliseconds'] / 1000


def decoder_snapshot(raw, began, ended):
    """Keep every channel; a Dolby Vision enhancement layer is not a new total."""
    import hashlib
    import re
    blocks = list(re.finditer(r'(?m)^vdec channel (\d+) statistics:', raw))
    channels = []
    for index, marker in enumerate(blocks):
        text = raw[marker.end():blocks[index + 1].start() if index + 1 < len(blocks) else len(raw)]
        device = re.search(r'(?m)^\s*device name\s*:\s*(\S+)', text)
        fields = {key.strip(): int(value) for key, value in re.findall(
            r'(?m)^\s*(frame count|drop count|fra err count|hw err count|frame width|frame height)\s*:\s*(\d+)', text)}
        channels.append(dict(channel=int(marker[1]), device=device[1] if device else None, counters=fields))
    channels.sort(key=lambda row: (row['channel'], row['device'] or ''))
    known = bool(channels) and len({row['channel'] for row in channels}) == len(channels)
    bases = [row for row in channels if row['device'] == 'dvbldec']
    primary = (bases[0] if len(bases) == 1 else channels[0] if len(channels) == 1 else None) if known else None
    return dict(schema=2, read_started=began, read_completed=ended, raw=raw,
                sha256=hashlib.sha256(raw.encode()).hexdigest(), channels=channels,
                identity_known=known, primary_channel=primary['channel'] if primary else None)


def decoder_intervals(first, last):
    """Deltas only within one playback/channel identity, never across a reset."""
    a, b = first.get('decoder', {}), last.get('decoder', {})
    identity = ('native_instance', 'request_id')
    bindings = [tuple((row.get('native') or {}).get(k) for k in identity) for row in (first, last)]
    if (not a.get('identity_known') or not b.get('identity_known') or not all(bindings[0])
            or bindings[0] != bindings[1] or b['read_started'] < a['read_completed']):
        return []
    old = {row['channel']: row for row in a['channels']}
    result = []
    for row in b['channels']:
        previous = old.get(row['channel'])
        if not previous or not row['device'] or previous['device'] != row['device']:
            continue
        x, y = previous['counters'], row['counters']
        if any(x.get(k) != y.get(k) for k in ('frame width', 'frame height')):
            continue
        keys = ('frame count', 'drop count', 'fra err count', 'hw err count')
        reset = any(y[k] < x[k] for k in keys if k in x and k in y)
        result.append(dict(channel=row['channel'], device=row['device'], reset=reset,
                           delta=None if reset else {k: y[k]-x[k] for k in keys if k in x and k in y}))
    return result


def decoder_frame_pair(first, last):
    if 'decoder' not in first and 'decoder' not in last:
        # Read frozen schema-1 evidence as-is; do not invent its lost channels.
        return tuple(row.get('decoder_counters', {}).get('frame count') for row in (first, last))
    a, b = first.get('decoder', {}), last.get('decoder', {})
    selected = a.get('primary_channel')
    if selected is not None and selected == b.get('primary_channel'):
        interval = next((r for r in decoder_intervals(first, last) if r['channel'] == selected), None)
        if interval and not interval['reset'] and 'frame count' in interval['delta']:
            return tuple(next(r for r in row['channels'] if r['channel'] == selected)['counters']['frame count']
                         for row in (a, b))
    return None, None


def clock_interval_stable(first, last):
    """A positive advancing clock, not a stationary startup sentinel or jump."""
    if any(row.get('phase') != 'AV_STARTED' or row.get('speed') != 1
            or row.get('caching') is not False or row.get('seconds', -1) < 0 for row in (first, last)):
        return False
    wall = last['wall'] - first['wall']
    advance = last['seconds'] - first['seconds']
    frames = decoder_frame_pair(first, last)
    return (0.15 <= wall <= 2 and advance > 0.03
            and abs(advance - wall) <= max(.15, wall * .3)
            and all(type(value) is int for value in frames) and frames[1] > frames[0])


def bounded_clock_start(record, budget=5):
    """Retain every startup sample; never reset or extend the five-second bound."""
    assert 0 < budget <= 5
    began = time.monotonic()
    samples, consecutive = [], 0
    while True:
        current = sample(record)
        samples.append(current)
        elapsed = time.monotonic() - began
        if len(samples) > 1 and clock_interval_stable(samples[-2], current):
            consecutive += 1
        else:
            consecutive = 0
        if consecutive >= 2 and elapsed <= budget:
            return dict(stable=True, budget_seconds=budget, elapsed_seconds=elapsed, samples=samples,
                        **startup_health(samples))
        if elapsed >= budget:
            return dict(stable=False, budget_seconds=budget, elapsed_seconds=elapsed, samples=samples,
                        reason='CLOCK_NOT_STABLE_WITHIN_BOUND', **startup_health(samples))
        time.sleep(min(.25, budget - elapsed))


def startup_health(samples):
    """A later stable segment cannot erase an observed positive-clock freeze."""
    frozen, maximum = 0.0, 0.0
    discontinuities, gaps = 0, 0
    for first, last in zip(samples, samples[1:]):
        wall = last['wall'] - first['wall']
        if wall > 2:
            gaps += 1
        if (first.get('phase') != 'AV_STARTED' or last.get('phase') != 'AV_STARTED'
                or first.get('seconds', -1) < 0 or last.get('seconds', -1) < 0):
            frozen = 0.0
            continue  # Preserve, but do not misinterpret the negative initial sentinel.
        advance = last['seconds'] - first['seconds']
        frames = decoder_frame_pair(first, last)
        if (advance < -.03 or (all(type(value) is int for value in frames) and frames[1] < frames[0])
                or any(r['reset'] for r in decoder_intervals(first, last))):
            discontinuities += 1
        if advance > wall + max(.3, wall * .3):
            discontinuities += 1
        stalled = (advance <= .03 or last.get('caching') is True or last.get('speed') != 1
                   or all(type(value) is int for value in frames) and frames[1] == frames[0])
        frozen = frozen + max(0, wall) if stalled else 0.0
        maximum = max(maximum, frozen)
    return dict(no_observed_stall=maximum < 1 and not discontinuities and not gaps,
                max_observed_stall_seconds=maximum, clock_discontinuities=discontinuities,
                observation_gaps=gaps, stall_threshold_seconds=1)


def startup_signal_diagnostics(samples):
    """Separate observed signals without weakening/replacing the legacy verdict.

    Decoder progress is not proof of rendered frames, and a clock catch-up is
    not proof of a seek. Keep those distinctions and acquisition gaps explicit.
    Runs describe endpoint observations, not exact transition timestamps.
    """
    from math import isfinite
    def number(value):
        return type(value) in (int, float) and isfinite(value)
    runs = {name: [] for name in ('caching_sample_runs', 'stationary_decoder_with_caching_runs',
                                  'stationary_clock_with_decoder_progress_runs')}
    gaps, steps, resets = [], [], []
    def extend(name, index, first, last):
        entries = runs[name]
        if entries and entries[-1]['last_index'] == index:
            entries[-1].update(last_index=index + 1, last_wall=last['wall'])
        else:
            entries.append(dict(first_index=index, last_index=index + 1,
                                first_wall=first['wall'], last_wall=last['wall']))
        entries[-1]['wall_seconds'] = entries[-1]['last_wall'] - entries[-1]['first_wall']
    for index, (first, last) in enumerate(zip(samples, samples[1:])):
        if not all(number(row.get('wall')) for row in (first, last)):
            continue
        wall = last['wall'] - first['wall']
        if wall > 2:
            gaps.append(dict(first_index=index, last_index=index + 1, wall_seconds=wall,
                             first_phase=first.get('phase'), last_phase=last.get('phase')))
        if not 0 < wall <= 2:
            continue  # Do not convert an unobserved interval into an observed run.
        if any(row.get('phase') != 'AV_STARTED' or not number(row.get('seconds'))
               or row['seconds'] < 0 for row in (first, last)):
            continue
        identity = ('native_instance', 'request_id')
        bindings = [tuple((row.get('native') or {}).get(key) for key in identity) for row in (first, last)]
        if not all(bindings[0]) or bindings[0] != bindings[1]:
            continue
        advance = last['seconds'] - first['seconds']
        frames = decoder_frame_pair(first, last)
        counts = all(type(value) is int and value >= 0 for value in frames)
        if advance < -.03 or advance > wall + max(.3, wall * .3):
            steps.append(dict(first_index=index, last_index=index + 1, wall_seconds=wall,
                              media_seconds=advance, direction='backward' if advance < 0 else 'forward',
                              decoder_advanced=counts and frames[1] > frames[0],
                              meaning='CLOCK_STEP_NOT_SEEK_PROOF'))
        if (counts and frames[1] < frames[0]) or any(r['reset'] for r in decoder_intervals(first, last)):
            resets.append(dict(first_index=index, last_index=index + 1))
        caching = all(row.get('caching') is True for row in (first, last))
        if caching:
            extend('caching_sample_runs', index, first, last)
        if caching and counts and frames[1] == frames[0]:
            extend('stationary_decoder_with_caching_runs', index, first, last)
        if (abs(advance) <= .03 and counts and frames[1] > frames[0]
                and all(row.get('caching') is False and row.get('speed') == 1 for row in (first, last))):
            extend('stationary_clock_with_decoder_progress_runs', index, first, last)
    return dict(runs, observation_gap_events=gaps, clock_step_events=steps,
                decoder_counter_reset_events=resets, changes_legacy_result=False,
                decoder_channel_intervals=[dict(first_index=i, last_index=i+1, channels=decoder_intervals(a, b))
                                           for i, (a, b) in enumerate(zip(samples, samples[1:]))],
                render_continuity_proven=False, exact_transition_times_proven=False)


def request_status(record, desired):
    """A previous cancelled source is history, not this new picker's failure."""
    category = (desired.get('resolver_failure') or {}).get('category')
    current = bool(record.get('request_id')) and desired.get('request_id') == record['request_id']
    return dict(cancelled=desired.get('cancelled') if current else None,
                failure=category if current else None,
                prior_failure=category if not current else None)


def sample(record):
    observation_times = dict(sample_started=time.monotonic())
    authority, native, row = state(record)
    desired = authority.get('desired') or {}
    value = dict(wall=time.monotonic(), phase=row.get('phase'), native=row,
                 **request_status(record, desired))
    active = rpc('Player.GetActivePlayers')
    if active and row.get('phase') == 'AV_STARTED':
        observation_times['player_time_started'] = time.monotonic()
        properties = rpc('Player.GetProperties', dict(playerid=1, properties=['time', 'totaltime', 'speed',
            'subtitleenabled', 'currentsubtitle', 'currentvideostream', 'currentaudiostream']))
        observation_times['player_time_completed'] = time.monotonic()
        value['seconds'] = seconds(properties.pop('time'))
        value['duration'] = seconds(properties.pop('totaltime'))
        value.update(properties)
        observation_times['caching_started'] = time.monotonic()
        value['caching'] = rpc('XBMC.GetInfoBooleans', {'booleans': ['Player.Caching']})['Player.Caching']
        observation_times['caching_completed'] = time.monotonic()
    labels = ['Container(1000).ListItem.Label', 'Container(1000).NumItems',
              'Container(1000).ListItem.Property(source_site)', 'Window(10000).Property(AM6B.SubtitleState)',
              'Window.Property(playback_error)', 'Window.Property(source_count)']
    value['labels'] = rpc('XBMC.GetInfoLabels', {'labels': labels})
    value['window'] = rpc('GUI.GetProperties', {'properties': ['currentwindow']})
    observation_times['decoder_started'] = time.monotonic()
    decoder=Path('/sys/class/vdec/vdec_status').read_text()
    observation_times['decoder_completed'] = time.monotonic()
    value['decoder'] = decoder_snapshot(decoder, observation_times['decoder_started'],
                                        observation_times['decoder_completed'])
    primary = next((r for r in value['decoder']['channels']
                    if r['channel'] == value['decoder']['primary_channel']), None)
    value['decoder_counters'] = primary['counters'] if primary else {}
    value['decoder_counter_source'] = (dict(channel=primary['channel'], device=primary['device'])
                                       if primary else None)
    observation_times['sample_completed'] = time.monotonic()
    value['observation_times'] = observation_times
    return value


def startup_coverage(samples, health):
    """Coverage is additional to, never a replacement for, the old predicate."""
    from copy import deepcopy
    from math import isfinite
    def valid(value):
        return type(value) in (int, float) and isfinite(value)
    def positive(row):
        return (row.get('phase') == 'AV_STARTED' and valid(row.get('seconds'))
                and row['seconds'] >= 0 and valid(row.get('wall')))
    av = [row for row in samples if row.get('phase') == 'AV_STARTED']
    points = [row for row in av if positive(row)]
    pairs, span, longest = 0, 0.0, 0.0
    for first, last in zip(samples, samples[1:]):
        if positive(first) and positive(last) and last['wall'] > first['wall']:
            pairs += 1
            span += last['wall'] - first['wall']
            longest = max(longest, span)
        else:
            span = 0.0
    result = dict(legacy_health=deepcopy(health), av_sample_count=len(av),
        positive_av_sample_count=len(points), positive_adjacent_interval_count=pairs,
        longest_contiguous_positive_av_span_seconds=longest,
        whole_startup_or_render_continuity_proven=False)
    if pairs and health.get('no_observed_stall') is False:
        result.update(status='observed_anomaly', reason='ORIGINAL_HEALTH_FAILURE_PRESERVED', passed=False)
    elif not av:
        result.update(status='not_covered', reason='NO_AV_STARTED_WITHIN_CAPTURE', passed=None)
    elif not pairs or longest < health.get('stall_threshold_seconds', 1):
        result.update(status='not_covered', reason='INSUFFICIENT_POSITIVE_AV_INTERVALS', passed=None)
    elif health.get('no_observed_stall') is True:
        result.update(status='no_anomaly_in_observed_window', reason='BOUNDED_OBSERVATION_ONLY', passed=True)
    else:
        result.update(status='not_covered', reason='HEALTH_RECEIPT_UNAVAILABLE', passed=None)
    return result


PICKER_WINDOWS = (13001, 13002)
RETIRING_WINDOWS = PICKER_WINDOWS + (12002,)
PICKER_LABELS = (
    'Window.Property(info.ids)', 'Window.Property(info.media_type)', 'Window.Property(info.mode)',
    'Window.Property(info.tv_data)', 'Window.Property(info.year)', 'Window.Property(info.query)',
    'Window.Property(source_count)', 'Window.Property(playback_error)', 'Window.Property(source_loading)',
)


def gui_observation():
    """Bracket labels/window reads with native generations; never trust a torn view."""
    before = rpc('Player.BobiState')
    window = rpc('GUI.GetProperties', {'properties': ['currentwindow']})['currentwindow']['id']
    keys = ['System.HasModalDialog'] + ['Window.IsVisible({})'.format(i) for i in RETIRING_WINDOWS]
    visible = rpc('XBMC.GetInfoBooleans', {'booleans': keys})
    assert all(type(visible.get(key)) is bool for key in keys), 'WINDOW_RECEIPT_UNAVAILABLE'
    labels = rpc('XBMC.GetInfoLabels', {'labels': list(PICKER_LABELS)})
    after = rpc('Player.BobiState')
    generation, intent = after.get('gui_generation'), after.get('gui_user_intent')
    assert (type(generation) is int and generation >= 0 and type(intent) is int and intent >= 0
            and type(window) is int), 'GUI_RECEIPT_UNAVAILABLE'
    return dict(window=window, generation=generation, intent=intent, labels=labels,
        modal=visible.get('System.HasModalDialog') is True,
        visible=[i for i in RETIRING_WINDOWS if visible.get('Window.IsVisible({})'.format(i)) is True],
        stable=(before.get('gui_generation') == generation and before.get('gui_user_intent') == intent))


def assert_picker_idle(record):
    assert rpc('Player.GetActivePlayers') == [], 'UNEXPECTED_PLAYBACK'
    desired = snapshot().get('desired') or {}
    assert desired.get('request_id') == record.get('prior_request'), 'USER_CHANGED_SELECTION'
    assert not desired or desired.get('cancelled'), 'UNEXPECTED_SELECTION'


def prepare_home(record, timeout=8):
    """One Back only for the known old dialog, then observed closure and stable Home."""
    deadline = time.monotonic() + timeout
    initial = gui_observation()
    while not initial['stable'] and time.monotonic() < deadline:
        time.sleep(.1)
        initial = gui_observation()
    assert initial['stable'], 'UNSTABLE_GUI'
    assert_picker_idle(record)
    retiring = initial['window'] in RETIRING_WINDOWS or bool(initial['visible'])
    assert not initial['modal'] or initial['window'] in RETIRING_WINDOWS, 'UNOWNED_MODAL'
    if retiring:
        rpc('Input.Back')
    while time.monotonic() < deadline:
        assert_picker_idle(record)
        view = gui_observation()
        if (view['stable'] and not view['visible'] and not view['modal']
                and view['window'] not in RETIRING_WINDOWS
                and (not retiring or view['generation'] > initial['generation'])):
            break
        time.sleep(.1)
    else:
        raise AssertionError('OLD_WINDOW_NOT_RETIRED')
    if view['window'] != 10000:
        rpc('Input.Home')
    previous = None
    while time.monotonic() < deadline:
        assert_picker_idle(record)
        view = gui_observation()
        key = (view['generation'], view['intent'])
        if view['stable'] and view['window'] == 10000 and not view['modal'] and not view['visible']:
            if key == previous:
                return dict(generation=view['generation'], intent=view['intent'],
                            retired_generation=initial['generation'], observed_at=time.monotonic())
            previous = key
        else:
            previous = None
        time.sleep(.1)
    raise AssertionError('HOME_NOT_STABLE')


def property_dict(value):
    if not isinstance(value, str) or not value or len(value) > 4096:
        return {}
    try:
        result = ast.literal_eval(value)
    except (ValueError, SyntaxError, TypeError):
        return {}
    return result if isinstance(result, dict) else {}


def picker_identity(view, test):
    labels = view['labels']
    ids = property_dict(labels.get('Window.Property(info.ids)'))
    if not ids or not labels.get('Window.Property(source_count)'):
        return False  # The newly created window may not have populated yet.
    assert str(ids.get('tmdb_id')) == str(test['tmdb_id']), 'PICKER_MEDIA_MISMATCH'
    kind = labels.get('Window.Property(info.media_type)')
    mode = labels.get('Window.Property(info.mode)')
    assert kind == test['kind'] or (not kind and mode == ('movies' if test['kind'] == 'movie' else 'tv')), 'PICKER_KIND_MISMATCH'
    if test['kind'] == 'tv':
        episode = property_dict(labels.get('Window.Property(info.tv_data)'))
        assert all(str(episode.get(k)) == str(test[k]) for k in ('season', 'episode')), 'PICKER_EPISODE_MISMATCH'
    return True


def bind_picker(record, view):
    home = record['home']
    if (not view['stable'] or view['window'] not in PICKER_WINDOWS
            or view['window'] not in view['visible'] or view['generation'] <= home['generation']):
        return False
    assert view['intent'] == home['intent'], 'GUI_USER_INTENT_CHANGED'
    if not picker_identity(view, record['test']):
        return False
    binding = dict(window=view['window'], generation=view['generation'], intent=view['intent'],
                   tmdb_id=record['test']['tmdb_id'], kind=record['test']['kind'])
    if record.get('picker'):
        assert record['picker'] == binding, 'PICKER_REPLACED'
    else:
        record['picker'] = binding
        record['picker_observed_at'] = time.monotonic()
        save(record)
    return True


def require_picker(record):
    assert record.get('picker'), 'NEW_PICKER_NOT_OBSERVED'
    assert_picker_idle(record)
    view = gui_observation()
    assert bind_picker(record, view), 'PICKER_NOT_CURRENT'
    return view


def rewind_picker(record, timeout=3):
    """Every traversal starts at observed item 1, even on a non-wrapping list."""
    assert 0 < timeout <= 3, 'PICKER_REWIND_SCOPE'
    require_picker(record)
    subprocess.run([shutil.which('kodi-send'), '--action=SetFocus(1000)'],
                   check=True, timeout=3, stdout=subprocess.DEVNULL)
    deadline = time.monotonic() + timeout
    sent = False
    labels = ['Container(1000).CurrentItem', 'Container(1000).NumItems']
    while time.monotonic() < deadline:
        require_picker(record)
        focused = rpc('XBMC.GetInfoBooleans', {'booleans': ['Control.HasFocus(1000)']})
        if focused.get('Control.HasFocus(1000)') is True:
            if not sent:
                require_picker(record)
                rpc('Input.ExecuteAction', {'action': 'firstpage'})
                sent = True
            require_picker(record)
            position = rpc('XBMC.GetInfoLabels', {'labels': labels})
            require_picker(record)
            count = position.get(labels[1], '')
            if position.get(labels[0]) == '1' and isinstance(count, str) and count.isdigit() and int(count) > 0:
                return dict(current_item=1, item_count=int(count), reset_action='firstpage')
        time.sleep(.1)
    raise AssertionError('PICKER_FIRST_ITEM_NOT_OBSERVED')


def wait_picker_idle(record, duration=35):
    """Read-only >30s proof: no Select, playback command or navigation is issued."""
    assert type(duration) in (int, float) and 30 < duration <= 40, 'PICKER_WAIT_SCOPE'
    began = time.monotonic()
    observations = 0
    while True:
        view = require_picker(record)
        observations += 1
        elapsed = time.monotonic() - began
        if elapsed >= duration:
            result = dict(passed=True, seconds=elapsed, observations=observations,
                          picker=record['picker'], query_finished=view['labels'].get('Window.Property(source_loading)') == 'false')
            record['picker_idle'] = result
            save(record)
            return result
        time.sleep(min(.5, duration - elapsed))


def checked_trial_metadata(test, data):
    import unicodedata
    import re
    def normalized(text):
        text=''.join(c for c in unicodedata.normalize('NFKD',text) if not unicodedata.combining(c))
        return ' '.join(re.findall(r'[^\W_]+',text.casefold()))
    field, date = ('title','release_date') if test['kind']=='movie' else ('name','first_air_date')
    assert isinstance(data,dict) and data.get('id')==test['tmdb_id'], 'TRIAL_METADATA_ID_MISMATCH'
    assert normalized(test['title']) in {normalized(str(data.get(k) or '')) for k in (field,'original_'+field)}, 'TRIAL_METADATA_TITLE_MISMATCH'
    assert str(data.get(date,'')).startswith(str(test['year'])+'-'), 'TRIAL_METADATA_YEAR_MISMATCH'
    assert not test.get('animation') or 16 in [v.get('id') for v in data.get('genres',[])], 'TRIAL_NOT_ANIMATION'
    return {key:data.get(key) for key in ('id',field,'original_'+field,'original_language',date)}


def trial_metadata(test):
    from bobbi_core.project_metadata import tmdb_key
    from bobbi_core.metadata_transport import fetch
    key=tmdb_key()
    assert key, 'TRIAL_APPLICATION_CONFIG_MISSING'
    result=fetch('https://api.themoviedb.org/3/'+test['kind']+'/'+str(test['tmdb_id'])+'?'+urlencode(
        dict(api_key=key,language='en-US')),time.monotonic()+12)
    assert result['status']==200, 'TRIAL_METADATA_UNAVAILABLE'
    verified=checked_trial_metadata(test,json.loads(result['body']))
    return dict(verified=verified,route=result['route'],checked_at=time.time())


if OP in ('start','requery'):
    assert rpc('Player.GetActivePlayers') == [], 'ACTIVE_PLAYER'
    initial = snapshot()
    desired = initial.get('desired') or {}
    assert not desired or desired.get('cancelled'), 'ACTIVE_SELECTION'
    if OP=='start':assert not record_path.exists(), 'TRIAL_ALREADY_STARTED'
    else:assert record_path.exists() and not json.loads(record_path.read_text()).get('request_id'), 'OPEN_REQUEST_EXISTS'
    test = TESTS[NAME]
    verified = trial_metadata(test)  # Before any GUI change; no guessed work identities.
    record = dict(test=test, metadata_verification=verified, prior_request=desired.get('request_id'), started=time.monotonic())
    save(record)
    record['home'] = prepare_home(record)
    record['picker_mode'] = globals().get('PICKER') is True
    record['ordinary_ui'] = globals().get('ORDINARY_UI') is True
    record['force_select'] = record['picker_mode'] and not record['ordinary_ui']
    record['launch_mode'] = ('ordinary_ui' if record['ordinary_ui'] else
                             'forced_picker' if record['picker_mode'] else 'legacy_unforced')
    params = dict(action='search', query=test['title'], year=str(test['year']),
        mode='movies' if test['kind']=='movie' else 'tv', media_type=test['kind'],
        ids=json.dumps(dict(tmdb_id=test['tmdb_id'])),
        tv_data=json.dumps({k:test[k] for k in ('season','episode') if k in test}), skip_cancel_on_back='true')
    if globals().get('START_OVER') is True:
        params['_bobi_start_over']='true'
        record['explicit_start_over']=True
    if globals().get('RESUME_PERCENT') is not None:
        percent = RESUME_PERCENT
        assert type(percent) in (int,float) and 0 < percent < 100, 'RESUME_SCOPE'
        params['_bobi_resume_percent'] = str(percent)
        record['explicit_resume_percent'] = percent
    url = 'plugin://plugin.video.bobbi/?' + urlencode(params)
    if record['force_select']:
        url += '&force_select=true'
    record['launched_at'] = time.monotonic()
    save(record)
    subprocess.run([shutil.which('kodi-send'), '--action=RunPlugin(' + url + ')'],
                   check=True, timeout=4, stdout=subprocess.DEVNULL)
    samples=[]
    while time.monotonic() - record['launched_at'] < 28:
        if record['picker_mode']:
            assert_picker_idle(record)
            view = gui_observation()
            bound = bind_picker(record, view)
        current=sample(record)
        samples.append(current)
        if record['picker_mode']:
            assert not record.get('request_id'), 'UNEXPECTED_SELECTION'
            if bound and view['labels'].get('Window.Property(source_loading)') == 'false':
                break
        if record.get('request_id') and (current.get('phase')=='AV_STARTED' or current.get('failure') or current.get('cancelled')):
            break
        time.sleep(2)
    if record['picker_mode']:
        require_picker(record)
    print(json.dumps(dict(name=NAME, operation=OP, record=record, samples=samples), ensure_ascii=True))
else:
    record=json.loads(record_path.read_text())
    assert record.get('test') == TESTS[NAME], 'TRIAL_MEDIA_MISMATCH'
    if OP=='cancel':
        authority,native,row=state(record)
        assert record.get('request_id') and (authority.get('desired') or {}).get('request_id')==record['request_id']
        if rpc('GUI.GetProperties',{'properties':['currentwindow']})['currentwindow']['id']==10138:
            rpc('Input.Back')
        result=call(dict(operation='cancel',boot_id=authority['boot_id'],epoch=authority['epoch'],request_id=record['request_id']))
        assert result.get('cancelled') is True
        print(json.dumps(dict(name=NAME,operation=OP,cancelled=True,request_id=record['request_id'])))
    elif OP in ('cards','select'):
        traversal_start = rewind_picker(record)
        labels=['Container(1000).ListItem.Label','Container(1000).ListItem.Property(source_site)',
                'Container(1000).ListItem.Property(resolution)','Container(1000).ListItem.Property(size)',
                'Container(1000).ListItem.Property(subtitle_badge)',
                'Container(1000).ListItem.Property(source_key)']
        cards=[]
        chosen=False
        for _ in range(60 if OP=='select' else 20):
            require_picker(record)
            card=rpc('XBMC.GetInfoLabels',{'labels':labels})
            if (OP=='select' and card[labels[0]]==TITLE and card[labels[1]]==SITE
                    and (globals().get('SOURCE_KEY') is None or card[labels[-1]]==SOURCE_KEY)):
                assert not record.get('request_id'), 'REQUEST_ALREADY_STARTED'
                require_picker(record)
                assert rpc('XBMC.GetInfoLabels',{'labels':labels}) == card, 'CARD_CHANGED'
                record['selected_card']=card
                record['selected_at']=time.monotonic()
                save(record)
                rpc('Input.Select');chosen=True
                break
            if card in cards:break
            cards.append(card)
            rpc('Input.Down');time.sleep(.1)
        trace=[]
        if chosen and globals().get('TRACE') is True:
            # One uninterrupted, bounded acquisition starts immediately after
            # Select. Separate tool-call latency must not hide subtitle startup.
            deadline=time.monotonic()+40
            while time.monotonic()<deadline:
                began=time.monotonic()
                current=sample(record)
                # Keep every temporal/ownership sample, but omit repeated GUI
                # labels and static stream metadata from the bounded transport.
                compact={key:current[key] for key in ('wall','phase','seconds','speed','caching','observation_times',
                    'cancelled','failure','subtitleenabled','decoder_counters','decoder_counter_source','decoder') if key in current}
                compact['native']={key:current.get('native',{}).get(key) for key in (
                    'native_instance','request_id','subtitle_file_applied','subtitle_file_sha256',
                    'subtitle_intent','user_intent','sequence')}
                trace.append(compact)
                time.sleep(max(0,min(.5-(time.monotonic()-began),deadline-time.monotonic())))
        result=dict(name=NAME,operation=OP,cards=cards if OP=='cards' else [],selected=chosen, picker_start=traversal_start,
                    samples=trace,record=record if trace else None)
        if trace:
            result['trace_health']=startup_health(trace)
            result['trace_signal_diagnostics']=startup_signal_diagnostics(trace)
            result['trace_coverage']=startup_coverage(trace, result['trace_health'])
            result['trace_passed']=result['trace_coverage']['passed'] is True
            with record_path.with_suffix('.startup.json').open('x') as output:
                json.dump(result,output)
        print(json.dumps(result,ensure_ascii=True))
    elif OP=='picker_wait':
        result = wait_picker_idle(record, globals().get('DURATION', 35))
        print(json.dumps(dict(name=NAME, operation=OP, record=record, **result), ensure_ascii=True))
    elif OP=='wait':
        began=time.monotonic()
        samples=[]
        while time.monotonic()-began<28:
            current=sample(record)
            samples.append(current)
            if record.get('request_id') and (current.get('phase')=='AV_STARTED' or current.get('failure') or current.get('cancelled')):break
            time.sleep(2)
        print(json.dumps(dict(name=NAME, operation=OP, record=record, samples=samples),ensure_ascii=True))
    elif OP=='inspect':
        print(json.dumps(dict(name=NAME, operation=OP, record=record, sample=sample(record), gui=gui_observation()), ensure_ascii=True))
    elif OP=='stop':
        from uuid import uuid4
        _, native, row = state(record, require=True)
        before=sample(record)
        result=rpc('Player.BobiControl', dict(native_instance=row['native_instance'], user_intent=row['user_intent'],
            expected_sequence=row['sequence'], selection_epoch=native['selection_epoch'], action='stop', command_id=uuid4().hex))
        assert result.get('queued') is True
        began=time.monotonic()
        while time.monotonic()-began<12 and rpc('Player.GetActivePlayers'): time.sleep(.25)
        print(json.dumps(dict(name=NAME, operation=OP, stopped=rpc('Player.GetActivePlayers')==[],
                              before=before, seconds=round(time.monotonic()-began,2))))
    elif OP in ('seek','manual_off','font_switch'):
        print(json.dumps(dict(name=NAME, **unsupported_control_evidence(record, OP)), ensure_ascii=True))
    elif OP=='observe':
        _, native, row=state(record, require=True)
        target=None
        settle=[]
        startup=bounded_clock_start(record)
        samples=[]
        began=time.monotonic()
        for index in range(4):
            samples.append(sample(record))
            if index<3:time.sleep(10)
        first,last=samples[0],samples[-1]
        wall=last['wall']-first['wall']
        advance=last.get('seconds',0)-first.get('seconds',0)
        passed=(startup['stable'] and startup['no_observed_stall']
                and all(s.get('phase')=='AV_STARTED' and s.get('speed')==1 and not s.get('caching') for s in samples)
                and wall-2 <= advance <= wall+2)
        print(json.dumps(dict(name=NAME, operation=OP, target=target, settle=settle, samples=samples, passed=passed,
            startup_clock=startup, record=record,
            start_timing_note='Select-to-first-AV is an observed upper bound, not an exact native event timestamp; startup samples remain separate',
            wall_seconds=round(wall,3), play_seconds=round(advance,3),
            decoder=Path('/sys/class/vdec/vdec_status').read_text()[:3000],
            crashes=sorted(p.name for p in Path('/storage/.kodi/temp').glob('kodi_crashlog*'))[-4:]),ensure_ascii=True))
