"""Real catalog composition; replace Kodi/transport, not candidate or review logic."""
from frozen_history import source_bytes
import ast
import builtins
from copy import deepcopy
import hashlib
import importlib
import json
from pathlib import Path
import subprocess
import sys
from types import ModuleType, SimpleNamespace

import pytest

from bobbi_platform import catalog_ui, runtime
from bobbi_platform.paths import ProfileBinding
from test_architecture_boundaries import imports
from test_catalog_ui_profile_admission import ui
from test_media_library_index import ref, scope

ROOT = Path(__file__).resolve().parents[1]
BASELINE = '1eb2e58b668916b950d332337486109184c48a18'
PLATFORM_UI = 'addons/script.module.bobbi.platform/lib/bobbi_platform/catalog_ui.py'
PERSONAL_UI = 'addons/plugin.video.bobbi/lib/utils/views/personal_catalog.py'
SCOPES = [
    scope(),
    dict(reference_kind='mounted_path', source_id='a' * 32, namespace='b' * 64, generation=''),
    dict(reference_kind='local_path', source_id='a' * 32, namespace='b' * 64, generation=''),
    dict(reference_kind='network_path', source_id='a' * 32, namespace='b' * 64, generation='c' * 64),
    dict(reference_kind='network_path', source_id='a' * 32, namespace='b' * 64, generation='d' * 64),
    dict(scope(provider='plex', epoch=0), source_id='a' * 32, generation='c' * 64),
]


def frozen_source(path):
    return source_bytes(BASELINE, path)


@pytest.fixture(scope='module')
def frozen_personal():
    # Execute the complete original module, not reconstructed/hash-lookalike helpers.
    module = ModuleType('frozen_catalog_route_contract')
    exec(compile(frozen_source(PERSONAL_UI), BASELINE + ':' + PERSONAL_UI, 'exec'), module.__dict__)
    return module


@pytest.mark.parametrize('expected', SCOPES, ids=['native', 'mounted', 'local', 'network', 'network-rebound', 'server'])
@pytest.mark.parametrize('query', [
    dict(mode='review', view=None, source_id=None),
    dict(view='files', text='特别篇 & café / 第 0 集', parent_entity_id='a:b', cursor=None),
    dict(view='works', text='', sort='name', offset=0, enabled=False),
])
def test_saved_route_hash_and_url_bytes_match_frozen_owner(frozen_personal, expected, query):
    from bobbi_platform import catalog_routes
    assert catalog_routes.scope_key(expected).encode('ascii') == frozen_personal.scope_key(expected).encode('ascii')
    assert list(catalog_routes.scope_params(expected).items()) == list(frozen_personal.scope_params(expected).items())
    actual = catalog_routes.route(action='personal_catalog', **catalog_routes.scope_params(expected), **query)
    frozen = frozen_personal.route(action='personal_catalog', **frozen_personal.scope_params(expected), **query)
    assert actual.encode('utf-8') == frozen.encode('utf-8')
    assert 'None' not in actual


def test_personal_compatibility_exports_are_same_functions(ui):
    from bobbi_platform import catalog_routes
    assert ui.catalog is importlib.import_module('lib.utils.views.personal_catalog')
    for name in ('route', 'scope_key', 'scope_params'):
        assert getattr(ui.catalog, name) is getattr(catalog_routes, name)
    assert catalog_routes.scope_key(SCOPES[3]) != catalog_routes.scope_key(SCOPES[4])


