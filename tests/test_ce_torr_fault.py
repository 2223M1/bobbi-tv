"""Local-only fixtures: no real device, process signal, mount or backend IO."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.core/lib'))
import ce_torr_fault_remote as remote
import ce_torr_fault as driver
from bobbi_core.video_context import video_identity
from bobbi_core.playback_request import torrent_file_identity

REQUEST = 'a' * 32
INSTANCE = '11111111-2222-3333-4444-555555555555'


def qualified():
    selected = dict(source_info_hash='b' * 40, torrent_file_id=7, torrent_path='Series/episode01.mkv',
                    torrent_file_bytes=123456789)
    video = video_identity('tmdb:tv:123:s1:e1', 'c' * 64, selected)
    row = dict(key='d' * 64, state='qualified', bytes=selected['torrent_file_bytes'], path='private-cloud-path',
        prepared_account='account-scope', prepared_file_id='private-id', prepared_qualification='e' * 64,
        prepared_source_info_hash=selected['source_info_hash'], prepared_version_key=video['release_key'], video_context=video)
    account = dict(account_id='115:' + 'f' * 64, epoch=3, authenticated=True)
    index = dict(schema_version=1, prepared_schema=2, account='account-scope', account_scope=account,
                 titles=[dict(kind='tv', sources=[row])])
    status = dict(request_id=REQUEST, state='accepted', result=dict(tasks=[dict(media_id=video['media_id'],
        version_key=video['release_key'])], source_proof=dict(request_id=REQUEST, account='account-scope', anchor=video)))
    backend = dict(endpoint='http://127.0.0.1:8090', host='127.0.0.1', port=8090, fingerprint='1' * 64)
    address = backend['endpoint'] + '/stream/Series/episode01.mkv?link=' + 'b' * 40 + '&index=7&play'
    native = dict(request_id=REQUEST, native_instance=INSTANCE, phase='AV_STARTED', open_epoch=5,
        user_intent=0, paused=False, url_sha256=remote.digest(address),
        file_identity=torrent_file_identity(selected['source_info_hash'],7,selected['torrent_path'],selected['torrent_file_bytes']))
    return index, status, account, native, address, backend


def test_qualified_proof_matches_exact_media_file_and_account_without_url_output():
    args = qualified()
    result = remote.qualified_candidate(*args)
    assert result['media_id'] == 'tmdb:tv:123:s1:e1'
    assert 'http' not in json.dumps(result) and 'private' not in json.dumps(result)


@pytest.mark.parametrize('change', ['file','account','request','version','qualification','url','duplicate'])
def test_same_title_or_cached_receipt_cannot_rescue_mismatch(change):
    index, status, account, native, address, backend = qualified()
    if change == 'file': native['file_identity'] += 'changed'
    if change == 'account': account = dict(account, epoch=4)
    if change == 'request': status['result']['source_proof']['request_id'] = '0' * 32
    if change == 'version': status['result']['tasks'][0]['version_key'] = '0' * 64
    if change == 'qualification': index['titles'][0]['sources'][0]['prepared_qualification'] = ''
    if change == 'url': address = address.replace(':8090', ':19798')
    if change == 'duplicate': index['titles'][0]['sources'].append(deepcopy(index['titles'][0]['sources'][0]))
    with pytest.raises(remote.Refused):
        remote.qualified_candidate(index,status,account,native,address,backend)


def stat_line(pid=54321, state='S', start=1234):
    return '%d (TorrServer worker) %s ' % (pid,state) + ' '.join(['0'] * 18 + [str(start)] + ['0'] * 10)


def test_proc_stat_does_not_split_names_with_spaces_or_parentheses():
    value = remote.proc_stat(stat_line().replace('TorrServer worker', 'TorrServer (worker)'))
    assert value['start_ticks'] == 1234 and value['state'] == 'S' and value['pid'] == 54321


def tcp_line(inode='98765', address='0100007F', port=8090):
    return 'header\n 0: %s:%04X 00000000:0000 0A 0:0 00:0 0 0 0 %s 0\n' % (address,port,inode)


def test_listen_inode_requires_exact_port_and_loopback_route():
    assert remote.tcp_listeners(tcp_line(),4,8090,'127.0.0.1') == {'98765'}
    assert remote.tcp_listeners(tcp_line(),4,8091,'127.0.0.1') == set()
    assert remote.tcp_listeners(tcp_line(address='0101A8C0'),4,8090,'127.0.0.1') == set()
    assert remote.tcp_listeners(tcp_line(address='00000000'),4,8090,'127.0.0.1') == {'98765'}


def proc_fixture(tmp_path, monkeypatch):
    proc = tmp_path / 'proc'
    (proc / 'net').mkdir(parents=True)
    (proc / 'net/tcp').write_text(tcp_line())
    target = proc / '54321'
    (target / 'fd').mkdir(parents=True)
    (target / 'stat').write_text(stat_line())
    (target / 'exe').write_bytes(b'\x7fELF' + b'fixture-executable')
    (target / 'fd/6').touch()
    links = {str(target/'exe'):'/storage/engine/TorrServer',str(target/'fd/6'):'socket:[98765]'}
    monkeypatch.setattr(remote.os, 'readlink', lambda path: links[str(path)])
    return proc, target, links


def test_listener_maps_unique_pid_starttime_and_executable(tmp_path, monkeypatch):
    proc,target,links = proc_fixture(tmp_path,monkeypatch)
    value,state = remote.listener_process({'host':'127.0.0.1','port':8090},proc)
    assert value['pid'] == 54321 and value['start_ticks'] == 1234 and state == 'S'
    assert value['listen_inodes'] == ['98765'] and len(value['exe_sha256']) == 64


def test_kodi_or_unknown_executable_is_never_signal_target(tmp_path,monkeypatch):
    proc,target,links = proc_fixture(tmp_path,monkeypatch)
    for path in ('/usr/lib/kodi/kodi.bin','/storage/CloudDrive','/storage/engine/TorrServer (deleted)'):
        links[str(target/'exe')] = path
        with pytest.raises(remote.Refused,match='PROCESS_INVALID'):
            remote.listener_process({'host':'127.0.0.1','port':8090},proc)


def test_multiple_listener_owners_refused(tmp_path,monkeypatch):
    proc,target,links = proc_fixture(tmp_path,monkeypatch)
    other=proc/'54322'
    (other/'fd').mkdir(parents=True)
    (other/'fd/1').touch()
    links[str(other/'fd/1')]='socket:[98765]'
    with pytest.raises(remote.Refused,match='LISTENER_AMBIGUOUS'):
        remote.listener_process({'host':'127.0.0.1','port':8090},proc)


def test_inspect_never_dispatches_twice_after_lost_ack(tmp_path):
    output,calls=tmp_path/'receipt.json',[]
    def sender(source,code):
        calls.append(code)
        assert json.loads(output.read_text())['state']=='unconfirmed'
        raise TimeoutError('Cookie=private URL=http://secret')
    result=driver.inspect_once(tmp_path,output,REQUEST,INSTANCE,sender)
    assert len(calls)==1 and result['state']=='unconfirmed' and 'private' not in output.read_text()
    with pytest.raises(FileExistsError):
        driver.inspect_once(tmp_path,output,REQUEST,INSTANCE,sender)
    assert len(calls)==1


def test_inspect_entry_rejects_mutating_operation_without_io(monkeypatch):
    monkeypatch.setattr(remote,'current_inspection',lambda *args: pytest.fail('unexpected IO'))
    assert remote.inspect_entry({'operation':'pause'})['error']=='SCOPE_INVALID'


def test_old_kernel_pidfd_is_reported_unsupported_not_assumed_from_python_api(monkeypatch):
    import errno
    def unavailable(pid,flags):
        raise OSError(errno.ENOSYS,'unpublished kernel message')
    monkeypatch.setattr(remote.os,'pidfd_open',unavailable,raising=False)
    monkeypatch.setattr(remote.signal,'pidfd_send_signal',lambda *args: pytest.fail('no signal allowed'),raising=False)
    result=remote.capabilities()
    assert result['pidfd_api_present'] and not result['pidfd_supported']
    assert result['pidfd_errno']==errno.ENOSYS and not result['signal_sent']


def test_capability_probe_opens_only_its_own_pid_and_never_sends_signal(monkeypatch):
    calls=[]
    monkeypatch.setattr(remote.os,'pidfd_open',lambda pid,flags: calls.append(('open',pid,flags)) or 81,raising=False)
    monkeypatch.setattr(remote.os,'close',lambda descriptor:calls.append(('close',descriptor)))
    monkeypatch.setattr(remote.signal,'pidfd_send_signal',lambda *args:pytest.fail('no signal allowed'),raising=False)
    result=remote.inspect_entry({'operation':'capabilities'})
    assert result['pidfd_supported'] and calls==[('open',os.getpid(),0),('close',81)]


def test_failed_inspect_does_not_misreport_api_presence_as_kernel_support(monkeypatch):
    def fail(*args):
        raise remote.Refused('QUALIFIED_MISSING')
    monkeypatch.setattr(remote,'current_inspection',fail)
    monkeypatch.setattr(remote.os,'pidfd_open',lambda *args:pytest.fail('not checked'),raising=False)
    monkeypatch.setattr(remote.signal,'pidfd_send_signal',lambda *args:pytest.fail('no signal'),raising=False)
    result=remote.inspect_entry(dict(operation='inspect',request_id=REQUEST,native_instance=INSTANCE))
    assert result['pidfd_api_present'] and result['pidfd_supported'] is None and not result['pidfd_kernel_checked']
