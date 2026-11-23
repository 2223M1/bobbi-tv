"""Repeated immutable lexical input must not repeatedly parse the same release."""
from itertools import product
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'addons/script.module.bobbi.core/lib'))
from bobbi_core import episode_scope as scope


@pytest.fixture(autouse=True)
def clean_projection():
    memo = getattr(scope, '_cached_release_scope', None)
    if memo:
        memo.cache_clear()
    yield
    if memo:
        memo.cache_clear()


def test_repeated_catalogue_input_parses_once(monkeypatch):
    calls = []
    consume = scope._consume_aliases
    def counted(*args):
        calls.append(1)
        return consume(*args)
    monkeypatch.setattr(scope, '_consume_aliases', counted)
    title, aliases = '[Group] Hyouka - 01 [1080p][FLAC]', ['Hyouka', '冰菓']
    first = scope.release_scope(title, aliases, 1, 2012)
    count = len(calls)
    assert count > 0
    for _ in range(4):
        assert scope.release_scope(title, list(aliases), 1, 2012) == first
    assert len(calls) == count, 'Repeated identical release scope still reparses the full title'


def test_every_identity_and_policy_input_is_part_of_the_key():
    title = 'Hyouka S01-S02 Complete [2012] [1080p]'
    for aliases, season, year, pack, filename in product(
            [['Hyouka'], ['Other'], ['Hyouka', 'Hyouka Special']],
            [0, 1, 2, 3], [None, 2012, 2013, (2011, 2012)], [False, True], [False, True]):
        expected = scope._release_scope(title, aliases, season, year, pack, filename)
        assert scope.release_scope(title, aliases, season, year, pack, filename) == expected
    aliases = ['Hyouka']
    assert scope.release_scope('Hyouka S01E01', aliases, 1) == 'matched'
    aliases[0] = 'Other'
    assert scope.release_scope('Hyouka S01E01', aliases, 1) != 'matched'


def test_alias_validation_and_cache_key_use_the_same_snapshot(monkeypatch):
    aliases = ['Hyouka']
    real_sum = sum
    def mutate_after_validation(values):
        result = real_sum(values)
        aliases[0] = []
        return result
    monkeypatch.setattr(scope, 'sum', mutate_after_validation, raising=False)
    assert scope.release_scope('Hyouka S01E01', aliases, 1) == 'matched'
    assert aliases == [[]]


def test_scope_projection_is_bounded_and_custom_inputs_stay_uncached():
    for index in range(600):
        scope.release_scope('Hyouka S01E01 [1080p] ' + str(index), ['Hyouka'], 1)
    assert scope._cached_release_scope.cache_info().currsize <= 512
    before = scope._cached_release_scope.cache_info()
    for aliases in (['Hyouka'] * 129, ['x' * 513], {'Hyouka'}):
        assert scope.release_scope('Hyouka S01E01', aliases, 1) == scope._release_scope('Hyouka S01E01', aliases, 1)
    assert scope._cached_release_scope.cache_info() == before


@pytest.mark.parametrize('year', [True, '2012', [2012], (2011, 2012, 2013)])
def test_invalid_year_does_not_raise_unhashable_or_accept_cached_verdict(year):
    assert scope.release_scope('Hyouka S01E01', ['Hyouka'], 1, year) == 'unknown'
