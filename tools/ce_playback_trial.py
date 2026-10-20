"""Ordinary UI tests for previously untested works, with native owner guards."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]


def result_exit_code(result, remote_code=0, diagnostic=False):
    if remote_code or diagnostic or result.get('error'):
        return 1
    if any(row.get('failure') for row in result.get('samples', [])):
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
    parser.add_argument('work',choices=('coherence','odd_taxi','wild_tales','girls_last_tour','burning','flip_flappers',
                                      'lives_of_others','tokyo_godfathers','haibane_renmei','man_from_earth','lain',
                                      'twelve_angry_men','tatami_galaxy'))
    parser.add_argument('operation',choices=('start','cards','select','picker_wait','wait','inspect','observe','stop','cancel',
        'seek','manual_off','font_switch'), help='seek/manual_off/font_switch currently record read-only NOT TESTED evidence (exit 2); they never issue unguarded controls')
    parser.add_argument('--transport-source',type=Path,required=True)
    parser.add_argument('--title')
    parser.add_argument('--site')
    parser.add_argument('--key')
    parser.add_argument('--trace',action='store_true')
    parser.add_argument('--brief',action='store_true',help='Keep full evidence on disk; print bounded summary')
    parser.add_argument('--start-over',action='store_true',help='Attended A/B from beginning, not stored resume')
    parser.add_argument('--attempt',type=int,choices=range(1,11),default=1,
                        help='A separate retained defect-regression attempt, not new-work coverage')
    args=parser.parse_args()
    sys.path.insert(0,str(args.transport_source/'ui-redesign/runtime/ssh-python'))
    spec=importlib.util.spec_from_file_location('ce_trial_transport',args.transport_source/'ui-redesign/tools/device_transport.py')
    transport=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)
    parameters=dict(NAME=args.work,OP=args.operation,TITLE=args.title,SITE=args.site,SOURCE_KEY=args.key,
                    TRACE=args.trace,ATTEMPT=args.attempt,PICKER=True,ORDINARY_UI=True,START_OVER=args.start_over)
    code='\n'.join(key+'='+repr(value) for key,value in parameters.items())+'\n'+(ROOT/'tools/ce_trial_remote.py').read_text(encoding='utf-8')
    # Failure evidence is retained and cannot turn a failed attempt into a pass.
    script='import json,traceback,sys\nsys.dont_write_bytecode=True\ntry:\n    exec(compile('+repr(code)+',"ce-ordinary-ui-trial","exec"))\nexcept Exception as error:\n    print(json.dumps(dict(error=type(error).__name__,reason=str(error) if isinstance(error,AssertionError) else "TRIAL_ERROR",frames=[dict(function=f.name,line=f.lineno) for f in traceback.extract_tb(error.__traceback__)])))\n'
    client,wire=transport.connect()
    try:
        rc,result,diagnostic=wire.readonly(client,script.encode(),deadline_seconds=60)
    finally:client.close()
    output=ROOT/'review-evidence'/('ce-new-work-'+args.work+'-'+args.operation+'-'+str(time.time_ns())+'.json')
    value=dict(exit_code=rc,result=result,diagnostic_present=bool(diagnostic),work=args.work,
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
    code = result_exit_code(result, rc, diagnostic)
    if code:raise SystemExit(code)


if __name__=='__main__':main()
