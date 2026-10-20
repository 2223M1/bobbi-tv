"""Real Windows ordinary-search trials, with expected picker/player ownership.

Reuse the reviewed CE ownership predicates, not CE transports or hardware claims.
No video/CDN prefetch, account exchange, cloud mutation, transcoding or autoselect.
"""
import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import sys
import time
import traceback
from urllib.parse import urlencode
import urllib.request
from uuid import uuid4
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
INSTALLED = Path(os.environ.get('BOBBI_VALIDATION_INSTALL', str(ROOT / 'native/build/windows-installer-1903'))).resolve()
PROFILE = INSTALLED / 'profile'
assert json.loads((PROFILE / 'validation-profile.json').read_text(encoding='utf-8')) == {
    'schema': 1, 'installed': str(INSTALLED), 'test_profile': True}, 'NOT_A_VALIDATION_PROFILE'
BUILD = json.loads((INSTALLED / 'bobbi-build.json').read_text(encoding='utf-8'))
BASE = PROFILE / 'validation-trials'
BASE.mkdir(exist_ok=True)
RPC_AUTH = json.loads((PROFILE / 'validation-rpc.json').read_text(encoding='utf-8'))
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def rpc(method, params=None):
    authorization = base64.b64encode((RPC_AUTH['username'] + ':' + RPC_AUTH['password']).encode()).decode()
    request = urllib.request.Request('http://127.0.0.1:%d/jsonrpc' % RPC_AUTH['port'],
        data=json.dumps(dict(jsonrpc='2.0', id=1903, method=method, params=params or {})).encode(),
        headers={'Content-Type': 'application/json', 'Authorization': 'Basic ' + authorization})
    with OPENER.open(request, timeout=5) as response:
        value = json.load(response)
    if 'error' in value:
        raise RuntimeError('RPC_FAILURE_' + str(value['error'].get('code')))
    return value['result']


def host_call(message):
    config = json.loads((PROFILE / 'userdata/addon_data/script.module.bobbi.platform/runtime.json').read_text())
    request = urllib.request.Request('http://127.0.0.1:%d/control' % config['port'],
        data=json.dumps(dict(action='playback', body=message)).encode(),
        headers={'Authorization': 'Bearer ' + config['token'], 'Content-Type': 'application/json'})
    with OPENER.open(request, timeout=.8) as response:
        value = json.load(response)
    assert value.get('ok') is True, 'HOST_REQUEST_FAILED'
    return value['result']


def event(action):
    sys.path.insert(0, str(ROOT / 'native/.work/kodi/tools/EventClients/lib/python'))
    from xbmcclient import PacketACTION, ACTION_BUTTON
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as channel:
        PacketACTION(actionmessage=action, actiontype=ACTION_BUTTON).send(channel, ('127.0.0.1', 9777), uid=0)


helper_path = ROOT / 'tools/ce_trial_remote.py'
helper = ast.parse(helper_path.read_text(encoding='utf-8'))
selected = [node for node in helper.body if isinstance(node, (ast.Import, ast.ImportFrom, ast.FunctionDef))
            or isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id in
                ('PICKER_WINDOWS', 'RETIRING_WINDOWS', 'PICKER_LABELS') for target in node.targets)]
helpers = dict(__name__='windows_trial_ownership')
exec(compile(ast.Module(body=selected, type_ignores=[]), str(helper_path), 'exec'), helpers)
# Fresh Windows starts its first WindowXMLDialog at 13000; CE's existing
# profile starts at 13001. Exact media/window-generation guards remain required.
helpers.update(rpc=rpc, call=host_call, BASE=BASE,
               PICKER_WINDOWS=(13000, 13001, 13002), RETIRING_WINDOWS=(13000, 13001, 13002, 12002))


