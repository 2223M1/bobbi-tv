#!/usr/bin/env python3
"""Replay the actual movie card gates with public titles and bounded controls.

Loads production AST function bodies and real matching/year modules. Only
logging, Kodi LOGINFO and enum values are supplied; no matching function is
replaced. It does not query providers, open media, or establish why a specific
VCB result was absent from a live search.
"""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.repo.resolve()
    sys.path.insert(0, str(root / 'addons/script.module.bobbi.core/lib'))
    sys.path.insert(0, str(root / 'addons/plugin.video.bobbi'))
    from bobbi_core.candidate_titles import matches
    from bobbi_core.movie_years import from_details
    path = root / 'addons/plugin.video.bobbi/lib/search.py'
    tree = ast.parse(path.read_text(encoding='utf-8'))
    names = {'_cinema_requires_catalog_admission', '_cinema_filter_catalog_candidates', '_filter_movie_year_candidates'}
    definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    assert {node.name for node in definitions} == names
    scope = dict(Indexer=SimpleNamespace(JACKETT='Jackett'),
                 IndexerType=SimpleNamespace(TORRENT='Torrent', DIRECT='Direct', DEBRID='Debrid', STREMIO_DEBRID='Stremio Debrid'),
                 kodilog=lambda *a, **kw: None, xbmc=SimpleNamespace(LOGINFO=1))
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(path), 'exec'), scope)
    gate = scope['_cinema_filter_catalog_candidates']
    year_gate = scope['_filter_movie_year_candidates']
    # The first title is copied byte-for-byte from the final CE2051 public card
    # receipt. Other rows exercise generic grammar, not a title allow/deny list.
    cases = [
        ('actual_manga_publisher_alias', 'Claymore (01-27) (Yagi) (2006) [Digital-1920] [Manga FR] (PapriKa+)', ['Paprika', 'パプリカ'], False),
        ('other_movie_parenthetical_alias', 'Another Work 2006 1080p (Paprika)', ['Paprika', 'パプリカ'], False),
        ('synthetic_other_alias_publisher', 'Different Story (2006) [Manga FR] (Northern Light+)', ['Northern Light'], False),
        ('actual_vcb_positive', '[VCB-Studio] Paprika / パプリカ 10-bit 1080p HEVC BDRip [MOVIE]', ['Paprika', 'パプリカ'], True),
        ('bilingual_positive', 'Paprika (パプリカ) 2006 1080p BluRay', ['Paprika', 'パプリカ'], True),
        ('ordinary_positive', 'Paprika.2006.1080p.BluRay.x264-GROUP', ['Paprika', 'パプリカ'], True),
        ('other_publisher_negative', 'Claymore (01-27) (Yagi) (2006) [Digital-1920] [Manga FR] (OtherPublisher+)', ['Paprika', 'パプリカ'], False),
        ('wrong_year_negative', 'Paprika.2022.1080p.BluRay', ['Paprika', 'パプリカ'], False),
        ('manga_wrong_year_with_resolution', 'DARLING in the FRANXX (01-08) (Code:000-Yabuki) (2022) [Digital-1920] [Manga FR] (PapriKa+)', ['Paprika', 'パプリカ'], False),
    ]
    output = []
    for index, (name, title, aliases, expected) in enumerate(cases, 1):
        row = SimpleNamespace(title=title, indexer='Jackett', type='Torrent', infoHash=format(index, '040x'), preparedResourceId='')
        catalog = dict(aliases=aliases, tmdb_id=4977, evidence=from_details({'id': 4977, 'release_date': '2006-10-01'}, 4977))
        screened = gate([row], aliases, 'movies', anime=True)
        admitted = row in year_gate(screened, catalog)
        output.append(dict(case=name, title=title, aliases=aliases,
                           lexical_match=matches(title, aliases, 'movies'),
                           expected_admitted=expected, actual_admitted=admitted,
                           passed=admitted == expected))
    source_paths = ['addons/plugin.video.bobbi/lib/search.py',
                    'addons/script.module.bobbi.core/lib/bobbi_core/candidate_titles.py',
                    'addons/script.module.bobbi.core/lib/bobbi_core/movie_identity.py',
                    'addons/script.module.bobbi.core/lib/bobbi_core/movie_release_kind.py',
                    'addons/plugin.video.bobbi/lib/utils/general/anime_identity.py']
    result = dict(schema=1, scope='Production movie lexical/adaptation/year gates; local row fixtures; no remote provider or media IO',
                  source=[dict(path=p, sha256=hashlib.sha256((root/p).read_bytes()).hexdigest()) for p in source_paths],
                  cases=output, passed=sum(r['passed'] for r in output), failed=sum(not r['passed'] for r in output),
                  proves_vcb_omission_cause=False, proves_wrong_media_playback=False,
                  status='PASS' if all(r['passed'] for r in output) else 'FAIL')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('status', 'passed', 'failed')}))
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
