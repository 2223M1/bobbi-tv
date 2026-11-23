import ast
import copy
from pathlib import Path
import subprocess
import sys
import pytest


def subject():
    path=Path(__file__).resolve().parents[1]/'tools/ce_personal_smoke_remote.py'
    tree=ast.parse(path.read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='acceptance')
    env={}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),env)
    return env['acceptance']


def data():
    row=dict(identity=('movie',329865),percent='1',count='1')
    return dict(expected_identity=row['identity'],expected_percent='1',resume_count=31,directory_position=0,
        directory=dict(row,count='11'),personal=dict(row,loading=False))


def test_identity_and_both_progress_values_required():
    check=subject()
    assert check(data())
    for section in ('directory','personal'):
        for key,value in [('identity',('movie',1)),('percent','99'),('count','0')]:
            result=data();result[section][key]=value
            assert not check(result)


def test_unidentified_records_never_prove_same_work():
    result=data()
    result['expected_identity']=('unidentified','')
    for section in ('directory','personal'):result[section]['identity']=('unidentified','')
    original=copy.deepcopy(result)
    assert not subject()(result)
    assert result==original


def test_empty_case_is_not_proven_without_item_bound_completion():
    result=dict(expected_identity=None,resume_count=0,directory=dict(count='0'),personal=dict(count='0'))
    assert not subject()(result)
    result['personal']['count']='1'
    assert not subject()(result)


def test_nonfirst_selection_and_loading_are_not_accepted():
    result=data();result['directory_position']=1
    assert not subject()(result)


def test_incident_probe_stays_suspended_at_both_entries(tmp_path):
    root=Path(__file__).resolve().parents[1]
    result=subprocess.run([sys.executable,str(root/'tools/ce_keyboard_smoke.py'),
        '--probe','personal','--transport-source',str(tmp_path/'missing-transport'),
        '--output',str(tmp_path/'not-created')],capture_output=True,text=True,timeout=5)
    assert result.returncode==2 and 'suspended' in result.stderr
    assert not (tmp_path/'not-created').exists()
    with pytest.raises(RuntimeError,match='PERSONAL_PROBE_SUSPENDED'):
        exec(compile((root/'tools/ce_personal_smoke_remote.py').read_bytes(),'retired-probe','exec'),{'__name__':'__main__'})
    result=data();result['personal']['loading']=True
    assert not subject()(result)
