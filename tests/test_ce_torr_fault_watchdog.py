"""Simulation only: no real SIGSTOP/CONT, subprocess or device connection."""
from copy import deepcopy
import json
from pathlib import Path
import signal
import sys
import threading
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
import ce_torr_fault_remote as common
import ce_torr_fault_watchdog as watchdog
import ce_torr_fault_pause as driver


@pytest.fixture(autouse=True)
def portable_signal_numbers(monkeypatch):
    monkeypatch.setattr(signal, 'SIGSTOP', 19, raising=False)
    monkeypatch.setattr(signal, 'SIGCONT', 18, raising=False)


def receipt():
    return dict(schema=1,operation='inspect',state='inspected',can_inject=True,observation=1000,
        native=dict(request_id='a'*32,native_instance='11111111-2222-3333-4444-555555555555',
            selection_epoch=9,open_epoch=9,user_intent=0,file_identity_sha256='b'*64,url_sha256='c'*64),
        qualified=dict(prepared_entry_sha256='d'*64,media_id='tmdb:tv:1:s1:e1'),
        process=dict(pid=54321,start_ticks=1234,exe_path='/storage/engine/TorrServer',exe_device=1,
            exe_inode=2,exe_bytes=20,exe_sha256='e'*64,listen_inodes=['98765']),
        backend_sha256='f'*64,backend_port=8090,account_fingerprint='1'*64,account_epoch=2,boot_id_sha256='2'*64)


class Simulation:
    def __init__(self):
        self.now=0.
        self.state='S'
        self.calls=[]
        self.saved=[]
        self.stop_ack_lost=False
        self.cont_ack_lost=False
        self.restore_fails=False
        self.changed=False
    def clock(self): return self.now
    def wait(self,seconds): self.now+=seconds
    def check(self,target):
        if self.changed: raise common.Refused('PROCESS_CHANGED')
        return self.state
    def save(self,value): self.saved.append(deepcopy(value))
    def send(self,fd,number):
        assert fd==81
        self.calls.append((fd,number))
        if number==signal.SIGSTOP:
            self.state='T'
            if self.stop_ack_lost: raise TimeoutError('private STOP body')
        elif number==signal.SIGCONT:
            if self.restore_fails: raise PermissionError('private recovery body')
            self.state='S'
            if self.cont_ack_lost: raise TimeoutError('private CONT body')
        else: raise AssertionError('Only exact STOP/CONT are simulated')
    def run(self,observe=lambda:True,seconds=60):
        return watchdog.execute_pause(receipt()['process'],81,seconds,observe,self.save,
            self.send,self.check,self.clock,self.wait,recover_check=self.check)


def test_pause_once_restores_same_handle_before_sixty_seconds():
    sim=Simulation()
    result=sim.run()
    assert sim.calls==[(81,signal.SIGSTOP),(81,signal.SIGCONT)]
    assert result['state']=='restored' and result['deadline_met'] and sim.state=='S'
    assert 59 <= result['finished_at'] <= 60
    assert sim.saved[0]['state']=='stop_unconfirmed' and not sim.saved[0]['retry_allowed']


def test_lost_stop_ack_restores_immediately_without_repeating_stop():
    sim=Simulation();sim.stop_ack_lost=True
    result=sim.run()
    assert sim.calls==[(81,signal.SIGSTOP),(81,signal.SIGCONT)] and result['state']=='restored'
    assert sim.now==0 and 'private' not in json.dumps(result)


def test_lost_cont_ack_is_confirmed_from_state_without_false_failure():
    sim=Simulation();sim.cont_ack_lost=True
    result=sim.run(observe=lambda:False)
    assert result['state']=='restored' and result['recovery']['ack_uncertain']
    assert len(sim.calls)==2


def test_recovery_failure_is_retained_and_never_repeats_stop():
    sim=Simulation();sim.restore_fails=True
    result=sim.run(observe=lambda:False)
    assert result['state']=='recovery_failed' and not result['recovery']['confirmed']
    assert [number for _,number in sim.calls].count(signal.SIGSTOP)==1
    assert [number for _,number in sim.calls].count(signal.SIGCONT)==3
    assert sim.state=='T' and 'private' not in json.dumps(result)