def test_platform_navigation_runs_with_all_plugin_imports_denied(frozen_personal, tmp_path):
    query = dict(view='files', text='特别篇 & café', cursor=None)
    commands = ['ActivateWindow(Videos,"' + frozen_personal.route(
        action='personal_catalog', **frozen_personal.scope_params(expected), **query) + '",return)'
        for expected in SCOPES]
    commands.append('ActivateWindow(Videos,"' + frozen_personal.route(
        action='personal_catalog', **frozen_personal.scope_params(scope(provider='uc')), mode='review') + '",return)')
    script = r'''
import importlib.abc, json, sys
from types import SimpleNamespace
class DenyPlugin(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        assert fullname.split('.')[0] != 'lib', 'Unexpected plugin import: ' + fullname
sys.meta_path.insert(0, DenyPlugin())
sys.path[:0] = sys.argv[1:4]
scopes, query, expected_commands = json.loads(sys.argv[5])
events, prompts, calls = [], [], []
dialog = SimpleNamespace(select=lambda title, labels: prompts.append((title, labels)) or 1,
                         ok=lambda *args: (_ for _ in ()).throw(AssertionError(args)))
sys.modules['xbmc'] = SimpleNamespace(executebuiltin=events.append)
sys.modules['xbmcgui'] = SimpleNamespace(Dialog=lambda: dialog)
sys.modules['xbmcvfs'] = SimpleNamespace(translatePath=lambda path: sys.argv[4] + '/' + path.rsplit('/', 1)[-1])
from bobbi_platform import catalog_routes, catalog_ui, pan_ui
from bobbi_platform.pan_accounts import NAMES, empty_scope
for expected in scopes:
    catalog_ui._open_catalog(expected, **query)
def rpc(action, body, **options):
    calls.append((action, body))
    assert action == 'pan_status' and body == {}
    rows = []
    for provider in NAMES:
        account = empty_scope(provider)
        if provider in ('quark', 'uc'):
            account.update(account_id=provider + ':' + 'a' * 64, epoch=1, authenticated=True)
        rows.append(dict(provider=provider, account=account, capabilities=['list_files']))
    return dict(providers=rows)
pan_ui.call = rpc
catalog_ui.manage()
assert events == expected_commands, (events, expected_commands)
assert len(prompts) == 1 and len(prompts[0][1]) == 2
assert calls == [('pan_status', {})]
assert not any(name == 'lib' or name.startswith('lib.') for name in sys.modules)
'''
    result = subprocess.run([sys.executable, '-I', '-c', script,
        str(ROOT / 'addons/script.module.bobbi.core/lib'),
        str(ROOT / 'addons/script.module.bobbi.platform/lib'),
        str(ROOT / 'addons/plugin.video.bobbi'), str(tmp_path),
        json.dumps([SCOPES, query, commands])], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr


def test_actual_frozen_ui_is_negative_control_for_same_architecture_detector():
    frozen = frozen_source(PLATFORM_UI)
    assert hashlib.sha1(b'blob ' + str(len(frozen)).encode('ascii') + b'\0' + frozen).hexdigest() == (
        '3affd35c1eea60d7235999f7c09bf9828a907a46')
    forbidden = lambda source: {name for name in imports(ast.parse(source)) if name.split('.')[0] == 'lib'}
    assert forbidden(frozen.decode('utf-8-sig')) == {
        'lib.clients.tmdb.catalog_candidates',
        'lib.utils.views.personal_catalog',
        'lib.clients.stremio.manage_phone',
    }
    assert forbidden((ROOT / PLATFORM_UI).read_text(encoding='utf-8-sig')) == set()


def test_review_context_retains_real_binding_and_two_element_contract(ui):
    context = catalog_ui._review_context(ui.expected)
    assert isinstance(context, tuple) and len(context) == 2
    binding, invoke = context
    assert isinstance(binding, ProfileBinding)
    assert invoke('catalog_item', file_id=ui.extra['id']) == ui.item
    assert ui.bindings == ['A']
    ui.active = 'B'
    before = len(ui.calls)
    with pytest.raises(ValueError, match='PROFILE_CHANGED'):
        invoke('catalog_item', file_id=ui.extra['id'])
    assert len(ui.calls) == before


@pytest.fixture
def candidates(ui, monkeypatch):
    """Extend the shared admission fixture with real grouped SQLite reads."""
    ui.fetches, ui.multi, ui.confirmations, ui.candidate_cards = [], [], [], []
    ui.cancelled = False
    monkeypatch.setattr(sys.modules['xbmc'], 'Monitor',
                        lambda: SimpleNamespace(abortRequested=lambda: ui.cancelled), raising=False)

    class ListItem:
        def __init__(self, *, label):
            self.label, self.art = label, {}
            ui.candidate_cards.append(self)

        def setArt(self, art):
            self.art.update(art)

    monkeypatch.setattr(sys.modules['xbmcgui'], 'ListItem', ListItem, raising=False)

    def fetch(endpoint, params):
        ui.fetches.append((endpoint, deepcopy(params)))
        return dict(results=[dict(media_type='person', id=7, name='Not a work'),
            dict(media_type='tv', id=123, name='Show', original_name='Original Show',
                 first_air_date='2020-01-01', poster_path='/safe.jpg')])

    # This is the existing metadata transport seam, not a replacement search/mapping adapter.
    monkeypatch.setitem(sys.modules, 'lib.clients.tmdb.utils.utils', SimpleNamespace(tmdb_get=fetch))
    ui.candidate_tools = importlib.import_module('lib.clients.tmdb.catalog_candidates')
    assert Path(ui.candidate_tools.__file__).resolve() == (
        ROOT / 'addons/plugin.video.bobbi/lib/clients/tmdb/catalog_candidates.py').resolve()
    original_bind = runtime.bind_call

    def bind(path):
        profile = Path(path).parent.parent.name
        original = original_bind(path)

        def invoke(action, body, **options):
            if action == 'catalog_group':
                ui.calls.append((profile, action, deepcopy(body)))
                return ui.indexes[profile].group(**body)
            return original(action, body, **options)
        return invoke

    monkeypatch.setattr(runtime, 'bind_call', bind)

    def seed(count):
        ui.files = [ref(number + 101, name='Show.2020.S00E%03d.mkv' % (number + 1), parent='tv-folder')
                    for number in range(count)]
        for index in ui.indexes.values():
            task = index.start('a' * 32, ui.expected)
            index.begin(task)
            for offset in range(0, count, 20):
                batch = ui.files[offset:offset + 20]
                index.batch(task, batch, dict(page=offset // 20 + 1), len(batch))
            index.finish(task, 'completed')
        ui.params['object_id'] = ui.files[0]['id']

    ui.seed = seed

    def multiselect(title, labels, preselect):
        ui.multi.append((title, labels, preselect))
        return preselect

    def yesno(title, message):
        ui.confirmations.append(title)
        return title not in ('需要逐项调整季集？', '继续整理本剧？')

    ui.dialog.multiselect, ui.dialog.yesno = multiselect, yesno
    return ui


def applied(ui):
    return [body for _, action, body in ui.calls if action == 'catalog_apply']


def test_personal_manage_search_mapping_and_real_preview_apply(candidates):
    state = candidates
    state.seed(1)
    state.choices, state.inputs = [0, 0], ['Show']
    result = state.catalog.manage(state.params)
    assert result['complete'] and result['saved'] == 1
    assert state.fetches == [('search_multi', dict(query='Show', page=1))]
    assert len(state.candidate_cards) == 1
    assert 'Original Show' in state.candidate_cards[0].label
    assert state.candidate_cards[0].art == {'thumb': 'https://image.tmdb.org/t/p/w185/safe.jpg'}
    saved = state.indexes['A'].item(state.expected, state.files[0]['id'])
    assert saved['mapping'] == dict(kind='tv', title='Show', tmdb_id=123, season=0, episode=1, version=None)
    assert saved['revision'] == 1
    assert state.indexes['B'].item(state.expected, state.files[0]['id'])['revision'] == 0
    assert state.views[0][0] == '逐项预览（尚未保存）'
    assert 'S00E01' in state.views[0][1]
    assert state.views[-1][0] == '真实回执 · 已保存 1/1'
    assert state.bindings == ['A'] and all(profile == 'A' for profile, _, _ in state.calls)
    assert state.builtins == ['Container.Refresh'] and not state.messages


@pytest.mark.parametrize('cancel_at', ['candidate', 'confirmation'])
def test_candidate_selection_or_confirmation_cancel_never_writes(candidates, cancel_at):
    state = candidates
    state.seed(1)
    state.choices, state.inputs = [0, -1 if cancel_at == 'candidate' else 0], ['Show']
    state.dialog.yesno = lambda title, message: state.confirmations.append(title) or False
    state.catalog.manage(state.params)
    assert state.fetches and not applied(state)
    assert not state.choices and not state.inputs and not state.messages
    previews = [body for _, action, body in state.calls if action == 'catalog_preview']
    if cancel_at == 'candidate':
        assert not previews and not state.confirmations and not state.views
    else:
        assert len(previews) == 1 and state.confirmations == ['确认分批保存？']
        assert state.views[0][0] == '逐项预览（尚未保存）'
    assert all(index.item(state.expected, state.files[0]['id'])['revision'] == 0 for index in state.indexes.values())
    assert not state.builtins


def test_single_item_continuation_keeps_candidate_adapter_for_group(candidates):
    state = candidates
    state.seed(2)
    state.choices, state.inputs = [0, 0], ['Show']
    state.dialog.yesno = lambda title, message: title != '需要逐项调整季集？'
    result = state.catalog.manage(state.params)
    assert result['saved'] == 1  # The entry still returns its original single-item receipt.
    assert [len(body['commands']) for body in applied(state)] == [1, 2]
    assert [state.indexes['A'].item(state.expected, row['id'])['revision'] for row in state.files] == [2, 1]
    assert len(state.fetches) == 1 and len(state.multi) == 1
    assert not state.messages


@pytest.mark.parametrize('skip_first', [False, True])
def test_group_round_recursion_preserves_adapter_and_original_profile(candidates, skip_first):
    state = candidates
    state.seed(101)
    state.choices, state.inputs = [6, 0], ['Show']
    original_multi = state.dialog.multiselect

    def multiselect(title, labels, preselect):
        result = original_multi(title, labels, preselect)
        return [] if skip_first and len(state.multi) == 1 else result

    state.dialog.multiselect = multiselect
    result = state.catalog.manage(state.params)
    assert result['complete'] and result['saved'] == 1
    assert [len(labels) for _, labels, _ in state.multi] == [100, 1]
    assert [len(body['commands']) for body in applied(state)] == ([1] if skip_first else [5] * 20 + [1])
    revisions = [state.indexes['A'].item(state.expected, row['id'])['revision'] for row in state.files]
    assert sum(revisions) == (1 if skip_first else 101)
    if skip_first:
        assert [row['id'] for row, revision in zip(state.files, revisions) if revision] == [
            max(row['id'] for row in state.files)]
    else:
        assert revisions == [1] * 101
    assert all(state.indexes['B'].item(state.expected, row['id'])['revision'] == 0 for row in state.files)
    assert state.bindings == ['A'] and all(profile == 'A' for profile, _, _ in state.calls)
    assert len(state.fetches) == 1 and not state.messages


@pytest.mark.parametrize('choice', [0, 6])
@pytest.mark.parametrize('adapter', [None, SimpleNamespace(search=lambda *args: {})], ids=['missing', 'incomplete'])
def test_missing_candidate_capability_is_local_and_does_not_write(ui, choice, adapter):
    ui.choices = [choice]
    catalog_ui.review_item(ui.dialog, ui.expected, ui.item, candidate_tools=adapter)
    assert ui.messages[0][0] == '候选搜索暂不可用'
    assert not ui.calls and not ui.views and not ui.builtins
    assert all(index.item(ui.expected, ui.extra['id'])['revision'] == 0 for index in ui.indexes.values())


def test_missing_candidate_adapter_keeps_file_inspection_and_manual_tv_mapping(ui):
    ui.choices = [1]
    catalog_ui.review_item(ui.dialog, ui.expected, ui.item)
    assert ui.messages[0][0] == '原文件与建议' and not ui.calls
    ui.choices, ui.inputs = [5, 2], ['人工特别篇', '123', '0', '4']
    result = catalog_ui.review_item(ui.dialog, ui.expected, ui.item)
    assert result['complete'] and result['saved'] == 1
    assert ui.indexes['A'].item(ui.expected, ui.extra['id'])['mapping'] == dict(
        kind='tv', title='人工特别篇', tmdb_id=123, season=0, episode=4, version=None)
    assert ui.indexes['B'].item(ui.expected, ui.extra['id'])['revision'] == 0


@pytest.mark.parametrize('manual', [False, True])
def test_personal_candidate_import_failure_only_disables_candidate_choices(ui, monkeypatch, manual):
    original_import = builtins.__import__
    attempts = []

    def without_candidates(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'lib.clients.tmdb' and 'catalog_candidates' in fromlist:
            attempts.append(name)
            raise ImportError('Optional candidate adapter unavailable')
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, '__import__', without_candidates)
    ui.choices, ui.inputs = ([5, 0], ['手工名称']) if manual else ([0], [])
    result = ui.catalog.manage(ui.params)
    assert attempts == ['lib.clients.tmdb'] and ui.bindings == ['A']
    if manual:
        assert result['complete'] and result['saved'] == 1
        assert ui.indexes['A'].item(ui.expected, ui.extra['id'])['mapping']['title'] == '手工名称'
        assert ui.builtins == ['Container.Refresh'] and not ui.messages
    else:
        assert result is None and ui.messages[0][0] == '候选搜索暂不可用'
        assert not applied(ui) and not ui.builtins
    assert ui.indexes['B'].item(ui.expected, ui.extra['id'])['revision'] == 0


def test_missing_phone_launcher_does_not_grant_or_read_or_write(ui):
    ui.choices = [2]
    catalog_ui.manage_scope(ui.expected)
    assert ui.messages[0][0] == '手机管理暂不可用'
    assert not ui.calls and not ui.views and not ui.builtins
    assert ui.bindings == ['A']  # Admission only; no second phone-session binding.


def test_personal_phone_import_failure_is_local_before_any_approval_or_grant(ui, monkeypatch):
    original_import = builtins.__import__
    attempts = []

    def without_phone(name, globals=None, locals=None, fromlist=(), level=0):
        if name == 'lib.clients.stremio.manage_phone':
            attempts.append(name)
            raise ImportError('Optional phone component unavailable')
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, '__import__', without_phone)
    ui.dialog.yesno = lambda *args, **kwargs: pytest.fail('Unavailable phone component requested approval')
    ui.choices = [2]
    result = ui.catalog.manage(ui.catalog.scope_params(ui.expected))
    assert result is None and attempts == ['lib.clients.stremio.manage_phone']
    assert not ui.choices and ui.messages[0][0] == '手机管理暂不可用'
    assert '未创建授权' in ui.messages[0][1]
    assert ui.bindings == ['A']  # No PhoneManagement construction/second profile binding.
    assert [(profile, action, body) for profile, action, body in ui.calls] == [('A', 'pan_status', {})]
    assert not applied(ui) and not ui.views and not ui.builtins
    assert all(index.item(ui.expected, ui.extra['id'])['revision'] == 0 for index in ui.indexes.values())


@pytest.mark.parametrize('kind', ['native', 'mounted_path', 'local_path', 'network_path'])
@pytest.mark.parametrize('approved', [False, True])
def test_personal_manage_phone_uses_real_launcher_grant_and_scope(ui, monkeypatch, kind, approved):
    events, managers, prompts = [], [], []
    expected = ui.expected if kind == 'native' else dict(
        reference_kind=kind, source_id='a' * 32, namespace='b' * 64, generation='c' * 64)
    original_bind = runtime.bind_call

    def bind(path):
        original = original_bind(path)

        def rpc(action, body, **options):
            if action == 'catalog_network_scope':
                ui.calls.append((Path(path).parent.parent.name, action, deepcopy(body)))
                assert body == dict(source_id=expected['source_id'])
                return deepcopy(expected)
            return original(action, body, **options)
        return rpc

    monkeypatch.setattr(runtime, 'bind_call', bind)

    class Server:
        is_running = True

        def __init__(self, *, port, phone_management):
            assert port == 8081
            managers.append(phone_management)
            self.manager = phone_management

        def start(self):
            events.append('start')

        def stop(self):
            events.append('stop')
            # Model the server boundary's cleanup; the actual revoke method stays real.
            self.manager.revoke()

    qr = SimpleNamespace(setup=lambda **options: events.append('setup'),
                         doModal=lambda: events.append('modal'))
    modules = {
        'lib.gui.qr_progress_dialog': SimpleNamespace(QRProgressDialog=lambda *args: qr),
        'lib.services.webserver': SimpleNamespace(StremioWebServer=Server, get_local_ip=lambda: '127.0.0.1'),
        'lib.utils.debrid.qrcode_utils': SimpleNamespace(make_qrcode=lambda value: ''),
        'lib.utils.kodi.utils': SimpleNamespace(ADDON_PATH='', kodilog=lambda *args: None, translation=lambda value: value),
    }
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)
    # Do not reuse another test's launcher globals; exercise the canonical lazy import.
    # Recording a temporary sentinel also restores an originally absent module
    # after the real import below; delitem(..., raising=False) alone cannot do so.
    monkeypatch.setitem(sys.modules, 'lib.clients.stremio.manage_phone', None)
    monkeypatch.delitem(sys.modules, 'lib.clients.stremio.manage_phone')
    parent = importlib.import_module('lib.clients.stremio')
    monkeypatch.setattr(parent, 'manage_phone', None, raising=False)
    monkeypatch.delattr(parent, 'manage_phone')

    def confirm(title, message):
        prompts.append((title, message))
        return approved

    ui.dialog.yesno = confirm
    ui.choices = [2, 0] if kind == 'native' and approved else [2]
    params = ui.catalog.scope_params(expected)
    assert ui.catalog.manage(params) is approved
    assert prompts[0][0] == '允许手机管理当前片库？'
    assert not applied(ui) and not ui.messages
    if not approved:
        assert not managers and not events and ui.bindings == ['A']
        return
    from lib.services.phone_management import PhoneManagement, SCOPES as PHONE_SCOPES
    manager = managers[0]
    assert type(manager) is PhoneManagement and manager.scopes == PHONE_SCOPES
    normalized = dict(expected)
    if kind in ('mounted_path', 'local_path'):
        normalized['generation'] = ''
    assert manager.expected == normalized
    assert isinstance(manager.profile_binding, ProfileBinding)
    assert ui.bindings == ['A', 'A']
    assert events == ['start', 'setup', 'modal', 'stop'] and manager.revoked.is_set()
    if kind != 'native':
        assert expected['source_id'] in prompts[0][1] and expected['namespace'] in prompts[0][1]
