"""A source rebuild baseline is not the currently installed overlay."""
import json

import pytest

from test_ce_native_handoff_profile import artifacts, digest
from test_ce_native_reapply import harness, tool


def successor(a):
    old = b'installed handoff predecessor'
    launch = ('FIX=' + digest(old) + '\nunchanged launcher behavior\n').encode()
    previous = dict(binary=digest(old), conf=digest(b'handoff conf'), launch=digest(launch),
                    binary_path='/storage/.local/share/bobbi-native/2026102035/kodi.bin',
                    launch_path='/storage/.local/share/bobbi-native/2026102035/launch.py')
    profile = dict(a.profile, tag='2038', sequence=2026102038,
                   base='/storage/.local/share/bobbi-native/2026102038', predecessor=previous)
    layout = dict(files={previous['binary_path']: dict(sha256=previous['binary']),
                        previous['launch_path']: dict(source=launch.decode(), sha256=previous['launch'])},
                  dropins={'/storage/.config/system.d/kodi.service.d/60-am6b-subtitle284.conf':
                           dict(sha256=previous['conf'])}, running=[dict(sha256=previous['binary'])])
    a.layout_path.write_text(json.dumps(layout))
    return profile, layout, launch


def test_successor_uses_installed_launcher_not_original_relink_baseline(artifacts):
    a = artifacts
    profile, _, launch = successor(a)
    files = tool.staged_files(a.result_path, profile, a.layout_path)
    assert files['launch.py'] == launch.replace(profile['predecessor']['binary'].encode(),
                                               profile['candidate'].encode())
    assert b'/2026102038/launch.py ' in files['next.conf']
    assert tool.OLD.encode() not in files['launch.py']
    # The original baseline proof still pins the retained historical objects.
    assert a.result['baseline_sha256'] == tool.OLD


@pytest.mark.parametrize('damage', ['running', 'binary', 'launcher', 'conf'])
def test_successor_rejects_wrong_installed_layout(artifacts, damage):
    a = artifacts
    profile, layout, _ = successor(a)
    if damage == 'running':
        layout['running'] = [dict(sha256=tool.OLD)]
    elif damage == 'conf':
        next(iter(layout['dropins'].values()))['sha256'] = tool.OLD_CONF
    else:
        path = profile['predecessor']['binary_path' if damage == 'binary' else 'launch_path']
        layout['files'][path]['sha256'] = 'changed'
    a.layout_path.write_text(json.dumps(layout))
    with pytest.raises(AssertionError):
        tool.staged_files(a.result_path, profile, a.layout_path)


def abi_report(a):
    a.result['baseline_inputs'] = dict(a.proof['inputs'])
    a.result['additional_inputs'] = {'original-header-consumer-object': 'additional-digest'}
    a.result['inputs'] = dict(a.result['baseline_inputs'], **a.result['additional_inputs'])
    a.result_path.write_text(json.dumps(a.result))
    return dict(a.profile, build_proof_sha256=tool.sha_file(a.result_path))


def test_additional_abi_inputs_require_complete_pinned_build_report(artifacts):
    a = artifacts
    profile = abi_report(a)
    assert tool.checked_build(a.result_path, profile)[1].read_bytes() == a.candidate
    with pytest.raises(AssertionError, match='BASELINE_INPUTS_CHANGED'):
        tool.checked_build(a.result_path, a.profile)
    a.result_path.write_text(a.result_path.read_text() + '\n')
    with pytest.raises(AssertionError, match='BUILD_PROOF_CHANGED'):
        tool.checked_build(a.result_path, profile)


@pytest.mark.parametrize('damage', ['baseline', 'overlap', 'unlisted', 'empty'])
def test_pinned_report_must_express_exact_baseline_plus_abi_inputs(artifacts, damage):
    a = artifacts
    profile = abi_report(a)
    if damage == 'baseline':
        a.result['baseline_inputs'] = {'changed': 'digest'}
    elif damage == 'overlap':
        a.result['additional_inputs'].update(a.result['baseline_inputs'])
    elif damage == 'unlisted':
        a.result['inputs']['unlisted'] = 'digest'
    else:
        a.result['additional_inputs'] = {}
    a.result_path.write_text(json.dumps(a.result))
    profile['build_proof_sha256'] = tool.sha_file(a.result_path)
    with pytest.raises(AssertionError):
        tool.checked_build(a.result_path, profile)


def test_remote_successor_rollback_uses_predecessor_paths_and_preserves_history(tmp_path, monkeypatch):
    h = harness(tmp_path, monkeypatch)
    predecessor = tmp_path/'previous-overlay'
    predecessor.mkdir()
    binary, launch = predecessor/'kodi.bin', predecessor/'launch.py'
    binary.write_bytes(h.oldbin.read_bytes())
    launch.write_bytes(b'old launcher')
    h.ns.update(OLD_BINARY_PATH=str(binary), OLD_LAUNCH_PATH=str(launch))
    h.oldbin.write_bytes(b'legacy overlay not this predecessor')
    h.run()
    assert json.loads(h.receipt.read_text())['state'] == 'applied'
    h.ns['MODE'] = 'rollback'
    h.run()
    record = json.loads(h.receipt.read_text())
    assert record['state'] == 'rolled_back' and record['recovered'] is True
    assert h.conf.read_bytes() == h.old_conf
    assert any(row['state'] == 'applied' for row in record['history'])
    assert h.oldbin.read_bytes() == b'legacy overlay not this predecessor'


@pytest.mark.parametrize('damage', ['binary', 'launch'])
def test_remote_successor_checks_pinned_predecessor_before_stop(tmp_path, monkeypatch, damage):
    h = harness(tmp_path, monkeypatch)
    binary, launch = tmp_path/'previous.bin', tmp_path/'previous.py'
    binary.write_bytes(h.oldbin.read_bytes())
    launch.write_bytes(b'old launcher')
    h.ns.update(OLD_BINARY_PATH=str(binary), OLD_LAUNCH_PATH=str(launch))
    (binary if damage == 'binary' else launch).write_bytes(b'changed')
    with pytest.raises(AssertionError, match='OLD_BINARY_CHANGED|OLD_LAUNCH_CHANGED'):
        h.run()
    assert not h.calls
