import hashlib
import importlib.util
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.platform/lib'))
spec=importlib.util.spec_from_file_location('sign_private_bundle_audit',ROOT/'tools/sign_private_bundle.py')
signer=importlib.util.module_from_spec(spec)
spec.loader.exec_module(signer)


def built(tmp_path):
    name='plugin.video.bobbi'
    relative=name+'/'+name+'-1.0.0.zip'
    target=tmp_path/relative
    target.parent.mkdir()
    target.write_bytes(b'original checked content')
    row=dict(id=name,version='1.0.0',file=relative,bytes=target.stat().st_size,
             sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    return dict(components=[row]),dict(components=[name]),target


@pytest.mark.parametrize('change',[dict(file='../userdata/account.json'),dict(file='C:/userdata/account.json'),
    dict(file='plugin.video.bobbi/../../key.pem'),dict(bytes=True),dict(version='../invalid'),dict(sha256='x'*64)])
def test_signing_rejects_manifest_paths_and_shape_before_reading_any_blob(tmp_path,monkeypatch,change):
    value,trust,target=built(tmp_path)
    value['components'][0].update(change)
    opened=[]
    original=Path.open
    def spy(path,*a,**kw):
        opened.append(path)
        return original(path,*a,**kw)
    monkeypatch.setattr(Path,'open',spy)
    with pytest.raises(ValueError,match='metadata'):
        signer.checked_components(tmp_path,value,trust)
    assert not opened


def test_duplicate_inventory_cannot_hide_missing_or_extra_components(tmp_path):
    value,trust,_=built(tmp_path)
    value['components']*=2
    with pytest.raises(ValueError,match='inventory'):
        signer.checked_components(tmp_path,value,trust)


def test_checked_blob_is_retained_for_output_not_read_again_after_signing(tmp_path):
    value,trust,target=built(tmp_path)
    checked=signer.checked_components(tmp_path,value,trust)
    target.write_bytes(b'changed later')
    assert checked[0][1]==b'original checked content'
    assert hashlib.sha256(checked[0][1]).hexdigest()==checked[0][0]['sha256']


def test_actual_blob_mutation_before_check_is_rejected(tmp_path):
    value,trust,target=built(tmp_path)
    target.write_bytes(b'x'*value['components'][0]['bytes'])
    with pytest.raises(ValueError,match='changed'):
        signer.checked_components(tmp_path,value,trust)
