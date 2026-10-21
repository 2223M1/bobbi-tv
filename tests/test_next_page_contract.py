import ast
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT=Path(__file__).resolve().parents[1]
PLUGIN=ROOT/'addons/plugin.video.bobbi/lib'


def function(path,name,namespace):
    tree=ast.parse(path.read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name==name)
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(path),'exec'),namespace)
    return namespace[name]


class Item:
    def __init__(self,label):self.label,self.props=label,{}
    def setProperty(self,k,v):self.props[k]=v
    def setArt(self,value):pass


def test_shared_next_button_preserves_page_and_filters():
    rows=[]
    import os
    ns=dict(make_list_item=Item,os=os,ADDON_PATH='addon',ADDON_HANDLE=1,
        addDirectoryItem=lambda h,url,row,isFolder:rows.append((url,row,isFolder)),
        build_url=lambda action,**params:dict(action=action,**params))
    function(PLUGIN/'utils/general/utils.py','add_next_button',ns)('search',page=2,query='动画')
    url,row,folder=rows[0]
    assert url==dict(action='search',page=3,query='动画') and folder
    assert row.label=='下一页' and row.props=={'Bobi.NextPage':'true'}


@pytest.mark.parametrize('action,page', [('next_page_anime',2),('catalog',3)])
def test_anime_keeps_legacy_current_vs_target_page(action,page):
    rows=[]
    ns=dict(xbmcgui=SimpleNamespace(ListItem=Item),_build_url=lambda action,**params:dict(action=action,**params))
    function(PLUGIN/'clients/tmdb/anime_fast_catalog.py','_add_next_item',ns)(rows,action,2,label='旧标签',query='新番')
    url,row,folder=rows[0]
    assert url==dict(action=action,page=page,query='新番') and folder
    assert row.label=='下一页' and row.props=={'Bobi.NextPage':'true'}


@pytest.mark.parametrize('path', ['utils/views/continue_watching.py','utils/views/last_titles.py',
    'clients/mdblist/mdblist.py','nav/debrid.py'])
def test_remaining_next_row_creators_publish_contract(path):
    tree=ast.parse((PLUGIN/path).read_text(encoding='utf-8'))
    calls=[node for node in ast.walk(tree) if isinstance(node,ast.Call)]
    assert any(isinstance(c.func,ast.Attribute) and c.func.attr=='setProperty'
        and [a.value for a in c.args if isinstance(a,ast.Constant)]==['Bobi.NextPage','true'] for c in calls)
    assert any(isinstance(n,ast.Constant) and n.value=='下一页' for n in ast.walk(tree))
    assert not any(isinstance(n,ast.Constant) and isinstance(n.value,str)
        and n.value.startswith(('Next Page','Next (')) for n in ast.walk(tree))
