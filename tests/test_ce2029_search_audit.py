"""Independent CE2029 counterexamples: real providers and matching/publication.

The Jackett transport is bounded synthetic RSS; its actual HTTP fanout, RSS
parser, TorrentStream conversion and production catalogue/episode gate execute.
Only Kodi UI and settings are stubbed. No device or outside service is touched.
"""
import ast
from pathlib import Path
import sys
import time
from types import SimpleNamespace
from xml.sax.saxutils import escape

import pytest

from test_provider_streaming import chain, Response
from test_share_subtitle_references import API, entry, fetch, sidecar

ROOT = Path(__file__).resolve().parents[1]
LIB = ROOT / 'addons/plugin.video.bobbi/lib'


@pytest.fixture
def provider_gate(chain, monkeypatch):
    chain.stub('lib.utils.kodi.utils', get_setting=lambda key, default=None:
               True if key == 'include_season_packs' else default,
               notification=lambda *args: None, translation=str,
               kodilog=lambda *args, **kwargs: None)
    monkeypatch.setattr(chain.jackett, 'get_setting',
                        sys.modules['lib.utils.kodi.utils'].get_setting)
    chain.package('lib.cinema', LIB/'cinema')
    chain.stub('lib.cinema._shared')
    for name in ('utils.parsers.title_parser', 'utils.parsers.pack_parser',
                 'utils.general.source_resolution', 'utils.general.anime_identity',
                 'utils.general.processors'):
        chain.load('lib.'+name, LIB.joinpath(*name.split('.')).with_suffix('.py'))
    # Import the production gate without importing Kodi's GUI/action tree.
    # No function body, matching decision or provider result is replaced.
    source = LIB/'search.py'
    tree = ast.parse(source.read_text(encoding='utf-8'))
    names = {'_cinema_requires_catalog_admission', '_cinema_filter_catalog_candidates'}
    definitions = [node for node in tree.body
                   if isinstance(node, ast.FunctionDef) and node.name in names]
    scope = dict(Indexer=SimpleNamespace(JACKETT='Jackett'),
                 kodilog=lambda *args, **kwargs: None, xbmc=SimpleNamespace(LOGINFO=1))
    exec(compile(ast.Module(body=definitions, type_ignores=[]), str(source), 'exec'), scope)

    def request(titles, aliases, anime=True):
        raw = ('<rss><channel>' + ''.join(
            '<item><title>'+escape(title)+'</title><link>magnet:?xt=urn:btih:'+
            format(i+1, '040x')+'</link><size>12345</size></item>'
            for i, title in enumerate(titles)) + '</channel></rss>').encode()
        responses = []
        def get(url, **kwargs):
            result = Response(raw)
            responses.append(result)
            return result
        client = chain.jackett.Jackett('http://fixture.invalid', 'fixture-key', '9117',
            None, session=SimpleNamespace(headers={}, get=get))
        client._configured_indexers = ['nyaasi']
        published = []
        gate = scope['_cinema_filter_catalog_candidates']
        def checked(rows):
            published.extend(gate(rows, aliases, 'tv', 1, 1, anime=anime))
        result = client.search(aliases[0], 'tv', 1, 1, deadline=time.monotonic()+2,
                               publish=checked)
        assert result is not None and result.completion.complete
        assert responses and all(response.closed for response in responses)
        filtered = gate(result, aliases, 'tv', 1, 1, anime=anime)
        return {row.title for row in filtered}, {row.title for row in published}
    return request


@pytest.mark.parametrize('title,aliases', [
    pytest.param('Keep Your Hands Off Eizouken! (Nogizaka46 Drama) - S01E01 (1080p)',
     ['Keep Your Hands Off Eizouken!'], marks=pytest.mark.xfail(strict=True,
         reason='Known live-action row lacks strong type evidence in retained provider data; '
                'do not guess from a performer name plus Drama')),
    ('Example Series (Live Action) S01E01 1080p', ['Example Series']),
    ('Example Series S01E01 [真人版][1080p]', ['Example Series']),
    ('Example Series S01E01 [真人][1080p]', ['Example Series']),
    ('Example Series S01E01 真人 1080p', ['Example Series']),
    ('Example Series S01E01 [実写版][1080p]', ['Example Series']),
    ('Example Series S01E01 実写 1080p', ['Example Series']),
    ('[真人版] Example Series S01E01 1080p', ['Example Series']),
    ('[Group] Example Series S01E01 (Live-Action) 1080p', ['Example Series']),
])
def test_real_provider_never_publishes_explicit_live_action_for_animation(provider_gate, title, aliases):
    good = '[Group] '+aliases[0]+' S01E01 1080p'
    final, incremental = provider_gate([title, good], aliases)
    assert final == {good}
    assert incremental == {good}


