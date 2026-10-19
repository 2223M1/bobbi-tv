"""Journalled v1 userdata migration, shared by startup and offline tooling."""
from contextlib import closing, contextmanager, ExitStack
import fcntl
import json
import os
from pathlib import Path
import shutil
import sqlite3
import time

from .data_paths import LOCATIONS, relative_path, LayoutError, LAYOUT_MARKER
from .storage import write_json

UPGRADE_STATE = 'config/layout-upgrade-v1.json'

def plan(profile):
    profile = Path(profile)
    names = set(LOCATIONS)
    for path in profile.iterdir():
        if path.name.endswith(('.lock', '.sock', '.flag')) or path.name.startswith('codex-resident'):
            names.add(path.name)
    moves = [(profile / name, profile / relative_path(name)) for name in names]
    for path in profile.glob('codebuddy-*.json'):
        if path.name.startswith('codebuddy-auth-'):
            continue
        moves.append((path, profile / 'diagnostics/codebuddy' / path.name))
    old_backup = profile / 'components/codex-test-backups'
    moves.append((old_backup, profile / 'diagnostics/backups/codex'))
    # Move a specifically classified child (ASR diagnostics) before its parent.
    moves = sorted(set(moves), key=lambda pair: (-len(pair[0].parts), str(pair[0])))
    result = []
    for source, destination in moves:
        if source == destination or not (source.exists() or source.is_symlink()):
            continue
        if source.is_symlink():
            raise ValueError('迁移源不能是符号链接：' + source.name)
        if destination.exists() or destination.is_symlink():
            raise ValueError('迁移目标已存在，请先检查：' + str(destination.relative_to(profile)))
        result.append((source, destination))
    return result


def _project_key(path):
    return str(path).replace('/', '-').lstrip('-')


def _fix_codex(profile, backup):
    database = profile / LOCATIONS['codex-home'] / 'state_5.sqlite'
    if not database.is_file():
        return 0
    saved = backup / 'codex-state.sqlite'
    changes = 0
    temporary = backup / 'codex-state.sqlite.tmp'
    with closing(sqlite3.connect(str(database), timeout=5)) as connection:
        with closing(sqlite3.connect(str(temporary))) as copy:
            connection.backup(copy)
        temporary.chmod(0o600)
        os.replace(temporary, saved)
        columns = {'threads': ('rollout_path', 'cwd', 'agent_path'),
                   'rollout_migration_skipped_rollouts': ('rollout_path',),
                   'project_roots': ('path',)}
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for table, candidates in columns.items():
            if table not in tables:
                continue
            present = {row[1] for row in connection.execute('PRAGMA table_info("' + table + '")')}
            for column in set(candidates) & present:
                for name in ('codex-home', 'codex-work'):
                    old, new = str(profile / name), str(profile / LOCATIONS[name])
                    query = ('UPDATE "{0}" SET "{1}" = ? || substr("{1}", ?) '
                             'WHERE "{1}" = ? OR substr("{1}",1,?) = ?').format(table, column)
                    cursor = connection.execute(query, (new, len(old) + 1, old, len(old) + 1, old + '/'))
                    changes += cursor.rowcount
        connection.commit()
        connection.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    return changes


def migrate(profile, backup):
    profile, backup = Path(profile), Path(backup)
    moves = plan(profile)  # Validate every destination before moving anything.
    backup.mkdir(mode=0o700, parents=True, exist_ok=False)
    journal = {'phase': 'moving', 'profile': str(profile.resolve()), 'moves': [], 'codex_paths_updated': 0}
    record = backup / 'journal.json'
    write_json(record, journal)

    def move(source, destination):
        destination.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        # Journal intent first; rollback also handles an interrupted rename.
        journal['moves'].append([str(source), str(destination)])
        write_json(record, journal)
        source.rename(destination)

    try:
        for source, destination in moves:
            move(source, destination)
        for region, old_home, old_work in (('external', 'codebuddy-home', 'codebuddy-work'),
                                            ('internal', 'codebuddy-home-internal', 'codebuddy-work-internal')):
            projects = profile / LOCATIONS[old_home] / 'projects'
            source = projects / _project_key(profile / old_work)
            destination = projects / _project_key(profile / LOCATIONS[old_work])
            if source.is_dir():
                if destination.exists():
                    raise ValueError('CodeBuddy 目标会话目录已存在：' + region)
                move(source, destination)
        if any(Path(old) == profile / 'codex-home' for old, new in journal['moves']):
            journal['codex_paths_updated'] = _fix_codex(profile, backup)
        journal['phase'] = 'done'
        write_json(record, journal)
        return {'moved': len(journal['moves']), 'codex_paths_updated': journal['codex_paths_updated']}
    except BaseException:
        rollback(backup, profile)
        raise


