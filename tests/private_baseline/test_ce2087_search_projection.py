"""Identity/ranking speedups must preserve the existing admission semantics."""
from copy import deepcopy
import pytest

from lib.domain.torrent import TorrentStream


def test_catalog_gate_uses_identity_fast_path_without_losing_equal_copies(monkeypatch):
    from lib import search
    calls = []
    equality = TorrentStream.__eq__
    def counted(left, right):
        calls.append(1)
        return equality(left, right)
    monkeypatch.setattr(TorrentStream, '__eq__', counted)
    rows = [TorrentStream(title='Hyouka S01E01 [1080p]', indexer=search.Indexer.JACKETT,
        type='Torrent', infoHash='%040x' % number) for number in range(120)]
    result = search._cinema_filter_catalog_candidates(rows, ['Hyouka'], 'tv', 1, 1, anime=True)
    assert [id(row) for row in result] == [id(row) for row in rows]
    assert len(calls) < 120 * 120, 'Catalog membership repeats whole-dataclass comparisons'
    original = TorrentStream(title='Hyouka - 01 [1080p]', indexer='Jackett',
                             type='Torrent', infoHash='a'*40)
    copies = [original, deepcopy(original)]
    result = search._cinema_filter_catalog_candidates(copies, ['Hyouka'], 'tv', 1, 1, anime=True)
    assert [id(row) for row in result] == [id(row) for row in copies]


@pytest.mark.parametrize('enum_value', [False, True])
@pytest.mark.parametrize('title,expected', [
    ('Hyouka - 01 [1080p]', True), ('Other Story - 01 [1080p]', False),
    ('Hyouka - 02 [1080p]', False), ('Hyouka S02E01 [1080p]', False),
    ('Hyouka OVA - 01 [1080p]', False)])
def test_real_jackett_string_and_constant_apply_identical_identity_gate(enum_value, title, expected):
    from lib import search
    source = TorrentStream(title=title, indexer=search.Indexer.JACKETT if enum_value else 'Jackett')
    assert search._cinema_requires_catalog_admission(source)
    assert bool(search._cinema_filter_catalog_candidates([source], ['Hyouka'], 'tv', 1, 1,
                                                        anime=True)) is expected


def test_locator_character_rejection_matches_previous_rule_for_all_unicode():
    from lib.utils.general import cinema_source_dedupe as dedupe
    pattern = dedupe._INVALID_LOCATOR
    # Python's Unicode whitespace semantics must stay identical to isspace().
    for code in range(0x110000):
        char = chr(code)
        assert bool(pattern.search(char)) == (code < 33 or code == 127 or char.isspace())
