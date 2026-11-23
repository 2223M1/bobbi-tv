"""Offline five-cold/five-warm ledger retains every failure and evidence gap."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('trial_campaign', ROOT / 'tools/ce_trial_campaign.py')
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    original = campaign._module
    monkeypatch.setattr(campaign, '_module', lambda name: SimpleNamespace(
        source_binding=lambda result, repo: dict(matched=result.get('source_bound', True)))
        if name == 'ce_trial_metrics' else original(name))
    manifest = campaign.template()
    manifest['run_id'] = 'fixed-115'
    manifest['expected'].update(work='movie', source_key_sha256='a' * 64,
        file_identity_sha256='b' * 64, source_tree='c' * 40, native_sha256='d' * 64,
        installed_sequence=4, audio=dict(index=1, language='zho'),
        subtitle=dict(enabled=True, stream=dict(index=2, language='eng'), external_sha256='e' * 64))
    def save(name, value):
        path = tmp_path / name
        raw = json.dumps(value).encode()
        path.write_bytes(raw)
        return dict(path=name, sha256=hashlib.sha256(raw).hexdigest())
    def envelope(result, attempt):
        return dict(result=result, exit_code=0, trial_exit_code=0, transport_exit_code=0,
            diagnostic_present=False, attempt=attempt, run_id='fixed-115', work='movie')
    def process(index):
        return dict(boot_sha256='f' * 64, pid=1000 + index, start_ticks=100 * index + 1)
    for slot in manifest['attempts']:
        i = slot['attempt']
        selected = i * 100
        current = process(min(i, 5))
        owner = dict(request_id=str(i).zfill(32), native_instance='11111111-1111-1111-1111-%012d' % i)
        sample = dict(phase='AV_STARTED', currentaudiostream=dict(index=1, language='zho'),
            currentsubtitle=dict(index=2, language='eng'), subtitleenabled=True,
            native=dict(owner, subtitle_file_sha256='e' * 64))
        record = dict(owner, launch_mode='ordinary_ui', explicit_start_over=True,
            exact_source_key_requested=True, selected_source_key_sha256='a' * 64,
            file_identity_sha256='b' * 64, selection_process=current, selected_at=selected,
            select_to_av_observed_seconds=i / 10)
        startup = envelope(dict(name='movie', operation='select', selected=True, trace_passed=True,
            trace_coverage={'passed': True}, record=record, samples=[sample, deepcopy(sample)]), i)
        metric = envelope(dict(sample_name='movie', repeat=i, cache_state=slot['cache_state'],
            condition='playback', source_tree='c' * 40, errors=[],
            installed=dict(native_sha256='d' * 64, installed_sequence=4,
                pid=current['pid'], boot_sha256=current['boot_sha256']),
            monotonic_started=selected + 40, monotonic_ended=selected + 41,
            samples=[dict(start_ticks=current['start_ticks'], player=owner) for _ in range(2)]), i)
        slot['startup'] = save('startup-%d.json' % i, startup)
        slot['metrics'] = save('metric-%d.json' % i, metric)
        if i <= 5:
            baseline = deepcopy(metric)
            baseline['result'].update(condition='idle', monotonic_started=selected - 10, monotonic_ended=selected - 9)
            baseline['result']['installed'].update(pid=process(i - 1)['pid'])
            for row in baseline['result']['samples']:
                row['start_ticks'] = process(i - 1)['start_ticks']
                row['player'] = {}
            slot['pre_restart_metrics'] = save('before-%d.json' % i, baseline)
    path = tmp_path / 'manifest.json'
    def run():
        path.write_text(json.dumps(manifest))
        return campaign.summarize(path, ROOT)
    def change(slot, role, mutate):
        descriptor = manifest['attempts'][slot - 1][role]
        value = json.loads((tmp_path / descriptor['path']).read_text())
        mutate(value)
        manifest['attempts'][slot - 1][role] = save(descriptor['path'], value)
    return SimpleNamespace(root=tmp_path, manifest=manifest, run=run, change=change)


def test_complete_ledger_qualifies_only_process_evidence_without_p95(fixture):
    result = fixture.run()
    assert result['accepted'] and not result['device_contacted']
    assert len(result['attempts']) == 10 and result['outcomes'] == {'passed': 10}
    assert [row['cache_evidence'] for row in result['attempts']] == ['process_restart_observed'] * 5 + ['same_process_reuse_observed'] * 5
    assert result['statistics']['process_cold']['qualified_successes'] == 5
    assert result['statistics']['page_warm']['median'] == .8
    assert 'p95' not in json.dumps(result['statistics']).lower()
    assert 'not first rendered frames' in result['qualification']


def test_all_ten_failures_are_retained_and_not_filtered_out(fixture):
    for i in range(1, 11):
        fixture.change(i, 'startup', lambda value: value.update(exit_code=1, trial_exit_code=1))
    result = fixture.run()
    assert not result['accepted'] and result['outcomes'] == {'failed': 10}
    assert len(result['attempts']) == 10
    assert all(row['receipts']['startup']['state'] == 'retained' and row['receipts']['startup']['sha256'] for row in result['attempts'])
    assert all(row['qualified_successes'] == 0 and row['median'] is None for row in result['statistics'].values())


def test_unconfirmed_transport_and_missing_slots_remain_visible(fixture):
    fixture.change(1, 'startup', lambda value: value.update(transport_exit_code=1,
        result=dict(error='OSError', reason='TRIAL_TRANSPORT_OR_TRACE_ERROR')))
    fixture.manifest['attempts'][1]['startup'] = None
    result = fixture.run()
    assert result['attempts'][0]['outcome'] == 'unconfirmed'
    assert result['attempts'][1]['outcome'] == 'missing'
    assert len(result['attempts']) == 10 and not result['accepted']


@pytest.mark.parametrize('role,change,reason', [
    ('startup', lambda v: v['result']['record'].update(exact_source_key_requested=False), 'FIXED_FILE_UNPROVEN'),
    ('startup', lambda v: v['result']['record'].update(file_identity_sha256='0' * 64), 'FIXED_FILE_UNPROVEN'),
    ('startup', lambda v: v['result']['record'].update(explicit_start_over=False), 'FIXED_START_UNPROVEN'),
    ('startup', lambda v: v['result']['samples'][0]['currentaudiostream'].update(index=9), 'FIXED_TRACKS_UNPROVEN'),
    ('startup', lambda v: v['result']['samples'][0].update(subtitleenabled=False), 'FIXED_TRACKS_UNPROVEN'),
    ('metrics', lambda v: v['result'].update(source_bound=False), 'SAMPLED_SOURCE_BINDING_UNPROVEN'),
    ('metrics', lambda v: v['result']['installed'].update(native_sha256='0' * 64), 'BUILD_IDENTITY_MISMATCH'),
    ('metrics', lambda v: v['result']['samples'][0]['player'].update(request_id='other'), 'METRICS_OWNER_UNPROVEN'),
    ('metrics', lambda v: v['result'].update(monotonic_started=0), 'RECEIPT_ORDER_UNPROVEN'),
    ('metrics', lambda v: v['result'].update(monotonic_ended=None), 'RECEIPT_ORDER_UNPROVEN'),
    ('startup', lambda v: v['result']['samples'][0]['native'].update(request_id='other'), 'STARTUP_OWNER_UNPROVEN'),
])
def test_mismatched_identity_or_intent_is_not_comparable(fixture, role, change, reason):
    fixture.change(1, role, change)
    result = fixture.run()
    assert not result['accepted'] and not result['attempts'][0]['comparable']
    assert reason in result['attempts'][0]['reasons']


@pytest.mark.parametrize('damage', ['missing', 'same_process', 'late', 'reused_old_baseline'])
def test_cold_label_requires_actual_distinct_restart_in_order(fixture, damage):
    if damage == 'missing':
        fixture.manifest['attempts'][1]['pre_restart_metrics'] = None
    elif damage == 'same_process':
        def same(value):
            value['result']['installed']['pid'] = 1002
            for row in value['result']['samples']:
                row['start_ticks'] = 201
        fixture.change(2, 'pre_restart_metrics', same)
    elif damage == 'late':
        fixture.change(2, 'pre_restart_metrics', lambda value: value['result'].update(monotonic_ended=9999))
    else:
        fixture.manifest['attempts'][1]['pre_restart_metrics'] = fixture.manifest['attempts'][0]['pre_restart_metrics']
    result = fixture.run()
    assert not result['accepted'] and result['attempts'][1]['cache_evidence'] == 'unverified'


def test_reusing_the_same_cold_process_does_not_count_as_another_restart(fixture):
    fixture.change(2, 'startup', lambda value: value['result']['record']['selection_process'].update(pid=1001, start_ticks=101))
    def same(value):
        value['result']['installed']['pid'] = 1001
        for row in value['result']['samples']:
            row['start_ticks'] = 101
    fixture.change(2, 'metrics', same)
    assert fixture.run()['attempts'][1]['cache_evidence'] == 'unverified'


def test_failed_metrics_keep_startup_outcome_but_cannot_qualify_the_attempt(fixture):
    fixture.change(1, 'metrics', lambda value: value.update(exit_code=1))
    result = fixture.run()
    assert result['attempts'][0]['outcome'] == 'passed'
    assert not result['attempts'][0]['comparable'] and result['qualified_attempts'] == 9
    assert not result['accepted']


def test_warm_label_requires_same_process_and_prior_success(fixture):
    fixture.change(5, 'startup', lambda value: value.update(exit_code=1))
    result = fixture.run()
    assert result['attempts'][5]['cache_evidence'] == 'unverified'
    assert not result['accepted']


@pytest.mark.parametrize('damage,state', [('hash', 'digest_mismatch'), ('json', 'unreadable'), ('path', 'invalid_descriptor'), ('oversize', 'too_large')])
def test_invalid_receipt_is_retained_as_gap_without_loading_arbitrary_paths(fixture, damage, state):
    slot = fixture.manifest['attempts'][0]
    descriptor = slot['startup']
    if damage == 'hash':
        descriptor['sha256'] = '0' * 64
    elif damage == 'path':
        descriptor['path'] = '../private-token.json'
    else:
        raw = b'{"private":"secret"' if damage == 'json' else b' ' * (campaign.MAX_RECEIPT + 1)
        (fixture.root / descriptor['path']).write_bytes(raw)
        descriptor['sha256'] = hashlib.sha256(raw).hexdigest()
    result = fixture.run()
    assert result['attempts'][0]['receipts']['startup']['state'] == state
    assert len(result['attempts']) == 10 and not result['accepted']
    assert 'private-token' not in json.dumps(result) and 'secret' not in json.dumps(result)


@pytest.mark.parametrize('role,field,value', [
    ('startup', 'samples', 'malformed'), ('startup', 'record', []),
    ('metrics', 'installed', []), ('metrics', 'samples', [{'start_ticks': []}, {}]),
])
def test_malformed_receipt_fields_cannot_abort_remaining_attempts(fixture, role, field, value):
    fixture.change(1, role, lambda envelope: envelope['result'].update({field: value}))
    result = fixture.run()
    assert len(result['attempts']) == 10 and not result['accepted']


def test_duplicate_receipt_cannot_satisfy_two_slots(fixture):
    fixture.manifest['attempts'][1]['startup'] = fixture.manifest['attempts'][0]['startup']
    assert 'REUSED_RECEIPT' in fixture.run()['attempts'][1]['reasons']


@pytest.mark.parametrize('damage', ['nine', 'six_cold', 'duplicate_attempt', 'unknown_track_field'])
def test_manifest_requires_ten_fixed_slots_and_safe_track_contract(fixture, damage):
    if damage == 'nine':
        fixture.manifest['attempts'].pop()
    elif damage == 'six_cold':
        fixture.manifest['attempts'][5].update(cache_state='process_cold', warm_after=None)
    elif damage == 'duplicate_attempt':
        fixture.manifest['attempts'][1]['attempt'] = 1
    else:
        fixture.manifest['expected']['audio']['token'] = 'private'
    with pytest.raises(ValueError, match='CAMPAIGN_'):
        fixture.run()


def test_template_is_not_mistaken_for_evidence_and_tool_has_no_device_controller():
    with pytest.raises(ValueError, match='CAMPAIGN_'):
        campaign.validate(campaign.template())
    source = (ROOT / 'tools/ce_trial_campaign.py').read_text()
    assert 'transport.connect' not in source and 'wire.readonly' not in source
    assert 'Player.BobiControl' not in source and 'Input.Select' not in source
