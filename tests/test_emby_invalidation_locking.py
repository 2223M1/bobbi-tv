"""Real-thread regression for the three early returns that used to reacquire Lock."""
from contextlib import nullcontext
from threading import Event, Thread
from types import SimpleNamespace

import pytest

import os, sys
from pathlib import Path
ROOT = Path(os.environ.get("BOBBI_AUDIT_REPO", os.environ.get("BOBBI_REPO", Path.cwd()))).resolve()
for part in ("core", "platform"):
    sys.path.insert(0, str(ROOT / ("addons/script.module.bobbi." + part + "/lib")))
from bobbi_platform.emby_session import EmbyInvalidationHub


@pytest.mark.parametrize('state', ['ws_connected', 'throttled', 'auth_required'])
def test_poll_early_return_and_close_never_reacquire_nonreentrant_lock(tmp_path, state):
    hub = EmbyInvalidationHub(tmp_path)
    sid, generation = 'a' * 32, 'b' * 64
    client = SimpleNamespace(session=SimpleNamespace(budget=lambda seconds: nullcontext()),
        _identity=lambda **kw: None, page_rows=lambda *a, **kw: ([], 0))
    loader = lambda *args: (client, {})
    if state == 'throttled':
        first = hub.poll_server_digest(sid, generation, client_loader=loader)
        assert first['last_confirmed_at'] is not None
    elif state == 'auth_required':
        hub.mark_auth_state(sid, generation, 'AUTH_REQUIRED')
    else:
        with hub._lock:
            hub._entry(sid, generation)['ws_connected'] = True

    done, results, errors = Event(), [], []

    def poll():
        try:
            results.append(hub.poll_server_digest(sid, generation, client_loader=loader))
        except BaseException as exc:
            errors.append(exc)
        finally:
            done.set()

    worker = Thread(target=poll, daemon=True)
    worker.start()
    assert done.wait(1), 'poll_server_digest blocked while reacquiring its own lock'
    worker.join(1)
    assert not errors
    assert len(results) == 1 and results[0]['revision'] >= 1
    closed = Event()

    def close():
        hub.close()
        closed.set()

    closer = Thread(target=close, daemon=True)
    closer.start()
    assert closed.wait(1), 'invalidation hub cannot drain after polling'
    closer.join(1)
