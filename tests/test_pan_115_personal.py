"""115 personal drive uses the real shared pipeline; upstream remains a fixture.

No credentials, device playback or live 115 availability are claimed here.
"""
from copy import deepcopy
import json
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from bobbi_core.account_scope import AccountError, validate_snapshot
from bobbi_core.file_ref import from_selected, same_file, validate
from bobbi_platform.account_manager import AccountManager
from bobbi_platform import pan_115, pan_115_cipher, pan_stream, pan_ui
from bobbi_platform.pan_accounts import PanAccounts, PanError, scope
from bobbi_platform.pan_http import Session
from bobbi_platform.pan_history import prepare_history_play
from bobbi_platform.pan_service import PanService
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.libraries import Registry
from test_accounts import credential
from test_ce2096_pan_stream import Upstream, read
from test_ce2097_file_history import database, history, playback
from test_media_library_index import command

RAW = dict(fid='101', cid='42', n='Movie.mkv', s='8', sha='A' * 40,
           pc='fixture-pick', aid=1)
SELECTED = dict(file_id='101', parent='42', name='Movie.mkv', size=8,
                sha1='a' * 40, directory=False)


class Wire:
    def __init__(self):
        self.calls, self.before = [], lambda: None
        self.operation = None
        self.raw = deepcopy(RAW)
        self.rows = [self.raw]
        self.download = {'101': dict(file_name='Movie.mkv', file_size='8', sha1='A' * 40,
            pick_code='fixture-pick', url={'url': 'https://download.115cdn.net/original?fixture=private'})}

    def request(self, url, **kwargs):
        if self.operation is not None:
            self.operation.consume_request()
        self.calls.append((url, deepcopy(kwargs)))
        self.before()
        if self.operation is not None:
            self.operation.check()
        if url == pan_115.WEB + '/files':
            query = kwargs['query']
            parent, offset, limit = query['cid'], query['offset'], query['limit']
            rows = ([dict(cid='42', pid='0', n='Movies')] if parent == '0' else self.rows)
            return dict(state=True, path=[dict(cid=parent)], count=len(rows), offset=offset,
                        data=deepcopy(rows[offset:offset + limit]))
        if url == pan_115.WEB + '/files/get_info':
            assert kwargs == {'query': {'file_id': '101'}}
            return dict(state=True, data=[deepcopy(self.raw)])
        assert url == pan_115.DOWNLOAD and set(kwargs) == {'form'}
        assert kwargs['form'] == {'data': pan_115_cipher.encrypt(
            json.dumps(dict(pickcode='fixture-pick', user_id=123), separators=(',', ':')))}
        return dict(state=True, data='encrypted-fixture')


@pytest.fixture
def drive(tmp_path, monkeypatch):
    legacy = AccountManager(tmp_path / '115-os_linux.json')
    legacy.install(credential(), legacy.snapshot())
    wire = Wire()
    monkeypatch.setattr(pan_115_cipher, 'decrypt', lambda value: json.dumps(wire.download).encode())
    pans = PanService(tmp_path, legacy,
        client_factory=lambda provider, saved: pan_115.Client(saved, session=wire))
    yield SimpleNamespace(pans=pans, legacy=legacy, expected=pans.accounts.snapshot('115'), wire=wire)
    pans.close()