def test_pid_reuse_during_pause_never_sends_signal_to_replacement():
    sim=Simulation()
    def changed():
        sim.changed=True
        return False
    result=sim.run(observe=changed)
    assert sim.calls==[(81,signal.SIGSTOP)] and result['state']=='recovery_failed'
    assert result['recovery']['state']=='identity_changed_no_signal'


def test_identity_change_or_already_stopped_before_attempt_sends_nothing():
    sim=Simulation();sim.changed=True
    with pytest.raises(common.Refused):sim.run()
    assert sim.calls==[]


def test_external_stop_between_initial_check_and_signal_is_not_resumed_by_us():
    sim=Simulation()
    checks=iter(['S','T'])
    result=watchdog.execute_pause(receipt()['process'],81,60,lambda:True,sim.save,
        sim.send,lambda target:next(checks),sim.clock,sim.wait)
    assert result['state']=='not_paused' and sim.calls==[]
    sim=Simulation();sim.state='T'
    with pytest.raises(common.Refused):sim.run()
    assert sim.calls==[]


def test_parent_loss_during_observation_still_runs_independent_recovery():
    sim=Simulation()
    def disconnected():raise BrokenPipeError('SSH gone')
    result=sim.run(observe=disconnected)
    assert result['state']=='restored' and sim.state=='S'
    assert sim.calls==[(81,signal.SIGSTOP),(81,signal.SIGCONT)]


def test_no_receipt_write_can_block_recovery_while_paused():
    sim=Simulation()
    def save(value):
        if value['state']=='paused':pytest.fail('No potentially blocking disk write while stopped')
        sim.save(value)
    result=watchdog.execute_pause(receipt()['process'],81,60,lambda:True,save,
        sim.send,sim.check,sim.clock,sim.wait,recover_check=sim.check)
    assert result['state']=='restored' and sim.calls[-1][1]==signal.SIGCONT


@pytest.mark.parametrize('change',['native','qualified','process','account_epoch','backend_sha256','owner'])
def test_live_guard_refuses_changed_scope_before_arm(monkeypatch,change):
    expected=receipt();fresh=deepcopy(expected)
    owner=dict(boot_id='3'*32,epoch=4,request_id=expected['native']['request_id'])
    current_owner=dict(owner)
    if change=='native':fresh['native']['native_instance']='other'
    elif change=='qualified':fresh['qualified']['prepared_entry_sha256']='0'*64
    elif change=='process':fresh['process']['start_ticks']+=1
    elif change=='owner':current_owner['epoch']+=1
    else:fresh[change]='changed'
    monkeypatch.setattr(watchdog,'capabilities',lambda:{'pidfd_supported':True})
    monkeypatch.setattr(watchdog,'current_inspection',lambda *args:fresh)
    monkeypatch.setattr(watchdog,'owner_binding',lambda *args:current_owner)
    monkeypatch.setattr(watchdog,'rpc',lambda *args:pytest.fail('Must fail before final native read'))
    with pytest.raises(common.Refused):watchdog.guard(expected,owner)


def test_paused_or_unsupported_device_cannot_arm(monkeypatch):
    expected=receipt()
    monkeypatch.setattr(watchdog,'capabilities',lambda:{'pidfd_supported':False})
    monkeypatch.setattr(watchdog,'current_inspection',lambda *args:pytest.fail('No inspection after unsupported'))
    with pytest.raises(common.Refused,match='PIDFD_UNAVAILABLE'):watchdog.guard(expected)
    monkeypatch.setattr(watchdog,'capabilities',lambda:{'pidfd_supported':True})
    monkeypatch.setattr(watchdog,'current_inspection',lambda *args:dict(expected,can_inject=False))
    with pytest.raises(common.Refused,match='PLAYER_PAUSED'):watchdog.guard(expected)


