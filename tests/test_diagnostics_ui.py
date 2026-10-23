"""Actual menu/preview/export code, without starting a player or any network IO."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'addons/script.module.bobbi.core/lib'))
from bobbi_core import search_trace
from bobbi_platform import diagnostics_ui


@pytest.fixture
def screen(tmp_path, monkeypatch):
    from bobbi_platform import paths
    state = SimpleNamespace(choices=[], dialogs=[], previews=[], files=[], choose_folder=str(tmp_path/'out'),
                            confirm=True, written=True)
    monkeypatch.setattr(search_trace, '_sink', None)
    monkeypatch.setattr(paths, 'profile', lambda *args: tmp_path)
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(
        Monitor=lambda: SimpleNamespace(abortRequested=lambda: False)))
    class File:
        def __init__(self, path, mode):
            state.files.append(path)
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            self.stream = Path(path).open('xb')
        def write(self, raw):
            return self.stream.write(raw) if state.written is True else state.written
        def close(self): self.stream.close()
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(
        exists=lambda path: Path(path).exists(), File=File))
    state.dialog = SimpleNamespace(
        select=lambda title, choices: state.choices.pop(0),
        ok=lambda *args: state.dialogs.append(args),
        yesno=lambda *args: state.confirm,
        textviewer=lambda *args: state.previews.append(args),
        browse=lambda *args: state.choose_folder)
    state.root = tmp_path
    return state


def record(root):
    search_trace.set_enabled(root, True)
    search_trace.configure(root, 'a'*32)
    search_trace.observe('visible', [])
    search_trace.observe_providers('a'*32, {'juku:1': dict(state='PARTIAL', count=2,
        completion=dict(planned=2, succeeded=1, failed=0, timed_out=1, stale=1,
                        truncated=1, snapshot_age=7200))})


def test_menu_enables_and_disables_without_export_or_other_effects(screen):
    screen.choices = [1, 1, -1]
    diagnostics_ui.show(screen.dialog)
    assert not search_trace.enabled(screen.root)
    assert not screen.files and not screen.previews
    assert '已开启' in screen.dialogs[0][0] and '已关闭' in screen.dialogs[1][0]


def test_preview_explains_incomplete_queries_and_stale_snapshot(screen):
    record(screen.root)
    screen.choices = [2, 0, -1]
    diagnostics_ui.show(screen.dialog)
    text = screen.previews[0][1]
    assert '超时 1' in text and '120 分钟' in text and '尚未搜遍' in text
    assert '查询失败不等于没有资源' in text and '不是播放成功证明' in text
    assert not screen.files


@pytest.mark.parametrize('cancel_at', ['selector', 'confirmation', 'folder'])
def test_cancel_export_at_any_user_boundary_creates_nothing(screen, cancel_at):
    record(screen.root)
    screen.confirm = cancel_at != 'confirmation'
    if cancel_at == 'folder': screen.choose_folder = ''
    screen.choices = [3, -1 if cancel_at == 'selector' else 0, -1]
    diagnostics_ui.show(screen.dialog)
    assert not screen.files


def test_export_is_explicit_and_matches_the_sanitized_preview(screen):
    record(screen.root)
    expected = search_trace.read_report(search_trace.reports(screen.root)[0])
    screen.choices = [3, 0, -1]
    diagnostics_ui.show(screen.dialog)
    assert len(screen.files) == 1 and screen.previews
    assert json.loads(Path(screen.files[0]).read_bytes()) == expected
    assert '诊断已保存' in screen.dialogs[-1][0]
    assert 'invocation' not in Path(screen.files[0]).read_text()


@pytest.mark.parametrize('written', [False, None, 0, 1])
def test_failed_export_never_claims_saved(screen, written):
    record(screen.root)
    screen.written = written
    screen.choices = [3, 0, -1]
    diagnostics_ui.show(screen.dialog)
    assert '诊断暂不可用' in screen.dialogs[-1][0]
    assert '诊断已保存' not in str(screen.dialogs)


def test_clear_requires_confirmation_and_preserves_other_files(screen):
    record(screen.root)
    (screen.root/'config.json').write_text('KEEP')
    screen.confirm = False
    screen.choices = [4, -1]
    diagnostics_ui.show(screen.dialog)
    assert search_trace.reports(screen.root)
    screen.confirm = True
    screen.choices = [4, -1]
    diagnostics_ui.show(screen.dialog)
    assert not search_trace.reports(screen.root) and not search_trace.enabled(screen.root)
    assert (screen.root/'config.json').read_text() == 'KEEP'


def test_full_report_quota_has_a_user_recovery_path(screen):
    search_trace.set_enabled(screen.root, True)
    for index in range(8): search_trace.configure(screen.root, format(index, '032x'))
    search_trace.set_enabled(screen.root, False)
    screen.choices = [1, 4, 1, -1]
    diagnostics_ui.show(screen.dialog)
    assert '记录已满' in screen.dialogs[0][0]
    assert search_trace.enabled(screen.root) and not search_trace.reports(screen.root)
