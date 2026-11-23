"""Real Git repositories/worktrees; source identity is execution, not recorder."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('ce2025_gate',ROOT/'tools/closure_gate.py')
gate=importlib.util.module_from_spec(spec);spec.loader.exec_module(gate)


def git(root,*args):
    return subprocess.check_output(['git','-C',str(root),*args],stderr=subprocess.DEVNULL,text=True).strip()


def repository(path):
    path.mkdir();git(path,'init','-q')
    (path/'one').write_text('one')
    git(path,'add','one')
    git(path,'-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','initial')
    return path


@pytest.mark.parametrize('mode',['same','different','worktree','no-git','dirty','change-head','change-status'])
def test_real_identity_and_acceptance(tmp_path,monkeypatch,mode):
    recorder=repository(tmp_path/'recorder')
    execution=recorder
    if mode=='different': execution=repository(tmp_path/'execution')
    if mode=='worktree':
        execution=tmp_path/'worktree';git(recorder,'worktree','add','--detach',str(execution),'HEAD')
    if mode=='no-git':execution=tmp_path/'no-git';execution.mkdir()
    if mode=='dirty':(execution/'untracked').write_text('cannot ignore')
    monkeypatch.setattr(gate,'ROOT',recorder)
    code='print("executed")'
    if mode=='change-status':code='from pathlib import Path; Path("new").write_text("changed")'
    if mode=='change-head':code='import subprocess;subprocess.run(["git","-c","user.name=Test","-c","user.email=test@example.invalid","commit","--allow-empty","-qm","changed"],check=True)'
    output=tmp_path/'receipt'
    assert gate.run(mode,[sys.executable,'-c',code],root=execution,output=output)==0
    value=json.loads((output/'result.json').read_text())
    before=value['execution_before']
    assert before['cwd']==str(execution.resolve())
    if mode=='no-git':assert value['commit'] is None and value['dirty'] is None
    else:assert value['commit']==before['commit'] and before['tree']
    if mode in ('same','different','worktree'):
        assert gate.require_clean_receipt(value,before['commit'],before['tree'])
    else:
        with pytest.raises(ValueError,match='GATE_EXECUTION_IDENTITY_UNVERIFIED'):
            gate.require_clean_receipt(value,before['commit'],before['tree'])


def test_only_own_generated_receipts_ignored_and_command_exit_preserved(tmp_path,monkeypatch):
    root=repository(tmp_path/'repo');monkeypatch.setattr(gate,'ROOT',root)
    assert gate.run('local',[sys.executable,'-c','raise SystemExit(7)'],root=root)==7
    result=json.loads((root/'review-evidence/ce2023/local/result.json').read_text())
    assert result['dirty'] is False and result['execution_after']['dirty'] is False
    assert result['execution_stable'] is True
    (root/'review-evidence/ce2023/local/extra').write_text('not a generated receipt')
    current=gate.checkout_identity(root,[root/'review-evidence/ce2023/local/result.json'])
    assert current['dirty'] is True
    with pytest.raises(ValueError):gate.require_clean_receipt(result,result['commit'],result['execution_before']['tree'])
    with pytest.raises(ValueError):gate.require_clean_receipt(dict(commit=result['commit'],exit_code=0,dirty=False),result['commit'],'tree')