def rollback(backup, profile=None):
    backup = Path(backup)
    record = backup / 'journal.json'
    journal = json.loads(record.read_text())
    if profile is not None:
        _validate_journal(Path(profile), journal)
    for old, new in reversed(journal['moves']):
        source, destination = Path(new), Path(old)
        if source.exists() or source.is_symlink():
            if destination.exists() or destination.is_symlink():
                raise ValueError('回滚目标已存在：' + destination.name)
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            source.rename(destination)
    saved = backup / 'codex-state.sqlite'
    if saved.exists():
        home = next(Path(old) for old, new in journal['moves'] if Path(old).name == 'codex-home')
        database = home / 'state_5.sqlite'
        for suffix in ('-wal', '-shm'):
            Path(str(database) + suffix).unlink(missing_ok=True)
        shutil.copy2(saved, database)
    journal['phase'] = 'rolled_back'
    write_json(record, journal)


def _validate_journal(profile, journal):
    if not isinstance(journal, dict) or not isinstance(journal.get('moves'), list):
        raise ValueError('迁移日志无效，已停止自动恢复。')
    base = profile.resolve()
    for pair in journal['moves']:
        if not isinstance(pair, list) or len(pair) != 2:
            raise ValueError('迁移日志无效，已停止自动恢复。')
        for name in pair:
            if not isinstance(name, str) or not Path(name).is_absolute():
                raise ValueError('迁移日志包含无效路径。')
            try:
                Path(name).resolve().relative_to(base)
            except ValueError:
                raise ValueError('迁移日志路径超出插件数据目录，已停止自动恢复。') from None


def _cancelled(cancelled):
    if cancelled():
        raise InterruptedError('已取消升级数据迁移。')


def _lock(handle, deadline, cancelled):
    while True:
        _cancelled(cancelled)
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except BlockingIOError:
            if time.monotonic() >= deadline:
                raise LayoutError('旧版语音助手仍在运行，请先关闭当前弹窗，再重新启动插件以完成升级。') from None
            time.sleep(.05)


def _native_busy(profile):
    # A crashed old service may have left a native child using its database.
    # Never terminate an unrelated process or rename a live agent's HOME.
    work = {str(profile / name) for name in ('codex-work', 'codebuddy-work', 'codebuddy-work-internal')}
    work.update(str(profile / LOCATIONS[name]) for name in ('codex-work', 'codebuddy-work', 'codebuddy-work-internal'))
    proc = Path('/proc')
    if not proc.is_dir():
        return False
    for row in proc.iterdir():
        if row.name.isdigit():
            try:
                if os.readlink(row / 'cwd') in work:
                    return True
            except OSError:
                pass
    return False