def test_bridge_is_only_scope_projection_and_never_second_credentials(tmp_path, drive):
    pans, legacy, expected = drive.pans, drive.legacy, drive.expected
    original = legacy.path.read_bytes()
    assert expected == dict(legacy.snapshot(), provider='115')
    assert pans.accounts.credentials(expected) == legacy.credentials(legacy.snapshot())
    assert not (tmp_path / 'pan-accounts-v1.json').exists()
    with pytest.raises(AccountError):
        validate_snapshot(expected)
    with pytest.raises(PanError):
        scope(legacy.snapshot())
    for operation in (lambda: pans.accounts.install(credential(), expected),
                      lambda: pans.accounts.renew(credential(), expected),
                      lambda: pans.begin('115', 'a' * 32, expected),
                      lambda: PanAccounts(tmp_path / 'other.json', {'115': lambda value: ('123', value)}),
                      lambda: pans.accounts.native.snapshot('115')):
        with pytest.raises(PanError):
            operation()
    assert legacy.path.read_bytes() == original
    status = next(row for row in pans.status()['providers'] if row['provider'] == '115')
    assert status['account'] == expected and status['verification'] == 'native_index_experimental'
    assert set(status['capabilities']) == {'qr_login', 'share_play', 'list_files', 'personal_play'}
    assert 'fixture' not in json.dumps(status)


def test_existing_login_logout_notifies_bridge_and_a_b_a_never_revives(drive):
    pans, legacy, expected = drive.pans, drive.legacy, drive.expected
    events = []
    unsubscribe = pans.accounts.subscribe(lambda old, new: events.append((old, new)))
    with pans.scan_operation(expected) as operation:
        legacy.install(credential(user='456'), legacy.snapshot())
        assert operation.cancelled.is_set()
        legacy.install(credential(), legacy.snapshot())
        assert not pans.accounts.is_current(expected)
        assert pans.accounts.snapshot('115')['epoch'] > expected['epoch']
        with pytest.raises(PanError, match='ACCOUNT_CHANGED'):
            pans.accounts.run_if_current(expected, lambda: pytest.fail('late publish'))
    current = pans.accounts.snapshot('115')
    assert not pans.logout(current)['authenticated'] and not legacy.snapshot()['authenticated']
    assert events[0][0] == expected and all(item['provider'] == '115' for pair in events for item in pair)
    unsubscribe()


def test_cookie_projection_is_api_only_with_exact_route_allowlist():
    session = Session('115', credential())
    assert 'fixture-seid' in session.cookie_header(pan_115.WEB + '/files')
    assert 'fixture-seid' in session.cookie_header(pan_115.DOWNLOAD)
    assert session.cookie_header('https://download.115cdn.net/file') == ''
    for url, options in [('https://evil.test/files', {}),
                         (pan_115.WEB + '/files/download', {}),
                         (pan_115.DOWNLOAD, {}),
                         (pan_115.WEB + '/files', {'body': {}}),
                         ('https://proapi.115.com/os_linux/2.0/ufile/downurl', {'form': {}})]:
        with pytest.raises(PanError, match='ORIGIN_REJECTED'):
            session.request(url, **options)
    with pytest.raises(PanError):
        session.export()  # No native 115 credential-rotation format exists.


def test_pinned_upstream_wire_encoding_known_answer():
    # Generated independently by the pinned unmodified p115rsacipher module.
    payload = json.dumps(dict(pickcode='fixture-pick', user_id='123'), separators=(',', ':'))
    assert pan_115_cipher.encrypt(payload) == (
        'ei7sT4NrkR8B7gOBDsn/jiZyM0XBV3/7018JiQb8ilnG2TNjffR6fEm0ygZ0rWL/'
        'Ug6Dp1qXWNG9SEe5iTN4KZdPRs4w+mJxjVD8d4BZ4r0a3OJj5YxY6dO3KGNERrzc'
        'ui9XspJeDMq0/RLHnpthAFsYWjYtS8XSvWBY7i+fi5c=')
    assert len(pan_115_cipher._TABLE) == 144


@pytest.mark.parametrize('wire', [None, '', '!', 'A' * 16385, 'AAAA', 'A' * 172])
def test_cipher_rejects_unbounded_or_malformed_reply(wire):
    with pytest.raises(PanError, match='PAN_REPLY_INVALID'):
        pan_115_cipher.decrypt(wire)


