from pathlib import Path
import sys
from threading import Event, Thread
from urllib.parse import urlsplit

import pytest

from bobbi_platform.account_manager import AccountError
from test_accounts import logged_in, credential

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
from bobbi_core.share_stream import ShareStream, Binding, Handler, checked


def body(request='1' * 32):
    return dict(request_id=request, locator='am6bqqdocs://A1/123', guid='qqdocs:fixture',
                title='Fixture.mkv', size=1000, media='movie:1:0:0')


def stream(manager, resolver=None):
    return ShareStream(lambda _: None, resolver or (lambda b, s: 'https://fixture.115cdn.com/video|User-Agent=fixture'),
                       lambda url: url.startswith('https://fixture.115cdn.com/'), account=manager,
                       observer=lambda _: None)


def test_old_url_removed_same_account_renewal_preserves_url(tmp_path):
    manager, a = logged_in(tmp_path)
    service = stream(manager)
    try:
        ready = service.register(body(), account=a)
        path = urlsplit(ready['url']).path
        entry = service.acquire(path)
        assert entry is not None
        address = entry.grant()
        service.release(entry)
        renewed = manager.install(credential(suffix='A2_new'), a)
        assert renewed == a
        assert service.register(body(), account=a)['url'] == ready['url']
        assert entry.grant() == address
        manager.install(credential('456'), a)
        assert service.acquire(path) is None and entry.address is None
        with pytest.raises(OSError, match='SHARE_STOPPED'):
            entry.grant()
        with pytest.raises(AccountError):
            service.register(body('2' * 32), account=a)
    finally:
        service.close()
        service.close()


def test_late_resolver_result_after_switch_not_cached_or_delivered(tmp_path):
    manager, a = logged_in(tmp_path)
    started, release = Event(), Event()
    errors = []
    def resolver(body, scope):
        assert scope == a
        started.set()
        assert release.wait(2)
        return 'https://fixture.115cdn.com/video|User-Agent=fixture'
    service = stream(manager, resolver)
    try:
        ready = service.register(body(), account=a)
        entry = service.acquire(urlsplit(ready['url']).path)
        def grant():
            try:
                entry.grant()
            except Exception as error:
                errors.append(type(error))
        worker = Thread(target=grant)
        worker.start()
        assert started.wait(1)
        manager.logout(a)
        release.set()
        worker.join(2)
        assert errors == [OSError] and entry.address is None
        service.release(entry)
    finally:
        release.set()
        service.close()


def test_logout_shuts_down_active_socket_and_cancels_delivery(tmp_path):
    manager, a = logged_in(tmp_path)
    shutdowns = []
    class Connection:
        def shutdown(self, how):
            shutdowns.append(how)
    connection = Connection()
    service = stream(manager)
    try:
        ready = service.register(body(), account=a)
        entry = service.acquire(urlsplit(ready['url']).path, connection)
        manager.logout(a)
        assert shutdowns and entry.cancelled()
        handler = Handler.__new__(Handler)
        handler.entry = entry
        assert handler.cancelled() is True
        service.release(entry, connection)
    finally:
        service.close()


def test_cannot_register_without_explicit_scope(tmp_path):
    manager, a = logged_in(tmp_path)
    service = stream(manager)
    try:
        with pytest.raises(AccountError):
            service.register(body())
    finally:
        service.close()


def test_juku_uses_original_locator_grammar_and_same_transport():
    value = body()
    value.update(locator='am6bjuku://' + 'a' * 64, guid='juku:' + 'a' * 64)
    assert checked(value) == value
