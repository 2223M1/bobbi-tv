"""Detached, one-shot TorrServer fault actor with pidfd-scoped recovery.

No caller sends STOP. After READY + one ARM, this independent actor alone may
send it once, then CONT in finally. This avoids a delayed SSH caller sending a
late STOP after a separate recovery deadline has already expired. No service,
backend, player, mount, CD2, firmware or proxy setting is changed.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

from ce_torr_fault_remote import (KODI, PROC, RID, Refused, account_scope, capabilities, current_inspection,
    digest, encode, host, native_binding, proc_stat, process_identity, read_json, read_text, require, rpc, safe_error)

MAX_SECONDS = 60
ARM_SECONDS = 8
RECOVERY_RESERVE = .5
OBSERVATION_MAX_AGE = 1.0


def directory_for(run_id):
    require(RID.fullmatch(str(run_id)), 'SCOPE_INVALID')
    return Path('/tmp') / ('bobbi-torr-fault-' + run_id)


def private_directory(path):
    path = Path(path)
    require(path.parent == Path('/tmp') and path.name.startswith('bobbi-torr-fault-')
        and path.is_dir() and not path.is_symlink() and path.stat().st_uid == os.geteuid()
        and path.stat().st_mode & 0o077 == 0, 'PRIVATE_DIRECTORY_INVALID')
    return path


def write_json(path, value, exclusive=False):
    path = Path(path)
    if exclusive:
        with path.open('x', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, allow_nan=False)
            stream.flush()
            os.fsync(stream.fileno())
        return
    temporary = path.with_suffix('.pending')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, allow_nan=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(str(temporary), str(path))


def stable_inspection(value, include_intent=False):
    require(value.get('schema') == 1 and value.get('operation') == 'inspect' and value.get('state') == 'inspected',
            'RECEIPT_INVALID')
    fields = ('request_id','native_instance','selection_epoch','open_epoch','file_identity_sha256','url_sha256')
    if include_intent:
        fields += ('user_intent',)
    native = {key: value['native'][key] for key in fields}
    return dict(native=native, qualified=value['qualified'], process=value['process'],
        backend_sha256=value['backend_sha256'], backend_port=value['backend_port'],
        account_fingerprint=value['account_fingerprint'], account_epoch=value['account_epoch'],
        boot_id_sha256=value['boot_id_sha256'])


def owner_binding(inspection):
    native = inspection['native']
    account = account_scope(host('account_status', {}))
    require(account['account_id'][4:] == inspection['account_fingerprint']
        and account['epoch'] == inspection['account_epoch'], 'ACCOUNT_CHANGED')
    # Pause is explicitly mutating diagnostic work. This existing snapshot may
    # reconcile authority; strict read-only inspect never invokes it.
    state = host('playback', dict(operation='snapshot', request_id=native['request_id'], account_scope=account))
    desired, observed = state.get('desired') or {}, state.get('observed') or {}
    require(desired.get('request_id') == native['request_id'] and desired.get('cancelled') is False
        and desired.get('file_bound') is True and desired.get('start_claimed') is True
        and desired.get('file_evidence') == 'AUTO_VERIFIED_FILE'
        and observed.get('request_id') == native['request_id'] and observed.get('native_instance') == native['native_instance']
        and observed.get('av_started') is True and not observed.get('error')
        and desired.get('file_identity') == observed.get('file_identity')
        and digest(desired['file_identity']) == native['file_identity_sha256']
        and type(state.get('epoch')) is int and RID.fullmatch(str(state.get('boot_id'))), 'NATIVE_CHANGED')
    return dict(boot_id=state['boot_id'], epoch=state['epoch'], request_id=native['request_id'],
                selection_sha256=digest(desired['selection_identity']))


def guard(expected, owner=None):
    require(capabilities()['pidfd_supported'], 'PIDFD_UNAVAILABLE')
    native = expected['native']
    fresh = current_inspection(native['request_id'], native['native_instance'])
    require(fresh.get('can_inject') is True, 'PLAYER_PAUSED')
    require(stable_inspection(fresh) == stable_inspection(expected), 'QUALIFIED_CHANGED')
    current_owner = owner_binding(fresh)
    if owner is not None:
        require(current_owner == owner and stable_inspection(fresh, True) == stable_inspection(expected, True),
                'NATIVE_CHANGED')
    # Another native observation after the slower qualification/process reads.
    require(native_binding(rpc('Player.BobiState'), native['request_id'], native['native_instance']) == fresh['native'],
            'NATIVE_CHANGED')
    return fresh, current_owner


def same_process(expected):
    value, state = process_identity(expected['pid'], hash_exe=False)
    require(all(value.get(key) == expected.get(key) for key in value), 'PROCESS_CHANGED')
    return state


def recovery_process(expected):
    """Identify the held process lifetime without requiring an unchanged pathname.

    Renaming/unlinking a running binary does not replace its process. Admission
    still uses the strict path/name/ELF check. During undo, only a positively
    identified lifetime or executable-inode replacement prevents CONT.
    """
    directory = PROC / str(expected['pid'])
    before = proc_stat(read_text(directory / 'stat', 4096))
    require(before['pid'] == expected['pid'] and before['start_ticks'] == expected['start_ticks'], 'PROCESS_CHANGED')
    try:
        info = (directory / 'exe').stat()
    except OSError:
        info = None  # Unavailable pathname metadata cannot abandon our STOP.
    if info is not None:
        require(info.st_dev == expected['exe_device'] and info.st_ino == expected['exe_inode'], 'PROCESS_CHANGED')
    after = proc_stat(read_text(directory / 'stat', 4096))
    require(after['pid'] == before['pid'] and after['start_ticks'] == before['start_ticks'], 'PROCESS_CHANGED')
    if after['state'] in ('Z', 'X', 'x'):
        raise ProcessLookupError()
    return after['state']


class ScopeObservation:
    """At most one daemon observer; its IO can never block the recovery actor.

    The initial lease is from the immediately preceding full guard. A failed
    observation is latched; an unavailable/slow observer expires within one
    second. No join is performed while the target may be stopped.
    """
    def __init__(self, sample, cancelled, clock=time.monotonic):
        self.sample, self.cancelled, self.clock = sample, cancelled, clock
        self.latest = (True, clock())
        self.closed = False
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self.thread.start()

    def _run(self):
        while not self.closed and not self.cancelled():
            began = self.clock()
            try:
                valid = self.sample() is True
            except BaseException:
                valid = False
            self.latest = (valid, began)
            if not valid:
                return
            time.sleep(.1)

    def current(self):
        valid, began = self.latest
        return not self.closed and not self.cancelled() and valid and self.clock() - began <= OBSERVATION_MAX_AGE

    def close(self):
        self.closed = True


def send_pidfd(descriptor, number):
    # Only a held kernel process handle, never kill(pid), pkill or service stop.
    signal.pidfd_send_signal(descriptor, number, None, 0)


def resume_exact(descriptor, target, send=send_pidfd, check=recovery_process, wait=time.sleep):
    """CONT may be retried under the same handle; STOP is never retried."""
    last = None
    for attempt in range(3):
        try:
            check(target)
        except ProcessLookupError:
            return dict(state='original_process_exited', confirmed=False, cont_attempts=attempt)
        except BaseException as error:
            if isinstance(error, Refused) and str(error) == 'PROCESS_CHANGED':
                return dict(state='identity_changed_no_signal', confirmed=False, **safe_error(error), cont_attempts=attempt)
            # The held pidfd cannot ever address a recycled PID. A transient
            # procfs/read/interruption error must not prevent undoing our STOP.
            last = safe_error(error)
        try:
            send(descriptor, signal.SIGCONT)
        except ProcessLookupError:
            return dict(state='original_process_exited', confirmed=False, cont_attempts=attempt + 1)
        except BaseException as error:
            last = safe_error(error)
        try:
            if check(target) not in ('T','t'):
                return dict(state='resumed', confirmed=True, cont_attempts=attempt + 1,
                            ack_uncertain=last is not None)
        except ProcessLookupError:
            return dict(state='original_process_exited', confirmed=False, cont_attempts=attempt + 1)
        except BaseException as error:
            if isinstance(error, Refused) and str(error) == 'PROCESS_CHANGED':
                return dict(state='identity_changed_no_signal', confirmed=False, **safe_error(error), cont_attempts=attempt + 1)
            last = safe_error(error)
        if attempt < 2:
            try:
                wait(.1)
            except BaseException:
                pass  # An interrupt cannot prevent the remaining exact recovery attempts.
    return dict(state='recovery_failed', confirmed=False, error='RECOVERY_FAILED', cont_attempts=3)


def execute_pause(target, descriptor, seconds, observe, save, send=send_pidfd,
                  check=same_process, clock=time.monotonic, wait=time.sleep,
                  recover_check=recovery_process, cancelled=lambda: False):
    """Always enter recovery after an ambiguous STOP, without another STOP."""
    require(type(seconds) is int and 1 <= seconds <= MAX_SECONDS, 'SCOPE_INVALID')
    require(check(target) not in ('T','t'), 'PROCESS_CHANGED')
    record = dict(state='stop_unconfirmed', stop_attempts=0, cont_attempts=0, retry_allowed=False,
                  requested_max_seconds=seconds, recovery_reserve_seconds=RECOVERY_RESERVE)
    began = clock()
    record.update(stop_attempted_at=began, recovery_deadline=began + seconds,
                  resume_due=began + max(0, seconds - RECOVERY_RESERVE))
    save(record)  # Durable before the only STOP; never a replay invitation.
    attempted = False
    try:
        # Even a scheduling delay before the signal cannot outlive the recovery
        # actor: this same independent actor performs STOP then immediate CONT
        # if its own already-established deadline has elapsed.
        require(clock() < record['resume_due'], 'WATCHDOG_EXPIRED')
        require(check(target) not in ('T','t'), 'PROCESS_CHANGED')
        require(not cancelled(), 'WATCHDOG_EXPIRED')
        attempted = True
        record['stop_attempts'] = 1
        send(descriptor, signal.SIGSTOP)
        record['state'] = 'paused'
        # Do not fsync/write receipts while stopped: filesystem IO is not an
        # absolute-time-bounded operation. Durable stop_unconfirmed already
        # exists; the next write happens only after recovery.
        next_observation = clock()
        while clock() < record['resume_due']:
            if cancelled():
                record['resume_reason'] = 'watchdog_interrupted'
                break
            recover_check(target)
            if clock() >= next_observation:
                if not observe():
                    record['resume_reason'] = 'playback_changed_or_unavailable'
                    break
                next_observation = clock() + .5
            wait(min(.1, max(0, record['resume_due'] - clock())))
        record.setdefault('resume_reason', 'bounded_deadline')
    except BaseException as error:
        record.update(state='unconfirmed', **safe_error(error))
        record['resume_reason'] = 'control_or_observation_unconfirmed'
    finally:
        if attempted:
            result = resume_exact(descriptor, target, send, recover_check, wait)
            record['recovery'] = result
            record['cont_attempts'] = result['cont_attempts']
            record['state'] = 'restored' if result['confirmed'] else 'recovery_failed'
        else:
            record['state'] = 'not_paused'
        record['finished_at'] = clock()
        record['deadline_met'] = record['finished_at'] <= record['recovery_deadline']
        try:
            save(record)
        except Exception:
            record['receipt_write_failed'] = True  # Recovery already ran; never relabel as not paused.
    return record


def worker(directory):
    directory = private_directory(directory)
    parameters = read_json(directory / 'intent.json', 65536)
    require(directory == directory_for(parameters['run_id']), 'SCOPE_INVALID')
    expected, owner = parameters['inspection'], parameters['owner']
    require(type(parameters['seconds']) is int and 1 <= parameters['seconds'] <= MAX_SECONDS, 'SCOPE_INVALID')
    require(capabilities()['pidfd_supported'], 'PIDFD_UNAVAILABLE')
    descriptor = os.pidfd_open(expected['process']['pid'], 0)
    record = dict(run_id=parameters['run_id'], state='preflight', retry_allowed=False,
                  request_id=expected['native']['request_id'], native_instance=expected['native']['native_instance'])
    def save(value):
        record.update(value)
        write_json(directory / 'result.json', record)
    interrupted_requested = [False]
    def interrupted(signum, frame):
        # Cooperative only: never throw while finally is undoing our STOP.
        interrupted_requested[0] = True
    # Detached from SSH, with output redirected. Normal TERM/INT still unwind
    # through recovery; HUP from a disconnected controlling session is ignored.
    # SIGKILL/OOM of this actor cannot run finally; this remains an attended test,
    # not a promise of recovery after the recovery actor itself is destroyed.
    signal.signal(signal.SIGHUP, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    try:
        same_process(expected['process'])
        send_pidfd(descriptor, 0)  # Permission/kernel check only, before READY.
        own = proc_stat(read_text(PROC / str(os.getpid()) / 'stat', 4096))
        ready = dict(run_id=parameters['run_id'], target_sha256=parameters['target_sha256'],
            watchdog_pid=os.getpid(), watchdog_start_ticks=own['start_ticks'], arm_deadline=time.monotonic() + ARM_SECONDS)
        write_json(directory / 'ready.json', ready, exclusive=True)
        save(dict(state='ready', watchdog_pid=os.getpid(), arm_deadline=ready['arm_deadline']))
        arm = directory / 'arm.json'
        while not arm.is_file() and not interrupted_requested[0] and time.monotonic() < ready['arm_deadline']:
            time.sleep(.05)
        require(arm.is_file() and time.monotonic() < ready['arm_deadline'], 'WATCHDOG_EXPIRED')
        require(not interrupted_requested[0], 'WATCHDOG_EXPIRED')
        armed = read_json(arm, 4096)
        require(armed == dict(run_id=parameters['run_id'], target_sha256=parameters['target_sha256']), 'ARM_INVALID')
        write_json(directory / 'consumed.json', {'run_id': parameters['run_id']}, exclusive=True)
        fresh, actual_owner = guard(expected, owner)
        require(digest(encode(dict(inspection=stable_inspection(fresh, True), owner=actual_owner))) == parameters['target_sha256'],
                'NATIVE_CHANGED')
        same_process(expected['process'])
        require(time.monotonic() < ready['arm_deadline'], 'WATCHDOG_EXPIRED')
        def observe():
            try:
                # This existing owner snapshot can reconcile authority (as in
                # guard); it is isolated here because HTTP inactivity timeouts
                # are not absolute deadlines. Never rescan processes/qualified
                # files while paused. No STOP/CONT is sent from this thread.
                if owner_binding(expected) != owner:
                    return False
                native = rpc('Player.BobiState')
                return (native_binding(native, expected['native']['request_id'],
                        expected['native']['native_instance']) == expected['native']
                        and native['playback']['paused'] is False)
            except Exception:
                return False
        observation = ScopeObservation(observe, lambda: interrupted_requested[0])
        observation.start()
        try:
            execute_pause(expected['process'], descriptor, parameters['seconds'], observation.current, save,
                          cancelled=lambda: interrupted_requested[0])
        finally:
            observation.close()
    except BaseException as error:
        save(dict(state='not_paused', **safe_error(error)))
    finally:
        os.close(descriptor)


def actor_exited(ready):
    """No signals to the actor. A live/unreadable actor forbids fallback CONT."""
    require(type(ready.get('watchdog_pid')) is int and ready['watchdog_pid'] > 1
            and type(ready.get('watchdog_start_ticks')) is int, 'RECEIPT_INVALID')
    try:
        current = proc_stat(read_text(PROC / str(ready['watchdog_pid']) / 'stat', 4096))
    except FileNotFoundError:
        # Distinguish an absent actor from a missing/unmounted procfs view.
        own = proc_stat(read_text(PROC / str(os.getpid()) / 'stat', 4096))
        require(own['pid'] == os.getpid(), 'PROCESS_INVALID')
        return True
    require(current['pid'] == ready['watchdog_pid'], 'PROCESS_INVALID')
    return current['start_ticks'] != ready['watchdog_start_ticks'] or current['state'] in ('Z','X','x')


def fallback_target(expected):
    # A fresh pidfd has not yet proved that it was the originally held handle:
    # fallback admission therefore requires readable inode evidence as well.
    info = (PROC / str(expected['pid']) / 'exe').stat()
    require(info.st_dev == expected['exe_device'] and info.st_ino == expected['exe_inode'], 'PROCESS_CHANGED')
    return recovery_process(expected)


def resume_after_exit(run_id, request_id, native_instance):
    """Attended CONT-only fallback after confirmed death of this run's actor."""
    directory = private_directory(directory_for(run_id))
    parameters = read_json(directory / 'intent.json', 65536)
    require(parameters.get('run_id') == run_id, 'RECEIPT_INVALID')
    expected, owner = parameters['inspection'], parameters['owner']
    target_hash = digest(encode(dict(inspection=stable_inspection(expected, True), owner=owner)))
    require(target_hash == parameters['target_sha256']
        and expected['native']['request_id'] == request_id and expected['native']['native_instance'] == native_instance,
        'RECEIPT_INVALID')
    previous_path = directory / 'resume-result.json'
    if previous_path.is_file():
        previous = read_json(previous_path, 65536)
        require(previous.get('schema') == 1 and previous.get('operation') == 'resume'
            and previous.get('run_id') == run_id and previous.get('request_id') == request_id
            and previous.get('native_instance') == native_instance, 'RECEIPT_INVALID')
        recovered = previous.get('recovery') or {}
        if (previous.get('state') == 'restored' and previous.get('actor_confirmed_exited') is True
                and recovered.get('state') == 'resumed' and recovered.get('confirmed') is True
                and type(previous.get('cont_attempts')) is int and 1 <= previous['cont_attempts'] <= 3):
            # A later external STOP is not ours to undo. Successful restoration
            # is terminal for this run, even if that same process is stopped now.
            return dict(schema=1, operation='resume', run_id=run_id, request_id=request_id,
                native_instance=native_instance, state='already_restored', signal_sent=False,
                prior_recovery_confirmed=True, current_process_state_verified=False, retry_allowed=False)
    require(digest(read_text(PROC / 'sys/kernel/random/boot_id', 128).strip()) == expected['boot_id_sha256'], 'PROCESS_CHANGED')
    ready = read_json(directory / 'ready.json', 4096)
    require(ready.get('run_id') == run_id and ready.get('target_sha256') == target_hash
        and ready.get('watchdog_pid') != expected['process']['pid'], 'RECEIPT_INVALID')
    require(read_json(directory / 'arm.json', 4096) == dict(run_id=run_id, target_sha256=target_hash)
        and read_json(directory / 'consumed.json', 4096) == {'run_id': run_id}, 'RECEIPT_INVALID')
    result = read_json(directory / 'result.json', 65536)
    require(result.get('run_id') == run_id and result.get('request_id') == request_id
        and result.get('native_instance') == native_instance
        and result.get('state') in ('stop_unconfirmed','paused','unconfirmed','recovery_failed')
        and type(result.get('recovery_deadline')) in (int, float)
        and type(result.get('stop_attempted_at')) in (int, float), 'RECEIPT_INVALID')
    require(actor_exited(ready), 'WATCHDOG_STILL_RUNNING')
    target = expected['process']
    require(fallback_target(target) in ('T','t'), 'PROCESS_NOT_STOPPED')
    descriptor = os.pidfd_open(target['pid'], 0)
    try:
        # Recheck after opening: a PID reused between reads can never cause a
        # signal to the replacement. No pathname/ELF-name check blocks undo of
        # the verified original inode after its binary was renamed/deleted.
        require(fallback_target(target) in ('T','t') and actor_exited(ready), 'PROCESS_CHANGED')
        pending = dict(schema=1, operation='resume', run_id=run_id, request_id=request_id,
            native_instance=native_instance, state='resume_unconfirmed', retry_allowed=False,
            actor_confirmed_exited=True, cont_attempts=0)
        recovery = resume_exact(descriptor, target)
        pending.update(state='restored' if recovery['confirmed'] else 'recovery_failed',
                       recovery=recovery, cont_attempts=recovery['cont_attempts'])
        try:
            write_json(directory / 'resume-result.json', pending)
        except Exception:
            pending['receipt_write_failed'] = True  # Never block CONT on receipt IO.
        return pending
    finally:
        os.close(descriptor)


