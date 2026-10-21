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


@pytest.mark.parametrize('value,expected', [('personal','personal'), ('mine','personal'),
    ('1197','personal'), ('11197','personal'), ('10000','home'), ('library','library'),
    ('10103','keyboard'), ('Keyboard','keyboard')])
def test_window_allowlist_and_custom_id_mapping(value,expected):
    assert p.window_name(value) == expected
    assert p.WINDOWS['personal']['id'] == 10000 + 1197


@pytest.mark.parametrize('value', ['12005','fullscreenvideo','1197,return','Home);PlayMedia(test)',
    'plugin://plugin.video.bobbi/',' personal','personal ', '',None,True,1197])
def test_window_target_rejects_unknown_or_command_input(value):
    with pytest.raises(ValueError,match='INVALID_PREVIEW_WINDOW'):
        p.window_name(value)


def test_navigation_verifies_installed_personal_window_and_stable_observation(tmp_path,monkeypatch):
    skin=tmp_path/'skin'
    (skin/'1080p').mkdir(parents=True)
    (skin/'1080p/Custom_1197_BobiPersonal.xml').write_text('<window id="1197"/>')
    monkeypatch.setattr(p,'LIVE',{'skin':skin})
    home={'currentwindow':{'id':10000}}
    personal={'currentwindow':{'id':11197}}
    states=iter([home,home,personal,personal])
    calls=[]
    monkeypatch.setattr(p,'idle',lambda:next(states))
    monkeypatch.setattr(p.subprocess,'run',lambda args,**kwargs:calls.append(args))
    monkeypatch.setattr(p.time,'sleep',lambda seconds:None)
    target=p.navigate(tmp_path,'mine')
    assert target['id']==11197 and target['name']=='personal'
    assert calls==[['kodi-send','--action=ActivateWindow(1197)']]


def test_missing_personal_window_does_not_send_action(tmp_path,monkeypatch):
    monkeypatch.setattr(p,'LIVE',{'skin':tmp_path})
    monkeypatch.setattr(p,'idle',lambda:{'currentwindow':{'id':10000}})
    monkeypatch.setattr(p.subprocess,'run',lambda *a,**k:pytest.fail('missing UI must not navigate'))
    with pytest.raises(RuntimeError,match='PREVIEW_WINDOW_NOT_INSTALLED'):
        p.navigate(tmp_path,'1197')


def test_navigation_never_interrupts_active_playback(tmp_path,monkeypatch):
    def active():raise RuntimeError('PLAYBACK_ACTIVE')
    monkeypatch.setattr(p,'idle',active)
    monkeypatch.setattr(p.subprocess,'run',lambda *a,**k:pytest.fail('active playback must remain untouched'))
    with pytest.raises(RuntimeError,match='PLAYBACK_ACTIVE'):
        p.navigate(tmp_path,'home')