def sample(record):
    authority, native, row = helpers['state'](record)
    desired = authority.get('desired') or {}
    value = dict(wall=time.monotonic(), phase=row.get('phase'), native=row,
                 cancelled=desired.get('cancelled'), failure=(desired.get('resolver_failure') or {}).get('category'))
    value['native_gui'] = {key: native.get(key) for key in
        ('selection_epoch', 'gui_generation', 'gui_user_intent', 'fullscreen_instance', 'windows')}
    value['dialogs'] = rpc('XBMC.GetInfoBooleans', {'booleans':
        ['System.HasModalDialog', 'Window.IsVisible(10138)', 'Window.IsVisible(13000)', 'Window.IsVisible(13001)']})
    if rpc('Player.GetActivePlayers') and row.get('phase') == 'AV_STARTED':
        props = rpc('Player.GetProperties', dict(playerid=1, properties=['time', 'totaltime', 'speed',
            'subtitleenabled', 'currentsubtitle', 'currentvideostream', 'currentaudiostream']))
        value.update(seconds=helpers['seconds'](props.pop('time')),
                     duration=helpers['seconds'](props.pop('totaltime')), **props)
        value['caching'] = rpc('XBMC.GetInfoBooleans', {'booleans': ['Player.Caching']})['Player.Caching']
    value['window'] = rpc('GUI.GetProperties', {'properties': ['currentwindow']})
    value['labels'] = rpc('XBMC.GetInfoLabels', {'labels': [
        'Window(10000).Property(AM6B.SubtitleState)', 'Window.Property(playback_error)',
        'Window.Property(source_count)', 'Player.Process(videodecoder)', 'Player.Process(videowidth)',
        'Player.Process(videoheight)', 'Player.Process(pixformat)', 'Player.Process(audiodecoder)']})
    return value


helpers['sample'] = sample


def rewind(record):
    helpers['require_picker'](record)
    event('SetFocus(1000)')
    deadline, sent = time.monotonic() + 3, False
    while time.monotonic() < deadline:
        helpers['require_picker'](record)
        if rpc('XBMC.GetInfoBooleans', {'booleans': ['Control.HasFocus(1000)']}).get('Control.HasFocus(1000)'):
            if not sent:
                rpc('Input.ExecuteAction', {'action': 'firstpage'})
                sent = True
            position = rpc('XBMC.GetInfoLabels', {'labels': ['Container(1000).CurrentItem', 'Container(1000).NumItems']})
            if position.get('Container(1000).CurrentItem') == '1':
                return position
        time.sleep(.1)
    raise AssertionError('FIRST_CARD_NOT_OBSERVED')


