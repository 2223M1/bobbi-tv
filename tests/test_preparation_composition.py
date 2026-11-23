"""Live preparation composition: explicit capabilities, no ambient fallback."""
from pathlib import Path
import subprocess
import sys
from threading import Event, Thread
from types import SimpleNamespace

import pytest

from bobbi_core import preparation_host, project_metadata
from bobbi_core.preparation_host import Lease, PreparationHost, Session
from bobbi_platform.host import Host
from bobbi_platform.instance_lock import InstanceLock
from bobbi_platform import android_engine, android_tools, native_engine, pairing, paths
from test_accounts import logged_in

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def setup(tmp_path, monkeypatch):
    import requests
    from bobbi_core.cd2 import CD2
    # Composition has no network IO and must not rely on an ignored build key.
    monkeypatch.setattr(project_metadata, 'tmdb_key', lambda: 'fixture-only-tmdb-key')
    def forbidden(*args, **kwargs):
        pytest.fail('composition must not perform network IO')
    monkeypatch.setattr(CD2, 'rpc', forbidden)
    monkeypatch.setattr(requests.Session, 'request', forbidden)
    accounts, scope = logged_in(tmp_path / 'account')
    token = tmp_path / 'token'
    token.write_text('fixture-local-token')
    config = dict(account='a' * 64, destination='/115open/fixture',
        cd2_endpoint='http://127.0.0.1:19798', torrserver_endpoint='http://127.0.0.1:8090',
        cd2_token_file=str(token), ffprobe='not-executed', download_capability='GetDownloadUrlPath')
    return SimpleNamespace(root=tmp_path / 'plugin-a', accounts=accounts, scope=scope, config=config)


@pytest.mark.parametrize('factory', [None, False, object()])
def test_missing_session_factory_rejected_before_subscription_or_thread(tmp_path, factory):
    accounts = SimpleNamespace(subscribe=lambda callback: pytest.fail('subscribed without composition'))
    with pytest.raises(ValueError, match='PREPARATION_SESSION_FACTORY_REQUIRED'):
        PreparationHost(tmp_path, accounts, {}, session_factory=factory)


def test_omitted_session_factory_has_no_default_owner(tmp_path):
    with pytest.raises(TypeError, match='session_factory'):
        PreparationHost(tmp_path, None, {})


def test_falsy_callable_session_factory_is_retained(setup):
    admitted = Event()
    class Factory:
        def __bool__(self):
            return False
        def __call__(self, *args):
            admitted.set()
            return SimpleNamespace(tick=lambda: None, close=lambda: None)
    factory = Factory()
    host = PreparationHost(setup.root, setup.accounts, setup.config, session_factory=factory)
    try:
        assert admitted.wait(1)
        assert host.factory is factory
    finally:
        host.close()


@pytest.mark.parametrize('config,capabilities,code', [
    ({}, dict(lock_factory=None), 'PREPARATION_LOCK_REQUIRED'),
    ({'torrserver_pairing_file': 'fixture'}, dict(lock_factory=InstanceLock), 'PREPARATION_PAIRING_REQUIRED'),
    ({'font_tool': 'fixture', 'font_decoder': 'android'}, dict(lock_factory=InstanceLock),
     'PREPARATION_FONT_DECODER_REQUIRED'),
])
def test_missing_required_capability_fails_before_local_state(tmp_path, config, capabilities, code):
    root = tmp_path / 'untouched'
    with pytest.raises(ValueError, match=code):
        Session(root, config, None, lambda: False, lambda _: None,
            owner_call=lambda _: None, subtitle_exporter=lambda *args: None, **capabilities)
    assert not root.exists()


def test_disabled_optional_capabilities_are_never_called(setup):
    def forbidden(*args):
        pytest.fail('disabled optional capability was invoked')
    session = Session(setup.root, setup.config, Lease(setup.accounts, setup.scope), lambda: False,
        lambda _: None, lock_factory=InstanceLock, owner_call=lambda _: None, subtitle_exporter=lambda *args: None,
        pairing_loader=forbidden, font_decoder_factory=forbidden)
    session.close()


def test_pairing_and_android_decoder_are_supplied_to_real_session(setup, tmp_path):
    seen, decoder = [], lambda *args: pytest.fail('decoder executed at startup')
    config = dict(setup.config, torrserver_pairing_file=str(tmp_path / 'pairing'),
        font_tool=str(tmp_path / 'tool'), font_native_directory=str(tmp_path / 'native-fonts'),
        font_decoder='android')
    def load(path):
        seen.append(('pairing', path))
        return SimpleNamespace(endpoint=config['torrserver_endpoint'], username='fixture', password='private')
    def decode(tool):
        seen.append(('decoder', tool))
        return decoder
    session = Session(setup.root, config, Lease(setup.accounts, setup.scope), lambda: False,
        lambda _: None, lock_factory=InstanceLock, owner_call=lambda _: None, subtitle_exporter=lambda *args: None,
        pairing_loader=load, font_decoder_factory=decode)
    try:
        assert session.torrent_session.auth == ('fixture', 'private')
        assert session.font_work.loader.decoder is decoder
        assert seen == [('pairing', Path(config['torrserver_pairing_file'])), ('decoder', config['font_tool'])]
    finally:
        session.close()


