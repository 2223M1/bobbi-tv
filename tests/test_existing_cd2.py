"""Existing CD2 file access must neither demand nor fabricate a 115 session."""
from urllib.parse import parse_qs, urlsplit

import pytest

from bobbi_platform import cd2_mounts, cloud_hub, library_ui
from bobbi_platform.libraries import vfs_source
from test_library_ui import context


MOUNT = '/storage/videos/Clouddrive/CloudDrive'


def line(path=MOUNT, filesystem='fuse', source='CloudFS'):
    return '81 29 0:47 / %s rw,nosuid shared:1 - %s %s rw,user_id=0' % (path, filesystem, source)


def test_actual_ce_mount_shape_without_assuming_private_path():
    text = '\n'.join([line(), line('/mnt/My\\040Cloud'), line(),
                      line('/mnt/unrelated', source='OtherFS')])
    assert cd2_mounts.parse_mounts(text) == ('/mnt/My Cloud', MOUNT)


@pytest.mark.parametrize('text', [
    '', 'malformed - fuse CloudFS', line('/'), line('/storage/../private'),
    line('/mnt/tab\\011here'), line('/mnt/newline\\012here'), line('/mnt/pipe|here'),
    line('/mnt/back\\134slash'), line('/mnt/a', filesystem='ext4'),
    line('/mnt/a', source='CloudFS-lookalike'), 'a' * (cd2_mounts.MAX_BYTES + 1),
    '\n'.join(line('/mount%d' % n) for n in range(cd2_mounts.MAX_MOUNTS + 1)),
], ids=('empty', 'malformed', 'root', 'traversal', 'tab', 'newline', 'pipe',
        'backslash', 'not-fuse', 'lookalike', 'oversized', 'too-many'))
def test_invalid_or_unrelated_mounts_are_not_offered(text):
    assert cd2_mounts.parse_mounts(text) == ()


def test_missing_proc_file_does_not_block_other_platforms(monkeypatch):
    def missing(*args, **kwargs):
        raise FileNotFoundError()
    monkeypatch.setattr(cd2_mounts.Path, 'open', missing)
    assert cd2_mounts.discover() == ()


def mounted(context, monkeypatch, paths=(MOUNT,)):
    monkeypatch.setattr(cd2_mounts, 'discover', lambda: paths)
    def forbidden(*args, **kwargs):
        pytest.fail('No credential or mounted-directory IO before navigation')
    context.vfs.File = context.vfs.exists = context.vfs.listdir = forbidden


def test_reuse_creates_only_local_source_and_opens_existing_library(context, monkeypatch):
    mounted(context, monkeypatch)
    assert library_ui.open_existing_cd2(context.dialog) is True
    assert context.shown == []  # One click, no confirmation or success popup.
    source, = context.store.sources()
    assert source.location == MOUNT + '/' and source.name == 'CD2 网盘'
    assert source.username == source.password == ''
    command, = context.builtins
    assert MOUNT not in command and command.startswith('ActivateWindow(Videos,plugin://plugin.video.bobbi.library/')
    params = parse_qs(urlsplit(command.split(',', 2)[1]).query)
    assert params == {'action': ['browse'], 'source': [source.id]}


def test_existing_source_is_not_duplicated_or_overwritten(context, monkeypatch):
    mounted(context, monkeypatch)
    original = vfs_source('我原来的网盘', MOUNT)
    context.store.save(original)
    assert library_ui.open_existing_cd2(context.dialog) is True
    assert library_ui.open_existing_cd2(context.dialog) is True
    assert context.store.sources() == (original,)
    assert len(context.builtins) == 2


def test_cancel_multiple_mount_selection_is_noop(context, monkeypatch):
    mounted(context, monkeypatch, (MOUNT, '/mnt/second'))
    context.selections = [-1]
    assert library_ui.open_existing_cd2(context.dialog) is False
    assert context.store.sources() == () and context.builtins == []


def test_mount_removed_before_navigation_does_not_save(context, monkeypatch):
    mounted(context, monkeypatch)
    calls = iter([(MOUNT,), ()])
    monkeypatch.setattr(cd2_mounts, 'discover', lambda: next(calls))
    assert library_ui.open_existing_cd2(context.dialog) is False
    assert context.store.sources() == () and context.builtins == []
    assert context.shown[-1][0] == 'CD2 挂载已变化'


def test_multiple_mounts_require_choice_and_keep_other_sources(context, monkeypatch):
    mounted(context, monkeypatch, (MOUNT, '/mnt/second'))
    original = vfs_source('CD2 网盘', '/mnt/original')
    context.store.save(original)
    context.selections = [1]
    assert library_ui.open_existing_cd2(context.dialog) is True
    sources = context.store.sources()
    assert original in sources and len(sources) == 2
    selected = next(row for row in sources if row.id != original.id)
    assert selected.location == '/mnt/second/' and selected.name == 'CD2 网盘 2'


def test_add_source_can_use_mount_without_login(context, monkeypatch):
    mounted(context, monkeypatch)
    context.selections = [5]
    assert library_ui.add_source(context.dialog, context.vfs, context.store) is True
    assert context.store.sources()[0].location == MOUNT + '/'
    assert context.builtins == []  # Adding a source does not auto-play or navigate.
    assert len(context.shown) == 1  # Only the source-type menu, no extra popup.


def test_missing_component_does_not_save(context, monkeypatch):
    mounted(context, monkeypatch)
    context.addon = False
    assert library_ui.open_existing_cd2(context.dialog) is False
    assert context.store.sources() == () and context.builtins == []


@pytest.mark.parametrize('authenticated', [False, True, None])
def test_cd2_entry_is_independent_of_share_login_and_closes_parent(context, monkeypatch, authenticated):
    mounted(context, monkeypatch)
    monkeypatch.setattr(cloud_hub, 'status', lambda: dict(authenticated=authenticated,
                       preparation={'state': 'NOT_CONFIGURED'}))
    from bobbi_platform import cloud_ui
    monkeypatch.setattr(cloud_ui, 'login', lambda: pytest.fail('CD2 must not start QR login'))
    context.selections = [0]
    assert cloud_hub.show(context.dialog) is True
    assert len(context.shown) == 1 and '无需扫码' in context.shown[0][1][0]
    assert '115 分享播放' in context.shown[0][1][1]
    assert len(context.builtins) == 1


def test_no_mount_never_claims_cd2_login_or_adds_source(context):
    assert library_ui.open_existing_cd2(context.dialog) is False
    assert context.shown[-1][0] == '未发现 CD2 挂载'
    assert context.store.sources() == () and context.builtins == []


def test_share_login_requirement_remains_explicit():
    text = cloud_hub.cd2_details({'state': 'NOT_CONFIGURED'})
    assert '无需扫码' in text and '分享片源需单独登录一次' in text
