"""Provider fixtures exercise real parsing/publication, without external calls."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import time

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
spec = importlib.util.spec_from_file_location('bobbi_manual_provider',
    ROOT / 'addons/script.bobbi.opensubtitles/resources/lib/provider.py')
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)


def context():
    return dict(mode='movie', tmdb=1234, imdb='tt1234567', year=2020,
                title='Fixture Movie', release='Fixture.Movie.2020.BluRay', duration=7200)


def row():
    return dict(attributes=dict(language='zh-cn', foreign_parts_only=False,
        machine_translated=False, ai_translated=False, release='Fixture.Movie.2020.BluRay',
        files=[dict(file_id=7, file_name='Fixture.Movie.2020.srt', cd_number=1)],
        feature_details=dict(feature_type='movie', tmdb_id=1234, imdb_id=1234567,
                             year=2020, title='Fixture Movie')))


class Transport:
    def __init__(self, rows=None):
        self.calls = []
        self.rows = rows if rows is not None else [row()]
        self.raw = '1\n03:00:01,000 --> 03:00:03,000\n中文对白\nChinese dialogue\n'.encode('utf-8')

    def __call__(self, url, deadline, cancelled, limit, **kwargs):
        assert deadline > time.monotonic() and not cancelled()
        assert kwargs['trusted_proxy'] is None
        self.calls.append((url, kwargs))
        if kwargs['mode'] == 'opensubtitles_download':
            assert 'Api-Key' not in kwargs['headers']
            return self.raw
        assert kwargs['headers']['Api-Key'] == 'FixtureKeyNeverAnActualCredential'
        if kwargs['method'] == 'POST':
            assert kwargs['json_body'] == {'file_id': 7, 'sub_format': 'srt'}
            return json.dumps(dict(link='https://dl.opensubtitles.com/fixture.srt?private=never-persist',
                                   remaining=4)).encode()
        return json.dumps(dict(data=self.rows)).encode()


def make(tmp_path, transport):
    return provider.Provider(tmp_path / 'state', transport=transport,
                             api_key='FixtureKeyNeverAnActualCredential')


@pytest.mark.parametrize('key', ['', None, 'short', 'line\nbreak'])
def test_no_bundled_key_or_default_network_fallback(tmp_path, key):
    calls = []
    value = provider.Provider(tmp_path, transport=lambda *a, **k: calls.append(a), api_key=key)
    with pytest.raises(provider.ProviderError, match='PROVIDER_NOT_CONFIGURED'):
        value.search(context(), time.monotonic() + 2, lambda: False)
    assert calls == []


def test_download_uses_personal_key_only_for_api_and_keeps_quality_not_timeline_gate(tmp_path):
    transport = Transport()
    value = make(tmp_path, transport)
    choices = value.search(context(), time.monotonic() + 2, lambda: False)
    result = value.download(choices[0], context(), time.monotonic() + 2, lambda: False, tmp_path / 'subs')
    assert Path(result['path']).read_bytes() == transport.raw
    assert result['bilingual'] is True and result['sync_verified'] is False
    assert result['remaining'] == 4 and result['cached'] is False
    assert len(transport.calls) == 3
    cached = value.download(choices[0], context(), time.monotonic() + 2, lambda: False, tmp_path / 'subs')
    assert cached['cached'] is True and len(transport.calls) == 3
    raw = (tmp_path / 'state/provider.sqlite3').read_bytes()
    assert b'FixtureKeyNeverAnActualCredential' not in raw and b'private=never-persist' not in raw


@pytest.mark.parametrize('edit', ['year', 'identity', 'forced', 'ai', 'commentary'])
def test_bad_identity_or_quality_claims_are_excluded(tmp_path, edit):
    candidate = row()
    attrs = candidate['attributes']
    if edit == 'year':
        attrs['feature_details']['year'] = 2019
    elif edit == 'identity':
        attrs['feature_details']['imdb_id'] = 9999999
    elif edit == 'forced':
        attrs['foreign_parts_only'] = True
    elif edit == 'ai':
        attrs['ai_translated'] = True
    else:
        attrs['release'] += '.Commentary'
    assert make(tmp_path, Transport([candidate])).search(context(), time.monotonic() + 2, lambda: False) == []


def test_forged_candidate_cannot_spend_download_quota(tmp_path):
    transport = Transport()
    value = make(tmp_path, transport)
    choices = value.search(context(), time.monotonic() + 2, lambda: False)
    changed = copy.deepcopy(choices[0])
    changed['file_id'] = 8
    with pytest.raises(provider.ProviderError, match='IDENTITY_REJECTED'):
        value.download(changed, context(), time.monotonic() + 2, lambda: False, tmp_path / 'subs')
    assert len(transport.calls) == 1


def test_download_cancelled_before_submission(tmp_path):
    transport = Transport()
    value = make(tmp_path, transport)
    choices = value.search(context(), time.monotonic() + 2, lambda: False)
    with pytest.raises(provider.ProviderError, match='CANCELLED'):
        value.download(choices[0], context(), time.monotonic() + 2, lambda: True, tmp_path / 'subs')
    assert len(transport.calls) == 1