def test_exact_personal_listing_and_original_revalidation(drive):
    client = pan_115.Client(credential(), drive.wire)
    assert client.list_files('42')['items'] == [SELECTED]
    resolved = client.resolve_original(SELECTED)
    assert resolved['original'] and resolved['headers'] == {'User-Agent': pan_115.USER_AGENT}
    assert [url for url, _ in drive.wire.calls] == [pan_115.WEB + '/files', pan_115.WEB + '/files/get_info', pan_115.DOWNLOAD]
    assert all('/share/' not in url for url, _ in drive.wire.calls)
    assert 'pick' not in json.dumps(SELECTED)
    assert not pan_stream.headers(dict(provider='115'), resolved['url'], dict(resolved['headers'], Cookie='private'))


@pytest.mark.parametrize('change', [dict(path=[dict(cid='0')]), dict(path=[]), dict(offset=1),
    dict(count=2), dict(data=[]), dict(data=[dict(RAW, cid='0')]),
    dict(data=[dict(RAW, sha='not-sha1')]), dict(data=[dict(RAW, fid=True)])])
def test_root_fallback_parent_mismatch_and_incomplete_page_are_rejected(change):
    value = dict(state=True, path=[dict(cid='42')], offset=0, count=1, data=[RAW])
    value.update(change)
    client = pan_115.Client(credential(), SimpleNamespace(request=lambda *a, **kw: value))
    with pytest.raises(PanError):
        client.list_files('42')


@pytest.mark.parametrize('field,value', [('fid', '102'), ('cid', '43'), ('s', '9'),
    ('sha', 'B' * 40), ('n', 'Replacement.mkv'), ('aid', 120), ('pc', '')])
def test_changed_exact_metadata_never_requests_downurl(drive, field, value):
    drive.wire.raw[field] = value
    with pytest.raises(PanError):
        pan_115.Client(credential(), drive.wire).resolve_original(SELECTED)
    assert len(drive.wire.calls) == 1


@pytest.mark.parametrize('change', ['fid', 'size', 'hash', 'pickcode', 'foreign', 'http', 'no_url'])
def test_decrypted_download_must_be_exact_original(drive, change):
    item = drive.wire.download['101']
    if change == 'fid':
        drive.wire.download = {'102': item}
    elif change == 'size':
        item['file_size'] = 9
    elif change == 'hash':
        item['sha1'] = 'B' * 40
    elif change == 'pickcode':
        item['pick_code'] = 'other'
    elif change == 'foreign':
        item['url']['url'] = 'https://115cdn.net.evil.test/file'
    elif change == 'http':
        item['url']['url'] = 'http://download.115.com/file'
    else:
        item.pop('url')
    with pytest.raises(PanError):
        pan_115.Client(credential(), drive.wire).resolve_original(SELECTED)


def test_real_registry_scan_review_history_ticket_and_range_share_one_identity(tmp_path, drive, database):
    pans, expected = drive.pans, drive.expected
    registry = Registry(tmp_path / 'libraries.sqlite3')
    source = registry.save_directory('115 Movies', expected, '0')
    registry.close()
    catalog = CatalogService(tmp_path, pans)
    try:
        task = catalog.start_scan(expected, source['id'])['task_id']
        catalog.worker.join(3)
        assert not catalog.worker.is_alive()
        job = catalog.index.jobs(expected, task=task)['items'][0]
        assert job['state'] == 'completed' and job['counts']['discovered'] == 1
        ref = from_selected(expected, SELECTED, '42')
        assert catalog.index.trusted_file(expected, ref['id']) == ref
        assert ref['fingerprint'] == dict(kind='115_sha1', value='a' * 40)
        applied = catalog.dispatch('catalog_apply', dict(expected=expected,
            request_id='1' * 32, commands=[command(ref, title='My movie')]))
        assert applied['items'][0]['status'] == 'applied'
        ticket = catalog.prepare_play(expected, ref['id'], '2' * 32, 'play')['ticket']
        claim = pans.claim_play(ticket)
        assert claim['file_ref'] == ref and claim['account'] == expected
        ready = pans.open_stream(expected, claim['selected'], ticket)
        upstream = []
        pans.streams.session_factory = lambda: Upstream(upstream)
        assert read(ready['url'])[0::2] == (206, b'cdef')
        assert 'Cookie' not in upstream[0][1]
        assert 'private' not in json.dumps(ready)
        storage, _ = database
        files = history.FileHistory(storage.PickleDatabase())
        context = files.begin(ref)
        assert files.save(playback(context, position=40))
        record = files.get(ref['id'])
        replay = prepare_history_play(pans, record, '3' * 32)
        assert pans.claim_play(replay['ticket'])['file_ref'] == ref
        drive.legacy.logout(drive.legacy.snapshot())
        assert read(ready['url'])[0] == 404
        with pytest.raises(PanError, match='LOGIN_REQUIRED'):
            prepare_history_play(pans, record, '4' * 32)
    finally:
        catalog.close()