@pytest.mark.parametrize('failure', ['missing', 'endpoint', 'loader'])
def test_pairing_failure_releases_real_epoch_lock(setup, failure):
    locks = []
    def lock_factory(path):
        lock = InstanceLock(path)
        locks.append(lock)
        return lock
    def load(path):
        if failure == 'loader':
            raise OSError('PAIRING_READ_FAILED')
        if failure == 'missing':
            return None
        return SimpleNamespace(endpoint='http://127.0.0.1:9999')
    with pytest.raises((ValueError, OSError), match='PAIRING'):
        Session(setup.root, dict(setup.config, torrserver_pairing_file='fixture'),
            Lease(setup.accounts, setup.scope), lambda: False, lambda _: None,
            lock_factory=lock_factory, pairing_loader=load, owner_call=lambda _: None, subtitle_exporter=lambda *args: None)
    assert len(locks) == 1 and locks[0].fd is None
    replacement = InstanceLock(locks[0].path)
    replacement.acquire()
    replacement.close()


def test_lock_failure_stops_before_pairing_or_database(setup):
    calls = []
    class FailingLock:
        def __init__(self, path):
            self.path = path
        def acquire(self):
            calls.append('acquire')
            raise OSError('LOCK_DENIED')
        def close(self):
            pytest.fail('failed acquire owns no registered lease')
    with pytest.raises(OSError, match='LOCK_DENIED'):
        Session(setup.root, dict(setup.config, torrserver_pairing_file='fixture'),
            Lease(setup.accounts, setup.scope), lambda: False, lambda _: None,
            lock_factory=FailingLock, owner_call=lambda _: None, subtitle_exporter=lambda *args: None,
            pairing_loader=lambda _: pytest.fail('read pairing after lock denial'))
    assert calls == ['acquire']
    assert not list(setup.root.rglob('*.sqlite'))


@pytest.mark.parametrize('result', [None, False, 'not-a-decoder'])
def test_android_missing_decoder_never_falls_back_to_ce(setup, tmp_path, result):
    config = dict(setup.config, font_tool=str(tmp_path / 'tool'),
        font_native_directory=str(tmp_path / 'fonts'), font_decoder='android')
    locks = []
    def lock_factory(path):
        lock = InstanceLock(path)
        locks.append(lock)
        return lock
    with pytest.raises(ValueError, match='PREPARATION_FONT_DECODER_REQUIRED'):
        Session(setup.root, config, Lease(setup.accounts, setup.scope), lambda: False, lambda _: None,
            lock_factory=lock_factory, font_decoder_factory=lambda tool: result, owner_call=lambda _: None, subtitle_exporter=lambda *args: None)
    assert len(locks) == 1 and locks[0].fd is None
    replacement = InstanceLock(locks[0].path)
    replacement.acquire()
    replacement.close()


@pytest.mark.parametrize('close_failure', [False, True])
def test_shutdown_drains_io_and_closes_sqlite_before_releasing_lock(setup, monkeypatch, close_failure):
    from bobbi_core.ledger import Ledger
    original_close, events = Ledger.close, []
    def ledger_close(ledger):
        original_close(ledger)
        events.append('ledger_closed')
    monkeypatch.setattr(Ledger, 'close', ledger_close)
    class RecordedLock(InstanceLock):
        def close(self):
            assert events == ['io_drained', 'ledger_closed']
            super().close()
            events.append('lock_closed')
            if close_failure:
                raise OSError('LOCK_CLOSE_FAILED')
    ready, release, closing, stop, done = (Event() for _ in range(5))
    shared, errors = {}, []
    def owner():
        session = None
        try:
            session = Session(setup.root, setup.config, Lease(setup.accounts, setup.scope),
                lambda: False, lambda _: None, lock_factory=RecordedLock, owner_call=lambda _: None, subtitle_exporter=lambda *args: None)
            shared['path'] = session.ledger.path.parent / 'owner.lock'
            def pending_io():
                assert release.wait(4)
                events.append('io_drained')
            session.executor.submit(pending_io)
            ready.set()
            assert stop.wait(4)
            closing.set()
        except BaseException as error:
            errors.append(error)
        finally:
            try:
                if session is not None:
                    session.close()
            except BaseException as error:
                errors.append(error)
            done.set()
    worker = Thread(target=owner)
    worker.start()
    try:
        assert ready.wait(2)
        stop.set()
        assert closing.wait(1) and not done.wait(.05)
        assert events == []
        with pytest.raises(OSError):
            InstanceLock(shared['path']).acquire()
    finally:
        stop.set()
        release.set()
        worker.join(4)
    assert not worker.is_alive()
    assert events == ['io_drained', 'ledger_closed', 'lock_closed']
    assert [str(error) for error in errors] == (['LOCK_CLOSE_FAILED'] if close_failure else [])
    replacement = InstanceLock(shared['path'])
    replacement.acquire()
    replacement.close()