@contextmanager
def _quiescent(profile, deadline, cancelled, stop_service):
    with ExitStack() as handles:
        # Refuse an active dialogue before asking any service to stop.
        for directory in (profile, profile / 'runtime'):
            for name in ('invocation.lock', 'capture.lock', 'conversation.lock'):
                path = directory / name
                if not path.is_file():
                    continue
                handle = handles.enter_context(path.open('a'))
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    raise LayoutError('请先关闭当前语音助手弹窗，再重新启动插件以完成升级数据迁移。') from None
        for directory in (profile, profile / 'runtime'):
            path = directory / 'cmcc-service.lock'
            if not path.is_file():
                continue
            handle = handles.enter_context(path.open('a'))
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                if not stop_service:
                    raise LayoutError('旧版语音服务仍在运行，请重新启动 Kodi 以完成升级数据迁移。') from None
                stop = directory / 'cmcc-stop.flag'
                created = not stop.exists()
                if created:
                    stop.touch(exist_ok=False)
                try:
                    _lock(handle, deadline, cancelled)
                finally:
                    if created:
                        stop.unlink(missing_ok=True)
        for directory in (profile, profile / 'runtime'):
            for name in ('codebuddy-account.lock', 'codebuddy-owner.lock', 'codex-resident.lock', 'components.lock'):
                path = directory / name
                if path.is_file():
                    _lock(handles.enter_context(path.open('a')), deadline, cancelled)
        if _native_busy(profile):
            raise LayoutError('旧版智能体仍在使用登录或会话数据，请先退出旧版助手，再重新启动插件完成升级。')
        _cancelled(cancelled)
        yield


def _backup_from_state(profile):
    path = profile / UPGRADE_STATE
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text())
    except (ValueError, UnicodeError):
        raise ValueError('升级迁移状态文件无效，已停止自动恢复。') from None
    if not isinstance(state, dict) or not isinstance(state.get('backup'), str):
        raise ValueError('升级迁移状态无效，已停止自动恢复。')
    relative = Path(state['backup'])
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('升级迁移备份路径无效。')
    backup = profile / relative
    try:
        backup.resolve().relative_to(profile.resolve() / 'diagnostics')
    except ValueError:
        raise ValueError('升级迁移备份路径无效。') from None
    return backup


def _complete(profile, result, backup=None):
    write_json(profile / LAYOUT_MARKER, dict(result, version=1, completed_at=time.time(),
        backup=str(backup.relative_to(profile)) if backup else None))
    (profile / UPGRADE_STATE).unlink(missing_ok=True)


def ensure(profile, cancelled=lambda: False, timeout=30, stop_service=False):
    """Serialize first-start upgrade, recover interrupted moves, then mark done."""
    profile = Path(profile).resolve()
    directory = profile / 'runtime'
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    try:
        with (directory / 'layout-migration.lock').open('a') as lock:
            _lock(lock, deadline, cancelled)
            if (profile / LAYOUT_MARKER).is_file():
                return False
            backup = _backup_from_state(profile)
            if backup and (backup / 'journal.json').exists():
                with _quiescent(profile, deadline, cancelled, stop_service):
                    journal = json.loads((backup / 'journal.json').read_text())
                    _validate_journal(profile, journal)
                    if journal.get('phase') == 'done':
                        _complete(profile, {'moved': len(journal['moves']),
                                           'codex_paths_updated': journal.get('codex_paths_updated', 0)}, backup)
                        return True
                    if journal.get('phase') in ('moving', 'rolled_back'):
                        rollback(backup, profile)
                    else:
                        raise ValueError('升级迁移日志状态无效，已停止自动恢复。')
                (profile / UPGRADE_STATE).unlink(missing_ok=True)
            if not plan(profile):
                _complete(profile, {'moved': 0})
                return False
            with _quiescent(profile, deadline, cancelled, stop_service):
                # Recheck after an old service has closed and removed its sockets.
                moves = plan(profile)
                if not moves:
                    _complete(profile, {'moved': 0})
                    return False
                backup = profile / 'diagnostics' / ('layout-upgrade-v1-' + str(time.time_ns()))
                write_json(profile / UPGRADE_STATE, {'backup': str(backup.relative_to(profile))})
                result = migrate(profile, backup)
                _complete(profile, result, backup)
                return True
    except (InterruptedError, LayoutError):
        raise
    except (OSError, ValueError, sqlite3.Error) as error:
        detail = str(error) if isinstance(error, ValueError) else '请检查数据目录是否可写、存储空间及迁移备份。'
        raise LayoutError('升级数据迁移未完成，已停止启动，已有数据仍保留。\n' + detail) from None

