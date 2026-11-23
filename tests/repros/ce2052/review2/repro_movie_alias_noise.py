#!/usr/bin/env python3
"""Replay explicit manga/uploader false positives through production search.

Uses the repository's test_provider_streaming.chain fixture only to supply
Kodi/settings stubs and module loading. Production Jackett HTTP fanout, RSS
parser, TorrentStream conversion, catalogue gate, year filter, source ranking
and SourceListSession execute. Remote HTTP bodies are synthetic; there is no
real provider, account, device, or playback. The first bad title is copied from
the frozen CE2051 device receipt. It proves an admission defect, not the cause
of the missing VCB row or that the device used this precise provider.
"""
import argparse
import ast
from contextlib import ExitStack
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import time
from types import SimpleNamespace
from xml.sax.saxutils import escape


OBSERVED = 'Claymore (01-27) (Yagi) (2006) [Digital-1920] [Manga FR] (PapriKa+)'
VCB = '[VCB-Studio] Paprika / パプリカ 10-bit 1080p HEVC BDRip [MOVIE]'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expect', required=True, choices=['current-bug','fixed'])
    args = parser.parse_args()
    repo = args.repo.resolve()
    import pytest
    fixture_path = repo/'tests/test_provider_streaming.py'
    spec = importlib.util.spec_from_file_location('audit_chain_fixture', fixture_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    lib = repo/'addons/plugin.video.bobbi/lib'
    with TemporaryDirectory(prefix='ce2051-alias-noise-') as directory, pytest.MonkeyPatch.context() as monkey:
        chain = module.chain.__wrapped__(monkey, Path(directory))
        chain.stub('lib.utils.kodi.utils', get_setting=lambda key, default=None:default,
                   notification=lambda *a,**k:None, translation=str, kodilog=lambda *a,**k:None)
        chain.package('lib.cinema', lib/'cinema')
        chain.stub('lib.cinema._shared')
        for name in ('utils.parsers.title_parser','utils.parsers.pack_parser',
                     'utils.general.source_resolution','utils.general.anime_identity',
                     'utils.general.processors','utils.general.cinema_source_rank'):
            chain.load('lib.'+name, lib.joinpath(*name.split('.')).with_suffix('.py'))
        source_path = lib/'search.py'
        tree = ast.parse(source_path.read_text(encoding='utf-8'))
        names = {'_cinema_requires_catalog_admission','_cinema_filter_catalog_candidates','_filter_movie_year_candidates'}
        definitions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
        assert len(definitions) == len(names)
        scope = dict(Indexer=SimpleNamespace(JACKETT='Jackett'),
                     IndexerType=SimpleNamespace(TORRENT='Torrent', DIRECT='Direct', DEBRID='Debrid', STREMIO_DEBRID='Stremio'),
                     kodilog=lambda *a,**k:None, xbmc=SimpleNamespace(LOGINFO=1))
        exec(compile(ast.Module(body=definitions,type_ignores=[]),str(source_path),'exec'),scope)
        from bobbi_core.source_list_session import SourceListSession
        from bobbi_core.candidate_titles import matches
        from bobbi_core.movie_years import from_details
        from lib.utils.general.cinema_source_rank import rank_sources
        cases = []
        plans = [dict(name='observed_device_title', title='Paprika', aliases=['Paprika','パプリカ','红辣椒'], tmdb=4977,
                      bad=OBSERVED, goods=[VCB,'Paprika.2006.1080p.BluRay.x264.mkv']),
                 dict(name='generic_uploader_collision', title='Orchid', aliases=['Orchid'], tmdb=101,
                      bad='Moonlight Files (01-12) (Writer) (2006) [Digital-1920] [Manga EN] (Orchid+)',
                      goods=['[Group] Orchid.2006.1080p.BluRay.x264.mkv'])]
        for plan in plans:
            aliases = plan['aliases']
            wrong = 'Different Film.2006.1080p.BluRay.mkv'
            titles = [plan['bad'],*plan['goods'],wrong]
            raw = ('<rss><channel>'+''.join(
                '<item><title>'+escape(title)+'</title><link>magnet:?xt=urn:btih:'+format(i+1,'040x')+
                '</link><size>12345</size></item>' for i,title in enumerate(titles))+'</channel></rss>').encode()
            responses = []
            def get(url, **kwargs):
                response = module.Response(raw)
                responses.append(response)
                return response
            client = chain.jackett.Jackett('http://fixture.invalid','fixture-key','9117',None,
                                           session=SimpleNamespace(headers={},get=get))
            client._configured_indexers = ['nyaasi']
            evidence = from_details(dict(id=plan['tmdb'],release_date='2006-10-01'),plan['tmdb'])
            catalog = dict(aliases=aliases,evidence=evidence,tmdb_id=plan['tmdb'])
            context = dict(mode='movies',query=plan['title'],genre_ids=[16],ids=dict(tmdb_id=plan['tmdb']))
            session = SourceListSession(dict(tmdb=plan['tmdb'],mode='movies'),
                lambda rows:rank_sources(scope['_filter_movie_year_candidates'](rows,catalog),context))
            streamed = []
            def screen(rows):
                return scope['_cinema_filter_catalog_candidates'](rows,aliases,'movies',anime=True)
            def publish(rows):
                kept = screen(rows)
                streamed.extend(row.title for row in kept)
                session.publish(session.epoch,'Jackett',kept,'RUNNING')
            result = client._search_cinema(plan['title'],'movies',1,1,None,None,2006,'',
                movie_years=evidence,movie_tmdb_id=plan['tmdb'],deadline=time.monotonic()+3,publish=publish)
            assert result.completion.complete and responses and all(response.closed for response in responses)
            kept = screen(result)
            session.publish(session.epoch,'Jackett',kept,'COMPLETE',completion=result.completion)
            snapshot = session.snapshot(full=True)
            visible = [row.title for _,row in snapshot['entries']]
            cases.append(dict(name=plan['name'],requested=plan['title'],aliases=aliases,
                bad_title=plan['bad'],title_matcher_admitted=matches(plan['bad'],aliases,'movies'),
                streamed_bad=plan['bad'] in streamed,final_gate_bad=any(row.title==plan['bad'] for row in kept),
                visible_bad=plan['bad'] in visible,visible_titles=visible,
                good_titles_preserved=all(title in visible for title in plan['goods']),
                different_title_rejected=wrong not in visible,provider_completion=result.completion.state,
                source_count=len(snapshot['entries']),http_responses_closed=all(response.closed for response in responses)))
    violations = []
    for row in cases:
        if not row['good_titles_preserved'] or not row['different_title_rejected']:
            violations.append(row['name']+': positive/negative control failed')
        observed = row['streamed_bad'] and row['final_gate_bad'] and row['visible_bad']
        fixed = not row['streamed_bad'] and not row['final_gate_bad'] and not row['visible_bad']
        if not (observed if args.expect=='current-bug' else fixed):
            violations.append(row['name']+': expected '+args.expect+' contract not satisfied')
    paths = ['addons/script.module.bobbi.core/lib/bobbi_core/candidate_titles.py',
             'addons/plugin.video.bobbi/lib/search.py','addons/plugin.video.bobbi/lib/clients/jackett.py',
             'tests/test_provider_streaming.py']
    receipt = dict(source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
        source_sha256={path:hashlib.sha256((repo/path).read_bytes()).hexdigest() for path in paths},
        expect=args.expect,contract_passed=not violations,violations=violations,
        zero_exit_means='defect reproduced' if args.expect=='current-bug' else 'fixed contract satisfied',
        scope=__doc__,new_device_execution=False,external_network=False,
        device_evidence='review-evidence/ce-new-work-paprika-cards-1792661501419521300.json',
        missing_vcb_cause='not established by this probe',cases=cases)
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(receipt,ensure_ascii=False,indent=2))
    raise SystemExit(1 if violations else 0)


if __name__=='__main__':
    main()