def metadata():
    settings = ET.parse(PROFILE / 'userdata/addon_data/plugin.video.bobbi/settings.xml').getroot()
    node = settings.find("setting[@id='tmdb_api_key']")
    key = (node.text or node.get('value', '')).strip() if node is not None else ''
    assert key, 'PERSONAL_TMDB_KEY_NOT_CONFIGURED'

    def query(path, **params):
        url = 'https://api.themoviedb.org/3/' + path + '?' + urlencode(dict(api_key=key, **params))
        try:
            with OPENER.open(url, timeout=12) as response:
                return json.load(response)
        except Exception:
            raise RuntimeError('METADATA_FETCH_FAILED') from None

    movie = query('movie/60243', language='en-US')
    assert movie['title'] == 'A Separation' and movie['release_date'].startswith('2011-'), 'MOVIE_IDENTITY_MISMATCH'
    found = query('search/tv', query='Haibane Renmei', language='en-US')
    rows = [row for row in found['results'] if row.get('name') == 'Haibane Renmei'
            and row.get('first_air_date', '').startswith('2002-')]
    assert len(rows) == 1, 'TV_IDENTITY_AMBIGUOUS'
    tv = query('tv/' + str(rows[0]['id']), language='en-US')
    season = query('tv/%d/season/1' % tv['id'], language='en-US')
    assert any(row['episode_number'] == 1 for row in season['episodes']), 'EPISODE_NOT_FOUND'
    tests = {'a_separation': dict(title=movie['title'], tmdb_id=movie['id'], kind='movie', year=2011),
             'haibane_renmei': dict(title=tv['name'], tmdb_id=tv['id'], kind='tv', year=2002, season=1, episode=1)}
    alternate = query('search/tv', query='Den-noh Coil', language='en-US')
    rows = [row for row in alternate['results'] if row.get('name') in ('Den-noh Coil', 'Dennou Coil')
            and row.get('first_air_date', '').startswith('2007-')]
    assert len(rows) == 1, 'ALTERNATE_TV_IDENTITY_AMBIGUOUS'
    alternate_tv = query('tv/' + str(rows[0]['id']), language='en-US')
    alternate_season = query('tv/%d/season/1' % alternate_tv['id'], language='en-US')
    assert any(row['episode_number'] == 1 for row in alternate_season['episodes']), 'ALTERNATE_EPISODE_NOT_FOUND'
    tests['dennou_coil'] = dict(title=alternate_tv['name'], tmdb_id=alternate_tv['id'],
        kind='tv', year=2007, season=1, episode=1)
    (BASE / 'works.json').write_text(json.dumps(tests, ensure_ascii=False, indent=2), encoding='utf-8')
    return dict(works=tests, metadata_fetched=True, personal_key_printed=False,
                anime_original_name=tv.get('original_name'), season_episode_count=len(season['episodes']),
                alternate_anime_original_name=alternate_tv.get('original_name'),
                alternate_season_episode_count=len(alternate_season['episodes']))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['metadata', 'start', 'bind', 'cards', 'picker_wait', 'select', 'inspect', 'observe', 'stop'])
    parser.add_argument('--work', choices=['a_separation', 'haibane_renmei', 'dennou_coil'])
    parser.add_argument('--key')
    parser.add_argument('--attempt', type=int, choices=range(1, 9), default=1)
    args = parser.parse_args()
    if args.operation == 'metadata':
        return metadata()
    assert args.work, 'WORK_REQUIRED'
    tests = json.loads((BASE / 'works.json').read_text(encoding='utf-8'))
    test = tests[args.work]
    record_path = BASE / ('trial-' + args.work + ('' if args.attempt == 1 else '-' + str(args.attempt)) + '.json')
    helpers['record_path'] = record_path
    if args.operation == 'start':
        assert not record_path.exists(), 'TRIAL_ALREADY_EXISTS'
        assert rpc('Player.GetActivePlayers') == [], 'ACTIVE_PLAYBACK'
        desired = helpers['snapshot']().get('desired') or {}
        assert not desired or desired.get('cancelled'), 'ACTIVE_SELECTION'
        record = dict(test=test, prior_request=desired.get('request_id'), started=time.monotonic(),
                      ordinary_ui=True, force_select=False, helper_sha256=hashlib.sha256(helper_path.read_bytes()).hexdigest())
        helpers['save'](record)
        record['home'] = helpers['prepare_home'](record)
        params = dict(action='search', query=test['title'], year=str(test['year']),
            mode='movies' if test['kind'] == 'movie' else 'tv', media_type=test['kind'],
            ids=json.dumps(dict(tmdb_id=test['tmdb_id'])),
            tv_data=json.dumps({k: test[k] for k in ('season', 'episode') if k in test}), skip_cancel_on_back='true')
        record['launched_at'] = time.monotonic()
        helpers['save'](record)
        event('RunPlugin(plugin://plugin.video.bobbi/?' + urlencode(params) + ')')
        observations = []
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            helpers['assert_picker_idle'](record)
            view = helpers['gui_observation']()
            bound = helpers['bind_picker'](record, view)
            observations.append(dict(wall=time.monotonic(), window=view['window'], labels=view['labels']))
            if bound and view['labels'].get('Window.Property(source_loading)') == 'false':
                break
            time.sleep(1)
        (BASE / (args.work + '-search-observations.json')).write_text(
            json.dumps(observations, ensure_ascii=False, indent=2), encoding='utf-8')
        helpers['require_picker'](record)
        return dict(record=record, observations=observations, auto_play_observed=False)
    record = json.loads(record_path.read_text(encoding='utf-8'))
    assert record['test'] == test, 'TRIAL_MEDIA_MISMATCH'
    if args.operation == 'bind':
        helpers['assert_picker_idle'](record)
        view = helpers['gui_observation']()
        assert helpers['bind_picker'](record, view), 'PICKER_NOT_CURRENT'
        return dict(record=record, view=view,
            diagnostic_note='Bind the existing exact-identity ordinary picker after accepting observed Windows dialog ID 13000; no new search or playback.')
    if args.operation == 'picker_wait':
        return helpers['wait_picker_idle'](record, 35)
    if args.operation in ('cards', 'select'):
        rewind(record)
        labels = ['Container(1000).ListItem.Label', 'Container(1000).ListItem.Property(source_site)',
            'Container(1000).ListItem.Property(resolution)', 'Container(1000).ListItem.Property(size)',
            'Container(1000).ListItem.Property(subtitle_badge)', 'Container(1000).ListItem.Property(source_key)']
        cards, selected = [], False
        for _ in range(80):
            helpers['require_picker'](record)
            card = rpc('XBMC.GetInfoLabels', {'labels': labels})
            if args.operation == 'select' and card[labels[-1]] == args.key:
                assert args.key and not record.get('request_id'), 'SELECTION_ALREADY_EXISTS'
                helpers['require_picker'](record)
                assert rpc('XBMC.GetInfoLabels', {'labels': labels}) == card, 'CARD_CHANGED'
                record.update(selected_card=card, selected_at=time.monotonic())
                helpers['save'](record)
                rpc('Input.Select')
                selected = True
                break
            if card in cards:
                break
            cards.append(card)
            rpc('Input.Down')
            time.sleep(.08)
        if args.operation == 'cards':
            return dict(cards=cards, count=len(cards))
        assert selected, 'CHOSEN_CARD_NOT_FOUND'
        trace = []
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            began = time.monotonic()
            trace.append(sample(record))
            time.sleep(max(0, min(.5 - (time.monotonic() - began), deadline - time.monotonic())))
        health = helpers['startup_health'](trace)
        return dict(selected=True, record=record, samples=trace, trace_health=health,
                    trace_coverage=helpers['startup_coverage'](trace, health),
                    decoder_frame_counts_available=False, renderer_continuity_certified=False)
    if args.operation == 'inspect':
        return dict(record=record, sample=sample(record))
    if args.operation == 'observe':
        helpers['state'](record, require=True)
        trace = []
        for index in range(31):
            trace.append(sample(record))
            if index < 30:
                time.sleep(1)
        health = helpers['startup_health'](trace)
        return dict(record=record, samples=trace, clock_health=health,
            coverage=helpers['startup_coverage'](trace, health), decoder_frame_counts_available=False,
            renderer_continuity_certified=False)
    if args.operation == 'stop':
        _, native, row = helpers['state'](record, require=True)
        before = sample(record)
        response = rpc('Player.BobiControl', dict(native_instance=row['native_instance'],
            user_intent=row['user_intent'], expected_sequence=row['sequence'],
            selection_epoch=native['selection_epoch'], action='stop', command_id=uuid4().hex))
        assert response.get('queued') is True, 'STOP_NOT_QUEUED'
        deadline = time.monotonic() + 12
        while time.monotonic() < deadline and rpc('Player.GetActivePlayers'):
            time.sleep(.25)
        return dict(stopped=rpc('Player.GetActivePlayers') == [], before=before)


