"""Accepted standard-player history belongs to the writer's captured profile."""
import ast
from datetime import datetime
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
from urllib.parse import unquote

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def case(tmp_path, monkeypatch):
    active = {'root': tmp_path / 'A'}
    monkeypatch.syspath_prepend(str(ROOT / 'addons/plugin.video.bobbi'))
    monkeypatch.setitem(sys.modules, 'lib.jacktook.utils', SimpleNamespace(kodilog=lambda *args: None))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(
        translatePath=lambda _: str(active['root']),
        mkdirs=lambda root: Path(root).mkdir(parents=True, exist_ok=True)))
    monkeypatch.setitem(sys.modules, 'lib.utils.kodi.utils', SimpleNamespace(ADDON_ID='plugin.video.bobbi'))
    storage = load('standard_profile_storage', 'addons/plugin.video.bobbi/lib/db/pickle_db.py')
    monkeypatch.setitem(sys.modules, 'lib.db.pickle_db', storage)
    subject = load('standard_profile_subject', 'addons/plugin.video.bobbi/lib/services/standard_playback.py')

    class DeferredThread:
        def __init__(self, target, **kwargs):
            self.target, self.finished = target, False

        def start(self):
            pass

        def join(self):
            if not self.finished:
                self.finished = True
                self.target()

    monkeypatch.setattr(subject, 'Thread', DeferredThread)
    writers, reports = [], []

    def writer():
        result = subject.HistoryWriter(reports.append)
        writers.append(result)
        return result

    def activate(name):
        active['root'] = tmp_path / name
        # The product imports this module in the worker on its first save.
        # Execute the actual function body, including its legacy default DB,
        # while isolating unrelated Kodi/provider imports.
        path = ROOT / 'addons/plugin.video.bobbi/lib/utils/general/utils.py'
        tree = ast.parse(path.read_text(encoding='utf-8'))
        function = next(node for node in tree.body if isinstance(node, ast.FunctionDef)
                        and node.name == 'set_watched_file')
        namespace = dict(pickle_db=storage.PickleDatabase(), unquote=unquote, datetime=datetime,
            get_random_color=lambda *args, **kwargs: 'white',
            IndexerType=SimpleNamespace(DIRECT='direct', STREMIO_DEBRID='stremio'))
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(path), 'exec'), namespace)
        monkeypatch.setitem(sys.modules, 'lib.utils.general.utils', SimpleNamespace(
            set_watched_file=namespace['set_watched_file']))

    def rows(name):
        return storage.PickleDatabase(profile_root=tmp_path/name).get_key('jt:lfh')

    activate('A')
    yield SimpleNamespace(writer=writer, activate=activate, rows=rows, reports=reports, root=tmp_path)
    for item in writers:
        item.close()


@pytest.mark.parametrize('submit_after_switch', [False, True], ids=['queued-before-switch', 'late-old-owner'])
def test_old_writer_never_puts_accepted_history_in_new_profile(case, submit_after_switch):
    writer = case.writer()
    data = dict(title='Profile A movie', current_time=42, completed=False)
    if not submit_after_switch:
        writer.save(data)
    case.activate('B')
    if submit_after_switch:
        writer.save(data)
    writer.close()
    assert writer.accepted == writer.completed == 1
    assert writer.failed == 0 and not case.reports
    assert [row['current_time'] for row in case.rows('A').values()] == [42]
    assert case.rows('B') == {}


def test_each_profile_writer_keeps_its_own_target_when_drained_in_reverse(case):
    a = case.writer()
    a.save(dict(title='A movie', current_time=11))
    case.activate('B')
    b = case.writer()
    b.save(dict(title='B movie', current_time=22))
    case.activate('A')
    b.close()
    a.close()
    assert [row['current_time'] for row in case.rows('A').values()] == [11]
    assert [row['current_time'] for row in case.rows('B').values()] == [22]
    assert not case.reports


def test_same_profile_history_still_drains_and_snapshots_input(case):
    writer = case.writer()
    data = dict(title='A movie', current_time=12)
    writer.save(data)
    data['current_time'] = 99
    writer.close()
    assert [row['current_time'] for row in case.rows('A').values()] == [12]
    assert writer.accepted == writer.completed == 1 and writer.failed == 0