@pytest.mark.parametrize('android', [False, True])
def test_real_host_composition_captures_profile_and_platform_capabilities(setup, tmp_path, monkeypatch, android):
    class DeferredThread:
        def __init__(self, **kwargs):
            pass
        def start(self):
            pass
        def join(self):
            pass
    monkeypatch.setattr(preparation_host, 'Thread', DeferredThread)
    monkeypatch.setattr(android_engine, 'available', lambda: android)
    monkeypatch.setattr(native_engine, 'architecture', lambda: 'aarch64')
    monkeypatch.setattr(paths, 'profile', lambda *args: pytest.fail('worker resolved current profile'))
    config = dict(setup.config, playback_transport='http' if android else 'mount')
    monkeypatch.setattr(preparation_host, 'configuration', lambda path: config)
    platform_root = tmp_path / 'platform-a'
    platform_root.mkdir()
    (platform_root / 'preparation.json').write_text('fixture')
    host = Host(platform_root)
    host.accounts = setup.accounts
    host.configure_preparation(setup.root)
    host._tick_preparation()
    prepared = host.preparation
    try:
        assert isinstance(prepared, PreparationHost)
        assert prepared.factory.func is Session
        assert callable(prepared.factory.keywords['owner_call'])
        assert prepared.factory.keywords['subtitle_exporter'] == host.export_subtitle
        assert prepared.current == host.check_profile
        assert {key: value for key, value in prepared.factory.keywords.items() if key not in ('owner_call', 'subtitle_exporter')} == dict(lock_factory=InstanceLock,
            pairing_loader=pairing.load, font_decoder_factory=android_tools.font_decoder)
        config['cd2_token_file'] = 'new-profile-token'
        host.configure_preparation(tmp_path / 'plugin-b')
        host.root = tmp_path / 'platform-b'
        session = prepared.factory(prepared.root, prepared.config, Lease(setup.accounts, setup.scope),
            prepared.playing, prepared.report)
        try:
            assert session.ledger.path.is_relative_to(setup.root)
            assert not (tmp_path / 'plugin-b').exists()
        finally:
            session.close()
    finally:
        prepared.close()


def test_real_core_session_can_start_with_platform_and_kodi_imports_denied(tmp_path):
    import requests
    script = r'''
import importlib.abc, sys
from pathlib import Path
from types import SimpleNamespace
class DenyEnvironment(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        assert fullname.split('.')[0] not in {'bobbi_platform', 'lib', 'xbmc', 'xbmcaddon', 'xbmcvfs', 'xbmcgui'}, fullname
sys.meta_path.insert(0, DenyEnvironment())
sys.path.insert(0, sys.argv[1])
sys.path.insert(0, sys.argv[3])
from bobbi_core.preparation_host import Lease, Session
from bobbi_core import project_metadata
import requests
project_metadata.tmdb_key = lambda: 'fixture-only-tmdb-key'
def forbidden(*args, **kwargs):
    raise AssertionError('network during startup')
requests.Session.request = forbidden
root = Path(sys.argv[2])
token = root / 'token'
token.write_text('fixture')
scope = dict(account_id='115:'+'a'*64, epoch=1, authenticated=True)
accounts = SimpleNamespace(is_current=lambda value: value == scope)
events = []
class Lock:
    def __init__(self, path):
        assert path.is_relative_to(root)
    def acquire(self):
        events.append('acquire')
    def close(self):
        events.append('close')
config = dict(account='b'*64, destination='/115open/fixture', cd2_endpoint='http://127.0.0.1:19798',
    torrserver_endpoint='http://127.0.0.1:8090', cd2_token_file=str(token),
    ffprobe='not-executed', download_capability='GetDownloadUrlPath')
session = Session(root, config, Lease(accounts, scope), lambda: False, lambda _: None,
    lock_factory=Lock, owner_call=lambda _: None, subtitle_exporter=lambda *args: None)
session.close()
assert events == ['acquire', 'close']
'''
    result = subprocess.run([sys.executable, '-I', '-B', '-c', script,
        str(ROOT / 'addons/script.module.bobbi.core/lib'), str(tmp_path),
        str(Path(requests.__file__).resolve().parents[1])],
        capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
