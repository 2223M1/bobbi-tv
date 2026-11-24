import pytest
from bobbi_platform import optimization as o


def test_failed_and_lost_ack_retry_with_same_event_then_delete(tmp_path, monkeypatch):
    clock = [1000]
    monkeypatch.setattr(o.time, 'time', lambda: clock[0])
    o.record(tmp_path, '0.1.98','install','space',3.7)
    sent=[]
    def attempt(e):
        sent.append(e)
        return len(sent)==2
    o.flush_one(tmp_path, lambda: True, attempt)
    o.flush_one(tmp_path, lambda: True, attempt)
    assert len(sent)==1 and o.status(tmp_path)==(True,1)
    clock[0]+=60
    o.flush_one(tmp_path, lambda: True, attempt)
    assert sent[0]==sent[1] and sent[0]['elapsed']==5
    assert set(sent[0])=={'v','id','build','stage','outcome','elapsed'}
    assert o.status(tmp_path)==(True,0)


def test_opt_out_and_profile_fence(tmp_path):
    a,b = tmp_path/'a',tmp_path/'b'
    o.record(a,'0.1.98','install','failed',0)
    o.record(b,'0.1.98','emby_play','handoff',5)
    o.set_enabled(a, False)
    o.record(a,'0.1.98','install','ok',0)
    o.set_enabled(a, True)
    o.flush_one(a,lambda:True,lambda _:pytest.fail('revived'))
    o.flush_one(b,lambda:False,lambda _:pytest.fail('revoked'))
    assert o.status(a)==(True,0) and o.status(b)==(True,1)


def test_no_free_text_no_unbounded_queue(tmp_path, monkeypatch):
    for field in range(3):
        args=['0.1.98','emby_play','failed']
        args[field]='https://private.example/?token=secret'
        with pytest.raises(ValueError):o.record(tmp_path,*args,0)
    assert not list(tmp_path.iterdir())
    for _ in range(o.LIMIT+2):o.record(tmp_path,'0.1.98','install','ok',0)
    assert o.status(tmp_path)==(True,o.LIMIT)
    later=o.time.time()+o.AGE+10
    monkeypatch.setattr(o.time,'time',lambda:later)
    o.flush_one(tmp_path,lambda:True,lambda _:pytest.fail('expired'))
    assert o.status(tmp_path)==(True,0)