def test_no_ready_watchdog_never_writes_arm_or_signals(tmp_path,monkeypatch):
    expected=receipt();owner=dict(boot_id='3'*32,epoch=4,request_id=expected['native']['request_id'])
    directory=tmp_path/'new-run'
    monkeypatch.setattr(watchdog,'guard',lambda *args:(expected,owner))
    monkeypatch.setattr(watchdog,'directory_for',lambda run:directory)
    monkeypatch.setattr(watchdog,'private_directory',lambda path:path)
    monkeypatch.setattr(watchdog.time,'time',lambda:1000)
    calls=[]
    def launch(*args,**kwargs):
        calls.append((args,kwargs))
        return SimpleNamespace(pid=777,poll=lambda:1)
    monkeypatch.setattr(watchdog.subprocess,'Popen',launch)
    monkeypatch.setattr(watchdog,'send_pidfd',lambda *args:pytest.fail('Launcher must never signal'))
    with pytest.raises(common.Refused,match='WATCHDOG_NOT_READY'):
        watchdog.launch(dict(run_id='4'*32,inspection=expected,seconds=60),
            {'ce_torr_fault_remote.py':'# fixture','ce_torr_fault_watchdog.py':'# fixture'})
    assert not (directory/'arm.json').exists()
    assert calls[0][1]['start_new_session'] is True and calls[0][1]['close_fds'] is True


def test_transport_lost_ack_has_one_dispatch_and_exclusive_unconfirmed_receipt(tmp_path):
    output,calls=tmp_path/'pause.json',[]
    def sender(source,code):
        calls.append(code)
        assert json.loads(output.read_text())['state']=='unconfirmed'
        raise TimeoutError('auth=secret')
    result=driver.pause_once(tmp_path,output,receipt(),60,sender)
    assert result['state']=='unconfirmed' and len(calls)==1 and 'secret' not in output.read_text()
    with pytest.raises(FileExistsError):driver.pause_once(tmp_path,output,receipt(),60,sender)
    assert len(calls)==1


def test_generated_dispatch_and_collection_compile_without_device_or_subprocess():
    code=driver.launch_code(dict(run_id='4'*32,inspection=receipt(),seconds=60))
    compile(code,'remote-launch','exec')
    compile(driver.collect_code('4'*32),'collect','exec')
    assert 'systemctl stop' not in code and 'os.kill(' not in code
    assert code.count('signal.pidfd_send_signal(')==1


def test_original_process_exit_is_not_reported_as_restored_service():
    calls=[]
    def gone(target):raise ProcessLookupError()
    result=watchdog.resume_exact(81,receipt()['process'],send=lambda *args:calls.append(args),check=gone)
    assert result['state']=='original_process_exited' and not result['confirmed'] and not calls


def test_interrupted_recovery_read_still_continues_original_pidfd():
    sim=Simulation();reads=[0]
    def recovery(target):
        reads[0]+=1
        if reads[0]==1:raise InterruptedError('WATCHDOG_INTERRUPTED')
        return sim.check(target)
    result=watchdog.execute_pause(receipt()['process'],81,60,lambda:False,sim.save,
        sim.send,sim.check,sim.clock,sim.wait,recover_check=recovery)
    assert result['state']=='restored' and sim.state=='S'
    assert sim.calls==[(81,signal.SIGSTOP),(81,signal.SIGCONT)]


@pytest.mark.parametrize('error',[InterruptedError,PermissionError,FileNotFoundError])
def test_uncertain_procfs_never_prevents_cont_but_cannot_claim_confirmation(error):
    sim=Simulation();sim.state='T'
    def unavailable(target):raise error('private diagnostic')
    result=watchdog.resume_exact(81,receipt()['process'],sim.send,unavailable,sim.wait)
    assert result['state']=='recovery_failed' and not result['confirmed']
    assert sim.calls==[(81,signal.SIGCONT)]*3 and sim.state=='S'
    assert 'private' not in json.dumps(result)


@pytest.mark.parametrize('change',['deleted','renamed'])
def test_recovery_identity_ignores_executable_path_changes(tmp_path,monkeypatch,change):
    from test_ce_torr_fault import proc_fixture,stat_line
    proc,target,links=proc_fixture(tmp_path,monkeypatch)
    expected,_=common.process_identity(54321,proc=proc)
    monkeypatch.setattr(watchdog,'PROC',proc)
    (target/'stat').write_text(stat_line(state='T'))
    links[str(target/'exe')]=links[str(target/'exe')]+' (deleted)' if change=='deleted' else '/other/renamed'
    assert watchdog.recovery_process(expected)=='T'


def test_recovery_identity_rejects_definite_pid_lifetime_change(tmp_path,monkeypatch):
    from test_ce_torr_fault import proc_fixture,stat_line
    proc,target,links=proc_fixture(tmp_path,monkeypatch)
    expected,_=common.process_identity(54321,proc=proc)
    monkeypatch.setattr(watchdog,'PROC',proc)
    (target/'stat').write_text(stat_line(start=expected['start_ticks']+1,state='T'))
    with pytest.raises(common.Refused,match='PROCESS_CHANGED'):watchdog.recovery_process(expected)


