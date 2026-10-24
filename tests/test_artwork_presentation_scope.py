"""Endpoint snapshots are local to one projection, never a service registry."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from threading import Barrier

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'addons/script.module.bobbi.core/lib'))
from bobbi_core import image_cache as images
from bobbi_platform import paths


@pytest.fixture
def endpoint(tmp_path, monkeypatch):
    calls = []
    real = images._configuration
    monkeypatch.setattr(paths, 'profile', lambda: tmp_path)
    monkeypatch.setattr(images, '_configuration', lambda path: (calls.append(path), real(path))[1])
    monkeypatch.setattr(images, 'fetch', lambda *a, **kw: pytest.fail('No presentation HTTP'))
    def publish(port=12345, root=tmp_path):
        root.mkdir(exist_ok=True)
        (root / 'image-runtime.json').write_text(json.dumps(dict(port=port, token='a' * 64)))
    publish()
    return tmp_path, calls, publish


def test_scope_is_lazy_and_non_tmdb_does_not_read_profile(endpoint, monkeypatch):
    _, calls, _ = endpoint
    monkeypatch.setattr(paths, 'profile', lambda: pytest.fail('No profile access'))
    with images.image_batch():
        assert images.image_url('') == ''
        assert images.image_url(None) == ''
        assert images.image_url(12) == 12
        assert images.image_url('https://other.example/a.jpg') == 'https://other.example/a.jpg'
    assert calls == []


def test_nested_scope_reuses_and_exception_discards_snapshot(endpoint):
    _, calls, publish = endpoint
    with pytest.raises(RuntimeError):
        with images.image_batch():
            first = images.image_url('/p.jpg', 'w342')
            publish(23456)
            with images.image_batch():
                assert images.image_url('/p.jpg', 'w342') == first
            assert images.image_url('/p.jpg', 'w342') == first
            raise RuntimeError('renderer failed')
    assert len(calls) == 1
    assert ':23456/' in images.image_url('/p.jpg', 'w342')
    assert len(calls) == 2


@pytest.mark.parametrize('broken', ['missing', 'invalid', 'wrong_port', 'too_large', 'read_error'])
def test_failed_configuration_is_only_cached_for_current_projection(endpoint, broken, monkeypatch):
    root, calls, publish = endpoint
    config = root / 'image-runtime.json'
    if broken == 'missing': config.unlink()
    elif broken == 'invalid': config.write_text('{')
    elif broken == 'wrong_port': config.write_text(json.dumps(dict(port=True, token='a' * 64)))
    elif broken == 'too_large': config.write_text(' ' * 513)
    else:
        real = paths.profile
        monkeypatch.setattr(paths, 'profile', lambda: (_ for _ in ()).throw(OSError('unavailable')))
    with images.image_batch():
        assert images.image_url('/p.jpg', 'w342') == 'https://image.tmdb.org/t/p/w342/p.jpg'
        publish()
        if broken == 'read_error': monkeypatch.setattr(paths, 'profile', real)
        assert images.image_url('/p.jpg', 'w342') == 'https://image.tmdb.org/t/p/w342/p.jpg'
    with images.image_batch():
        assert ':12345/' in images.image_url('/p.jpg', 'w342')
    assert len(calls) == (1 if broken == 'read_error' else 2)


def test_removal_and_corruption_never_survive_into_next_batch(endpoint):
    root, calls, publish = endpoint
    with images.image_batch(): assert ':12345/' in images.image_url('/p.jpg')
    (root / 'image-runtime.json').unlink()
    with images.image_batch(): assert images.image_url('/p.jpg').startswith('https://image.tmdb.org/')
    publish(23456)
    with images.image_batch(): assert ':23456/' in images.image_url('/p.jpg')
    (root / 'image-runtime.json').write_text('[]')
    with images.image_batch(): assert images.image_url('/p.jpg').startswith('https://image.tmdb.org/')
    assert len(calls) == 4


def test_explicit_profiles_stay_independent_and_fresh_inside_default_batch(endpoint):
    root, calls, publish = endpoint
    other = root / 'other'
    publish(23456, other)
    with images.image_batch():
        assert ':12345/' in images.image_url('/p.jpg')
        assert ':23456/' in images.image_url('/p.jpg', root=other)
        publish(34567, other)
        assert ':34567/' in images.image_url('/p.jpg', root=other)
        assert ':12345/' in images.image_url('/p.jpg')
    assert len(calls) == 3


def test_concurrent_renderer_does_not_inherit_another_thread_snapshot(endpoint):
    _, _, publish = endpoint
    barrier = Barrier(2)
    def first():
        with images.image_batch():
            before = images.image_url('/p.jpg')
            barrier.wait(timeout=2)
            barrier.wait(timeout=2)
            return before, images.image_url('/p.jpg')
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(first)
        barrier.wait(timeout=2)
        publish(23456)
        with images.image_batch(): assert ':23456/' in images.image_url('/p.jpg')
        barrier.wait(timeout=2)
        before, after = future.result(timeout=2)
    assert before == after and ':12345/' in before


def test_decorated_projection_refreshes_between_calls_and_preserves_return(endpoint):
    _, calls, publish = endpoint
    @images.image_batch()
    def render():
        return images.image_url('/p.jpg'), images.image_url('/q.jpg')
    assert all(':12345/' in value for value in render())
    publish(23456)
    assert all(':23456/' in value for value in render())
    assert len(calls) == 2
