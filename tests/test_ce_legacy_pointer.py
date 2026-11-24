import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from ce_legacy_pointer import advance
from bobbi_platform.online_updates import release_url


@pytest.mark.parametrize('case',['ok','preview','unverified','old-proof','wrong-mirror','ahead','conflict'])
def test_legacy_stable_alias_never_adopts_an_unverified_pointer(tmp_path,case):
    stable=tmp_path/'stable';stable.mkdir()
    new=dict(schema=2,tag='ce2183',sequence=2183,size=23,sha256='a'*64,
             url=release_url('ce2183','github'),track='stable',prerelease=False,
             manifest_channel='private-stable',versions={'script.bobbi.start':'1.0'})
    previous=dict(schema=1,tag='ce2182',sequence=2182,size=21,sha256='b'*64,url=release_url('ce2182','github'))
    receipt=dict(track='stable',tag='ce2183',tree='t',commit='c',offers={'github':new,'gitcode':{}})
    proof=dict(**{k:receipt[k] for k in ('track','tag','tree','commit')},passed=True,promotable=True,
               phase='before-feed-commit',mirrors=['github','gitcode'])
    if case=='preview':receipt['track']='preview'
    if case=='unverified':proof['passed']=False
    if case=='old-proof':proof['tag']='ce2182'
    if case=='wrong-mirror':new['url']=release_url('ce2183','gitcode')
    if case=='ahead':previous['sequence']=2184
    if case=='conflict':previous['sequence']=2183
    path=tmp_path/'current.json'
    path.write_bytes(json.dumps(previous).encode());original=path.read_bytes()
    (stable/'current.json').write_bytes(json.dumps(new).encode())
    if case=='ok':
        row=advance(tmp_path,receipt,proof)
        assert set(row)==set(previous) and row['schema']==1 and row['tag']=='ce2183'
        assert advance(tmp_path,receipt,proof)==row
    else:
        with pytest.raises(ValueError):advance(tmp_path,receipt,proof)
        assert path.read_bytes()==original