@pytest.mark.parametrize('title,aliases,anime', [
    ('[Group] Example Series S01E01 1080p', ['Example Series'], True),
    ('[Drama] Example Series S01E01 1080p', ['Example Series'], True),
    ('[Live Action Fansubs] Example Series S01E01 1080p', ['Example Series'], True),
    ('Example Series S01E01 1080p [Live Action Fansubs]', ['Example Series'], True),
    ('[Group] My Live Action Club S01E01 1080p', ['My Live Action Club'], True),
    ('[Group] 真人版 S01E01 1080p', ['真人版'], True),
    ('Example Series (Fantasy Drama) S01E01 1080p', ['Example Series'], True),
    ('Example Series (Historical Drama) S01E01 1080p', ['Example Series'], True),
    ('Example Series (Some Unknown Drama) S01E01 1080p', ['Example Series'], True),
    ('Example Series S01E01 1080p Some Unknown Drama', ['Example Series'], True),
    ('[Group] My Drama Club S01E01 1080p', ['My Drama Club'], True),
    ('Example Series (Live Action) S01E01 1080p', ['Example Series'], False),
])
def test_no_type_contradiction_and_non_anime_requests_remain_visible(provider_gate, title, aliases, anime):
    final, incremental = provider_gate([title], aliases, anime)
    assert final == incremental == {title}


@pytest.mark.parametrize('name', ['Example 第二季 EP02.chs.srt',
    'Example 2nd Season EP02.chs.srt', 'Example OVA EP02.chs.srt',
    'Example S01E02,03.chs.srt', 'Example EP02、03.chs.srt'])
def test_share_reference_cannot_publish_conflicting_or_multi_episode_subtitle(tmp_path, name):
    api = API(refs={'7':entry(name=name)})
    with pytest.raises(sidecar.Stopped, match='NOT_FOUND'):
        fetch(tmp_path, api, transport=lambda *args, **kwargs:
              pytest.fail('Conflicting subtitle must be rejected before CDN download'))
    assert not (tmp_path/'subs').exists()


@pytest.mark.parametrize('name', ['中文字幕.srt', 'Example 第一季 EP02.chs.srt',
                                'Example S01E02.chs.srt'])
def test_share_reference_retains_generic_same_episode_and_shifted_high_quality_subtitles(tmp_path, name):
    result = fetch(tmp_path, API(refs={'7':entry(name=name)}))
    assert result['state'] == 'candidate'
    assert Path(result['file']['path']).is_file()


@pytest.mark.parametrize('title', ['Special', 'The Second Season', '第二季', 'OVA Story'])
def test_share_sidecar_season_and_special_words_in_canonical_title_are_not_declarations(title):
    context = dict(mode='series', title=title, season=1, episode=2)
    assert sidecar.matches(title+' S01E02.mkv', title+' EP02.chs.srt', True, context)
    assert not sidecar.matches(title+' S01E02.mkv', title+' 第三季 EP02.chs.srt', True, context)


@pytest.mark.parametrize('title,tag', [('第二季', '第二季'), ('Special', 'Special'),
                                     ('OVA', 'OVA'), ('2nd Season', '2nd Season')])
@pytest.mark.parametrize('prefix', ['', '[Group] '])
def test_repeated_canonical_season_word_does_not_erase_separate_season_declaration(title, tag, prefix):
    from bobbi_core.subtitle_candidates import rank
    from bobbi_core.subtitle_episode import SingleSeason
    context = dict(mode='series', title=title, season=1, episode=2, tmdb=42,
                   _subtitle_single_season=SingleSeason(42, 12))
    filename = prefix + title + ' ' + tag + ' EP02.chs.srt'
    assert not sidecar.matches(title+' S01E02.mkv', filename, True, context)
    assert rank(dict(videoname=title, filename=filename, lang={'langlist': {'langchs': True}}), context) is None


@pytest.mark.parametrize('title,group', [('Special', 'Specialist'), ('OVA Story', 'OVAStory'),
                                      ('The Second Season', 'The Second Seasons'),
                                      ('Example', 'Example')])
def test_group_and_partial_title_words_do_not_steal_canonical_title_exemption(title, group):
    from bobbi_core.subtitle_candidates import rank
    from bobbi_core.subtitle_episode import SingleSeason
    context = dict(mode='series', title=title, season=1, episode=2, tmdb=42,
                   _subtitle_single_season=SingleSeason(42, 12))
    filename = '['+group+'] '+title+' EP02.chs.srt'
    assert sidecar.matches(title+' S01E02.mkv', filename, True, context)
    assert rank(dict(videoname=title, filename=filename, lang={'langlist': {'langchs': True}}), context) is not None


@pytest.mark.parametrize('tag', ['S02', '第二季', '2nd Season', 'OVA'])
def test_leading_explicit_season_tag_is_not_discarded_as_a_group(tag):
    context = dict(mode='series', title='Example', season=1, episode=2)
    assert not sidecar.matches('Example S01E02.mkv', '['+tag+'] Example EP02.chs.srt', True, context)
