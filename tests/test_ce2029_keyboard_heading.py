"""Exercise the real product search prompt's native keyboard heading contract."""
import importlib.util
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest

ROOT=Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('section,heading', [('multi','搜索影视'),('tv','搜索电视剧'),
    ('movie','搜索电影'),('anime_tv','搜索动漫'),('anime_movie','搜索动漫电影')])
def test_product_search_passes_nonempty_heading_and_cancel_does_not_navigate(monkeypatch,section,heading):
    calls=[]
    class Keyboard:
        def __init__(self,initial,title):calls.append((initial,title))
        def doModal(self):calls.append('shown')
        def isConfirmed(self):return False
        def getText(self):pytest.fail('cancelled input is not consumed')
    monkeypatch.setitem(sys.modules,'xbmc',SimpleNamespace(Keyboard=Keyboard,
        executebuiltin=lambda *a:pytest.fail('cancelled search must not navigate')))
    for name in ('lib','lib.utils','lib.utils.kodi'):
        if name not in sys.modules:monkeypatch.setitem(sys.modules,name,ModuleType(name))
    utils=ModuleType('lib.utils.kodi.utils')
    utils.get_property=lambda name:''
    utils.set_property=lambda *a:pytest.fail('cancelled search must not persist input')
    monkeypatch.setitem(sys.modules,utils.__name__,utils)
    spec=importlib.util.spec_from_file_location('heading_product_search',
        ROOT/'addons/plugin.video.bobbi/lib/clients/cinema_ui.py')
    product=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(product)
    product.search_prompt({'section':section})
    assert calls==[('',heading),'shown']
