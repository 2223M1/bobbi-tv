import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import sys
from threading import Event
import time
from urllib.error import HTTPError
from urllib.request import build_opener, ProxyHandler, Request

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
from bobbi_core.image_cache import ImageCache, ImageService, image_path, image_url, MetadataError

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aT1cAAAAASUVORK5CYII=')


def test_helper_only_reads_local_configuration_never_fetches(tmp_path, monkeypatch):
    import bobbi_core.image_cache as module
    monkeypatch.setattr(module, 'fetch', lambda *a,**k:pytest.fail('No GUI network'))
    assert image_url('/poster.jpg', 'w342', tmp_path) == 'https://image.tmdb.org/t/p/w342/poster.jpg'
    (tmp_path/'image-runtime.json').write_text(json.dumps(dict(port=12345, token='a'*64)))
    assert image_url('/poster.jpg', 'w342', tmp_path) == 'http://127.0.0.1:12345/art/'+'a'*64+'/w342/poster.jpg'
    assert image_url('http://image.tmdb.org/t/p/w500/poster.jpg','w342',tmp_path).endswith('/w342/poster.jpg')
    assert image_url('https://other.example/art.jpg','w342',tmp_path) == 'https://other.example/art.jpg'


@pytest.mark.parametrize('value', ['//foreign/a.jpg','https://image.tmdb.org.evil/t/p/w342/a.jpg',
    'https://user@image.tmdb.org/t/p/w342/a.jpg','https://image.tmdb.org/t/p/w342/a.jpg?api_key=forbidden',
    'https://image.tmdb.org/t/p/w342/../secret','https://image.tmdb.org:444/t/p/w342/a.jpg'])
def test_only_bounded_keyless_tmdb_image_paths(value):
    with pytest.raises(ValueError):
        image_path(value)


def test_success_cache_is_offline_and_keeps_original_bytes(tmp_path):
    calls = []
    def fetch(url, deadline, cancelled):
        calls.append(url)
        return dict(status=200, body=PNG)
    cache = ImageCache(tmp_path, transport=fetch)
    expected = (PNG, 'image/png')
    assert cache.get('/t/p/w342/a.png', time.monotonic()+1) == expected
    cache.transport = lambda *a:pytest.fail('Disk cache must work offline')
    assert cache.get('/t/p/w342/a.png', time.monotonic()+1) == expected
    assert calls == ['https://image.tmdb.org/t/p/w342/a.png']
    assert len(list(tmp_path.iterdir())) == 1


@pytest.mark.parametrize('result', [dict(status=403,body=PNG),dict(status=200,body=b'<html>error'),dict(status=200,body=PNG[:-4])])
def test_failure_never_becomes_cached_art_and_cools_down(tmp_path, result):
    calls = []
    cache = ImageCache(tmp_path, transport=lambda *a:(calls.append(1),result)[1])
    with pytest.raises(MetadataError):
        cache.get('/t/p/w342/a.png',time.monotonic()+1)
    with pytest.raises(MetadataError,match='COOLDOWN'):
        cache.get('/t/p/w342/a.png',time.monotonic()+1)
    assert calls == [1] and not list(tmp_path.iterdir())


def test_same_image_is_single_flight(tmp_path):
    entered, release, calls = Event(), Event(), []
    def fetch(*args):
        calls.append(1)
        entered.set()
        assert release.wait(2)
        return dict(status=200,body=PNG)
    cache = ImageCache(tmp_path,transport=fetch)
    with ThreadPoolExecutor(max_workers=3) as pool:
        first=pool.submit(cache.get,'/t/p/w342/a.png',time.monotonic()+3)
        assert entered.wait(1)
        second=pool.submit(cache.get,'/t/p/w342/a.png',time.monotonic()+3)
        release.set()
        assert first.result() == second.result() == (PNG,'image/png')
    assert calls == [1]


def test_quota_evicts_only_owned_cache_images(tmp_path):
    (tmp_path/'do-not-touch.txt').write_text('unrelated')
    cache=ImageCache(tmp_path,transport=lambda *a:dict(status=200,body=PNG),max_files=2,max_bytes=len(PNG)*2)
    for name in ('one','two','three'):
        cache.get('/t/p/w342/'+name+'.png',time.monotonic()+1)
    assert len(list(tmp_path.glob('*.png'))) == 2
    assert (tmp_path/'do-not-touch.txt').read_text() == 'unrelated'


def test_shutdown_or_deadline_cannot_publish_late_bytes(tmp_path):
    stop=Event()
    def fetch(*a):
        stop.set()
        return dict(status=200,body=PNG)
    cache=ImageCache(tmp_path,stopped=stop,transport=fetch)
    with pytest.raises(MetadataError,match='CANCELLED'):
        cache.get('/t/p/w342/a.png',time.monotonic()+1)
    assert not list(tmp_path.iterdir())


def test_loopback_service_has_readonly_scope_and_requires_exact_host_token_path(tmp_path):
    calls=[]
    service=ImageService(tmp_path,transport=lambda url,*a:(calls.append(url),dict(status=200,body=PNG))[1])
    service.start()
    opener=build_opener(ProxyHandler({}))
    try:
        url=image_url('/test.png','w342',tmp_path)
        with opener.open(url,timeout=2) as response:
            assert response.read() == PNG and response.headers['Content-Type']=='image/png'
        with opener.open(url,timeout=2) as response:
            assert response.read() == PNG
        for bad in (url.replace(service.server.token,'b'*64),url.replace('/w342/test.png','/../../control'),
                    url+'?url=https://foreign.invalid/a'):
            with pytest.raises(HTTPError):
                opener.open(bad,timeout=2)
        with pytest.raises(HTTPError) as rejected:
            opener.open(Request(url,headers={'Host':'foreign.invalid'}),timeout=2)
        assert rejected.value.code == 403
        assert calls == ['https://image.tmdb.org/t/p/w342/test.png']
    finally:
        service.close()
    assert not (tmp_path/'image-runtime.json').exists()
    assert list((tmp_path/'images').glob('*.png'))


def test_old_service_cannot_remove_new_registration(tmp_path):
    service=ImageService(tmp_path)
    service.start()
    replacement=dict(port=12345,token='c'*64)
    (tmp_path/'image-runtime.json').write_text(json.dumps(replacement))
    service.close()
    assert json.loads((tmp_path/'image-runtime.json').read_text()) == replacement
