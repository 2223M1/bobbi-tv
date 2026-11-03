"""Alias grammar reuse cannot erase work, season or special identity."""
import ast
from pathlib import Path
import random
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
from bobbi_core import episode_scope as scope


def legacy(text, aliases):
    names = {scope.normalized(a) for a in aliases if isinstance(a, str)} - {''}
    found = False
    for alias in sorted(names, key=len, reverse=True):
        qualified = False
        for base in names:
            if len(base) >= len(alias) or not alias.startswith(base):
                continue
            suffix = alias[len(base):]
            if not (suffix.startswith(' ') or (not base[-1].isascii() and not suffix[0].isascii())):
                continue
            if (scope._BONUS.search(suffix) or scope.release_season_markers(suffix)
                    or re.search(r'(?i)\bseason\b|[季期]', suffix)):
                qualified = True
                break
        if qualified:
            continue
        pattern = r'(?<![a-z0-9])' + r'[\W_]*'.join(re.escape(t) for t in alias.split()) + r'(?![a-z0-9])'
        text, count = re.subn(pattern, ' ', text, flags=re.I)
        found = found or bool(count)
    return text, found


def test_same_alias_grammar_is_built_once_and_mutation_gets_new_key(monkeypatch):
    scope._cached_alias_patterns.cache_clear()
    original = scope.normalized
    calls = []
    def counted(value):
        calls.append(value)
        return original(value)
    monkeypatch.setattr(scope, 'normalized', counted)
    aliases = ['Hyouka', '冰菓', 'Hyouka Season 2']
    for _ in range(100):
        assert scope._consume_aliases('Hyouka S01E01', aliases) == ('  S01E01', True)
    assert calls == aliases
    aliases.append('Example')
    assert scope._consume_aliases('Example S01E01', aliases)[1]
    assert calls == aliases[:3] + aliases
    scope._cached_alias_patterns.cache_clear()


def test_alias_grammar_is_equivalent_on_existing_identity_fixtures_and_generated_text():
    texts = set()
    for path in (ROOT/'tests').glob('test_*.py'):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        texts.update(node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)
                     and isinstance(node.value, str) and 2 <= len(node.value) <= 512
                     and ('Hyouka' in node.value or 'S01' in node.value or '进击' in node.value))
    aliases = ['Hyouka', '冰菓', 'Hyouka Season 2', 'Hyouka OVA', '进击的巨人',
               '進擊的巨人', 'Shingeki no Kyojin', 'Attack on Titan', 'Example',
               'Example Story', 'Example OVA', 'The Special Show', '!!!', None]
    rng = random.Random(2087)
    for _ in range(500):
        texts.add(''.join(rng.choices('Hyouka S01E02OVA剧场版冰菓[]_-. ', k=rng.randrange(1, 160))))
    for text in texts:
        assert scope._consume_aliases(text, aliases) == legacy(text, aliases)
    assert scope._cached_alias_patterns.cache_info().maxsize == 128


def test_large_alias_inputs_do_not_fill_grammar_cache():
    scope._cached_alias_patterns.cache_clear()
    for aliases in (['Hyouka']*129, ['x'*513], [None, [], {'title': 'x'}]):
        assert scope._consume_aliases('Hyouka S01E01', aliases) == legacy('Hyouka S01E01', aliases)
    assert scope._cached_alias_patterns.cache_info().currsize <= 1  # only empty validated tuple
