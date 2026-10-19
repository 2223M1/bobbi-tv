"""Presentation stays bounded without changing qualification or routing."""
from types import SimpleNamespace
import pytest
from lib.cinema.subtitle_projection import source_card_label, source_label
from lib.gui.source_select import _provider_display_name


@pytest.mark.parametrize('fonts,detail', [
    (True, '外挂中文可用'), (False, '外挂中文可用·字体样式待确认'),
])
def test_bound_subtitle_badge_reports_content_without_claiming_timeline_proof(fonts, detail):
    source = SimpleNamespace(type='Direct', guid='bobi:resource', preparedResourceId='resource',
        preparedSubtitle=dict(kind='external_chinese_binding', fonts_ready=fonts))
    assert source_card_label(source) == '外挂中文'
    assert len(source_card_label(source)) <= 8
    assert source_label(source) == detail
    source.type = 'Torrent'
    assert source_card_label(source) == ''


@pytest.mark.parametrize('raw,label', [('Torrent','BT种子'), ('Direct','直连资源'),
    ('Debrid','离线服务'), ('115','115'), ('Nyaa','Nyaa'),
    ('[COLOR red]Torrent[/COLOR]', 'BT种子')])
def test_provider_presentation_preserves_real_service_names(raw, label):
    assert _provider_display_name(raw) == label


def test_unknown_subtitle_evidence_never_invents_badge():
    assert source_card_label(SimpleNamespace()) == ''
