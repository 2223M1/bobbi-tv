"""Offline ten-attempt ledger for the existing ordinary-UI CE trial.

No transport, restart, cache eviction or playback control exists here. Supply
explicit SHA-bound receipts, including failed/unconfirmed attempts. A template
is a plan, not evidence. Five process-cold and five page-warm labels are always
retained; process observations qualify those labels without claiming disk/CDN
cache state, first rendered frame, or reliable P95 from ten starts.
"""
import argparse
from collections import Counter
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import statistics
import subprocess

MAX_RECEIPT = 4 * 1024 * 1024
STREAM_FIELDS = {'index', 'channels', 'bitrate', 'samplerate', 'bitsperrawsample',
    'isdefault', 'isforced', 'isexternal', 'name_sha256', 'language_sha256', 'codec_sha256', 'language'}


def _hash(value, length=64):
    return type(value) is str and re.fullmatch('[0-9a-f]{%d}' % length, value) is not None


def _number(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _mapping(value):
    return value if type(value) is dict else {}


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    def invalid(_):
        raise ValueError('NONFINITE_JSON')
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def _module(name):
    spec = importlib.util.spec_from_file_location('campaign_' + name, Path(__file__).with_name(name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def template():
    return dict(schema=1, run_id=None, expected=dict(work=None, source_key_sha256=None,
        file_identity_sha256=None, source_tree=None, native_sha256=None, installed_sequence=None,
        start='beginning', audio={'index': None}, subtitle={'enabled': None, 'stream': None}),
        attempts=[dict(attempt=i, cache_state='process_cold' if i <= 5 else 'page_warm',
            startup=None, metrics=None, pre_restart_metrics=None, warm_after=i - 1 if i > 5 else None)
            for i in range(1, 11)])


def _stream(value):
    if (type(value) is not dict or set(value) - STREAM_FIELDS
            or type(value.get('index')) is not int or not 0 <= value['index'] <= 4096):
        raise ValueError('CAMPAIGN_STREAM_REQUIRED')
    for key, item in value.items():
        if key.endswith('_sha256'):
            valid = _hash(item)
        elif key == 'language':
            valid = type(item) is str and re.fullmatch('[a-z]{2,3}(?:-[A-Za-z0-9]{2,8})?', item)
        elif key.startswith('is'):
            valid = type(item) is bool
        else:
            valid = type(item) is int and 0 <= item <= 1000000000
        if not valid:
            raise ValueError('CAMPAIGN_STREAM_INVALID')


def validate(manifest):
    if (type(manifest) is not dict or set(manifest) != {'schema', 'run_id', 'expected', 'attempts'}
            or type(manifest['schema']) is not int or manifest['schema'] != 1
            or type(manifest['run_id']) is not str
            or not re.fullmatch('[A-Za-z0-9_-]{1,64}', manifest['run_id'])):
        raise ValueError('CAMPAIGN_MANIFEST_INVALID')
    expected = manifest['expected']
    if type(expected) is not dict or set(expected) != set(template()['expected']):
        raise ValueError('CAMPAIGN_EXPECTATION_INVALID')
    if (type(expected['work']) is not str or not re.fullmatch('[A-Za-z0-9_-]{1,64}', expected['work'])
            or expected['start'] != 'beginning'
            or type(expected['installed_sequence']) is not int or expected['installed_sequence'] < 1
            or not all(_hash(expected[key]) for key in ('source_key_sha256', 'file_identity_sha256', 'native_sha256'))
            or not _hash(expected['source_tree'], 40)):
        raise ValueError('CAMPAIGN_FIXED_IDENTITY_REQUIRED')
    _stream(expected['audio'])
    subtitle = expected['subtitle']
    if (type(subtitle) is not dict or not {'enabled', 'stream'} <= set(subtitle)
            or set(subtitle) - {'enabled', 'stream', 'external_sha256'}
            or type(subtitle['enabled']) is not bool):
        raise ValueError('CAMPAIGN_SUBTITLE_REQUIRED')
    if subtitle['enabled']:
        _stream(subtitle['stream'])
    elif subtitle['stream'] is not None:
        raise ValueError('CAMPAIGN_SUBTITLE_DISABLED')
    if 'external_sha256' in subtitle and not _hash(subtitle['external_sha256']):
        raise ValueError('CAMPAIGN_SUBTITLE_INVALID')
    attempts = manifest['attempts']
    if type(attempts) is not list or len(attempts) != 10:
        raise ValueError('CAMPAIGN_TEN_SLOTS_REQUIRED')
    for i, row in enumerate(attempts, 1):
        if (type(row) is not dict or set(row) != set(template()['attempts'][0])
                or type(row['attempt']) is not int or row['attempt'] != i
                or type(row['cache_state']) is not str or row['cache_state'] not in ('process_cold', 'page_warm')):
            raise ValueError('CAMPAIGN_SLOT_INVALID')
        if row['cache_state'] == 'page_warm':
            if type(row['warm_after']) is not int or not 1 <= row['warm_after'] < i:
                raise ValueError('CAMPAIGN_WARM_BASELINE_REQUIRED')
        elif row['warm_after'] is not None:
            raise ValueError('CAMPAIGN_COLD_BASELINE_INVALID')
    if Counter(row['cache_state'] for row in attempts) != {'process_cold': 5, 'page_warm': 5}:
        raise ValueError('CAMPAIGN_FIVE_COLD_FIVE_WARM_REQUIRED')
    return manifest


def _receipt(root, descriptor):
    evidence = dict(state='missing', sha256=None)
    if descriptor is None:
        return None, evidence
    if (type(descriptor) is not dict or set(descriptor) != {'path', 'sha256'}
            or not _hash(descriptor['sha256']) or type(descriptor['path']) is not str
            or not re.fullmatch('[A-Za-z0-9_./-]{1,240}', descriptor['path'])
            or descriptor['path'].startswith('/') or '..' in descriptor['path'].split('/')):
        return None, dict(state='invalid_descriptor', sha256=None)
    path = root / descriptor['path']
    if any(part.is_symlink() for part in (path, *path.parents)):
        return None, dict(state='unsafe_path', sha256=None)
    try:
        with path.open('rb') as stream:
            raw = stream.read(MAX_RECEIPT + 1)
        if len(raw) > MAX_RECEIPT:
            return None, dict(state='too_large', sha256=None)
        evidence['sha256'] = hashlib.sha256(raw).hexdigest()
        if evidence['sha256'] != descriptor['sha256']:
            return None, dict(evidence, state='digest_mismatch')
        value = _json(raw)
        if type(value) is not dict or type(value.get('result')) is not dict:
            raise ValueError('RECEIPT_ENVELOPE')
        return value, dict(evidence, state='retained')
    except (OSError, ValueError, UnicodeError, RecursionError):
        return None, dict(evidence, state='unreadable')


def _ok(envelope):
    codes = [envelope[key] for key in ('exit_code', 'trial_exit_code', 'transport_exit_code', 'remote_exit_code') if key in envelope]
    return (bool(codes) and all(type(code) is int and code == 0 for code in codes)
        and envelope.get('diagnostic_present') is False and not envelope['result'].get('errors')
        and not envelope['result'].get('error'))


def _process(result):
    installed = result.get('installed', {})
    samples = result.get('samples', [])
    if (type(installed) is not dict or type(samples) is not list or not 2 <= len(samples) <= 61
            or not _hash(installed.get('boot_sha256')) or type(installed.get('pid')) is not int
            or installed['pid'] < 1 or any(type(row) is not dict for row in samples)):
        return None
    if any(type(row.get('start_ticks')) is not int or row['start_ticks'] <= 0 for row in samples):
        return None
    starts = {row['start_ticks'] for row in samples}
    if len(starts) != 1:
        return None
    return dict(boot_sha256=installed['boot_sha256'], pid=installed['pid'], start_ticks=starts.pop())


def _selection_process(value):
    return (type(value) is dict and set(value) == {'boot_sha256', 'pid', 'start_ticks'}
        and _hash(value['boot_sha256']) and type(value['pid']) is int and value['pid'] > 0
        and type(value['start_ticks']) is int and value['start_ticks'] > 0)


def _tracks(samples, expected):
    av = [row for row in samples if type(row) is dict and row.get('phase') == 'AV_STARTED']
    if not av:
        return False
    def contains(actual, required):
        return type(actual) is dict and all(actual.get(key) == value and type(actual.get(key)) is type(value)
            for key, value in required.items())
    subtitle = expected['subtitle']
    return all(contains(row.get('currentaudiostream'), expected['audio'])
        and row.get('subtitleenabled') is subtitle['enabled']
        and (not subtitle['enabled'] or contains(row.get('currentsubtitle'), subtitle['stream']))
        and ('external_sha256' not in subtitle or _mapping(row.get('native')).get('subtitle_file_sha256') == subtitle['external_sha256'])
        for row in av)


def summarize(manifest_path, repo):
    manifest_path = Path(manifest_path).resolve()
    with manifest_path.open('rb') as stream:
        raw = stream.read(65537)
    if len(raw) > 65536:
        raise ValueError('CAMPAIGN_MANIFEST_TOO_LARGE')
    manifest = validate(_json(raw))
    expected = manifest['expected']
    metrics, trial = _module('ce_trial_metrics'), _module('ce_playback_trial')
    rows, internal, used = [], {}, set()
    for slot in manifest['attempts']:
        number = slot['attempt']
        row = dict(attempt=number, cache_state=slot['cache_state'], outcome='missing',
            comparable=False, cache_evidence='unverified', reasons=[], receipts={})
        receipts = {}
        for role in ('startup', 'metrics', 'pre_restart_metrics'):
            receipt, evidence = _receipt(manifest_path.parent, slot[role])
            row['receipts'][role] = evidence
            receipts[role] = receipt
            if role != 'pre_restart_metrics' and evidence['state'] == 'retained':
                key = evidence['sha256']
                if key in used:
                    row['reasons'].append('REUSED_RECEIPT')
                used.add(key)
        startup, metric = receipts['startup'], receipts['metrics']
        record, measured, process = {}, {}, None
        if startup:
            value = startup['result']
            record = value.get('record') if type(value.get('record')) is dict else {}
            try:
                passed = (_ok(startup) and value.get('trace_passed') is True
                    and _mapping(value.get('trace_coverage')).get('passed') is True
                    and trial.result_exit_code(value, operation='select') == 0)
            except (TypeError, AttributeError):
                passed = False
            row['outcome'] = ('unconfirmed' if value.get('reason') == 'TRIAL_TRANSPORT_OR_TRACE_ERROR'
                else 'passed' if passed else 'failed')
            if (startup.get('run_id') != manifest['run_id'] or startup.get('work') != expected['work']
                    or startup.get('attempt') != number or value.get('name') != expected['work']
                    or value.get('operation') != 'select'):
                row['reasons'].append('STARTUP_SCOPE_MISMATCH')
            if (record.get('launch_mode') != 'ordinary_ui' or record.get('explicit_start_over') is not True
                    or 'explicit_resume_percent' in record):
                row['reasons'].append('FIXED_START_UNPROVEN')
            if (record.get('exact_source_key_requested') is not True
                    or record.get('selected_source_key_sha256') != expected['source_key_sha256']
                    or record.get('file_identity_sha256') != expected['file_identity_sha256']):
                row['reasons'].append('FIXED_FILE_UNPROVEN')
            samples = value.get('samples')
            if type(samples) is not list or len(samples) > 1000 or not _tracks(samples, expected):
                row['reasons'].append('FIXED_TRACKS_UNPROVEN')
            if (type(samples) is not list or not samples or any(type(item) is not dict or
                    (item.get('phase') == 'AV_STARTED' and any(
                        _mapping(item.get('native')).get(key) != record.get(key)
                        for key in ('request_id', 'native_instance'))) for item in samples)):
                row['reasons'].append('STARTUP_OWNER_UNPROVEN')
            elapsed = record.get('select_to_av_observed_seconds')
            row['select_to_av_observed_upper_bound_seconds'] = elapsed if _number(elapsed) else None
            if not _number(elapsed):
                row['reasons'].append('STARTUP_TIMING_UNPROVEN')
        else:
            row['reasons'].append('STARTUP_RECEIPT_UNAVAILABLE')
        if metric:
            measured = metric['result']
            process = _process(measured)
            installed = _mapping(measured.get('installed'))
            if (not _ok(metric) or metric.get('run_id') != manifest['run_id']
                    or measured.get('sample_name') != expected['work'] or measured.get('repeat') != number
                    or measured.get('cache_state') != slot['cache_state']
                    or measured.get('condition') not in ('playback', 'playback_scan')):
                row['reasons'].append('METRICS_FAILED_OR_SCOPE_MISMATCH')
            if (measured.get('source_tree') != expected['source_tree']
                    or installed.get('native_sha256') != expected['native_sha256']
                    or installed.get('installed_sequence') != expected['installed_sequence']):
                row['reasons'].append('BUILD_IDENTITY_MISMATCH')
            try:
                if not metrics.source_binding(measured, repo)['matched']:
                    raise ValueError('UNBOUND_SOURCE')
            except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.CalledProcessError):
                row['reasons'].append('SAMPLED_SOURCE_BINDING_UNPROVEN')
            selection_process = record.get('selection_process')
            if not process or not _selection_process(selection_process) or selection_process != process:
                row['reasons'].append('SELECTION_PROCESS_UNPROVEN')
            samples = measured.get('samples', [])
            owner = record.get('request_id'), record.get('native_instance')
            if (not _hash(owner[0], 32) or type(owner[1]) is not str
                    or not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', owner[1]) or type(samples) is not list
                    or not samples or any(type(item) is not dict or item.get('player_unavailable')
                        or (_mapping(item.get('player')).get('request_id'), _mapping(item.get('player')).get('native_instance')) != owner
                        for item in samples)):
                row['reasons'].append('METRICS_OWNER_UNPROVEN')
            at, began = record.get('selected_at'), measured.get('monotonic_started')
            ended = measured.get('monotonic_ended')
            if not _number(at) or not _number(began) or not _number(ended) or began < at or ended < began:
                row['reasons'].append('RECEIPT_ORDER_UNPROVEN')
        else:
            row['reasons'].append('METRICS_RECEIPT_UNAVAILABLE')
        row['comparable'] = not row['reasons']
        if row['comparable']:
            if slot['cache_state'] == 'process_cold':
                before = receipts['pre_restart_metrics']
                prior = before['result'] if before else {}
                previous = _process(prior)
                ended = prior.get('monotonic_ended')
                began = prior.get('monotonic_started')
                earlier_ends = [item['ended'] for item in internal.values() if _number(item['ended'])]
                if (before and _ok(before) and previous and previous['boot_sha256'] == process['boot_sha256']
                        and previous != process and _number(ended) and ended <= record['selected_at']
                        and _number(began) and began <= ended
                        and (not earlier_ends or max(earlier_ends) <= began)
                        and all(item['process'] != process for item in internal.values())
                        and prior.get('condition') == 'idle'):
                    row['cache_evidence'] = 'process_restart_observed'
            else:
                previous = internal.get(slot['warm_after'])
                if (previous and previous['row']['comparable'] and previous['row']['outcome'] == 'passed'
                        and previous['process'] == process and _number(previous['ended'])
                        and previous['ended'] <= record['selected_at']):
                    row['cache_evidence'] = 'same_process_reuse_observed'
        if row['cache_evidence'] == 'unverified':
            row['reasons'].append('CACHE_LABEL_UNVERIFIED')
        internal[number] = dict(row=row, process=process, ended=measured.get('monotonic_ended'))
        rows.append(row)
    accepted = all(row['outcome'] == 'passed' and row['comparable'] and row['cache_evidence'] != 'unverified' for row in rows)
    statistics_by_condition = {}
    for condition in ('process_cold', 'page_warm'):
        numbers = [row.get('select_to_av_observed_upper_bound_seconds') for row in rows
            if row['cache_state'] == condition and row['outcome'] == 'passed' and row['comparable']
            and row['cache_evidence'] != 'unverified' and _number(row.get('select_to_av_observed_upper_bound_seconds'))]
        statistics_by_condition[condition] = dict(planned=5, qualified_successes=len(numbers),
            median=statistics.median(numbers) if numbers else None, minimum=min(numbers) if numbers else None,
            maximum=max(numbers) if numbers else None)
    return dict(schema=1, operation='campaign_summary', device_contacted=False,
        manifest_sha256=hashlib.sha256(raw).hexdigest(), accepted=accepted, attempts=rows,
        qualified_attempts=sum(row['outcome'] == 'passed' and row['comparable']
            and row['cache_evidence'] != 'unverified' for row in rows),
        outcomes=dict(Counter(row['outcome'] for row in rows)), statistics=statistics_by_condition,
        qualification='All ten slots and failed/unconfirmed receipts are retained. Each outcome describes the startup '
            'trial; comparable/cache evidence additionally determine qualification. Statistics include only qualified '
            'successes with a visible denominator, not a reliability claim. Timings are selection-to-AV observed '
            'upper bounds, not first rendered frames. Process restart/reuse evidence does not prove disk, CDN or '
            'physical cache state. No reliable P95 is claimed. Build binding checks existing sampled source files; '
            'use ce_verify_installed separately for complete installation verification.')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--template', action='store_true')
    mode.add_argument('--manifest', type=Path)
    parser.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    value = template() if args.template else summarize(args.manifest, args.repo)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    print(json.dumps(dict(output=str(args.output), accepted=value.get('accepted'))))
    if not args.template and not value['accepted']:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