def test_navigation_wrong_window_times_out_without_screenshot(tmp_path,monkeypatch):
    clock=[0.0]
    monkeypatch.setattr(p.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(p.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    monkeypatch.setattr(p,'idle',lambda:{'currentwindow':{'id':10000}})
    monkeypatch.setattr(p.subprocess,'run',lambda *a,**k:None)
    monkeypatch.setattr(p,'framebuffer_png',lambda:pytest.fail('wrong window must not be captured'))
    with pytest.raises(RuntimeError,match='PREVIEW_WINDOW_NOT_REACHED'):
        p.navigate(tmp_path,'settings')
    assert not list(tmp_path.glob('framebuffer-*'))


def test_library_navigation_requires_exact_root_not_any_video_folder(monkeypatch):
    target=p.WINDOWS['library']
    monkeypatch.setattr(p,'rpc',lambda *a:{'Container.FolderPath':'plugin://plugin.video.bobbi.library/?source=private'})
    assert not p.window_matches({'currentwindow':{'id':10025}},target)
    monkeypatch.setattr(p,'rpc',lambda *a:{'Container.FolderPath':'plugin://plugin.video.bobbi.library/'})
    assert p.window_matches({'currentwindow':{'id':10025}},target)


def test_capture_refuses_window_change_during_frame_read(tmp_path,monkeypatch):
    states=iter([{'currentwindow':{'id':10000}}, {'currentwindow':{'id':11197}}])
    monkeypatch.setattr(p,'idle',lambda:next(states))
    monkeypatch.setattr(p,'framebuffer_png',lambda:b'fixture-frame')
    with pytest.raises(RuntimeError,match='PREVIEW_WINDOW_CHANGED'):
        p.capture(tmp_path,p.WINDOWS['home'])
    assert not list(tmp_path.glob('framebuffer-*'))


def test_navigation_failure_restores_transaction_not_successful_capture(transaction,monkeypatch):
    run,live,journal,sha=transaction
    def fail(*args):raise RuntimeError('PREVIEW_WINDOW_NOT_REACHED')
    monkeypatch.setattr(p,'navigate',fail)
    monkeypatch.setattr(p,'capture',lambda *a:pytest.fail('navigation failure cannot pass screenshot'))
    with pytest.raises(RuntimeError,match='PREVIEW_WINDOW_NOT_REACHED'):
        p.deploy(run,sha,window='personal')
    assert all(p.hashes(root)==journal['before'][c] for c,root in live.items())
    assert json.loads((run/'journal.json').read_text())['state']=='restored'


def test_keyboard_preview_uses_heading_aware_native_api_and_never_reads_text(monkeypatch):
    from types import SimpleNamespace
    calls=[]
    class Keyboard:
        def __init__(self,text,heading,hidden):calls.append((text,heading,hidden))
        def doModal(self,timeout):calls.append(('modal',timeout))
        def getText(self):pytest.fail('preview must not collect entered text')
    monkeypatch.setitem(sys.modules,'xbmc',SimpleNamespace(Keyboard=Keyboard,
        Player=lambda:SimpleNamespace(isPlaying=lambda:False)))
    monkeypatch.setitem(sys.modules,'xbmcgui',SimpleNamespace(getCurrentWindowDialogId=lambda:0))
    exec(compile(p.keyboard_preview_script('波比键盘预览 · 12345678'),'preview-keyboard','exec'),{})
    assert calls==[('','波比键盘预览 · 12345678',False),('modal',45000)]


def test_keyboard_preview_does_not_open_over_another_dialog(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules,'xbmc',SimpleNamespace(
        Keyboard=lambda *a:pytest.fail('must not replace user dialog'),
        Player=lambda:SimpleNamespace(isPlaying=lambda:False)))
    monkeypatch.setitem(sys.modules,'xbmcgui',SimpleNamespace(getCurrentWindowDialogId=lambda:10103))
    exec(compile(p.keyboard_preview_script('preview'),'preview-keyboard','exec'),{})


def test_keyboard_target_requires_its_own_heading(monkeypatch):
    target=dict(p.WINDOWS['keyboard'],heading='波比键盘预览 · 12345678')
    monkeypatch.setattr(p,'rpc',lambda *a:{'Control.GetLabel(311)':''})
    assert not p.window_matches({'currentwindow':{'id':10103}},target)
    monkeypatch.setattr(p,'rpc',lambda *a:{'Control.GetLabel(311)':target['heading']})
    assert p.window_matches({'currentwindow':{'id':10103}},target)


@pytest.mark.parametrize('changed',[False,True])
def test_cli_window_reaches_remote_even_when_ui_is_unchanged(tmp_path,monkeypatch,changed):
    import ast
    from types import ModuleType,SimpleNamespace
    monkeypatch.setitem(sys.modules,'ce_ui_preview_remote',p)
    spec=importlib.util.spec_from_file_location('local_window_preview',ROOT/'tools/ce_ui_preview.py')
    local=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(local)
    for relative in local.COMPONENTS.values():(tmp_path/relative).mkdir(parents=True)
    if changed:
        (tmp_path/'addons/skin.bobbi.cinema/1080p').mkdir()
        (tmp_path/'addons/skin.bobbi.cinema/1080p/Home.xml').write_text('<window/>')
    calls=[]
    class SFTP:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def put(self,*args):pass
    client=SimpleNamespace(close=lambda:None,open_sftp=lambda:SFTP())
    def readonly(client,script,**kwargs):
        source=ast.parse(script.decode('utf-8'))
        mode=ast.literal_eval(source.body[0].value)
        params=ast.literal_eval(source.body[1].value)
        calls.append((mode,params))
        if mode=='status':result={'manifest':{'skin':{},'dialogs':{}}}
        elif mode=='prepare':result={'remote_path':'/fixture/candidate.zip'}
        else:result={'state':'committed'}
        return 0,result,''
    class Loader:
        def create_module(self,spec):return ModuleType(spec.name)
        def exec_module(self,module):module.connect=lambda:(client,SimpleNamespace(readonly=readonly))
    wire_spec=importlib.util.spec_from_loader('preview_wire',Loader())
    monkeypatch.setattr(local.importlib.util,'spec_from_file_location',lambda *a:wire_spec)
    monkeypatch.setattr(sys,'argv',['ce_ui_preview','deploy','--source-root',str(tmp_path),
        '--transport-source',str(tmp_path/'transport'),'--output',str(tmp_path/'evidence'),'--window','mine'])
    assert local.main()==0
    expected_mode='deploy' if changed else 'screenshot'
    assert calls[-1][0]==expected_mode and calls[-1][1]['window']=='personal'


def test_screenshot_mode_can_create_its_own_evidence_directory(tmp_path,monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setitem(sys.modules,'fcntl',SimpleNamespace(flock=lambda *a:None,LOCK_EX=2,LOCK_NB=4))
    monkeypatch.setattr(p,'BASE',tmp_path/'preview')
    monkeypatch.setattr(p,'idle',lambda:{'currentwindow':{'id':10000}})
    monkeypatch.setattr(p,'navigate',lambda run,window:dict(p.WINDOWS[window]))
    monkeypatch.setattr(p,'framebuffer_png',lambda:b'fixture-frame')
    result=p.main('screenshot',{'transaction':'preview-20261021T000000Z-12345678','window':'home'})
    assert Path(result['screenshot']['remote_path']).is_file()
    assert result['screenshot']['window']=={'id':10000}