def launch(parameters, sources):
    require(set(parameters) == {'run_id','inspection','seconds'}, 'SCOPE_INVALID')
    require(type(parameters['seconds']) is int and 1 <= parameters['seconds'] <= MAX_SECONDS, 'SCOPE_INVALID')
    require(0 <= time.time() - parameters['inspection'].get('observation', 0) <= 180, 'RECEIPT_INVALID')
    inspection, owner = guard(parameters['inspection'])
    directory = directory_for(parameters['run_id'])
    directory.mkdir(mode=0o700, exist_ok=False)
    private_directory(directory)
    require(set(sources) == {'ce_torr_fault_remote.py','ce_torr_fault_watchdog.py'}, 'SCOPE_INVALID')
    for name, code in sources.items():
        with (directory / name).open('x', encoding='utf-8') as stream:
            stream.write(code)
    target_hash = digest(encode(dict(inspection=stable_inspection(inspection, True), owner=owner)))
    intent = dict(parameters, inspection=inspection, owner=owner, target_sha256=target_hash)
    write_json(directory / 'intent.json', intent, exclusive=True)
    script = directory / 'run.py'
    with script.open('x', encoding='utf-8') as stream:
        stream.write('import sys\nfrom pathlib import Path\nsys.path.insert(0,str(Path(__file__).parent))\n'
            'from ce_torr_fault_watchdog import worker\nworker(Path(__file__).parent)\n')
    child = subprocess.Popen([sys.executable,'-I','-B',str(script)], stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True, start_new_session=True)
    until = time.monotonic() + 3
    while not (directory / 'ready.json').is_file() and child.poll() is None and time.monotonic() < until:
        time.sleep(.05)
    require((directory / 'ready.json').is_file() and child.poll() is None, 'WATCHDOG_NOT_READY')
    ready = read_json(directory / 'ready.json', 4096)
    own = proc_stat(read_text(PROC / str(child.pid) / 'stat', 4096))
    require(ready.get('watchdog_pid') == child.pid and ready.get('watchdog_start_ticks') == own['start_ticks']
        and ready.get('run_id') == parameters['run_id'] and ready.get('target_sha256') == target_hash,
        'WATCHDOG_NOT_READY')
    fresh, actual_owner = guard(inspection, owner)
    require(digest(encode(dict(inspection=stable_inspection(fresh, True), owner=actual_owner))) == target_hash
        and child.poll() is None and time.monotonic() < ready['arm_deadline'], 'WATCHDOG_EXPIRED')
    write_json(directory / 'arm.json', dict(run_id=parameters['run_id'], target_sha256=target_hash), exclusive=True)
    return dict(state='armed_unconfirmed', run_id=parameters['run_id'], watchdog_ready=True,
                retry_allowed=False, requested_max_seconds=parameters['seconds'])
