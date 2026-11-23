"""Read-only metrics, scope-bound intervals and real Git source binding."""
import ast
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ce_metrics', ROOT / 'tools/ce_trial_metrics.py')
metrics = importlib.util.module_from_spec(spec)
spec.loader.exec_module(metrics)


def sample(at, task=None, start=10):
    return dict(monotonic=at, start_ticks=start, cpu_ticks=at*50,
        host_total_ticks=at*100, host_idle_ticks=at*40, rss_kib=1024+at,
        gui_query_ms=2+at, scans=[dict(task_id=task,state='running')] if task else [],
        network_device_totals={'eth0':dict(rx_bytes=at*1000,tx_bytes=at*500)})


def test_running_intervals_require_same_exact_task_and_process():
    result = dict(installed={'clock_ticks_per_second':100},
                  samples=[sample(1),sample(2,'a'),sample(3,'a'),sample(4,'b'),sample(5,'b',11)])
    running = metrics.metrics(result, True)
    assert running['cpu_interval_count'] == 1
    assert running['cpu_interval_seconds'] == 1
    assert running['process_cpu_percent_one_core']['median'] == 50
    assert running['rss_kib']['n'] == 4
    assert running['network_device_bytes'] == {}
    whole = metrics.metrics(result)
    assert whole['cpu_interval_count'] == 3
    assert whole['network_device_bytes']['eth0'] == dict(rx_bytes=4000,tx_bytes=2000)
    assert whole['upstream_bytes'] is None and whole['input_to_photon_ms'] is None


def test_short_window_statistics_are_explicit_and_empty_safe():
    assert metrics.distribution([])['p95_nearest_rank'] is None
    assert metrics.distribution(list(range(1,31)))['p95_nearest_rank'] == 29
    assert metrics.distribution([1])['n'] == 1


def test_remote_generation_is_bounded_readonly_and_scrubs_trace(tmp_path):
    args=SimpleNamespace(source_tree='a'*40,condition='scan',cache_state='unknown',
                         work='galactic_heroes',seconds=3,repeat=1)
    code=metrics.remote_code(args)
    compile(code,'generated-metrics','exec')
    tree=ast.parse(metrics.REMOTE)
    namespace={}
    definitions=[node for node in tree.body if isinstance(node,(ast.Import,ast.ImportFrom,ast.FunctionDef,ast.ClassDef))]
    exec(compile(ast.Module(body=definitions,type_ignores=[]),'metrics-definitions','exec'),namespace)
    row=namespace['trace_line'](b'prefix {"event":"share_read","phase":"fetch_end","len":13,"url":"secret","token":"secret"}')
    assert row == dict(phase='fetch_end',len=13)
    assert 'mode=ro' in code and 'Player.BobiControl' not in code and 'Input.' not in code
    assert 'write_text' not in code and 'DROP' not in code
    args.source_tree='HEAD'
    with pytest.raises(ValueError,match='SOURCE_TREE'):
        metrics.remote_code(args)


def test_summary_binds_installed_bytes_to_recorded_git_tree(tmp_path):
    repo=tmp_path/'repo';repo.mkdir()
    def git(*args):
        return subprocess.check_output(['git','-C',str(repo),*args]).decode().strip()
    git('init','-q')
    for name in metrics.METRIC_SOURCES:
        path=repo/'addons'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'old bytes\n')
    git('add','addons')
    git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture')
    tree=git('rev-parse','HEAD^{tree}')
    result=dict(source_tree=tree,samples=[sample(1),sample(2)],sample_name='example',
        condition='idle',cache_state='unknown',repeat=1,utc_started=1,utc_ended=2,trace={},errors=[],
        installed=dict(installed_source_sha256={name:hashlib.sha256(path.read_bytes()).hexdigest() for name in metrics.METRIC_SOURCES},
            components=[],native_sha256='b'*64,boot_sha256='c'*64,installed_sequence=1,pid=1,clock_ticks_per_second=100))
    path.write_bytes(b'unrelated current worktree edit\n')
    receipt=tmp_path/'explicit-new-run.json'
    receipt.write_text(json.dumps(dict(result=result)),encoding='utf-8')
    summary=metrics.summarize([receipt],repo)
    assert summary['same_build_and_boot'] and summary['samples'][0]['source_binding']['matched']
    assert summary['samples'][0]['observed_owner_count'] == 0
    assert not summary['device_contacted']
    result['installed']['installed_source_sha256'][metrics.METRIC_SOURCES[0]]='0'*64
    receipt.write_text(json.dumps(dict(result=result)),encoding='utf-8')
    with pytest.raises(ValueError,match='INSTALLED_SOURCE_MISMATCH'):
        metrics.summarize([receipt],repo)


def test_failed_receipt_cannot_be_a_successful_summary(tmp_path):
    path=tmp_path/'failed.json'
    path.write_text(json.dumps(dict(transport_exit_code=1,result={'samples':[sample(1)]})))
    with pytest.raises(ValueError,match='RECEIPT_FAILED'):
        metrics.summarize([path],ROOT)
    with pytest.raises(ValueError,match='EXPLICIT_RECEIPTS'):
        metrics.summarize([],ROOT)


@pytest.mark.parametrize('exit_field', ['exit_code','trial_exit_code','transport_exit_code','remote_exit_code'])
def test_summary_never_upgrades_a_cli_failure(tmp_path, exit_field):
    path=tmp_path/'failed.json'
    path.write_text(json.dumps({exit_field: 1, 'result': {'samples': [sample(1),sample(2)]}}))
    with pytest.raises(ValueError,match='RECEIPT_FAILED'):
        metrics.summarize([path],ROOT)


def test_scan_start_does_not_capture_pre_scan_rss_or_gui_latency():
    rows=[sample(1,'a'),sample(2,'a'),sample(3,'a')]
    for row in rows:
        row['activity_monotonic']=row['monotonic']+.1
    result=metrics.metrics(dict(samples=rows,installed={'clock_ticks_per_second':100}),True)
    assert result['cpu_interval_count'] == 1
    assert result['rss_kib']['n'] == result['gui_read_rpc_ms']['n'] == 2


def test_missing_sampled_source_is_not_silently_a_verified_subset():
    with pytest.raises(ValueError,match='REQUIRED_SOURCE_MISSING'):
        metrics.source_binding(dict(source_tree='a'*40,installed={'installed_source_sha256':{}}),ROOT)
