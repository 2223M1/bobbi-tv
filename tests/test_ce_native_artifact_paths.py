"""Windows access mapping never changes recorded Linux provenance or selects a distro."""
from pathlib import Path

import pytest

from test_ce_native_reapply import tool


@pytest.mark.parametrize('reference', ['/opt/bobbi-build/source-candidate/result.json',
    Path('/opt/bobbi-build/source-candidate/result.json')])
def test_opt_access_is_mapped_to_only_the_pinned_distro(reference):
    before=str(reference)
    path=tool.local_artifact_path(reference,windows=True)
    assert path.as_posix()=='//wsl.localhost/AM6B-F9-Build-20260905/opt/bobbi-build/source-candidate/result.json'
    assert str(reference)==before


def test_mapped_unc_is_idempotent_and_mnt_drive_mapping_is_preserved():
    value='//wsl.localhost/AM6B-F9-Build-20260905/opt/bobbi-build/result.json'
    assert tool.local_artifact_path(value,windows=True).as_posix()==value
    assert tool.local_artifact_path('/mnt/d/AM6B-Project/build/result.json',windows=True).as_posix()=='D:/AM6B-Project/build/result.json'
    assert tool.local_artifact_path('/opt/bobbi-build/result.json',windows=False).as_posix()=='/opt/bobbi-build/result.json'


@pytest.mark.parametrize('reference', ['/opt', '/opt/', '/opt/../etc/proof.json', '/opt/x/../../proof.json',
    '/opt//server/share', '/opt/./result.json', '/opt/x\\..\\other/proof.json', '/opt/x/C:/proof.json',
    '/opt/x/proof.json:stream', '/opt/x/dir./proof.json', '/opt/x/dir /proof.json', '/opt/x/a?b',
    '/opt/x/a\nb', '/opt/x/a\x00b', '/tmp/foreign/proof.json', '/mnt/UNC/share/proof.json',
    '/mnt/d/../../proof.json', '/mnt/d', '/mnt/D/proof.json',
    '//wsl.localhost/Other-Distro/opt/proof.json', '//wsl.localhost/AM6B-F9-Build-20260905-other/opt/proof.json',
    '//wsl.localhost/AM6B-F9-Build-20260905/opt/../proof.json'])
def test_noncanonical_linux_or_other_distro_paths_are_rejected(reference):
    with pytest.raises(AssertionError):tool.local_artifact_path(reference,windows=True)