@pytest.mark.parametrize('stage', ['list', 'resolve'])
def test_legacy_logout_during_io_cannot_publish_cache_ticket_or_stream(drive, stage):
    entered, release, errors = Event(), Event(), []
    def delay():
        entered.set()
        assert release.wait(3)
    drive.wire.before = delay
    def work():
        try:
            if stage == 'list':
                drive.pans.list_files(drive.expected, '42', 1)
            else:
                drive.pans.open_stream(drive.expected, SELECTED, 'a' * 32)
        except Exception as error:
            errors.append(error)
    thread = Thread(target=work)
    thread.start()
    assert entered.wait(1)
    drive.legacy.logout(drive.legacy.snapshot())
    release.set()
    thread.join(3)
    assert not thread.is_alive() and errors
    assert not drive.pans.directory_cache and not drive.pans.play_tickets
    if drive.pans.streams:
        assert all(entry.address is None for entry in drive.pans.streams.records.values())


def test_115_status_projection_accepted_by_existing_ui(drive, monkeypatch):
    monkeypatch.setattr(pan_ui, 'call', lambda *a, **kw: drive.pans.status())
    assert next(row for row in pan_ui._status() if row['provider'] == '115')['account'] == drive.expected


def test_115_sha1_is_stable_content_evidence_not_pickcode_or_epoch(drive):
    first = from_selected(drive.expected, SELECTED, '42')
    assert from_selected(dict(drive.expected, epoch=88), dict(SELECTED, name='Renamed.mkv'), '99')['id'] == first['id']
    assert not same_file(first, from_selected(drive.expected, dict(SELECTED, sha1='b' * 40), '42'))
    with pytest.raises(ValueError):
        validate(dict(first, fingerprint=dict(kind='115_sha1', value='not-a-hash')))


def test_pagination_uses_existing_operation_and_rejects_changed_total_or_duplicate(drive):
    pans, expected = drive.pans, drive.expected
    drive.wire.rows = [dict(RAW, fid=str(101 + i)) for i in range(21)]
    with pans.scan_operation(expected) as operation:
        first = pans.list_for_scan(expected, '42', operation=operation)
        second = pans.list_for_scan(expected, '42', page=2, operation=operation)
        assert len(first['items']) == 20 and first['has_more']
        assert len(second['items']) == 1 and not second['has_more']
        assert operation.pages == 2 and operation.requests == 2
    for change in ('total', 'duplicate'):
        drive.wire.rows = [dict(RAW, fid=str(101 + i)) for i in range(21)]
        with pans.scan_operation(expected) as operation:
            pans.list_for_scan(expected, '42', operation=operation)
            if change == 'total':
                drive.wire.rows.append(dict(RAW, fid='999'))
            else:
                drive.wire.rows[-1]['fid'] = '101'
            with pytest.raises(PanError, match='PAN_REPLY_INVALID'):
                pans.list_for_scan(expected, '42', page=2, operation=operation)


