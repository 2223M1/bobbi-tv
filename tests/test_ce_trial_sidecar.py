import hashlib
import importlib.util
import json
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('trace_cli',Path(__file__).resolve().parents[1]/'tools/ce_playback_trial.py')
cli=importlib.util.module_from_spec(spec);spec.loader.exec_module(cli)


def fixture():
    value=dict(name='movie',operation='select',selected=True,trace_passed=False,
               samples=[dict(decoder=dict(schema=2,raw='two complete channels'))])
    raw=json.dumps(value).encode()
    return value,raw,dict(artifact='/exact.json',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())


def test_sidecar_preserves_raw_channels_and_failure():
    value,raw,descriptor=fixture()
    assert cli.decode_trace(raw,descriptor,'/exact.json','movie')==value
    assert cli.result_exit_code(value,operation='collect')!=0


@pytest.mark.parametrize('field,value', [('artifact','/wrong.json'),('sha256','bad'),('bytes',0)])
def test_reject_changed_transport_descriptor(field,value):
    _,raw,descriptor=fixture();descriptor[field]=value
    with pytest.raises(ValueError):cli.decode_trace(raw,descriptor,'/exact.json','movie')


def test_retained_sidecar_still_requires_exact_identity_and_bound():
    _,raw,_=fixture()
    with pytest.raises(ValueError):cli.decode_trace(raw,dict(artifact='/exact.json'),'/exact.json','other',True)
    with pytest.raises(ValueError):cli.decode_trace(b' '* (4*1024*1024+1),dict(artifact='/exact.json'),'/exact.json','movie',True)
