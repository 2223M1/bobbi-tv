"""Presentation-only failures never revive playback control or remove a card."""
import ast
from copy import deepcopy
import json
from pathlib import Path
from threading import Event
from types import SimpleNamespace, ModuleType, MethodType
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
for addon in ('script.module.bobbi.core', 'script.module.bobbi.platform', 'script.module.bobbi.catalog'):
    sys.path.insert(0, str(ROOT/'addons'/addon/'lib'))

from bobbi_core import share_failure as failure
from bobbi_core.source_list_session import SourceListSession
from bobbi_platform import runtime

OWNER = dict(boot_id='a'*32, epoch=2, request_id='b'*32, file_identity='file-exact',
             native_instance='11111111-2222-3333-4444-555555555555', url_sha256='c'*64)
ACCOUNT = dict(account_id='115:'+'d'*64, epoch=3, authenticated=True)


def source():
    return SimpleNamespace(type='Direct', indexer='Juku · 115分享', guid='juku:'+'e'*64,
        url='am6bjuku://'+'e'*64, title='fixture.mkv', size=10, verifiedShareFile=True)


def player():
    return SimpleNamespace(_owner_context={k: OWNER[k] for k in ('boot_id', 'epoch', 'request_id', 'file_identity')},
        _startup_failure_receipt=deepcopy(OWNER), _read_startup_failure=lambda: deepcopy(OWNER),
        _startup_failure_category='native_startup_error')


@pytest.mark.parametrize('field,value', [('boot_id','f'*32), ('epoch',4), ('request_id','f'*32),
    ('file_identity','other-file'), ('native_instance','other-native'), ('url_sha256','f'*64)])
def test_receipt_must_be_fresh_and_match_original_failure(field, value):
    current = player()
    current._read_startup_failure = lambda: dict(OWNER, **{field:value})
    assert failure.presentation_receipt(current, OWNER, OWNER['request_id']) is None


def test_exact_failed_receipt_is_read_only():
    assert failure.presentation_receipt(player(), OWNER, OWNER['request_id']) == OWNER
    assert failure.presentation_receipt(player(), dict(OWNER, epoch=9), OWNER['request_id']) is None


@pytest.mark.parametrize('mutate', [lambda result:result.update(account=dict(ACCOUNT,epoch=9)),
    lambda result:result.update(owner=dict(OWNER,url_sha256='f'*64)),
    lambda result:result.update(tuple_sha256='f'*64),
    lambda result:result['failure'].update(code='unsafe server text'),
    lambda result:result['failure'].update(api_code=True),
    lambda result:result['failure'].update(extra='private'),
    lambda result:result.update(extra='private')])
def test_typed_query_requires_closed_exact_result(monkeypatch, mutate):
    item = dict(_account=ACCOUNT, ids={'tmdb_id':1}, mode='movies')
    card = source()
    def call(action, body, timeout):
        assert action == 'share_failure' and timeout == .3
        result = dict(matched=True, account=ACCOUNT, owner=OWNER,
            tuple_sha256=failure.tuple_hash(body['selected']),
            failure=dict(code='share_revoked',api_code=4100010,http_status=None,invalidation_failed=True))
        mutate(result)
        return result
    monkeypatch.setattr(runtime, 'call', call)
    assert failure.read_failure(card, item, OWNER) is None


def test_only_captured_exact_card_can_lose_verified_and_publish_cannot_revive_it():
    session = SourceListSession({'tmdb':1}, lambda rows:rows)
    card = source()
    assert session.publish(session.epoch, 'juku', [card], state='RUNNING')
    key = session.key(card)
    selected = session.capture(session.epoch, key)
    assert selected is not card
    assert not session.invalidate_share('wrong', selected)
    assert not session.invalidate_share(session.epoch, SimpleNamespace(**dict(vars(selected),size=11)))
    assert session.invalidate_share(session.epoch, selected)
    session.reopen()
    assert session.publish(session.epoch, 'juku', [card], state='COMPLETE')
    rows = session.snapshot()['entries']
    assert len(rows) == 1 and rows[0][0] == key and not rows[0][1].verifiedShareFile
    assert card.verifiedShareFile and selected.verifiedShareFile


def error_method():
    path = ROOT/'addons/plugin.video.bobbi/lib/gui/resolver_window.py'
    cls = next(node for node in ast.parse(path.read_text(encoding='utf-8')).body
               if isinstance(node,ast.ClassDef) and node.name=='ResolverWindow')
    node = next(node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name=='handle_playback_error')
    scope = dict(json=json, get_property=lambda key:'', kodilog=lambda *a,**kw:None,
                 xbmc=SimpleNamespace(LOGWARNING=2))
    exec(compile(ast.Module(body=[node],type_ignores=[]), str(path), 'exec'),scope)
    return scope['handle_playback_error']


@pytest.mark.parametrize('reason',['cancel_event','user_cancelled','superseded','no_receipt','av_started'])
def test_cancelled_or_superseded_ui_never_presents_old_failure(reason, monkeypatch):
    closed=[]
    window = SimpleNamespace(media_started=False,resolved=False,cancel_event=Event(),user_cancelled=False,
        _window_context=OWNER,player=player(),item_information={'request_id':OWNER['request_id']},
        _owns_selection=lambda:False,error_message='',close=lambda:closed.append(True),setProperty=lambda *a:None)
    if reason=='cancel_event': window.cancel_event.set()
    if reason=='user_cancelled': window.user_cancelled=True
    if reason=='superseded': window._window_context=dict(OWNER,epoch=99)
    if reason=='no_receipt': window.player._read_startup_failure=lambda:None
    if reason=='av_started': window.media_started=True
    monkeypatch.setattr(failure,'read_failure',lambda *args:pytest.fail('no typed query for cancelled presenter'))
    error_method()(window)
    assert window.error_message=='' and window._owns_selection() is False