def test_failed_115_scan_preserves_previous_presence_and_manual_review(tmp_path, drive):
    pans, expected = drive.pans, drive.expected
    registry = Registry(tmp_path / 'libraries.sqlite3')
    source = registry.save_directory('Movies', expected, '42')
    registry.close()
    catalog = CatalogService(tmp_path, pans)
    ref = from_selected(expected, SELECTED, '42')
    try:
        catalog.start_scan(expected, source['id'])
        catalog.worker.join(3)
        catalog.index.apply(expected, '9' * 32, [command(ref)])
        original = drive.wire.request
        def wrong_root(url, **kwargs):
            result = original(url, **kwargs)
            if url.endswith('/files'):
                result.update(path=[dict(cid='0')], count=0, data=[])
            return result
        drive.wire.request = wrong_root
        task = catalog.start_scan(expected, source['id'])['task_id']
        catalog.worker.join(3)
        job = catalog.index.jobs(expected, task=task)['items'][0]
        assert job['state'] == 'failed'
        row = catalog.index.item(expected, ref['id'])
        assert row['mapping']['title'] == 'Custom' and row['provenance'] == 'manual'
        assert catalog.index.db.execute('SELECT available FROM memberships WHERE file=?', (ref['id'],)).fetchone()[0] == 1
    finally:
        catalog.close()


def test_real_host_playback_scope_and_home_rail_keep_legacy_115_distinct(tmp_path, monkeypatch):
    from pathlib import Path
    from bobbi_platform.host import Host
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'addons/plugin.video.bobbi'))
    from lib.cinema.focus_anchor import HomeRailLifecycle, opaque
    from lib.utils.views.personal_catalog import scope_key
    host = Host(tmp_path)
    host.start()
    controller = None
    try:
        legacy = host.accounts.install(credential(), host.accounts.snapshot())
        pans = host._pans()
        expected = pans.accounts.snapshot('115')
        assert host.playback_accounts.run_if_current(expected, lambda: 'personal') == 'personal'
        assert host.playback_accounts.run_if_current(legacy, lambda: 'share') == 'share'
        props = {}
        window = SimpleNamespace(getProperty=lambda key: props.get(key, ''), setProperty=props.__setitem__)
        controller = HomeRailLifecycle(host, window)
        controller.tick()
        assert props['Bobbi.Rail.Scope.115'] == opaque(legacy)
        assert props['Bobbi.Rail.Scope.115.personal'] == scope_key(expected)
        assert props['Bobbi.Rail.Scope.115'] != props['Bobbi.Rail.Scope.115.personal']
        host.accounts.logout(legacy)
        assert props['Bobbi.Rail.Scope.115'] == props['Bobbi.Rail.Scope.115.personal'] == ''
        assert not host.playback_accounts.is_current(expected)
    finally:
        if controller:
            controller.close()
        host.close()


def test_115_iso_uses_exact_original_range_and_original_account_revocation(drive):
    drive.wire.raw['n'] = 'Disc.iso'
    drive.wire.download['101']['file_name'] = 'Disc.iso'
    selected = drive.pans.list_files(drive.expected, '42', 1)['items'][0]
    ticket = drive.pans.prepare_play(drive.expected, selected)['ticket']
    claimed = drive.pans.claim_play(ticket)
    ready = drive.pans.open_stream(drive.expected, claimed['selected'], ticket)
    upstream = []
    drive.pans.streams.session_factory = lambda: Upstream(upstream)
    assert ready['url'].endswith('/video.iso')
    assert drive.pans.streams.records[ticket].iso_passthrough
    assert read(ready['url'])[0::2] == (206, b'cdef')
    assert upstream[0][1]['Range'] == 'bytes=2-5' and 'Cookie' not in upstream[0][1]
    drive.legacy.logout(drive.legacy.snapshot())
    assert read(ready['url'])[0] == 404
    with pytest.raises(PanError):
        pan_stream.body('quark', selected, 'a' * 32)
