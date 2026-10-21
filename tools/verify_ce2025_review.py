"""Re-run frozen review cases after repair; no changed expected values."""
import argparse
import json
import os
from pathlib import Path
import sys
from closure_gate import run

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--dependencies',type=Path,required=True)
    args=parser.parse_args()
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    a,b=(ROOT/'review-evidence/ce2025'/name for name in ('review-a','review-b'))
    os.environ['BOBBI_REVIEW_ROOT']=str(ROOT)
    records=[]
    def check(name,command):
        os.environ['BOBBI_REVIEW_OUTPUT']=str(out/name)
        code=run(name,[sys.executable,*map(str,command)],root=ROOT,output=out/name)
        records.append(dict(name=name,exit_code=code))
    for name,script in (('quiesce','probe_quiesce_retry.py'),('history','probe_history_report_failure.py')):
        check(name,[a/'probes'/script,'--repo',ROOT])
    check('subtitle-original-interface',[a/'probes/probe_subtitle_episode.py','--repo',ROOT])
    check('subtitle-adapted',[ROOT/'review-evidence/ce2025/adapted-probe-subtitle-episode.py','--repo',ROOT])
    check('subtitle-scope',[b/'checks/reproduce_subtitle_scope.py','--repo',ROOT,'--output',out/'subtitle-scope/matrix.json'])
    check('identity',['-m','pytest','-q','-p','no:cacheprovider',b/'checks/test_closure_gate_identity.py'])
    names=('script.module.requests','script.module.urllib3','script.module.certifi','script.module.idna','script.module.chardet')
    os.environ['PYTHONPATH']=os.pathsep.join(str(args.dependencies/name/'lib') for name in names)
    check('progressive',['-m','pytest','-q','-p','no:cacheprovider',b/'checks/test_progressive_shutdown.py'])
    value=dict(commands=records,notes=[
        'Original subtitle AST probe may exit 2 after helper extraction; its adapted copy adds only the helper dependency, never changes assertions.',
        'The historical decoder overwrite probe is not a post-fix acceptance test; official tests assert channel preservation instead.',
        'Dirty execution is diagnostic only, not a clean release gate.'])
    (out/'INDEX.json').write_text(json.dumps(value,indent=2)+'\n',encoding='utf-8')
    return int(any(r['exit_code'] for r in records if r['name']!='subtitle-original-interface'))


if __name__=='__main__':raise SystemExit(main())
