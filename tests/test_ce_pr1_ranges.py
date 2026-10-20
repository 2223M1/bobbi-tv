"""PR1 range counterexamples on the product selector/preparation/owner chain."""
import hashlib
import json

import pytest

from test_bobbi_torrent_adapter import (Clock, FakeOwner, Session, Response,
    request, config, status, HASH, RID)
from bobbi_core.filename_semantics import parse_filename
from bobbi_core.release_identity import bound_family
from bobbi_core.episode_revision import compatible_pair, continuation_family
from bobbi_core.catalog_release import release_envelope
from bobbi_core.source_intent import verified_intents
from bobbi_core.torrent_selection import select_exact_file
from bobbi_core.playback_owner import PlaybackOwner
from bobbi_torrent.backend import Backend
from bobbi_torrent.resolver import Resolver


CASES = [
    ('S01E01-02v2', False), ('S01E01+02v2', False), ('S01E01&02v10', False),
    ('S01E01v2-02v2', False), ('1x01-02v2', False), ('S01E01-02', False),
    ('S01E01-E02v2', False), ('S01E01v2-E02v2', False), ('S01E01v2', True),
    ('S01E01-1080p', True), ('S01E01.[1920x1080.HEVC]', True),
    ('S01E01.[7E23ABCD]', True), ('S01E02', False), ('S01E01.S01E02', False),
]
RANGES = [token for token, _ in CASES[:8]] + [
    'S01E01v10+02v2', 'S01E01V2&02V10', '1x01v2-02v10',
    'S01E01–02v2', 'S01E01~02v2', 'S01E01～02v10',
]


def filename(token):
    return 'Audit.Show.' + token + '.1080p.HEVC.mkv'


def file(token, number=1):
    return dict(id=number, path=filename(token), length=1000000)


def binding():
    return json.dumps(dict(media_id='tmdb:42', season=1, episode=1,
        absolute_episode=1, source_info_hash=HASH, provenance='catalog-v1'))


def intent(selected):
    return dict(request_id=RID, purpose='current',
        media=dict(tmdb_id=42, kind='tv', season=1, episode=1, anime=True,
                   title='Audit Show', release_title='Audit Show S01'),
        selected=dict(source_info_hash=HASH, torrent_file_id=selected['id'],
                      torrent_path=selected['path'], torrent_file_bytes=selected['length']))


CATALOG = dict(provider='tmdb', id=42, kind='tv', aliases=['Audit Show'],
    year=2021, response_sha256='c'*64, ambiguous=False)


@pytest.mark.parametrize('token,accepted', CASES)
def test_web_fourteen_scenarios_on_family_and_both_selectors(token, accepted):
    selected = file(token)
    operations = [lambda: bound_family(selected['path'], 1, 1)]
    for proof in ('', binding()):
        operations.append(lambda proof=proof: select_exact_file(
            [selected], 1, 1, 'Audit Show S01', HASH, proof))
    for operation in operations:
        if accepted:
            assert operation()
        else:
            with pytest.raises(ValueError):
                operation()


@pytest.mark.parametrize('token', RANGES)
def test_range_never_seeds_automatic_current_or_next_preparation(token):
    selected = file(token)
    metadata = dict(hash=HASH, name='Audit Show S01', file_stats=[selected])
    with pytest.raises(ValueError):
        verified_intents(intent(selected), metadata, 'account', '/target',
                         select_exact_file, CATALOG)
    assert parse_filename(selected['path']).episode_pairs() == {(1, 1), (1, 2)}
    assert release_envelope(selected['path'], 1, 1) is None
    with pytest.raises(ValueError):
        continuation_family(selected['path'], 1, 1)
    assert not compatible_pair(selected['path'], filename('S01E02'), 1, 1, 'a'*64, 'b'*64)


@pytest.mark.parametrize('tail', ['-03v2', '+03v2', '&03v10', 'v2-03v2'])
def test_next_range_cannot_cancel_valid_current_or_become_next(tail):
    current, following = file('S01E01'), file('S01E02' + tail, 2)
    targets = verified_intents(intent(current), dict(hash=HASH, name='Audit Show S01',
        file_stats=[current, following]), 'account', '/target', select_exact_file, CATALOG)
    assert len(targets) == 1 and targets[0][0]['purpose'] == 'current'
    assert targets[0][0]['version_key'] == hashlib.sha256(
        bound_family(current['path'], 1, 1).encode()).hexdigest()


@pytest.mark.parametrize('token', RANGES[:5])
def test_real_resolver_requires_manual_choice_and_owner_cannot_upgrade_it(token):
    selected, clock, choices = file(token), Clock(), []
    info = dict(status(selected), name='Audit Show S01')
    owner = FakeOwner(clock)
    owner.choose_file = lambda files: choices.append(files) or files[0]
    session = Session([Response(b'MatriX.144.1'), Response({'hash': HASH}),
        Response(info), Response(info), Response(b''), Response(info)])
    result = Resolver(Backend(config(), session, clock), owner, Session([]), clock).resolve(
        request(title='Audit Show', release_title='Audit Show S01', episode_binding=binding()))
    assert choices == [[selected]]
    assert result['file_evidence'] == 'USER_CONFIRMED_FILE'
    assert not owner.targets  # No automatic preparation notification.
    actor = PlaybackOwner('boot')
    actor.select('boot', 0, RID, 'bt:' + HASH)
    args = ('boot', 1, RID)
    assert actor.bind_file(*args, 'bt:' + HASH, 'file', result['file_evidence'])
    assert not actor.bind_file(*args, 'bt:' + HASH, 'file', 'AUTO_VERIFIED_FILE')
    assert actor.claim_start(*args, 'resolved_url')
    assert actor.observe_started(*args, 'native', 'file')
    assert actor.observe_terminal('native', 'NATURAL_EOF')
    assert not actor.consume_next(*args, 'native')


@pytest.mark.parametrize('revision', ['v2', 'v10'])
def test_single_revision_keeps_exact_key_and_permits_same_release_next(revision):
    current, following = file('S01E01' + revision), file('S01E02' + revision, 2)
    targets = verified_intents(intent(current), dict(hash=HASH, name='Audit Show S01',
        file_stats=[current, following]), 'account', '/target', select_exact_file, CATALOG)
    assert [t[0]['purpose'] for t in targets] == ['current', 'next']
    expected = 'audit show EP ' + revision + ' 1080p hevc'
    assert bound_family(current['path'], 1, 1) == expected
    assert {t[0]['version_key'] for t in targets} == {hashlib.sha256(expected.encode()).hexdigest()}
