import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import zipfile
import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ce_ui_preview_remote', ROOT/'tools/ce_ui_preview_remote.py')
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


@pytest.mark.parametrize('name', ['skin/../settings.xml', 'skin/addon.xml',
    'dialogs/../default.py', 'skin/scripts/remote.py', '/skin/1080p/Home.xml',
    'skin//1080p/Home.xml','skin/1080p/evil.py','dialogs/default.py',
    'skin/media/link:stream.png'])
def test_reject_business_or_escaping_paths(name):
    assert not p.allowed(name)


@pytest.mark.parametrize('name', ['skin/1080p/Home.xml','skin/scripts/cinema_keyboard.py',
    'skin/media/bobi/icon.png','dialogs/Default/1080i/Source.xml'])
def test_allows_new_ui_ids(name):
    assert p.allowed(name)


@pytest.fixture
def transaction(tmp_path, monkeypatch):
    run = tmp_path/'preview-20261021T000000Z-12345678'
    run.mkdir()
    live = {c:tmp_path/('live-'+c) for c in ('dialogs','skin')}
    for root in live.values():
        root.mkdir()
        (root/'kept.txt').write_text('original')
    (live['skin']/'1080p').mkdir()
    (live['skin']/'1080p/Home.xml').write_text('<window/>')
    monkeypatch.setattr(p,'BASE',tmp_path)
    monkeypatch.setattr(p,'LIVE',live)
    monkeypatch.setattr(p,'idle',lambda: {'idle':True})
    monkeypatch.setattr(p,'reload_skin',lambda: {'reloaded':True})
    monkeypatch.setattr(p,'capture',lambda run: {'captured':True})
    files = {'skin/1080p/Home.xml':b'<window><defaultcontrol>10</defaultcontrol></window>',
             'dialogs/Default/1080i/Source.xml':b'<window/>'}
    archive = run/'candidate.zip'
    with zipfile.ZipFile(archive,'w') as zipped:
        for name,raw in files.items():
            zipped.writestr(name,raw)
    journal = dict(state='prepared',components=sorted(live),
        before={c:p.hashes(root) for c,root in live.items()},
        files={name:hashlib.sha256(raw).hexdigest() for name,raw in files.items()})
    p.save(run/'journal.json',journal)
    return run,live,journal,p.digest(archive)


def test_success_and_idempotent_rollback(transaction):
    run,live,journal,sha = transaction
    result = p.deploy(run,sha)
    assert result['state'] == 'committed' and result['screenshot']['captured']
    assert (live['dialogs']/'Default/1080i/Source.xml').exists()
    journal = json.loads((run/'journal.json').read_text())
    p.restore(run,journal)
    p.restore(run,journal)
    assert all(p.hashes(root) == journal['before'][c] for c,root in live.items())
    assert (run/'backup/skin').is_dir()


def test_reload_failure_restores_both(transaction,monkeypatch):
    run,live,journal,sha = transaction
    calls=[]
    def reload():
        calls.append(1)
        if len(calls)==1: raise RuntimeError('RELOAD_FAILED')
    monkeypatch.setattr(p,'reload_skin',reload)
    with pytest.raises(RuntimeError,match='RELOAD_FAILED'):
        p.deploy(run,sha)
    assert all(p.hashes(root)==journal['before'][c] for c,root in live.items())
    assert json.loads((run/'journal.json').read_text())['state']=='restored'


def test_conflict_refuses_entire_rollback(transaction):
    run,live,journal,sha = transaction
    p.deploy(run,sha)
    journal = json.loads((run/'journal.json').read_text())
    (live['skin']/'1080p/Home.xml').write_text('<window>newer edit</window>')
    before={c:p.hashes(root) for c,root in live.items()}
    with pytest.raises(RuntimeError,match='ROLLBACK_CONFLICT'):
        p.restore(run,journal)
    assert {c:p.hashes(root) for c,root in live.items()} == before


def test_mid_rename_process_death_recover(transaction,monkeypatch):
    run,live,journal,sha = transaction
    replace = p.os.replace
    def die(source,target):
        # Kill after the second component's live -> backup, before stage -> live.
        if str(source).endswith('stage/skin') or str(source).endswith('stage\\skin'):
            raise SystemExit('killed')
        replace(source,target)
    monkeypatch.setattr(p.os,'replace',die)
    # Simulate process death: skip this process's exception rollback.
    original_restore = p.restore
    monkeypatch.setattr(p,'restore',lambda *args: None)
    with pytest.raises(SystemExit):p.deploy(run,sha)
    monkeypatch.setattr(p.os,'replace',replace)
    monkeypatch.setattr(p,'restore',original_restore)
    p.restore(run,json.loads((run/'journal.json').read_text()))
    assert all(p.hashes(root)==journal['before'][c] for c,root in live.items())


def test_drift_before_deploy_no_writes(transaction):
    run,live,journal,sha = transaction
    (live['skin']/'1080p/Home.xml').write_text('<window>other agent</window>')
    with pytest.raises(RuntimeError,match='DEPLOYMENT_BASE_CHANGED'):
        p.deploy(run,sha)
    assert not (run/'backup').exists()


def test_unknown_symlink_and_package_hash_fail_before_switch(transaction):
    run,live,journal,sha = transaction
    with pytest.raises(RuntimeError,match='PACKAGE_CHANGED'):p.deploy(run,'0'*64)
    assert not (run/'backup').exists()


def test_framebuffer_reads_displayed_bgra_with_stride(tmp_path):
    (tmp_path/'stride').write_text('12')
    (tmp_path/'virtual_size').write_text('2,2')
    (tmp_path/'pan').write_text('0,1')
    fb=tmp_path/'fb'
    fb.write_bytes(b'\0'*12 + b'\x01\x02\x03\xff\x04\x05\x06\xff'+b'pad!')
    png=p.framebuffer_png(tmp_path,fb,1)
    import struct
    import zlib
    assert png[:8] == b'\x89PNG\r\n\x1a\n'
    assert struct.unpack('!II',png[16:24]) == (2,1)
    offset=8
    data=b''
    while offset<len(png):
        size=struct.unpack('!I',png[offset:offset+4])[0]
        if png[offset+4:offset+8]==b'IDAT':data+=png[offset+8:offset+8+size]
        offset+=size+12
    assert zlib.decompress(data)==b'\0\x03\x02\x01\xff\x06\x05\x04\xff'


def test_local_package_only_copies_selected_ui(tmp_path,monkeypatch):
    monkeypatch.setitem(sys.modules,'ce_ui_preview_remote',p)
    spec=importlib.util.spec_from_file_location('local_preview',ROOT/'tools/ce_ui_preview.py')
    local=importlib.util.module_from_spec(spec);spec.loader.exec_module(local)
    skin=tmp_path/'addons/skin.bobbi.cinema'
    (skin/'1080p').mkdir(parents=True)
    (skin/'1080p/Home.xml').write_text('<window/>')
    (skin/'addon.xml').write_text('<addon/>')
    (skin/'account.json').write_text('NEVER COPY')
    files=local.package(tmp_path,tmp_path/'test.zip',{'skin':{}},['skin'])
    assert set(files)=={'skin/1080p/Home.xml'}