def test_exact_cancelled_preav_error_can_present_typed_cause_without_control(monkeypatch):
    card=source()
    window=SimpleNamespace(media_started=False,resolved=False,cancel_event=Event(),user_cancelled=False,
        _window_context=OWNER,player=player(),item_information={'request_id':OWNER['request_id']}, source=card,
        _owns_selection=lambda:False,error_message='',close=lambda:None,setProperty=lambda *a:None)
    monkeypatch.setattr(failure,'read_failure',lambda *args:dict(code='share_revoked',api_code=4100010,
        http_status=None,invalidation_failed=True))
    error_method()(window)
    assert '分享已被取消' in window.error_message and not card.verifiedShareFile
    assert window.share_failure['invalidation_failed'] and window._owns_selection() is False


@pytest.mark.parametrize('race', ['owner_changed', 'account_changed', 'user_cancelled', 'cancel_event'])
def test_query_cannot_publish_after_presentation_scope_changes(monkeypatch, race):
    card=source()
    window=SimpleNamespace(media_started=False,resolved=False,cancel_event=Event(),user_cancelled=False,
        _window_context=OWNER,player=player(),item_information={'request_id':OWNER['request_id']}, source=card,
        _owns_selection=lambda:False,error_message='',close=lambda:None,setProperty=lambda *a:None)
    def query(*args):
        if race == 'owner_changed': window.player._read_startup_failure=lambda:None
        if race == 'account_changed':
            def unavailable(): raise RuntimeError('PLAYBACK_ACCOUNT_CHANGED')
            window.player._read_startup_failure=unavailable
        if race == 'user_cancelled': window.user_cancelled=True
        if race == 'cancel_event': window.cancel_event.set()
        return dict(code='share_revoked',api_code=4100010,http_status=None,invalidation_failed=True)
    monkeypatch.setattr(failure,'read_failure',query)
    error_method()(window)
    assert not window.error_message and not hasattr(window,'share_failure') and card.verifiedShareFile


def test_real_unscoped_manual_owner_requires_frozen_account_on_final_receipt(tmp_path, monkeypatch):
    from bobbi_core.playback_authority import PlaybackAuthority
    from bobbi_core import playback_request
    from test_accounts import logged_in, credential
    manager, scope = logged_in(tmp_path)
    class Native:
        epoch=0
        current=None
        def state(self):
            return dict(protocol=1,selection_epoch=self.epoch,playback=deepcopy(self.current),
                        gui_generation=0,gui_user_intent=0,fullscreen_instance='')
        def intent(self, command):
            assert command['expected_epoch']==self.epoch
            self.epoch+=1
            return dict(reserved=True,selection_epoch=self.epoch)
    native=Native()
    authority=PlaybackAuthority(native)
    authority.configure_accounts(manager)
    original=authority.dispatch({'operation':'snapshot'})
    args=dict(boot_id=original['boot_id'],epoch=original['epoch'],request_id='b'*32)
    args['epoch']=authority.dispatch(dict(args,operation='select',selection_identity='release'))['epoch']
    assert authority.selection_account is None  # Ordinary hand-picked source, not continuation.
    assert authority.dispatch(dict(args,operation='bind_file',selection_identity='release',
        file_identity='release|file',url_sha256='c'*64))['bound']
    assert authority.dispatch(dict(args,operation='claim_start',route='resolved_url'))['status']=='CLAIMED'
    native.current=dict(protocol=1,native_instance=OWNER['native_instance'],request_id=args['request_id'],
        file_identity='release|file',url_sha256='c'*64,phase='OPEN',sequence=1,user_intent=0,paused=False)
    authority.refresh()
    native.current.update(phase='TERMINAL',reason='ERROR',sequence=2)
    authority.refresh()
    context=dict(args,file_identity='release|file')
    monkeypatch.setattr(playback_request,'call',authority.dispatch)
    prior=playback_request.startup_failure(context,account_scope=scope)
    assert prior and playback_request.startup_failure(context)==prior
    adapter=ModuleType('lib.cinema.playback_request')
    adapter.call,adapter.startup_failure=authority.dispatch,playback_request.startup_failure
    monkeypatch.setitem(sys.modules,'lib.cinema.playback_request',adapter)
    path=ROOT/'addons/plugin.video.bobbi/lib/native_player.py'
    cls=next(node for node in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(node,ast.ClassDef))
    node=next(node for node in cls.body if isinstance(node,ast.FunctionDef) and node.name=='_read_startup_failure')
    namespace={}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
    current=SimpleNamespace(_owner_context=context,_startup_failure_receipt=prior,
        _startup_failure_category='native_startup_error',data={'_account':scope})
    current._read_startup_failure=MethodType(namespace['_read_startup_failure'],current)
    card=source()
    window=SimpleNamespace(media_started=False,resolved=False,cancel_event=Event(),user_cancelled=False,
        _window_context=context,player=current,item_information=dict(request_id=args['request_id'],_account=scope),
        source=card,_owns_selection=lambda:False,error_message='',close=lambda:None,setProperty=lambda *a:None)
    def query(*unused):
        manager.install(credential('456'),scope)
        assert authority.account_changed() is False
        assert playback_request.startup_failure(context)==prior  # Legacy observation has no account scope.
        return dict(code='share_revoked',http_status=None,api_code=4100010,invalidation_failed=False)
    monkeypatch.setattr(failure,'read_failure',query)
    error_method()(window)
    assert not window.error_message and not hasattr(window,'share_failure') and card.verifiedShareFile
    assert authority.owner.desired['cancelled'] is True
