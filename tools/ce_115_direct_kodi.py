"""Ephemeral attended direct-CDN/sharestream diagnostic, not an installed addon.

Uses the existing host's select/bind/claim protocol and native open fence.
Does not write Bobbi history/settings or install anything. Kodi may update its
own per-file playback records and logs. No automatic restoration or retry.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import traceback
from urllib.parse import quote
from uuid import uuid4

from ce_115_direct_remote import (DiagnosticError, checked_account, control, digest, encoded, inspect,
    require, retained_tuple, safe_error)

TOOL_REVISION = 8
SHARE_DIAGNOSTICS = {'sharestream-open-range': 'open_range',
                     'sharestream-open-range-microbatch': 'open_range_microbatch',
                     'sharestream-open-range-bound-guard': 'open_range_bound_guard',
                     'sharestream-block-startup-1m': 'block_startup_1m'}
ROUTES = ('direct', 'sharestream', *SHARE_DIAGNOSTICS)


def checked_route(value):
    require(isinstance(value, str) and value in ROUTES, 'DIAGNOSTIC_SCOPE')
    return value


def error_location(error):
    """Code locations only: no messages, source text, locals or full paths."""
    return dict(error_type=type(error).__name__, error_frames=[
        dict(file=Path(frame.filename).name, function=frame.name, line=frame.lineno)
        for frame in traceback.extract_tb(error.__traceback__)[-6:]])


class HostAbort(DiagnosticError):
    """Fixed cancellation code; never an upstream or native exception body."""
    code = 'cancelled'


def check_abort(runtime):
    if runtime.abort_requested():
        raise HostAbort('HOST_ABORT_REQUESTED')


def idle(view):
    authority, native, players = view
    require(players == [], 'ACTIVE_PLAYER')
    row = native.get('playback') or {}
    require(not row or row.get('phase') == 'TERMINAL', 'NATIVE_NOT_TERMINAL')
    require(authority.get('observed') is None, 'ACTIVE_SELECTION')
    desired, terminal = authority.get('desired') or {}, authority.get('terminal') or {}
    completed = (terminal.get('reason') == 'NATURAL_EOF' and terminal.get('consumed') is False
        and terminal.get('av_started') is True and not terminal.get('error')
        and desired.get('file_bound') is True and desired.get('start_claimed') is True
        and terminal.get('request_id') == desired.get('request_id')
        and terminal.get('epoch') == desired.get('epoch') == authority.get('epoch')
        and bool(terminal.get('native_instance')) and bool(desired.get('file_identity'))
        and terminal.get('file_identity') == desired.get('file_identity'))
    require(not desired or desired.get('cancelled') is True or completed, 'ACTIVE_SELECTION')
    require(type(native.get('selection_epoch')) is int, 'NATIVE_NOT_TERMINAL')
    return dict(boot_id=authority['boot_id'], epoch=authority['epoch'],
        request_id=desired.get('request_id'), selection_epoch=native['selection_epoch'],
        native_instance=row.get('native_instance'), phase=row.get('phase'))


def require_owned(view, record, unopened=False):
    authority, native, players = view
    desired = authority.get('desired') or {}
    context = record['owner_context']
    require(authority.get('boot_id') == context['boot_id'] and authority.get('epoch') == context['epoch']
        and desired.get('request_id') == record['request_id'] and desired.get('cancelled') is not True,
        'OTHER_REQUEST')
    row = native.get('playback') or {}
    if unopened:
        require(players == [] and authority.get('observed') is None
            and (not row or row.get('phase') == 'TERMINAL'), 'ACTIVE_PLAYER')
    elif row and row.get('phase') != 'TERMINAL':
        require(row.get('request_id') == record['request_id']
                and row.get('file_identity') == record['file_identity'], 'OTHER_INSTANCE')
        if record.get('native_instance'):
            require(row.get('native_instance') == record['native_instance'], 'OTHER_INSTANCE')
    return native, row


def preserved_address(address, ua, valid_cdn):
    require(isinstance(address, str) and address.count('|') == 1, 'UA_INVALID')
    url, headers = address.split('|')
    require(valid_cdn(url) and isinstance(ua, str) and bool(ua)
        and headers == 'User-Agent=' + quote(ua, safe=''), 'UA_INVALID')
    return address  # Never strip, decode/re-encode or append arbitrary headers.


def perform_start(runtime, expected, target, record):
    """Admission is single-shot; an ambiguous open is never issued twice."""
    route = checked_route(record.get('route', 'direct'))
    record.update(route=route, tool_revision=TOOL_REVISION)
    runtime.route = route
    if route in SHARE_DIAGNOSTICS:
        record['transport_diagnostic'] = {'mode': SHARE_DIAGNOSTICS[route], 'seconds': 60}
    check_abort(runtime)
    initial = runtime.view()
    check_abort(runtime)
    initial_token = idle(initial)
    fresh = runtime.inspect(target)
    check_abort(runtime)
    require(fresh == expected, 'INSPECT_CHANGED')
    account = checked_account(runtime.account())
    check_abort(runtime)
    require(account['account_id'][4:] == fresh['account_fingerprint']
        and account['epoch'] == fresh['account_epoch'], 'ACCOUNT_CHANGED')
    row = runtime.tuple(target)
    check_abort(runtime)
    require(digest(encoded(row)) == expected['tuple_sha256'], 'INSPECT_CHANGED')
    record.update(state='preflight', settings_before=runtime.settings())
    check_abort(runtime)
    record['native_before'] = runtime.native_identity()
    check_abort(runtime)
    record['user_state_before'] = runtime.user_state()
    check_abort(runtime)
    runtime.save(record)
    record.update(state='resolving', resolve_began=time.monotonic())
    runtime.save(record)
    check_abort(runtime)
    if route == 'direct':
        address, ua, valid_cdn = runtime.resolve(row, account)
        check_abort(runtime)
        address = preserved_address(address, ua, valid_cdn)
        record.update(ua_sha256=digest(ua), original_pipe_preserved=True,
                      grant_timing='during_resolve')
    else:
        address = runtime.resolve_sharestream(row, account)
        check_abort(runtime)
        # The existing resident stream validates its loopback URL and acquires
        # the CDN grant on GET. Do not request a second grant or invent its UA.
        record.update(original_pipe_preserved=None, grant_timing='first_stream_get',
                      ua_handling='resident_sharestream')
    record.update(resolve_completed=time.monotonic(), baseline_ua_comparison='not_recorded',
                  url_sha256=digest(address))
    require(runtime.account() == account, 'ACCOUNT_CHANGED')
    check_abort(runtime)
    latest = runtime.view()
    check_abort(runtime)
    require(idle(latest) == initial_token, 'STATE_CHANGED')
    record['state'] = 'select_unconfirmed'
    runtime.save(record)
    check_abort(runtime)
    # Existing owner CAS calls native BobiIntent. A newer user selection wins.
    selected = runtime.select(latest[0], record['request_id'], target['selection_identity'], account)
    check_abort(runtime)
    desired = selected.get('desired') or {}
    require(desired.get('request_id') == record['request_id'] and desired.get('cancelled') is not True,
            'OTHER_REQUEST')
    record['owner_context'] = dict(boot_id=selected['boot_id'], epoch=selected['epoch'],
                                   request_id=record['request_id'])
    record['file_identity'] = target['selection_identity'] + '|diagnostic:' + expected['tuple_sha256'] + '|transport:' + digest(address)
    runtime.save(record)
    require_owned(runtime.view(), record, unopened=True)
    check_abort(runtime)
    require(runtime.account() == account, 'ACCOUNT_CHANGED')
    check_abort(runtime)
    context = runtime.bind(record['request_id'], record['file_identity'], address)
    check_abort(runtime)
    require(all(context.get(k) == v for k, v in record['owner_context'].items()), 'OTHER_REQUEST')
    require_owned(runtime.view(), record, unopened=True)
    check_abort(runtime)
    require(runtime.account() == account, 'ACCOUNT_CHANGED')
    check_abort(runtime)
    record.update(state='open_unconfirmed', play_issued_at=time.monotonic(), retry_allowed=False)
    runtime.save(record)  # Before the only native opener; even a lost ACK stays unconfirmed.
    try:
        check_abort(runtime)
        runtime.play(address, record['request_id'], record['file_identity'])
    except HostAbort:
        # Runtime.play raises HostAbort only before its one native opener. This
        # known pre-call cancellation may revoke our still-pending exact intent.
        record['open_cancelled_before_call'] = True
        raise
    record['open_call_returned'] = True
    runtime.save(record)
    return record


def decoder(raw, began, ended):
    markers = list(re.finditer(r'(?m)^vdec channel (\d+) statistics:', raw))
    channels = []
    for index, marker in enumerate(markers):
        block = raw[marker.end():markers[index + 1].start() if index + 1 < len(markers) else len(raw)]
        device = re.search(r'(?m)^\s*device name\s*:\s*([a-zA-Z0-9_-]+)', block)
        fields = {key.strip(): int(value) for key, value in re.findall(
            r'(?m)^\s*(frame count|drop count|fra err count|hw err count|frame width|frame height)\s*:\s*(\d+)', block)}
        channels.append(dict(channel=int(marker[1]), device=device[1] if device else None, counters=fields))
    return dict(read_started=began, read_completed=ended, channels=channels,
                sha256=hashlib.sha256(raw.encode()).hexdigest())


def seconds(value):
    return value['hours'] * 3600 + value['minutes'] * 60 + value['seconds'] + value['milliseconds'] / 1000


class Runtime:
    def __init__(self, directory):
        import xbmc
        self.monitor = xbmc.Monitor()
        self.abort_requested = self.monitor.abortRequested
        self.directory = Path(directory)
        self.root = Path('/storage/.kodi')
        for addon in ('script.module.bobbi.platform', 'script.module.bobbi.core', 'script.module.bobbi.catalog'):
            sys.path.insert(0, str(self.root / 'addons' / addon / 'lib'))
        from bobbi_core import playback_request
        self.protocol = playback_request

    def rpc(self, method, params=None):
        import xbmc
        check_abort(self)
        value = json.loads(xbmc.executeJSONRPC(json.dumps(dict(jsonrpc='2.0', id=801,
            method=method, params=params or {}))))
        check_abort(self)
        require('error' not in value, 'RPC_REJECTED')
        return value['result']

    def account(self):
        return control('account_status', {})

    def view(self):
        return (self.protocol.call({'operation': 'snapshot'}), self.rpc('Player.BobiState'),
                self.rpc('Player.GetActivePlayers'))

    def inspect(self, target):
        return inspect(self.root, target, self.account)

    def tuple(self, target):
        return retained_tuple(self.root, target)

    def resolve(self, row, account):
        from bobbi_catalog.api import Client, valid_cdn
        require(self.account() == account, 'ACCOUNT_CHANGED')
        client = Client(credential=self.root / 'userdata/addon_data/script.module.bobbi.platform/115-os_linux.json',
                        account_scope=account)
        address = client.resolve(row['share'], row, time.monotonic() + 8)
        require(self.account() == account, 'ACCOUNT_CHANGED')
        return address, client.ua, valid_cdn

    def resolve_sharestream(self, row, account):
        from bobbi_catalog.stream import resolve
        check_abort(self)
        require(self.account() == account, 'ACCOUNT_CHANGED')
        # Same inspected locator/guid/title/size/media; no title search, cache
        # substitution, grant request, HEAD/GET probe or file download here.
        mode = SHARE_DIAGNOSTICS.get(getattr(self, 'route', None))
        options = {'diagnostic': {'mode': mode, 'seconds': 60}} if mode is not None else {}
        address = resolve(row['locator'], row['guid'], row['name'], row['size'], row['media'], account=account, **options)
        check_abort(self)
        require(self.account() == account, 'ACCOUNT_CHANGED')
        check_abort(self)
        return address  # bobbi_catalog.stream.resolve performs the existing strict URL validation.

    def select(self, state, request, identity, account):
        check_abort(self)
        # CE2035 authority supports the scoped wire operation, while its thin
        # Python select() helper predates the account_scope keyword. Preserve
        # the service-side account CAS; never retry without its scope.
        return self.protocol.call(dict(operation='select', boot_id=state['boot_id'],
            epoch=state['epoch'], request_id=request, selection_identity=identity,
            account_scope=account))

    def bind(self, request, identity, address):
        # Existing idempotent claim-status handling never retries Player.play.
        check_abort(self)
        return self.protocol.bind_and_claim(request, identity, address, self.abort_requested, 'player_play')

    def cancel_pending(self, record):
        state = self.protocol.call({'operation': 'snapshot'})
        desired = state.get('desired') or {}
        if desired.get('request_id') != record['request_id'] or desired.get('cancelled') is True:
            return {'performed': False}
        require(state.get('observed') is None and (not record.get('play_issued_at')
            or record.get('open_cancelled_before_call') is True), 'ACTIVE_PLAYER')
        context = dict(boot_id=state['boot_id'], epoch=state['epoch'], request_id=record['request_id'])
        # One exact cancellation. A concurrent newer selection makes it stale.
        result = self.protocol.call(dict(context, operation='cancel'))
        return {'performed': True, 'acknowledged': isinstance(result, dict) and result.get('cancelled') is True}

    def play(self, address, request, identity):
        import xbmc
        import xbmcgui
        check_abort(self)
        label = ('Gattaca sharestream supervised diagnostic' if getattr(self, 'route', 'direct').startswith('sharestream')
                 else 'Gattaca direct-CDN supervised diagnostic')
        item = xbmcgui.ListItem(label=label, path=address)
        item.setProperty('bobitv.request_id', request)
        item.setProperty('bobitv.file_identity', identity)
        item.setProperty('no-ext-subs-scan', 'true')
        item.setProperty('StartOffset', '0')
        item.setProperty('StartPercent', '0')
        item.getVideoInfoTag().setResumePoint(0, 0)
        player = xbmc.Player()
        check_abort(self)
        player.play(address, item, windowed=True)

    def wait(self, duration):
        check_abort(self)
        # Kodi's zero timeout means wait FOREVER, not yield immediately. A slow
        # observation already used this tick's delay; do not stall the deadline.
        if duration <= 0:
            return
        if self.monitor.waitForAbort(duration):
            raise HostAbort('HOST_ABORT_REQUESTED')
        check_abort(self)

    def save(self, record):
        temporary = self.directory / 'result.pending'
        with temporary.open('w', encoding='utf-8') as stream:
            json.dump(record, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(str(temporary), str(self.directory / 'result.json'))

    def settings(self):
        result = {}
        for name in ('audiooutput.channels', 'audiooutput.passthrough', 'audiooutput.ac3passthrough',
                     'audiooutput.dtshdpassthrough', 'audiooutput.truehdpassthrough',
                     'videoplayer.adjustrefreshrate', 'videoplayer.usedisplayasclock'):
            try:
                value = self.rpc('Settings.GetSettingValue', {'setting': name}).get('value')
                result[name] = value if type(value) in (bool, int, float) else None
            except Exception:
                result[name] = None
        return result

    def native_identity(self):
        result = hashlib.sha256()
        with Path('/proc/self/exe').open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                check_abort(self)
                result.update(block)
        return dict(sha256=result.hexdigest(), application=self.rpc('Application.GetProperties',
            {'properties': ['version']}))

    def user_state(self):
        # Only hashes of relevant existing files; no copied account/database state.
        result = {}
        for name in ('guisettings.xml', 'advancedsettings.xml',
                     'addon_data/plugin.video.bobbi/database.pickle', 'addon_data/plugin.video.bobbi/settings.xml'):
            path = self.root / 'userdata' / name
            if path.is_file() and path.stat().st_size <= 64 * 1024 * 1024:
                result[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                result[name] = None
        return result

    def sample(self, record):
        started = time.monotonic()
        native, row = require_owned(self.view(), record)
        sample = dict(wall=started, phase=row.get('phase'))
        if row.get('request_id') == record['request_id']:
            require(row.get('file_identity') == record['file_identity'], 'OTHER_INSTANCE')
            if record.get('native_instance'):
                require(record['native_instance'] == row['native_instance'], 'OTHER_INSTANCE')
            else:
                record['native_instance'] = row['native_instance']
            sample['native'] = {k: row.get(k) for k in ('request_id', 'native_instance', 'phase', 'sequence',
                'user_intent', 'open_epoch', 'monotonic_us', 'reason', 'read_error')}
            if row.get('phase') == 'AV_STARTED':
                properties = self.rpc('Player.GetProperties', dict(playerid=1,
                    properties=['time', 'totaltime', 'speed', 'currentvideostream', 'currentaudiostream']))
                sample.update(seconds=seconds(properties['time']), duration=seconds(properties['totaltime']),
                    speed=properties['speed'], caching=self.rpc('XBMC.GetInfoBooleans',
                    {'booleans': ['Player.Caching']})['Player.Caching'])
                for field in ('currentvideostream', 'currentaudiostream'):
                    stream = properties.get(field) or {}
                    sample[field] = {k: stream[k] for k in ('width', 'height', 'bitrate', 'channels', 'samplerate')
                                     if type(stream.get(k)) in (int, float)}
                labels = ('Player.CacheLevel', 'Player.ProgressCache', 'Player.CacheTime')
                raw_labels = self.rpc('XBMC.GetInfoLabels', {'labels': list(labels)})
                sample['cache_labels'] = {k: float(v) if re.fullmatch(r'-?\d+(?:\.\d+)?', str(v)) else None
                                          for k, v in raw_labels.items() if k in labels}
                if 'first_av_observed_at' not in record:
                    record['first_av_observed_at'] = time.monotonic()
                    record['play_to_av_observed_seconds'] = record['first_av_observed_at'] - record['play_issued_at']
                    record['resolve_to_av_observed_seconds'] = record['first_av_observed_at'] - record['resolve_began']
        began = time.monotonic()
        path = Path('/sys/class/vdec/vdec_status')
        raw = path.read_text()[:32768]
        sample['decoder'] = decoder(raw, began, time.monotonic())
        require_owned(self.view(), record)
        sample['completed'] = time.monotonic()
        return sample

    def stop(self, record):
        if hasattr(self, 'monitor'):
            check_abort(self)
        view = self.view()
        native, row = view[1], view[1].get('playback') or {}
        require(record.get('native_instance') and row.get('native_instance') == record['native_instance']
            and row.get('request_id') == record['request_id'] and row.get('file_identity') == record['file_identity'],
            'NO_NATIVE_INSTANCE')
        if row.get('phase') == 'TERMINAL':
            return dict(already_terminal=True, target_terminal=True, stop_issued=False,
                        confirmed=False, reason=row.get('reason'), confirmation_basis='already_terminal')
        require_owned(view, record)
        record['stop_state'] = 'unconfirmed'
        # None means the dispatch is not yet acknowledged, not permission to
        # replay it. A lost ACK or later observation error keeps this evidence.
        pending = dict(confirmed=False, target_terminal=None, stop_issued=None)
        record['stop'] = pending
        self.save(record)
        if hasattr(self, 'monitor'):
            check_abort(self)
        reply = self.rpc('Player.BobiControl', dict(native_instance=row['native_instance'],
            user_intent=row['user_intent'], expected_sequence=row['sequence'],
            selection_epoch=native['selection_epoch'], action='stop', command_id=uuid4().hex))
        pending['stop_issued'] = reply.get('queued') is True
        require(reply.get('queued') is True, 'OTHER_INSTANCE')
        # Read confirmation only; never resend Stop after a missing reply.
        until = time.monotonic() + 8
        while time.monotonic() < until:
            state = self.rpc('Player.BobiState')
            after = state.get('playback') or {}
            if after and any(after.get(key) != record[key] for key in ('request_id','native_instance','file_identity')):
                return dict(confirmed=False, target_terminal=None, stop_issued=True, scope_changed=True,
                            new_instance_observed=after.get('native_instance') != record['native_instance'])
            if after.get('phase') == 'TERMINAL':
                intent_matches = (type(after.get('user_intent')) is int and type(row['user_intent']) is int
                                  and after['user_intent'] == row['user_intent'])
                confirmed = after.get('reason') == 'STOP' and intent_matches
                # This is a post-command observation, not an execution receipt
                # for command_id: BobiState does not expose that causal proof.
                return dict(confirmed=confirmed, target_terminal=True, stop_issued=True,
                    reason=after.get('reason'), user_intent_unchanged=intent_matches,
                    confirmation_basis='post_command_scoped_terminal_stop' if confirmed
                                       else 'terminal_without_stop_confirmation')
            if hasattr(self, 'monitor'):
                self.wait(.25)
            else:
                # Explicit SSH-side exact stop has no Kodi Monitor instance.
                time.sleep(.25)
        return dict(confirmed=False, target_terminal=None, stop_issued=True)


def capture_stop_result(runtime, record):
    """Record one existing Stop workflow; receipt fields never authorize replay."""
    record.update(stop_state='unconfirmed', stop={'confirmed': False, 'target_terminal': None, 'stop_issued': None})
    stopped = runtime.stop(record)
    require(isinstance(stopped, dict), 'DIAGNOSTIC_SCOPE')
    stopped = dict(stopped, confirmed=stopped.get('confirmed') is True)
    record.update(stop=stopped,
                  stop_state='confirmed' if stopped.get('confirmed') is True else 'unconfirmed')
    return stopped


def kodi_entry(parameters, directory):
    route = checked_route(parameters.get('route', 'direct'))
    runtime = Runtime(directory)
    record = dict(schema=1, operation='start', run_id=parameters['run_id'], request_id=parameters['request_id'],
        tool_revision=TOOL_REVISION, route=route,
        state='preflight', diagnostic_only=True, product_proof=False, retry_allowed=False,
        limitations=['Not ordinary source-selection acceptance', 'Not renewal or account-revocation proof',
                     'Kodi may update per-file watch records and logs', 'Observed AV time is an upper bound',
                     'Windowed diagnostic with no automatic external subtitle discovery',
                     'Compare resolve-to-AV: sharestream obtains its CDN grant on GET'], samples=[])
    runtime.save(record)


    try:
        perform_start(runtime, parameters['inspection'], parameters['target'], record)
        deadline = record['play_issued_at'] + parameters['duration']
        while time.monotonic() < deadline:
            check_abort(runtime)
            began = time.monotonic()
            sample = runtime.sample(record)
            check_abort(runtime)
            record['samples'].append(sample)
            record['state'] = 'observing'
            runtime.save(record)
            if sample.get('phase') == 'TERMINAL' and sample.get('native', {}).get('request_id') == record['request_id']:
                break
            runtime.wait(max(0, min(.5 - (time.monotonic() - began), deadline - time.monotonic())))
        check_abort(runtime)
        stopped = capture_stop_result(runtime, record)
        record['state'] = 'completed' if stopped.get('confirmed') is True else 'stop_unconfirmed'
    except Exception as error:
        may_have_opened = record.get('play_issued_at') and record.get('open_cancelled_before_call') is not True
        record.update(state='unconfirmed' if may_have_opened else 'not_started',
                      **safe_error(error), **error_location(error))
        # Never guess ownership or replay either open or stop after an error.
        if not may_have_opened and record.get('state') == 'not_started':
            try:
                record['pending_cleanup'] = runtime.cancel_pending(record)
            except Exception as cleanup_error:
                record['pending_cleanup'] = dict(state='unconfirmed', **safe_error(cleanup_error))
    try:
        check_abort(runtime)
        record['settings_after'] = runtime.settings()
        check_abort(runtime)
        record['user_state_after'] = runtime.user_state()
        check_abort(runtime)
        record['settings_unchanged'] = record.get('settings_before') == record['settings_after']
        record['observed_user_files_unchanged'] = record.get('user_state_before') == record['user_state_after']
        record['native_after'] = runtime.native_identity()
    except Exception as error:
        record['after_observation'] = safe_error(error)
    runtime.save(record)


def standalone_stop(parameters, directory):
    """SSH-side exact stop; writes a separate receipt, never launches Kodi play."""
    import types
    import urllib.request
    runtime = Runtime.__new__(Runtime)
    runtime.directory = Path(directory)
    runtime.protocol = types.SimpleNamespace(call=lambda body: control('playback', body))
    def rpc(method, params=None):
        request = urllib.request.Request('http://127.0.0.1:8080/jsonrpc',
            data=json.dumps(dict(jsonrpc='2.0', id=802, method=method, params=params or {})).encode(),
            headers={'Content-Type': 'application/json'})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request, timeout=3) as response:
            value = json.load(response)
        require('error' not in value, 'RPC_REJECTED')
        return value['result']
    runtime.rpc = rpc
    record = json.loads((runtime.directory / 'result.json').read_text())
    require(all(record.get(key) == parameters.get(key) for key in ('run_id', 'request_id', 'native_instance'))
            and bool(record.get('native_instance')), 'OTHER_INSTANCE')
    output = runtime.directory / ('stop-' + parameters['command_id'] + '.json')
    with output.open('x', encoding='utf-8') as stream:
        json.dump(dict(state='unconfirmed', retry_allowed=False), stream)
        stream.flush()
        os.fsync(stream.fileno())
    def save(value):
        output.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
    runtime.save = save
    try:
        stopped = capture_stop_result(runtime, record)
        result = dict(state='stopped' if stopped.get('confirmed') is True else 'unconfirmed',
            run_id=record['run_id'], request_id=record['request_id'], native_instance=record['native_instance'],
            stop=stopped, stop_state=record['stop_state'], retry_allowed=False, diagnostic_only=True, product_proof=False)
    except Exception as error:
        result = dict(state='unconfirmed', stop_state='unconfirmed', stop=record['stop'],
                      retry_allowed=False, **safe_error(error))
    save(result)
    return result
