"""Pure network-free TVBox/T4 diagnosis and header-value safety tests (REV-12 & R13)."""
import json
import pytest

from bobbi_core import t4
from bobbi_core.library_contract import LibraryError


def test_diagnose_config_classifies_type3_spiders_relative_jar_and_lives_without_network():
    synthetic = {
        'spider': 'https://cdn.example.invalid/main.jar;md5;deadbeef',
        'wallpaper': 'https://wall.example.invalid/',
        'rules': [{'name': 'ad-strip', 'hosts': ['cdn.example.invalid']}],
        'sites': [
            {
                'key': 'AlistSynthetic',
                'name': 'Synthetic AList',
                'type': 3,
                'api': 'csp_AListSh',
                'jar': './libs/local_proxy.jar;md5;11223344',
                'searchable': 1,
                'ext': [{'name': 'Movies', 'server': 'http://192.168.10.20:5678/', 'startPage': '/movies'}],
            },
            {
                'key': 'DrpyJS',
                'name': 'JS Spider',
                'type': 3,
                'api': 'https://cdn.example.invalid/js/drpy2.min.js',
                'ext': 'https://cdn.example.invalid/js/site.js',
                'searchable': 0,
            },
            {
                'key': 'LegacyXml',
                'name': 'Old XML CMS',
                'type': 0,
                'api': 'https://cms.example.invalid/api.php/provide/vod/at/xml/',
            },
        ],
        'lives': [
            {'name': 'Channel Group A', 'type': 0, 'url': 'https://iptv.example.invalid/live.m3u', 'epg': 'https://epg.example.invalid/'},
            {'name': 'Channel Group B', 'type': 0, 'url': 'http://192.168.10.20:5678/iptv.m3u', 'ua': 'okhttp/3.15'},
        ],
    }
    raw = json.dumps(synthetic, ensure_ascii=False).encode('utf-8')
    diag = t4.diagnose_config(raw)
    assert diag['ok'] is True
    assert diag['can_save_t4'] is False
    assert diag['error_code'] == 'T4_NO_SITES'
    assert diag['counts'] == {
        'type4': 0,
        'type3': 2,
        'unsupported_type': 1,
        'unsupported_headers': 0,
        'invalid': 0,
        'lives': 2,
    }
    assert diag['type3_spiders'][0]['spider_kind'] == 'csp_jar'
    assert diag['type3_spiders'][0]['relative_jar_missing_base'] is True
    assert diag['type3_spiders'][0]['native_hint'] == 'alist'
    assert diag['type3_spiders'][1]['spider_kind'] == 'remote_js'
    assert diag['type3_spiders'][1]['relative_jar_missing_base'] is False
    assert set(diag['unsupported_top_fields']) == {'lives', 'rules', 'spider', 'wallpaper'}
    # Ensure raw server URLs in ext / lives are never leaked in the public diagnosis payload
    serialized = json.dumps(diag, ensure_ascii=False)
    assert '192.168.10.20' not in serialized

    # Providing base_url resolves the relative JAR base requirement
    diag_with_base = t4.diagnose_config(raw, base_url='https://sub.example.invalid/tvbox/config.json')
    assert diag_with_base['type3_spiders'][0]['relative_jar_missing_base'] is False


def test_r13_03_04_site_and_play_header_name_and_value_secret_inspection():
    # Valid site User-Agent and same-origin Referer are preserved (not silently dropped!)
    good_cfg = json.dumps({
        'sites': [{
            'key': 't4_ua',
            'name': 'T4 With UA',
            'type': 4,
            'api': 'https://vod.example.invalid/t4/api',
            'header': {
                'User-Agent': 'BobbiT4Client/2.0',
                'Referer': 'https://vod.example.invalid/',
            },
        }]
    }).encode('utf-8')
    p = t4.preview(good_cfg)
    assert len(p.sites) == 1
    assert p.sites[0]['headers'] == {
        'User-Agent': 'BobbiT4Client/2.0',
        'Referer': 'https://vod.example.invalid/',
    }
    src = p.source('https://vod.example.invalid/config.json')
    t4.validate_saved(src)

    # Sensitive values inside allowlisted header names (e.g. token in Referer or Bearer in UA)
    # or oversized / control-char / disallowed header names are explicitly rejected, never silently dropped!
    bad_headers = [
        {'Cookie': 'session=secret'},
        {'Authorization': 'Bearer secret-token'},
        {'Referer': 'https://vod.example.invalid/?token=secret'},
        {'Referer': 'https://other-origin.example.invalid/'},
        {'User-Agent': 'CustomClient Bearer abcdef123456'},
        {'User-Agent': 'Bad\r\nInjected: 1'},
        {'User-Agent': 'x' * 1025},
    ]
    for hdr in bad_headers:
        bad_cfg = json.dumps({
            'sites': [{
                'key': 'bad_hdr',
                'name': 'Bad Header Site',
                'type': 4,
                'api': 'https://vod.example.invalid/t4/api',
                'header': hdr,
            }]
        }).encode('utf-8')
        diag = t4.diagnose_config(bad_cfg)
        assert diag['can_save_t4'] is False
        assert diag['counts']['unsupported_headers'] == 1
        assert diag['error_code'] == 'T4_HEADERS'
        prev = t4.preview(bad_cfg)
        assert len(prev.sites) == 0 and prev.unsupported_headers == 1
        with pytest.raises(LibraryError, match='^T4_HEADERS$'):
            prev.source('')
