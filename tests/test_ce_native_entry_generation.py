"""Native maintenance must use the actual completed entry journal for CE2035."""
import json
from types import SimpleNamespace

import pytest

from test_ce_native_reapply import harness, tool


def entry_fixture(tmp_path, monkeypatch, mode='apply', sequence=2026102035):
    h = harness(tmp_path, monkeypatch)
    entry = tmp_path/'installation.json'
    state = dict(schema=1, sequence=sequence, high_watermark=sequence,
                 phase='complete', tx='a'*32)
    entry.write_text(json.dumps(state))
    h.generation.write_text(json.dumps(dict(sequence=2026102021)))
    original_path = h.ns['pathlib'].Path
    h.ns['pathlib'] = SimpleNamespace(Path=lambda value:
        entry if str(value) == tool.ENTRY_GENERATION_PATH else original_path(value))
    h.ns.update(MODE=mode, REQUIRED_SEQUENCE=2026102035, PROFILE_TAG='2035',
                GENERATION_KIND='entry_complete', GENERATION_PATH=tool.ENTRY_GENERATION_PATH)
    if mode == 'apply':
        h.receipt.unlink()
        (h.base/'previous.conf').unlink()
    return h, entry, state


def test_complete_entry_is_authoritative_even_when_legacy_updater_is_old(tmp_path, monkeypatch):
    h, entry, _ = entry_fixture(tmp_path, monkeypatch)
    before_entry, before_legacy = entry.read_bytes(), h.generation.read_bytes()
    h.run()
    assert json.loads(h.receipt.read_text())['state'] == 'applied'
    assert h.ns['out']['generation']['source'] == 'entry_complete'
    assert entry.read_bytes() == before_entry and h.generation.read_bytes() == before_legacy


@pytest.mark.parametrize('phase', ['staged', 'switching', 'restoring', 'activation_pending',
                                   'restore_pending', 'restored'])
def test_legacy_generation_never_bypasses_incomplete_entry(tmp_path, monkeypatch, phase):
    h, entry, state = entry_fixture(tmp_path, monkeypatch)
    h.generation.write_text(json.dumps(dict(sequence=2026102035)))
    state['phase'] = phase
    entry.write_text(json.dumps(state))
    with pytest.raises(AssertionError, match='ENTRY_INSTALLATION_INCOMPLETE'):
        h.run()
    assert not h.calls and not h.receipt.exists() and not (h.base/'previous.conf').exists()
    assert h.conf.read_bytes() == h.old_conf


@pytest.mark.parametrize('field,value', [('schema', True), ('schema', 2), ('sequence', True),
    ('sequence', '2026102035'), ('high_watermark', True), ('high_watermark', 2026102036),
    ('high_watermark', 2026102034), ('tx', ''), ('tx', 'A'*32), ('tx', '../untrusted'),
    ('host_pending', 'restore'), ('host_pending', False)])
def test_malformed_or_unsafe_entry_fails_before_backup_receipt_and_service(tmp_path, monkeypatch,
                                                                         field, value):
    h, entry, state = entry_fixture(tmp_path, monkeypatch)
    state[field] = value
    entry.write_text(json.dumps(state))
    before = entry.read_bytes()
    with pytest.raises(AssertionError): h.run()
    assert not h.calls and not h.receipt.exists() and not (h.base/'previous.conf').exists()
    assert entry.read_bytes() == before


@pytest.mark.parametrize('value', [None, [], {'schema': 1}, 'not-a-journal'])
def test_wrong_journal_shape_is_not_a_generation_proof(tmp_path, monkeypatch, value):
    h, entry, _ = entry_fixture(tmp_path, monkeypatch)
    entry.write_text(json.dumps(value))
    with pytest.raises(AssertionError): h.run()
    assert not h.calls and not h.receipt.exists()


@pytest.mark.parametrize('sequence', [2026102034, 2026102036])
def test_initial_apply_requires_exact_completed_sequence(tmp_path, monkeypatch, sequence):
    h, _, _ = entry_fixture(tmp_path, monkeypatch, sequence=sequence)
    with pytest.raises(AssertionError): h.run()
    assert not h.calls and not h.receipt.exists()


def test_reapply_may_use_later_completed_entry_without_changing_any_journal(tmp_path, monkeypatch):
    h, entry, _ = entry_fixture(tmp_path, monkeypatch, mode='reapply', sequence=2026102036)
    before = entry.read_bytes()
    h.run()
    assert json.loads(h.receipt.read_text())['state'] == 'applied'
    assert entry.read_bytes() == before


def test_entry_change_during_service_stop_recovers_old_native_without_changing_journal(tmp_path, monkeypatch):
    h, entry, state = entry_fixture(tmp_path, monkeypatch)
    original = h.ns['command']
    def command(*args):
        if args[:2] == ('systemctl', 'stop'):
            state['phase'] = 'switching'
            entry.write_text(json.dumps(state))
        return original(*args)
    h.ns['command'] = command
    with pytest.raises(AssertionError, match='PROGRAM_GENERATION_CHANGED'): h.run()
    assert h.conf.read_bytes() == h.old_conf
    assert json.loads(entry.read_text())['phase'] == 'switching'
    assert json.loads(h.receipt.read_text())['state'] == 'recovered_after_failure'


@pytest.mark.parametrize('message,expected', [
    ('INSTALL_COMPATIBLE_ADDONS_FIRST', 'INSTALL_COMPATIBLE_ADDONS_FIRST'),
    ('ENTRY_INSTALLATION_INCOMPLETE', 'ENTRY_INSTALLATION_INCOMPLETE'),
    ('arbitrary_private_diagnostic', 'UNEXPECTED_REMOTE_FAILURE')])
def test_remote_wrapper_preserves_only_fixed_codes_as_json(monkeypatch, capsys, message, expected):
    monkeypatch.setattr(tool, 'REMOTE', "REMOTE_STAGE='generation'\nraise AssertionError("+repr(message)+")\n")
    with pytest.raises(SystemExit) as stopped:
        exec(tool.remote_script({'MODE': 'apply'}), {})
    assert stopped.value.code == 1
    captured = capsys.readouterr()
    value = json.loads(captured.out)
    assert value == dict(action='apply', outcome='unconfirmed', next_action='status',
                         stage='generation', code=expected, error_type='AssertionError')
    assert not captured.err
    if expected == 'UNEXPECTED_REMOTE_FAILURE': assert message not in captured.out
