"""One real history projection for Home and Personal, with explicit empty/error."""
import ast
from copy import deepcopy
import importlib.util
import json
import os
from pathlib import Path
import pickle
import sys
from types import ModuleType, SimpleNamespace
from urllib.parse import unquote
import xml.etree.ElementTree as ET

import pytest

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT/'addons/plugin.video.bobbi'
SKIN = ROOT/'addons/skin.bobbi.cinema/1080p'


def module_at(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def renderer(monkeypatch):
    contract = module_at('preview_contract', PLUGIN/'lib/cinema/frontend_contract.py')
    calls = SimpleNamespace(rows=[], enriched=[], ended=[], views=[], reads=0)
    state = dict(history={}, failed=False)
    class Database:
        def get_key_checked(self, key):
            calls.reads += 1
            assert key == 'jt:lfh'
            if state['failed']:
                raise OSError('fixture read failure')
            return deepcopy(state['history'])
        def get_key(self, key):
            # Old fallback masks a failed read as an empty initial snapshot.
            return {} if state['failed'] else deepcopy(state['history'])
    class Item:
        def __init__(self, label):
            self.label, self.props, self.art = label, {}, {}
        def setProperty(self, key, value): self.props[key] = value
        def setArt(self, value): self.art.update(value)
        def addContextMenuItems(self, value): self.context = value
    metadata = ModuleType('lib.clients.tmdb.frontend_metadata')
    metadata.apply = lambda item, identifier, kind, display: calls.enriched.append(identifier)
    monkeypatch.setitem(sys.modules, metadata.__name__, metadata)
    source = PLUGIN/'lib/utils/views/continue_watching.py'
    functions = [n for n in ast.parse(source.read_text(encoding='utf-8')).body
                 if isinstance(n, ast.FunctionDef)]
    env = dict(json=json, os=os, unquote=unquote, PickleDatabase=Database,
               clean_title=contract.clean_title, history_rows=contract.history_rows,
               history_digest=contract.history_digest, progress=contract.progress,
               parse_time=lambda row:row[1].get('timestamp',0), ADDON_HANDLE=1,
               ADDON_PATH='plugin', make_list_item=Item, translation=str,
               set_pluging_category=lambda *_:None, setContent=lambda *_:None,
               build_url=lambda action,**params:json.dumps(dict(action=action,**params)),
               add_directory_items_batch=calls.rows.extend,
               end_of_directory=lambda **kw:calls.ended.append(kw),
               apply_section_view=lambda *a,**kw:calls.views.append((a,kw)))
    exec(compile(ast.Module(body=functions,type_ignores=[]),str(source),'exec'),env)
    return env['show_continue_watching'], state, calls


def history(count=12):
    return {str(n):dict(title='Work '+str(n),mode='movie',ids={'tmdb_id':n+1},
                       progress=20+n,completed=False,timestamp=n,direct_cloud_key='fixture')
            for n in range(count)}


def test_preview_is_same_first_record_without_enriching_other_rows_or_next_page(renderer):
    render,state,calls=renderer;state['history']=history();original=deepcopy(state['history'])
    render({});home=calls.rows[0];assert len(calls.rows)==11
    calls.rows.clear();calls.enriched.clear()
    render({'resume_preview':'true','page':'99'})
    assert len(calls.rows)==1 and len(calls.enriched)==1
    item=calls.rows[0]
    assert item[0]==home[0] and item[1].props['PercentPlayed']==home[1].props['PercentPlayed']
    assert item[1].props['Bobi.Resume.State']=='ready'
    assert item[1].props['IsPlayable']=='false' and not item[2]
    assert state['history']==original and calls.reads==2


def test_confirmed_empty_is_an_explicit_nonplayable_preview_status(renderer):
    render,state,calls=renderer
    render({'resume_preview':'true'})
    assert len(calls.rows)==1
    url,item,folder=calls.rows[0]
    assert url=='' and not folder and item.props['Bobi.Resume.State']=='empty'
    assert item.props['IsPlayable']=='false' and not calls.enriched
    calls.rows.clear();render({})
    assert not calls.rows  # Home keeps its genuinely empty rail semantics.


@pytest.mark.parametrize('preview',[False,True])
def test_read_failure_is_not_claimed_as_empty_or_mutated(renderer,preview):
    render,state,calls=renderer;state.update(history=history(),failed=True)
    original=deepcopy(state['history'])
    render({'resume_preview':'true'} if preview else {})
    assert len(calls.rows)==1
    url,item,folder=calls.rows[0]
    assert item.props['Bobi.Resume.State']=='error' and url=='' and not folder
    assert not calls.enriched and state['history']==original
    assert calls.ended==[{'cache':False}]


def test_changed_snapshot_does_not_reuse_previous_preview(renderer):
    render,state,calls=renderer;state['history']=history(2)
    render({'resume_preview':'true'});assert calls.rows[0][1].label=='Work 1'
    calls.rows.clear();state['history']['1']['completed']=True
    render({'resume_preview':'true'});assert calls.rows[0][1].label=='Work 0'
    calls.rows.clear();state['history']={}
    render({'resume_preview':'true'});assert calls.rows[0][1].props['Bobi.Resume.State']=='empty'
    calls.rows.clear();state['history']=history(3)
    render({'resume_preview':'true'});assert calls.rows[0][1].label=='Work 2'


def test_real_database_checked_read_distinguishes_corruption_and_preserves_file(tmp_path,monkeypatch):
    vfs=ModuleType('xbmcvfs');vfs.translatePath=lambda _:str(tmp_path)
    vfs.mkdirs=lambda _:None
    log=ModuleType('lib.jacktook.utils');log.kodilog=lambda _:None
    utils=ModuleType('lib.utils.kodi.utils');utils.ADDON_ID='plugin.video.bobbi'
    for module in (vfs,log,utils):monkeypatch.setitem(sys.modules,module.__name__,module)
    database=module_at('checked_history',PLUGIN/'lib/db/pickle_db.py').PickleDatabase()
    assert database.get_key_checked('jt:lfh')=={}
    target=tmp_path/'database.pickle';target.write_bytes(b'broken fixture')
    before=target.read_bytes()
    with pytest.raises(OSError,match='History unavailable'):database.get_key_checked('jt:lfh')
    assert target.read_bytes()==before
    target.write_bytes(pickle.dumps({'jt:lfh':history(1)}))
    assert database.get_key_checked('jt:lfh')==history(1)


def test_skin_waits_for_item_bound_empty_state_and_preview_uses_shared_route():
    root=ET.parse(SKIN/'Custom_1197_BobiPersonal.xml')
    content=root.find(".//control[@id='9130']/content").text
    assert 'action=continue_watching_menu' in content and 'resume_preview=true' in content
    variables=ET.parse(SKIN/'Includes_Home.xml')
    title=variables.find(".//variable[@name='HubResumeStateTitle']")
    assert title is not None
    entries=[(n.get('condition'),n.text) for n in title.findall('value')]
    assert entries[0][0]=='Container(9130).IsUpdating'
    empty=next(condition for condition,text in entries if text=='还没有在看的影片')
    assert 'Bobi.Resume.State),empty' in empty
    assert entries[-1][0] is None and '读取' in entries[-1][1]
    assert 'HubResumeStateTitle' in ET.tostring(root.getroot(),encoding='unicode')