def test_stuck_scope_observation_expires_without_blocking_actor():
    sim=Simulation();entered=threading.Event();release=threading.Event()
    def sample():
        entered.set();release.wait(2);return True
    observer=watchdog.ScopeObservation(sample,lambda:False,clock=sim.clock)
    observer.start()
    assert entered.wait(1)
    try:
        result=sim.run(observe=observer.current)
        assert result['state']=='restored' and result['finished_at']<2
        assert observer.thread.is_alive()
    finally:
        observer.close();release.set();observer.thread.join(1)


def test_cancellation_before_stop_sends_nothing_and_during_pause_recovers():
    sim=Simulation()
    result=watchdog.execute_pause(receipt()['process'],81,60,lambda:True,sim.save,
        sim.send,sim.check,sim.clock,sim.wait,recover_check=sim.check,cancelled=lambda:True)
    assert result['state']=='not_paused' and sim.calls==[]
    sim=Simulation()
    result=watchdog.execute_pause(receipt()['process'],81,60,lambda:True,sim.save,
        sim.send,sim.check,sim.clock,sim.wait,recover_check=sim.check,cancelled=lambda:sim.state=='T')
    assert result['state']=='restored' and result['resume_reason']=='watchdog_interrupted'


def fallback_fixture(tmp_path,monkeypatch,actor='gone',inode_change=False):
    from test_ce_torr_fault import proc_fixture,stat_line
    proc,target,links=proc_fixture(tmp_path,monkeypatch)
    identity,_=common.process_identity(54321,proc=proc)
    (target/'stat').write_text(stat_line(state='T'))
    (proc/'sys/kernel/random').mkdir(parents=True)
    (proc/'sys/kernel/random/boot_id').write_text('fixture-boot')
    (proc/str(watchdog.os.getpid())).mkdir()
    (proc/str(watchdog.os.getpid())/'stat').write_text(stat_line(pid=watchdog.os.getpid()))
    if actor!='gone':
        (proc/'9876').mkdir()
        (proc/'9876/stat').write_text(stat_line(pid=9876,start=78 if actor=='reused' else 77,
            state='Z' if actor=='zombie' else 'S'))
    expected=receipt();expected['process']=identity
    if inode_change:expected['process']['exe_inode']+=1
    expected['boot_id_sha256']=common.digest('fixture-boot')
    owner=dict(boot_id='3'*32,epoch=4,request_id=expected['native']['request_id'])
    target_hash=common.digest(common.encode(dict(inspection=watchdog.stable_inspection(expected,True),owner=owner)))
    run='4'*32;directory=tmp_path/'run';directory.mkdir()
    watchdog.write_json(directory/'intent.json',dict(run_id=run,inspection=expected,owner=owner,target_sha256=target_hash))
    watchdog.write_json(directory/'ready.json',dict(run_id=run,target_sha256=target_hash,
        watchdog_pid=9876,watchdog_start_ticks=77))
    watchdog.write_json(directory/'arm.json',dict(run_id=run,target_sha256=target_hash))
    watchdog.write_json(directory/'consumed.json',dict(run_id=run))
    watchdog.write_json(directory/'result.json',dict(run_id=run,request_id=expected['native']['request_id'],
        native_instance=expected['native']['native_instance'],state='stop_unconfirmed',
        recovery_deadline=60.,stop_attempted_at=0.))
    monkeypatch.setattr(watchdog,'PROC',proc)
    monkeypatch.setattr(watchdog,'directory_for',lambda _:directory)
    monkeypatch.setattr(watchdog,'private_directory',lambda path:path)
    sim=Simulation();sim.state='T'
    monkeypatch.setattr(watchdog.os,'pidfd_open',lambda *args:81,raising=False)
    monkeypatch.setattr(watchdog.os,'close',lambda fd:None)
    def send(fd,number,*unused):
        sim.send(fd,number)
        (target/'stat').write_text(stat_line(state=sim.state))
    monkeypatch.setattr(watchdog.signal,'pidfd_send_signal',send,raising=False)
    return run,expected,sim,directory,proc,target,links


