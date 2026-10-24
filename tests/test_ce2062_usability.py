"""Small remaining first-use/recovery issues through existing product entrypoints."""
import errno
import ssl
from urllib.error import URLError

import pytest

from test_online_updates import entry, environment, signing, ui, online
from test_library_ui import context
from bobbi_platform import library_ui
from bobbi_platform.updates import UpdateError


@pytest.mark.parametrize('error,expected', [
    (OSError(errno.ENOSPC, 'PRIVATE'), '空间不足'),
    (PermissionError(errno.EACCES, 'PRIVATE'), '写入权限'),
    (URLError(ssl.SSLCertVerificationError('PRIVATE')), '安全连接'),
    (UpdateError('ONLINE_SHORT_READ'), '未下载完整'),
    (UpdateError('ONLINE_CONTENT_INVALID'), '内容不符'),
    (UpdateError('ONLINE_GENERATION_MISMATCH'), '版本不一致'),
    (UpdateError('Offline release signature rejected'), '校验失败'),
])
def test_install_failure_explains_actual_stage_without_echoing_response(entry, monkeypatch, error, expected):
    def fail(*args):
        raise error
    monkeypatch.setattr(online, 'latest', fail)
    ui.main(online=True)
    assert expected in str(entry.dialogs)
    assert 'PRIVATE' not in str(entry.dialogs)
    assert entry.env.calls == [] and entry.commands == []


@pytest.mark.parametrize('playing', [True, False])
def test_return_original_skin_respects_playback_at_final_action(entry, monkeypatch, playing):
    entry.choice = 3
    entry.env.host.details = lambda _: {'version': '0.1.0'}
    entry.playing = playing
    changed = []
    monkeypatch.setattr(ui, 'rpc', lambda method, params: changed.append((method, params)))
    ui.main()
    assert len(changed) == (0 if playing else 1)
    if playing:
        assert '请先停止播放' in str(entry.dialogs)


def test_add_then_open_library_does_not_queue_a_second_refresh(context):
    context.selections = [0, 0, 1]
    context.inputs = ['nas.local/Movies', 'My NAS', '']
    context.confirmations = [True]
    assert library_ui.manage() is True
    assert context.builtins == ['ActivateWindow(Videos,plugin://plugin.video.bobbi.library/,return)']
    assert len(context.store.sources()) == 1


def test_migrate_then_open_library_does_not_queue_a_second_refresh(context):
    context.selections = [1]
    assert library_ui.manage('/storage/videos') is True
    assert context.builtins == ['ActivateWindow(Videos,plugin://plugin.video.bobbi.library/,return)']
    assert len(context.store.sources()) == 1


def test_storage_diagnostic_is_readonly_and_not_an_install_pass(monkeypatch):
    from types import SimpleNamespace
    from bobbi_platform import diagnostics_ui
    monkeypatch.setattr(diagnostics_ui.shutil, 'disk_usage',
                        lambda path: SimpleNamespace(free=123*1024**2, total=900*1024**2))
    result = diagnostics_ui.storage_text('/fixture')
    assert '123 MiB' in result and '安装时会另行计算所需空间' in result
    def failed(path):
        raise OSError('PRIVATE')
    monkeypatch.setattr(diagnostics_ui.shutil, 'disk_usage', failed)
    assert '无法读取' in diagnostics_ui.storage_text('/fixture')
    assert 'PRIVATE' not in diagnostics_ui.storage_text('/fixture')
