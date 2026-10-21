#!/usr/bin/env python3
"""Real subtitle rank + candidate materialization, deterministic provider IO.

No network, accounts, device, or playback command. The canonical TMDb record
contains one regular season and a specials season, just as the new code allows.
The fixture file bytes are benign Chinese SRT; only their provider-declared
episode/season filename changes. Synthetic labels are never real-world proof.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    root = args.repo.resolve()
    sys.path.insert(0, str(root / 'addons/script.module.bobbi.core/lib'))
    from bobbi_core.subtitle_candidates import AssrtCandidates, LookupStopped, rank
    try:
        from bobbi_core.subtitle_episode import from_details
    except ImportError:
        # The older implementation ignores this new evidence field entirely.
        # Use an inert stand-in so the provider/file fixtures are unchanged.
        from_details = lambda data, identifier: SimpleNamespace(tmdb=identifier, episodes=11)
    canonical = dict(id=60811, name='Ping Pong The Animation', number_of_seasons=1,
                     seasons=[dict(season_number=0, episode_count=2),
                              dict(season_number=1, episode_count=11)])
    scope = from_details(canonical, 60811)
    context = dict(title='Ping Pong The Animation', mode='series', season=1,
                   episode=1, tmdb=60811, year=2014, duration=1400,
                   release='Vodes 1080p HEVC', _subtitle_single_season=scope)
    raw = ('1\n00:00:01,000 --> 00:00:03,000\n这是字幕测试\n\n'
           '2\n00:00:05,000 --> 00:00:07,000\n继续字幕测试\n').encode()
    cases = [
        ('single-season-ep01', 'Ping Pong The Animation EP01.chs.srt', {}, None, True),
        ('single-season-asian-01', 'Ping Pong The Animation 第01話.chs.srt', {}, None, True),
        ('wrong-episode', 'Ping Pong The Animation EP02.chs.srt', {}, None, False),
        ('explicit-other-season', 'Ping Pong The Animation S02E01.chs.srt', {}, None, False),
        ('range-ep', 'Ping Pong The Animation EP01-EP02.chs.srt', {}, None, False),
        ('range-asian', 'Ping Pong The Animation 第01話-第02話.chs.srt', {}, None, False),
        ('special-ova', 'Ping Pong The Animation OVA EP01.chs.srt', {}, None, False),
        ('special-labelled', 'Ping Pong The Animation Specials EP01.chs.srt', {}, None, False),
        ('special-chinese', 'Ping Pong The Animation 番外篇 第01話.chs.srt', {}, None, False),
        ('other-season-chinese-digit', 'Ping Pong The Animation 第2季 EP01.chs.srt', {}, None, False),
        ('other-season-chinese-word', 'Ping Pong The Animation 第二季 第01話.chs.srt', {}, None, False),
        ('other-season-ordinal', 'Ping Pong The Animation 2nd Season EP01.chs.srt', {}, None, False),
        ('missing-scope', 'Ping Pong The Animation EP01.chs.srt', {'_subtitle_single_season': None}, None, False),
        ('wrong-tmdb', 'Ping Pong The Animation EP01.chs.srt', {'tmdb': 999}, None, False),
        ('out-of-range', 'Ping Pong The Animation EP12.chs.srt', {'episode': 12}, None, False),
        ('explicit-pack-season', 'Ping Pong The Animation EP01.chs.srt', {'season': 2, '_subtitle_single_season': None}, 'Ping Pong The Animation S02', True),
        ('metadata-season-conflict', 'Ping Pong The Animation EP01.chs.srt', {}, 'Ping Pong The Animation S02', False),
        ('filename-no-episode', 'Ping Pong The Animation.chs.srt', {}, None, False),
        ('explicit-first-season', 'Ping Pong The Animation S01E01.chs.srt', {'_subtitle_single_season': None}, None, True),
        ('duplicate-conflicting-episodes', 'Ping Pong The Animation EP01 EP02.chs.srt', {}, None, False),
    ]
    results = []
    with tempfile.TemporaryDirectory(prefix='ce2024-subtitle-review-') as temp:
        for name, filename, overrides, videoname, expected in cases:
            active = dict(context, **overrides)
            source = dict(id=1234, native_name='Ping Pong The Animation',
                          videoname=videoname or 'Ping Pong The Animation BD 1080p HEVC',
                          lang={'langlist': {'langchs': True}}, subtype='SRT')
            target = Path(temp) / name
            provider = AssrtCandidates(None, target / 'state')
            calls = []
            def search(query, deadline, cancelled):
                calls.append(dict(operation='search', query=query))
                return [dict(source)]
            def api(operation, params, deadline, cancelled):
                assert operation == 'detail'
                calls.append(dict(operation=operation))
                return [dict(source, filelist=[dict(f=filename, url='https://fixture.invalid/subtitle.srt')])]
            def read(url, deadline, cancelled, **kwargs):
                assert url == 'https://fixture.invalid/subtitle.srt'
                calls.append(dict(operation='read'))
                return raw
            provider.search, provider.api, provider.read = search, api, read
            score = rank(dict(source, filename=filename), active)
            candidate, stopped = None, None
            try:
                candidate = provider.candidates(active, provider.clock() + 10,
                                                lambda: False, root=target / 'text')
            except LookupStopped as error:
                stopped = str(error)
            accepted = candidate is not None
            results.append(dict(id=name, filename=filename, expected_candidate=expected,
                actual_candidate=accepted, passed=accepted == expected,
                rank=list(score) if score is not None else None,
                materialized_bytes=candidate['file']['bytes'] if candidate else None,
                materialized_sha256=candidate['file']['sha256'] if candidate else None,
                candidate_state=candidate.get('state') if candidate else None,
                stop_reason=stopped, calls=calls))
    paths = ['addons/script.module.bobbi.core/lib/bobbi_core/subtitle_candidates.py',
             'addons/script.module.bobbi.core/lib/bobbi_core/subtitle_episode.py',
             'addons/script.module.bobbi.core/lib/bobbi_core/filename_semantics.py']
    sources = []
    for path in paths:
        p = root / path
        if p.exists():
            data = p.read_bytes()
            sources.append(dict(path=path, bytes=len(data), sha256=hashlib.sha256(data).hexdigest(),
                git_blob_sha1=hashlib.sha1(('blob '+str(len(data))+'\0').encode()+data).hexdigest()))
    output = dict(schema=1, scope='Real rank + AssrtCandidates.candidates; deterministic provider IO; no device',
        canonical_fixture=canonical, count=len(results), passed=sum(r['passed'] for r in results),
        failed=sum(not r['passed'] for r in results), tests=results, sources=sources,
        expectation_note='An explicit non-S1 season or Special/OVA file must not become an automatic S1E1 candidate; exact subtitle display still needs native receipt.')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(dict(count=output['count'], passed=output['passed'], failed=output['failed'],
                          failed_ids=[r['id'] for r in results if not r['passed']]), ensure_ascii=False))
    return int(bool(output['failed']))


if __name__ == '__main__':
    raise SystemExit(main())
