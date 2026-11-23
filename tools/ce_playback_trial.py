"""Ordinary UI tests for previously untested works, with native owner guards."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def trial_cases():
    return json.loads((ROOT / 'tools/ce_trial_cases.json').read_text(encoding='utf-8'))


def remote_code(parameters):
    cases = trial_cases()
    if parameters.get('NAME') not in cases['works'] or parameters.get('OP') not in cases['operations']:
        raise ValueError('TRIAL_SCOPE')
    if parameters['OP'] in cases['local_operations']:
        raise ValueError('TRIAL_LOCAL_OPERATION')
    injected = dict(parameters, TESTS=cases['works'],
        OPERATIONS=[value for value in cases['operations'] if value not in cases['local_operations']])
    return '\n'.join(key+'='+repr(value) for key,value in injected.items())+'\n'+(
        ROOT/'tools/ce_trial_remote.py').read_text(encoding='utf-8')


def decode_trace(raw, descriptor, expected_path, work, retained=False):
    if descriptor.get('artifact') != expected_path:
        raise ValueError('UNEXPECTED_TRACE_PATH')
    if len(raw) > 4*1024*1024:
        raise ValueError('TRACE_TOO_LARGE')
    if not retained and (hashlib.sha256(raw).hexdigest() != descriptor.get('sha256')
                         or len(raw) != descriptor.get('bytes')):
        raise ValueError('TRACE_CHANGED')
    result = json.loads(raw)
    if result.get('name') != work or result.get('operation') != 'select':
        raise ValueError('TRACE_IDENTITY_MISMATCH')
    return result


def query_exit_code(result):
    """Launch ACKs and legacy source counts cannot prove query completion.

    Exit 0 accepts a completed, error-free query, including an empty result.
    Exit 1 retains an explicit query error; exit 2 means completion/acceptance
    was not proved. This says nothing about source playability or playback.
    """
    record = result.get('record')
    record = record if isinstance(record, dict) else {}
    query = result.get('query')
    if isinstance(query, dict):
        if query.get('accepted') is False or (
                isinstance(query.get('error'), str) and query['error'].strip()):
            return 1
        if (type(query.get('schema')) is int and query['schema'] == 1
                and result.get('launch_accepted') is True and record.get('launch_accepted') is True
                and isinstance(record.get('picker'), dict) and record['picker']
                and query.get('picker') == record['picker']
                and query.get('completed') is True and query.get('accepted') is True
                and query.get('loading') == 'false' and query.get('error') == ''
                and type(query.get('source_count')) is int and query['source_count'] >= 0):
            return 0
        return 2
    # Old start/requery receipts omit source_loading and the final guarded
    # picker view. Retain an observed same-picker error, but never promote a
    # launch timestamp, nonzero count, or absence of error to query success.
    last = (result.get('samples') or [{}])[-1]
    picker = record.get('picker')
    picker = picker if isinstance(picker, dict) else {}
    window = (last.get('window') or {}).get('currentwindow') or {}
    error = (last.get('labels') or {}).get('Window.Property(playback_error)')
    if picker and window.get('id') == picker.get('window') and isinstance(error, str) and error.strip():
        return 1
    return 2


def stop_exit_code(result):
    """Exit 0 needs the retained original-command receipt, never global idle."""
    evidence = result.get('stop')
    if not isinstance(evidence, dict):
        return 1 if result.get('stopped') is False else 2
    receipt = evidence.get('receipt')
    receipt = receipt if isinstance(receipt, dict) else {}
    if receipt.get('status') in ('rejected', 'failed') or evidence.get('admission_status') in ('rejected', 'failed'):
        return 1
    try:
        original = evidence['original']
        command, trial = original['command'], original['trial']
        expected = command['expected']
        counters = ('epoch', 'selection_epoch', 'expected_sequence', 'user_intent', 'subtitle_intent', 'audio_intent')
        fields = {'boot_id', 'request_id', 'native_instance', 'file_sha256', *counters}
        digest = hashlib.sha256(json.dumps(original, ensure_ascii=True,
            sort_keys=True, separators=(',', ':')).encode()).hexdigest()
        if (type(evidence.get('schema')) is int and evidence['schema'] == 1
                and type(original.get('schema')) is int and original['schema'] == 1
                and set(original) == {'schema', 'trial', 'command'}
                and set(command) == {'expected', 'command_id', 'action', 'params'}
                and command['action'] == 'user_stop' and command['params'] == {}
                and re.fullmatch('[0-9a-f]{32}', command['command_id'])
                and set(expected) == fields
                and all(type(expected[key]) is int and 0 <= expected[key] < 2**53 for key in counters)
                and all(re.fullmatch('[0-9a-f]{32}', expected[key]) for key in ('boot_id', 'request_id'))
                and re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', expected['native_instance'])
                and re.fullmatch('[0-9a-f]{64}', expected['file_sha256'])
                and trial['name'] == result['name']
                and all(expected[source] == trial[target] for source, target in (
                    ('request_id', 'request_id'), ('native_instance', 'native_instance'),
                    ('file_sha256', 'file_identity_sha256')))
                and evidence['journal_sha256'] == digest
                and evidence['original_receipt_verified'] is True and result.get('stopped') is True
                and receipt == {'command_id': command['command_id'], 'status': 'applied'}):
            return 0
    except (KeyError, TypeError, ValueError, AttributeError):
        pass
    return 2


def result_exit_code(result, remote_code=0, diagnostic=False, operation=None, transport_errors=()):
    operation = operation or result.get('operation')
    if transport_errors:
        if operation != 'stop':
            return 1  # Preserve non-stop transport/cleanup failure semantics.
        if stop_exit_code(result) == 1:
            return 1  # An explicit original rejection/failure stays a failure.
        if any(error.get('phase') != 'close' for error in transport_errors):
            return 2  # Connection/response loss does not prove command failure.
        # Cleanup cannot retract an already obtained original receipt. Its
        # attention flag is retained separately, including for unknown results.
    if remote_code or diagnostic or result.get('error'):
        return 1
    if any(row.get('failure') for row in result.get('samples', [])):
        return 1
    if operation == 'stop' or (operation is None and 'stopped' in result):
        return stop_exit_code(result)
    # Older retained stop/cancel envelopes did not include operation. Honor
    # their explicit failures too, without applying playback gates to cards.
    fields = {'select': 'selected', 'observe': 'passed', 'cancel': 'cancelled', 'next_watch': 'passed'}
    required = fields.get(operation)
    if required and result.get(required) is not True:
        return 2 if operation == 'select' else 1
    if any(result.get(key) is False for key in ('passed', 'stopped', 'cancelled')):
        return 1
    if result.get('operation') == 'select' and result.get('selected') is not True:
        return 2  # A missing/mismatched card is not a successful selection.
    coverage = result.get('trace_coverage') or {}
    if coverage.get('passed') is False:
        return 1
    if 'trace_passed' in result and result['trace_passed'] is not True:
        return 2  # A successful selection command is not playback coverage.
    if operation == 'metrics' and (result.get('errors') or len(result.get('samples', [])) < 2):
        return 1
    if operation in ('start', 'requery'):
        return query_exit_code(result)
    # A successful read of unsupported controls is not a successful trial.
    return 2 if result.get('state') == 'not_tested' else 0


def build_parser():
    parser=argparse.ArgumentParser()
    cases = trial_cases()
    parser.add_argument('work',choices=tuple(cases['works']))
    parser.add_argument('operation',choices=cases['operations'], help='start/requery exit 0 requires a completed error-free query (empty is valid), exit 1 means failure, exit 2 means unproved completion; launch acceptance is retained separately. stop persists one original scoped command before sending, repeats only read its receipt: exit 0 means original receipt applied (not global idle), exit 1 explicit failure, exit 2 unproved including connection/response loss; never resend or refresh expected. Cleanup attention is separate and cannot retract an obtained original receipt. seek/manual_off/font_switch record read-only NOT TESTED evidence (exit 2); they never issue unguarded controls')
    parser.add_argument('--transport-source',type=Path)
    parser.add_argument('--output-dir',type=Path,default=ROOT/'review-evidence')
    parser.add_argument('--run-id',default='20261020',help='Fresh retained device trial directory; old default remains compatible')
    parser.add_argument('--source-tree',help='Exact deployed Git tree for metrics; analyzer verifies sampled installed bytes')
    parser.add_argument('--condition',choices=('idle','scan','playback','playback_scan'))
    parser.add_argument('--cache-state',choices=('process_cold','page_first','page_warm','unknown'))
    parser.add_argument('--repeat',type=int,choices=range(1,11),default=1)
    parser.add_argument('--seconds',type=int,choices=range(1,61),default=30)
    parser.add_argument('--receipts',nargs='+',type=Path,help='Explicit metrics receipts for offline summarize')
    parser.add_argument('--title')
    parser.add_argument('--site')
    parser.add_argument('--key')
    parser.add_argument('--trace',action='store_true')
    parser.add_argument('--brief',action='store_true',help='Keep full evidence on disk; print bounded summary')
    parser.add_argument('--start-over',action='store_true',help='Attended A/B from beginning, not stored resume')
    parser.add_argument('--resume-percent',type=float,help='Explicit one-shot product StartPercent for an attended natural EOF trial')
    parser.add_argument('--attempt',type=int,choices=range(1,11),default=1,
                        help='A separate retained defect-regression attempt, not new-work coverage')
    return parser


def main():
    parser=build_parser()
    args=parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.run_id):
        parser.error('run-id must be a bounded directory name')
    if args.operation == 'summarize':
        from ce_trial_metrics import summarize
        result = summarize(args.receipts, ROOT)
        args.output_dir.mkdir(parents=True,exist_ok=True)
        output = args.output_dir / ('ce-metrics-summary-' + str(time.time_ns()) + '.json')
        with output.open('x',encoding='utf-8') as stream:
            json.dump(result,stream,ensure_ascii=False,indent=2)
            stream.write('\n')
        print(json.dumps(dict(evidence=str(output),same_build_and_boot=result['same_build_and_boot'],
                             sample_count=len(result['samples']))))
        return
    if not args.transport_source:
        parser.error('transport-source is required for device operations')
    if args.operation == 'select' and (args.title is None or args.site is None):
        parser.error('select requires the observed --title and --site (and optionally --key)')
    if args.resume_percent is not None and (args.start_over or not 0 < args.resume_percent < 100):
        parser.error('Resume must be between 0 and 100, without start-over')
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('ce_trial_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
    transport=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    parameters=dict(NAME=args.work,OP=args.operation,TITLE=args.title,SITE=args.site,SOURCE_KEY=args.key,
                    TRACE=args.trace,ATTEMPT=args.attempt,PICKER=True,ORDINARY_UI=True,START_OVER=args.start_over,
                    RESUME_PERCENT=args.resume_percent,RUN_ID=args.run_id,DURATION=args.seconds)
    if args.operation == 'metrics':
        from ce_trial_metrics import remote_code as metrics_code
        code = metrics_code(args)
    else:
        code=remote_code(parameters) if args.operation != 'collect' else ''
    # Failure evidence is retained and cannot turn a failed attempt into a pass.
    script='import json,traceback,sys\nsys.dont_write_bytecode=True\ntry:\n    exec(compile('+repr(code)+',"ce-ordinary-ui-trial","exec"))\nexcept Exception as error:\n    print(json.dumps(dict(error=type(error).__name__,reason=str(error) if isinstance(error,AssertionError) else "TRIAL_ERROR",frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)])))\n'
    tool_source = dict(driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        remote_template_sha256=hashlib.sha256((ROOT / 'tools/ce_trial_remote.py').read_bytes()).hexdigest(),
        request_script_sha256=hashlib.sha256(script.encode()).hexdigest() if args.operation != 'collect' else None)
    client, transport_errors, phase = None, [], 'connect'
    try:
        client,wire=transport.connect()
        phase = 'execute'
        artifact='/storage/.local/share/bobbi-private-trials/'+args.run_id+'/trial-'+args.work+('' if args.attempt==1 else '-'+str(args.attempt))+'.startup.json'
        if args.operation=='collect':
            rc,result,diagnostic=0,dict(artifact=artifact),False
        else:
            rc,result,diagnostic=wire.readonly(client,script.encode(),deadline_seconds=max(60,args.seconds+20) if args.operation in ('metrics','next_watch') else 60)
        if result.get('artifact'):
            phase = 'trace'
            if result['artifact']!=artifact:raise ValueError('UNEXPECTED_TRACE_PATH')
            with client.open_sftp() as sftp:
                with sftp.open(artifact,'rb') as stream:raw=stream.read(4*1024*1024+1)
            result=decode_trace(raw,result,artifact,args.work,retained=args.operation=='collect')
    except Exception as error:
        transport_errors.append(dict(phase=phase, error=type(error).__name__))
        rc,result,diagnostic=1,dict(error=type(error).__name__,reason='TRIAL_TRANSPORT_OR_TRACE_ERROR'),False
        if args.operation == 'stop':
            result.update(name=args.work, operation='stop', state='unproved', stopped=None)
    finally:
        if client is not None:
            try:
                client.close()
            except Exception as error:
                transport_errors.append(dict(phase='close', error=type(error).__name__))
    output=args.output_dir/('ce-new-work-'+args.run_id+'-'+args.work+'-'+args.operation+'-'+str(time.time_ns())+'.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    code = result_exit_code(result, rc, diagnostic, args.operation, transport_errors)
    value=dict(exit_code=code,transport_exit_code=rc,trial_exit_code=code,
               result=result,diagnostic_present=bool(diagnostic),work=args.work,
               operation=args.operation,attempt=args.attempt,run_id=args.run_id,regression_attempt=args.attempt>1,
               transport_errors=transport_errors,
               transport_cleanup_attention=any(error['phase'] == 'close' for error in transport_errors),
               tool_source=tool_source)
    with output.open('x',encoding='utf-8') as stream:
        stream.write(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    display = dict(value)
    if args.brief:
        display['result'] = {key: result[key] for key in ('name','operation','error','reason','selected',
            'stopped','stop','cancelled','passed','trace_passed','trace_health','trace_coverage','wall_seconds',
            'play_seconds','state','cards','launch_accepted','query') if key in result}
        display['result']['last_sample'] = (result.get('samples') or [result.get('sample')])[-1]
        display['result']['select_to_av_observed_seconds'] = (result.get('record') or {}).get('select_to_av_observed_seconds')
    print(json.dumps(dict(evidence=str(output),**display),ensure_ascii=False))
    if code:raise SystemExit(code)


if __name__=='__main__':main()
