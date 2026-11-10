import copy
import json
from urllib.error import URLError, HTTPError

import pytest

from bobbi_platform import online_updates as online
from bobbi_platform.updates import UpdateError
from test_online_updates import Response, tracked_offer, offer_for, entry
from test_ce_general_installer import environment, signing, package


@pytest.mark.parametrize('track', ['stable', 'preview'])
@pytest.mark.parametrize('sequences', [(1, 2), (2, 1), (2, 2)])
def test_both_mirrors_compared_within_explicit_track(monkeypatch, track, sequences):
    offers = [tracked_offer(sequence=value, track=track) for value in sequences]
    responses = iter(offers)
    urls = []
    def open_response(url):
        urls.append(url)
        return Response(json.dumps(next(responses)).encode())
    monkeypatch.setattr(online, '_open', open_response)
    report = {}
    assert online.latest(track=track, report=report)['sequence'] == max(sequences)
    assert len(urls) == 2 and all('/' + track + '/' in url for url in urls)
    assert report['mirrors'] == ('synchronized' if len(set(sequences)) == 1 else 'out-of-sync')


@pytest.mark.parametrize('field,value', [('sha256', 'a' * 64), ('size', 6), ('tag', 'ce2096'),
                                        ('versions', {'plugin.video.bobbi': '2.0.0'})])
def test_same_sequence_disagreement_fails_closed(monkeypatch, field, value):
    left = tracked_offer()
    right = dict(left, **{field: value})
    if field == 'tag': right['url'] = online.release_url(value)
    responses = iter((left, right))
    monkeypatch.setattr(online, '_open', lambda _: Response(json.dumps(next(responses)).encode()))
    with pytest.raises(UpdateError, match='ONLINE_MIRROR_CONFLICT'):
        online.latest()


def test_default_stable_rejects_ce2096_preview(monkeypatch):
    offer = tracked_offer(track='preview')
    offer.update(tag='ce2096', url=online.release_url('ce2096'))
    monkeypatch.setattr(online, '_open', lambda _: Response(json.dumps(offer).encode()))
    with pytest.raises(UpdateError, match='ONLINE_TRACK_MISMATCH'):
        online.latest()
    assert online.latest(track='preview')['tag'] == 'ce2096'


@pytest.mark.parametrize('change', [dict(track='nightly'), dict(prerelease=True),
                                   dict(manifest_channel='private-candidate'), dict(extra=1)])
def test_versioned_feed_has_closed_track_contract(change):
    with pytest.raises(UpdateError):
        online.parse_offer(json.dumps(dict(tracked_offer(), **change)), 'stable')


def test_legacy_parser_compatibility_does_not_adopt_unknown_stable_identity():
    unknown = offer_for(b'legacy')
    assert online.parse_offer(json.dumps(unknown)) == unknown  # Historical explicit download contract.
    with pytest.raises(UpdateError, match='ONLINE_TRACK_MISMATCH'):
        online.parse_offer(json.dumps(unknown), 'stable')
    known = dict(schema=1, **dict(zip(('tag', 'sequence', 'size', 'sha256'), online.LEGACY_STABLE)),
                 url=online.release_url(online.LEGACY_STABLE[0]))
    assert online.parse_offer(json.dumps(known), 'stable') == known
    with pytest.raises(UpdateError): online.parse_offer(json.dumps(known), 'preview')


def test_signed_manifest_must_bind_track_sequence_and_versions():
    offer = tracked_offer(track='preview')
    manifest = dict(channel='private-candidate', sequence=1, components=[dict(id='plugin.video.bobbi', version='1.0.0')])
    online.check_offer_manifest(offer, manifest)
    for altered in [dict(manifest, channel='private-stable'), dict(manifest, sequence=2),
                    dict(manifest, components=[dict(id='plugin.video.bobbi', version='2.0.0')])]:
        with pytest.raises(UpdateError): online.check_offer_manifest(offer, altered)


def test_track_switch_never_mutates_install_journal_or_highwater(entry, monkeypatch):
    from bobbi_platform import ce_install_ui as ui
    env = entry.env
    env.installer.apply(env.root / 'online.zip')
    state = env.installer._read()
    state['high_watermark'] = 2096
    env.installer._write(state)
    original = env.installer.state.read_bytes()
    assert online.selected_track(env.work) == 'stable'
    online.selected_track(env.work, 'preview')
    online.selected_track(env.work, 'stable')
    monkeypatch.setattr(online, 'latest', lambda *args, **kwargs: tracked_offer(sequence=2080))
    assert ui.install_online(env.installer, env.host, entry.dialog) is False
    assert '稳定版尚未追上' in str(entry.dialogs)
    assert env.installer.state.read_bytes() == original


