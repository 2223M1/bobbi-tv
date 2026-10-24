from types import SimpleNamespace

import pytest

from bobbi_platform import ce_install_ui as ui


@pytest.mark.parametrize('skin,font', [('skin.bobbi.cinema','Default'), ('skin.estuary','Arial'), ('skin.estuary','User')])
def test_keeps_existing_skin_or_font(monkeypatch, skin, font):
    monkeypatch.setattr(ui,'rpc',lambda method,params: {'value':font})
    host=SimpleNamespace(skin=lambda:skin)
    assert ui.readable_text(host,object()) is True


@pytest.mark.parametrize('accept',[False,True])
def test_first_stock_font_requires_explicit_choice(monkeypatch,accept):
    calls=[]; state={'font':'Default'}
    def rpc(method,params):
        calls.append((method,params))
        if method=='Settings.GetSettingValue':return {'value':state['font']}
        assert params=={'setting':'lookandfeel.font','value':'Arial'}
        state['font']='Arial';return True
    monkeypatch.setattr(ui,'rpc',rpc)
    checks=[]
    host=SimpleNamespace(skin=lambda:'skin.estuary',check_idle=lambda:checks.append('idle'))
    def choose(title,message):
        assert title.isascii() and message.isascii()
        return accept
    assert ui.readable_text(host,SimpleNamespace(yesno=choose)) is accept
    assert state['font']==('Arial' if accept else 'Default')
    assert len(checks)==(2 if accept else 1)
    assert all(p['setting']=='lookandfeel.font' for _,p in calls)


def test_new_playback_during_prompt_prevents_font_change(monkeypatch):
    monkeypatch.setattr(ui,'rpc',lambda method,params: {'value':'Default'} if method=='Settings.GetSettingValue' else pytest.fail('must not write'))
    calls=[]
    def idle():
        calls.append(1)
        if len(calls)==2:raise RuntimeError('PLAYBACK_ACTIVE')
    host=SimpleNamespace(skin=lambda:'skin.estuary',check_idle=idle)
    with pytest.raises(RuntimeError,match='PLAYBACK_ACTIVE'):
        ui.readable_text(host,SimpleNamespace(yesno=lambda *a:True))


def test_silent_setting_noop_is_not_success(monkeypatch):
    monkeypatch.setattr(ui,'rpc',lambda method,params: {'value':'Default'} if method=='Settings.GetSettingValue' else True)
    messages=[]
    host=SimpleNamespace(skin=lambda:'skin.estuary',check_idle=lambda:None)
    dialog=SimpleNamespace(yesno=lambda *a:True,ok=lambda *a:messages.append(a))
    assert ui.readable_text(host,dialog) is False
    assert messages and all(s.isascii() for s in messages[0])
