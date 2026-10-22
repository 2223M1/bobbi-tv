"""Ordinary UI tests for previously untested works, with native owner guards."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


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


def result_exit_code(result, remote_code=0, diagnostic=False, operation=None):
    if remote_code or diagnostic or result.get('error'):
        return 1
    if any(row.get('failure') for row in result.get('samples', [])):
        return 1
    operation = operation or result.get('operation')
    # Older retained stop/cancel envelopes did not include operation. Honor
    # their explicit failures too, without applying playback gates to cards.
    fields = {'select': 'selected', 'observe': 'passed', 'stop': 'stopped', 'cancel': 'cancelled'}
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
    # A successful read of unsupported controls is not a successful trial.
    return 2 if result.get('state') == 'not_tested' else 0


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('work',choices=('straight_story','paprika','station_agent','nichijou','paterson','planetes','moon','made_in_abyss','nightcrawler','heavenly_delusion','attack_on_titan','frieren','the_conversation','death_parade','man_who_wasnt_there','space_dandy','baccano','gattaca','samurai_champloo','arrival','mushishi','perfect_days','eizouken','grand_budapest','further_universe','ping_pong','amelie','barakamon','coherence','odd_taxi','wild_tales','girls_last_tour','burning','flip_flappers',
                                      'lives_of_others','tokyo_godfathers','haibane_renmei','man_from_earth','lain',
                                      'twelve_angry_men','tatami_galaxy','rashomon','cowboy_bebop'))
    parser.add_argument('operation',choices=('start','requery','cards','select','collect','picker_wait','wait','inspect','observe','stop','cancel',
        'seek','manual_off','font_switch'), help='seek/manual_off/font_switch currently record read-only NOT TESTED evidence (exit 2); they never issue unguarded controls')
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--title')
    parser.add_argument('--site')
    parser.add_argument('--key')
    parser.add_argument('--trace',action='store_true')
    parser.add_argument('--brief',action='store_true',help='Keep full evidence on disk; print bounded summary')
    parser.add_argument('--start-over',action='store_true',help='Attended A/B from beginning, not stored resume')
    parser.add_argument('--resume-percent',type=float,help='Explicit one-shot product StartPercent for an attended natural EOF trial')
    parser.add_argument('--attempt',type=int,choices=range(1,11),default=1,
                        help='A separate retained defect-regression attempt, not new-work coverage')
    args=parser.parse_args()
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
                    RESUME_PERCENT=args.resume_percent)
    code='\n'.join(key+'='+repr(value) for key,value in parameters.items())+'\n'+(ROOT/'tools/ce_trial_remote.py').read_text(encoding='utf-8')
    # Failure evidence is retained and cannot turn a failed attempt into a pass.
    script='import json,traceback,sys\nsys.dont_write_bytecode=True\ntry:\n    exec(compile('+repr(code)+',"ce-ordinary-ui-trial","exec"))\nexcept Exception as error:\n    print(json.dumps(dict(error=type(error).__name__,reason=str(error) if isinstance(error,AssertionError) else "TRIAL_ERROR",frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)])))\n'
    client,wire=transport.connect()
    try:
        artifact='/storage/.local/share/bobbi-private-trials/20261020/trial-'+args.work+('' if args.attempt==1 else '-'+str(args.attempt))+'.startup.json'
        if args.operation=='collect':
            rc,result,diagnostic=0,dict(artifact=artifact),False
        else:
            rc,result,diagnostic=wire.readonly(client,script.encode(),deadline_seconds=60)
        if result.get('artifact'):
            if result['artifact']!=artifact:raise ValueError('UNEXPECTED_TRACE_PATH')
            with client.open_sftp() as sftp:
                with sftp.open(artifact,'rb') as stream:raw=stream.read(4*1024*1024+1)
            result=decode_trace(raw,result,artifact,args.work,retained=args.operation=='collect')
    except Exception as error:
        rc,result,diagnostic=1,dict(error=type(error).__name__,reason='TRIAL_TRANSPORT_OR_TRACE_ERROR'),False
    finally:client.close()
    output=ROOT/'review-evidence'/('ce-new-work-'+args.work+'-'+args.operation+'-'+str(time.time_ns())+'.json')
    code = result_exit_code(result, rc, diagnostic, args.operation)
    value=dict(exit_code=code,transport_exit_code=rc,trial_exit_code=code,
               result=result,diagnostic_present=bool(diagnostic),work=args.work,
               operation=args.operation,attempt=args.attempt,regression_attempt=args.attempt>1)
    output.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    display = dict(value)
    if args.brief:
        display['result'] = {key: result[key] for key in ('name','operation','error','reason','selected',
            'stopped','cancelled','passed','trace_passed','trace_health','trace_coverage','wall_seconds',
            'play_seconds','state','cards') if key in result}
        display['result']['last_sample'] = (result.get('samples') or [result.get('sample')])[-1]
        display['result']['select_to_av_observed_seconds'] = (result.get('record') or {}).get('select_to_av_observed_seconds')
    print(json.dumps(dict(evidence=str(output),**display),ensure_ascii=False))
    if code:raise SystemExit(code)


if __name__=='__main__':main()