def test_one_unavailable_mirror_still_reports_valid_other(monkeypatch):
    def respond(url):
        if 'gitee.com' in url: raise URLError(TimeoutError())
        return Response(json.dumps(tracked_offer()).encode())
    monkeypatch.setattr(online, '_open', respond)
    report = {}
    assert online.latest(report=report)['track'] == 'stable'
    assert report['mirrors'] == 'unavailable'


def test_missing_versioned_stable_entry_only_migrates_known_legacy_bytes(monkeypatch):
    known = dict(schema=1, **dict(zip(('tag', 'sequence', 'size', 'sha256'), online.LEGACY_STABLE)),
                 url=online.release_url(online.LEGACY_STABLE[0]))
    calls = []
    def respond(url):
        calls.append(url)
        if '/stable/' in url: raise HTTPError(url, 404, '', {}, None)
        return Response(json.dumps(offer_for(b'unknown') if 'gitee.com' in url else known).encode())
    monkeypatch.setattr(online, '_open', respond)
    assert online.latest() == known
    assert len(calls) == 4


def test_preview_never_falls_back_to_legacy_current(monkeypatch):
    calls = []
    def absent(url):
        calls.append(url)
        raise HTTPError(url, 404, '', {}, None)
    monkeypatch.setattr(online, '_open', absent)
    with pytest.raises(HTTPError): online.latest(track='preview')
    assert len(calls) == 2 and all('/preview/' in url for url in calls)


@pytest.mark.parametrize('track', ['stable', 'preview'])
@pytest.mark.parametrize('fault', [None, 'channel', 'versions', 'hash'])
def test_real_signed_download_binds_feed_and_track(tmp_path, signing, monkeypatch, track, fault):
    import zipfile
    channel = 'private-stable' if track == 'stable' else 'private-candidate'
    path = package(tmp_path / 'signed.zip', signing, channel=channel)
    raw = path.read_bytes()
    with zipfile.ZipFile(path) as archive:
        manifest = json.loads(archive.read('release.json'))
    offer = dict(tracked_offer(raw, track=track),
                 versions={row['id']: row['version'] for row in manifest['components']})
    if fault == 'channel':
        other = 'preview' if track == 'stable' else 'stable'
        offer.update(track=other, prerelease=other == 'preview',
                     manifest_channel='private-candidate' if other == 'preview' else 'private-stable')
    if fault == 'versions': offer['versions']['plugin.video.bobbi'] = '9.0.0'
    if fault == 'hash': offer['sha256'] = '0' * 64
    monkeypatch.setattr(online, '_open', lambda _: Response(raw))
    if fault:
        with pytest.raises(UpdateError): online.download(offer, tmp_path / 'downloads', signing[1])
        assert not list((tmp_path / 'downloads').glob('online-*.zip'))
    else:
        assert online.download(offer, tmp_path / 'downloads', signing[1]).read_bytes() == raw


def test_mirror_attempts_share_twenty_second_budget_and_reserve_second(monkeypatch):
    now, deadlines = [100.0], []
    monkeypatch.setattr(online.time, 'monotonic', lambda: now[0])
    def transfer(url, maximum, consume, cancelled, progress, **kwargs):
        deadlines.append(kwargs['deadline'])
        if len(deadlines) == 1:
            now[0] = kwargs['deadline']
            raise UpdateError('ONLINE_TIMEOUT')
        consume(json.dumps(tracked_offer()).encode())
    monkeypatch.setattr(online, '_transfer', transfer)
    assert online.latest()['track'] == 'stable'
    assert deadlines == [110.0, 120.0]


def test_cancel_after_first_valid_mirror_never_returns_offer(monkeypatch):
    cancelled = [False]
    class First(Response):
        def read(self, size):
            block = super().read(size)
            if not block: cancelled[0] = True
            return block
    monkeypatch.setattr(online, '_open', lambda _: First(json.dumps(tracked_offer()).encode()))
    with pytest.raises(online.Cancelled): online.latest(lambda: cancelled[0])


@pytest.mark.parametrize('confirm', [True, False])
def test_product_preview_selection_requires_explicit_confirmation(entry, confirm):
    from bobbi_platform import ce_install_ui as ui
    entry.env.host.details = lambda _: {'version': '0.1.0'}
    choices = iter([7, 1])
    entry.dialog.select = lambda *args, **kwargs: next(choices)
    entry.dialog.yesno = lambda *args: confirm
    ui.main()
    assert online.selected_track(entry.env.work) == ('preview' if confirm else 'stable')
    assert entry.env.installer._read() is None
