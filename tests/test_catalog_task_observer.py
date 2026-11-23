"""Native visible task observation never changes executor ownership or retries writes."""
from copy import deepcopy
import sys
from types import SimpleNamespace

import pytest

from bobbi_platform import catalog_ui, cloud_hub


@pytest.fixture
def observer(monkeypatch):
    state = SimpleNamespace(now=0., calls=[], messages=[], closed=False, canceled=False,
                            cancel_at=None, responses=[], account_reads=0,
                            expected={'account_id': '115:'+'a'*64, 'epoch': 1, 'authenticated': True})
    progress = SimpleNamespace(create=lambda *args:state.messages.append(args),
        update=lambda percent,message:state.messages.append((percent,message)),
        close=lambda:setattr(state,'closed',True),
        iscanceled=lambda:state.canceled or state.cancel_at is not None and state.now>=state.cancel_at)
    def wait(seconds):
        state.now += seconds
        return False
    monitor = SimpleNamespace(abortRequested=lambda:False,waitForAbort=wait)
    monkeypatch.setitem(sys.modules,'xbmc',SimpleNamespace(Monitor=lambda:monitor))
    monkeypatch.setitem(sys.modules,'xbmcgui',SimpleNamespace(DialogProgress=lambda:progress))
    monkeypatch.setattr(catalog_ui,'time',SimpleNamespace(monotonic=lambda:state.now))
    def call(action,body,timeout):
        assert timeout == 2
        state.calls.append((state.now,action,deepcopy(body)))
        if action=='account_status':
            state.account_reads+=1
            return deepcopy(state.expected)
        result=state.responses.pop(0) if state.responses else OSError('offline')
        if isinstance(result,Exception):
            raise result
        return result
    monkeypatch.setattr(catalog_ui,'call',call)
    return state


def job(state='running',cancel=False):
    return {'items':[{'state':state,'kind':'scan','stage':'directory_scan','task_id':'b'*32,
                      'counts':{'scanned':7,'discovered':2},'cancel_requested':cancel}], 'next_offset':None}


def test_native_observer_shows_requested_then_confirmed_cancel_without_inventing_percent(observer):
    observer.responses=[job(cancel=True),job('canceled')]
    catalog_ui._watch_jobs({'provider':'quark'},offset=5)
    assert [(round(t),action) for t,action,_ in observer.calls]==[(0,'catalog_jobs'),(5,'catalog_jobs')]
    assert '等待后台确认' in observer.messages[1][1] and '已取消' in observer.messages[2][1]
    assert '已扫描 7 / 已发现 2' in observer.messages[1][1]
    assert all('%' not in str(message) for message in observer.messages)
    assert observer.closed and not any(action=='catalog_cancel' for _,action,_ in observer.calls)


def test_return_closes_only_observer_not_background_task(observer):
    observer.responses=[job()];observer.cancel_at=1
    catalog_ui._watch_jobs({'provider':'quark'})
    assert len(observer.calls)==1 and observer.closed and observer.now<2


def test_failure_backoff_and_total_deadline_are_finite(observer):
    observer.responses=[job()]
    catalog_ui._watch_jobs({'provider':'quark'})
    times=[round(t) for t,_,_ in observer.calls]
    assert times==[0,5,15,35,65,95]
    assert observer.now<=120.001 and observer.closed
    assert all(action=='catalog_jobs' for _,action,_ in observer.calls)


def test_account_generation_failure_stops_old_summary_immediately(observer):
    observer.responses=[job(),ValueError('CATALOG_ACCOUNT_MISMATCH')]
    catalog_ui._watch_jobs({'provider':'quark'})
    assert len(observer.calls)==2 and observer.now<6
    assert '账号或服务已变化' in observer.messages[-1][1] and observer.closed


def test_preparation_observer_uses_current_115_scope_and_keeps_uncertain_as_uncertain(observer):
    observer.responses=[{'items':[{'state':'uncertain','stage':'uncertain','counts':{},'cancel_requested':False}], 'next_offset':None}]
    dialog=SimpleNamespace(ok=lambda *args:pytest.fail('valid current account must display tasks'))
    catalog_ui.watch_preparation(dialog=dialog)
    calls=[(action,body) for _,action,body in observer.calls]
    assert calls==[('account_status',{}),('account_status',{}),
                  ('jobs',dict(expected=observer.expected,kind='preparation',offset=0,limit=5))]
    assert '结果待核对' in observer.messages[-1][1] and '不自动重试未知结果' in observer.messages[-1][1]
    assert observer.closed


def test_preparation_explicit_stale_scope_cannot_query_new_account(observer):
    messages=[]
    catalog_ui.watch_preparation(dict(observer.expected,epoch=0),dialog=SimpleNamespace(ok=lambda *args:messages.append(args)))
    assert [action for _,action,_ in observer.calls]==['account_status']
    assert messages[0][0]=='准备任务暂不可读'


def test_preparation_scope_rechecked_before_every_snapshot(observer,monkeypatch):
    old=deepcopy(observer.expected);calls=[]
    def call(action,body,timeout):
        calls.append((action,deepcopy(body)))
        if action=='account_status':
            return dict(old,epoch=2) if len(calls)>3 else old
        return {'items':[{'state':'running','stage':'downloading','counts':{},'cancel_requested':False}], 'next_offset':None}
    monkeypatch.setattr(catalog_ui,'call',call)
    catalog_ui.watch_preparation(dialog=SimpleNamespace(ok=lambda *args:None))
    assert [action for action,_ in calls].count('jobs')==1
    assert '账号或服务已变化' in observer.messages[-1][1] and observer.closed


def test_cloud_detailed_menu_has_live_preparation_entry_and_preserves_existing_indexes(observer,monkeypatch):
    selected=[7,-1];seen=[];menus=[]
    monkeypatch.setattr(cloud_hub,'status',lambda:dict(authenticated=True,preparation={'state':'NOT_CONFIGURED'}))
    monkeypatch.setattr(cloud_hub.cd2_mounts,'discover',lambda:())
    monkeypatch.setattr(catalog_ui,'watch_preparation',lambda **kw:seen.append(kw))
    dialog=SimpleNamespace(select=lambda title,labels:menus.append(labels) or selected.pop(0))
    cloud_hub.details(dialog)
    assert seen==[{'dialog':dialog}]
    assert menus[0][6]=='原生多网盘 · 接入与验证'
    assert menus[0][7]=='115 准备任务 · 只读实时状态'