@pytest.mark.parametrize('actor',['gone','reused','zombie'])
def test_fallback_only_continues_original_stopped_target_after_actor_exit(tmp_path,monkeypatch,actor):
    run,expected,sim,directory,proc,target,links=fallback_fixture(tmp_path,monkeypatch,actor)
    links[str(target/'exe')]+=' (deleted)'
    result=watchdog.resume_after_exit(run,expected['native']['request_id'],expected['native']['native_instance'])
    assert result['state']=='restored' and sim.calls==[(81,signal.SIGCONT)]
    assert json.loads((directory/'resume-result.json').read_text())['actor_confirmed_exited']


def test_fallback_live_actor_is_never_signalled_and_forbids_early_cont(tmp_path,monkeypatch):
    run,expected,sim,*_=fallback_fixture(tmp_path,monkeypatch,'alive')
    with pytest.raises(common.Refused,match='WATCHDOG_STILL_RUNNING'):
        watchdog.resume_after_exit(run,expected['native']['request_id'],expected['native']['native_instance'])
    assert sim.calls==[]


@pytest.mark.parametrize('change',['boot','inode','pid_reuse','request','already_running','missing_inode'])
def test_fallback_rechecks_exact_prior_identity_before_any_signal(tmp_path,monkeypatch,change):
    from test_ce_torr_fault import stat_line
    run,expected,sim,directory,proc,target,links=fallback_fixture(tmp_path,monkeypatch,inode_change=change=='inode')
    request=expected['native']['request_id']
    if change=='boot':(proc/'sys/kernel/random/boot_id').write_text('new-boot')
    elif change=='request':request='9'*32
    elif change=='already_running':(target/'stat').write_text(stat_line(state='S'))
    elif change=='missing_inode':monkeypatch.setattr(watchdog,'fallback_target',lambda target:(_ for _ in ()).throw(PermissionError()))
    elif change=='pid_reuse':
        def replaced(*args):
            (target/'stat').write_text(stat_line(start=9999,state='T'))
            return 81
        monkeypatch.setattr(watchdog.os,'pidfd_open',replaced)
    with pytest.raises((common.Refused,PermissionError)):
        watchdog.resume_after_exit(run,request,expected['native']['native_instance'])
    assert sim.calls==[]


def test_fallback_driver_never_redispatches_after_lost_ack(tmp_path):
    prior=dict(operation='pause',run_id='4'*32,request_id='a'*32,
               native_instance=receipt()['native']['native_instance'])
    output=tmp_path/'resume.json';calls=[]
    def sender(source,code):
        compile(code,'resume-test','exec');calls.append(code)
        raise TimeoutError('private')
    result=driver.resume_once(tmp_path,output,prior,sender)
    assert result['state']=='unconfirmed' and len(calls)==1 and 'private' not in output.read_text()
    with pytest.raises(FileExistsError):driver.resume_once(tmp_path,output,prior,sender)
    assert len(calls)==1


def test_fallback_receipt_write_failure_does_not_block_exact_cont(tmp_path,monkeypatch):
    run,expected,sim,*_=fallback_fixture(tmp_path,monkeypatch)
    def cannot_save(*args,**kwargs):
        assert sim.state=='S', 'Receipt IO must only happen after recovery'
        raise OSError('private disk error')
    monkeypatch.setattr(watchdog,'write_json',cannot_save)
    result=watchdog.resume_after_exit(run,expected['native']['request_id'],expected['native']['native_instance'])
    assert result['state']=='restored' and result['receipt_write_failed']
    assert sim.calls==[(81,signal.SIGCONT)] and 'private' not in json.dumps(result)


def test_successful_fallback_is_terminal_and_cannot_undo_later_external_stop(tmp_path,monkeypatch):
    from test_ce_torr_fault import stat_line
    run,expected,sim,directory,proc,target,links=fallback_fixture(tmp_path,monkeypatch)
    args=(run,expected['native']['request_id'],expected['native']['native_instance'])
    assert watchdog.resume_after_exit(*args)['state']=='restored'
    sim.state='T';(target/'stat').write_text(stat_line(state='T'))
    result=watchdog.resume_after_exit(*args)
    assert result['state']=='already_restored' and result['signal_sent'] is False
    assert sim.calls==[(81,signal.SIGCONT)] and sim.state=='T'