if __name__ == '__main__':
    operation = sys.argv[1] if len(sys.argv) > 1 else 'unknown'
    try:
        result = main()
    except Exception as error:
        result = dict(error=type(error).__name__, reason=str(error) if isinstance(error, AssertionError) else 'TRIAL_ERROR',
            frames=[dict(function=frame.name, line=frame.lineno) for frame in traceback.extract_tb(error.__traceback__)])
    report = ROOT / 'review-evidence' / ('windows-new-work-' + operation + '-' + str(time.time_ns()) + '.json')
    result['installed_generation'] = dict(sequence=BUILD['sequence'], path=str(INSTALLED),
        frozen_build_receipt_sha256=hashlib.sha256((INSTALLED / 'bobbi-build.json').read_bytes()).hexdigest())
    checked_files = ('host/kodi.exe',
        'host/addons/plugin.video.bobbi/lib/gui/resolver_window.py',
        'host/addons/plugin.video.bobbi/lib/services/playback_control.py',
        'host/addons/script.module.bobbi.core/lib/bobbi_core/playback_authority.py')
    observed_files = {name: hashlib.sha256((INSTALLED / name).read_bytes()).hexdigest() for name in checked_files}
    result['installed_generation']['observed_validation_files'] = observed_files
    result['installed_generation']['diagnostic_or_other_overlay_files'] = [name for name, digest in observed_files.items()
        if BUILD['files'].get(name) != digest]
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    summary = {key: result[key] for key in ('error', 'reason', 'count', 'selected', 'stopped', 'works', 'season_episode_count') if key in result}
    print(json.dumps(dict(evidence=str(report), **summary), ensure_ascii=False))
    if result.get('error'):
        raise SystemExit(1)
