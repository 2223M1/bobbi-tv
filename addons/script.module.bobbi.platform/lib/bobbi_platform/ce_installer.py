"""Kodi-local, journalled component installation. Never copies a user profile.

Kodi owns upstream dependencies and enabling/disabling addons. This transaction
only stages signed Bobbi code, with a launch gate until the complete vector is
verified. It is intentionally not the exit-only native UpdateEngine lifecycle.
"""
from contextlib import nullcontext
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import uuid

from .offline_updates import SignedBundle, load_trust
from .updates import UpdateEngine, UpdateError, _safe_path, _Lock, _atomic, _json
from .upstream_addons import OWNED_COMPONENTS, UPSTREAM_COMPONENTS, compare_versions
from .ce_storage import install_plan, require_space, RESERVE

ENTRY = 'script.bobbi.start'
MANAGED = OWNED_COMPONENTS - {ENTRY}
# A verified file vector may boot while its idempotent Kodi operations are
# pending. This is deliberately different from a completed transaction.
RUNNABLE = ('activation_pending', 'restore_pending', 'complete', 'restored')


def program_tree(path):
    """Bounded receipt of code bytes, paths and modes, not account data.

    Generated CPython bytecode is not a program source. Still inspect its
    entry types: symlinks/special files are never silently ignored.
    """
    path = _safe_path(path)
    if not path.is_dir():
        raise UpdateError('PREVIOUS_PROGRAM_INCOMPLETE')
    digest, count, total = hashlib.sha256(), 0, 0
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in sorted(dirs + files):
            item = Path(root) / name
            info = item.lstat()
            if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                raise UpdateError('PREVIOUS_PROGRAM_SPECIAL_FILE')
            relative = item.relative_to(path)
            count += 1
            total += info.st_size if stat.S_ISREG(info.st_mode) else 0
            if count > 100000 or total > 4 * 1024**3:
                raise UpdateError('PREVIOUS_PROGRAM_LIMIT')
            if '__pycache__' in relative.parts and (item.is_dir() or item.suffix == '.pyc'):
                continue
            digest.update(json.dumps([relative.as_posix(), stat.S_IMODE(info.st_mode),
                'dir' if item.is_dir() else info.st_size], separators=(',', ':')).encode())
            if item.is_file():
                with item.open('rb') as stream:
                    for block in iter(lambda: stream.read(1024*1024), b''):
                        digest.update(block)
        dirs.sort()
    return digest.hexdigest()


class PlaybackActive(UpdateError):
    """Host refusal before any quiesce effects; never used after draining starts."""


def blocked(work):
    path = Path(work) / 'installation.json'
    if not path.exists():
        return False  # Existing legacy install, never adopted/migrated implicitly.
    try:
        value = _json(path.read_bytes())
        return value.get('phase') not in RUNNABLE
    except (OSError, ValueError, UpdateError):
        return True


class Installer:
    def __init__(self, addons, work, host, trust=None):
        self.addons, self.work = _safe_path(addons), _safe_path(work)
        self.host, self.trust = host, trust or load_trust()
        self.work.mkdir(parents=True, exist_ok=True)
        self.addons.mkdir(parents=True, exist_ok=True)
        if (self.work == self.addons or self.addons in self.work.parents
                or self.work in self.addons.parents or self.work.stat().st_dev != self.addons.stat().st_dev):
            raise UpdateError('INSTALLATION_PATHS_INVALID')
        self.state = self.work / 'installation.json'

    def _write(self, state):
        _atomic(self.state, state)

    def _read(self):
        if not self.state.exists():
            return None
        if self.state.stat().st_size > 1024 * 1024:
            raise UpdateError('INSTALLATION_JOURNAL_INVALID')
        value = _json(self.state.read_bytes())
        import re
        if (not isinstance(value, dict) or not re.fullmatch('[0-9a-f]{32}', str(value.get('tx', '')))
                or not isinstance(value.get('items'), list)
                or any(not isinstance(row, dict) or row.get('id') not in MANAGED
                       or type(row.get('had_old')) is not bool for row in value['items'])
                or len({row['id'] for row in value['items']}) != len(value['items'])
                or value.get('schema') != 1
                or value.get('phase') not in ('staged', 'switching', 'restoring') + RUNNABLE
                or (value.get('host_pending') is not None
                    and (value['host_pending'] != 'restore' or value['phase'] != 'restored'))
                or type(value.get('sequence')) is not int or value['sequence'] < 1
                or type(value.get('high_watermark', 0)) is not int
                or value.get('high_watermark', 0) < 0):
            raise UpdateError('INSTALLATION_JOURNAL_INVALID')
        return value

    def _restore(self, state):
        self._restore_preflight(state)
        tx = _safe_path(self.work / state['tx'])
        abandoned = tx / 'abandoned'
        abandoned.mkdir(exist_ok=True)
        for row in reversed(state['items']):
            name = row['id']
            live, old, staged = (self.addons / name, tx / 'backup' / name, tx / 'stage' / name)
            for path in (live, old, staged):
                _safe_path(path)
            # Moves, not deletion: interrupted or failed code stays recoverable.
            if old.exists():
                if live.exists():
                    os.replace(live, abandoned / (name + '-' + uuid.uuid4().hex))
                os.replace(old, live)
            elif not row['had_old'] and not staged.exists() and live.exists():
                os.replace(live, abandoned / (name + '-' + uuid.uuid4().hex))
        self._restore_preflight(state)
        if any(not row['had_old'] and (self.addons / row['id']).exists() for row in state['items']):
            raise UpdateError('PREVIOUS_PROGRAM_INCOMPLETE')
        # All original paths are back before opening the boot gate. A crash
        # or RPC failure from here on resumes host state, never repeats moves.
        # CE2009's restored service only understands complete/restored. Expose
        # its verified FILE state using that compatible phase, but retain the
        # unfinished host operation independently. The new entry bootstrap
        # remains installed and must honor host_pending on every reopening.
        state.update(phase='restored', host_pending='restore')
        self._write(state)
        self._finish_restore(state)

    def _restore_preflight(self, state):
        # Complete-vector check BEFORE quiesce or any move. On re-entry, a
        # missing backup is acceptable only when live is already the exact old
        # vector (including the process-loss gap immediately after a move).
        for row in state['items']:
            backup = _safe_path(self.work / state['tx'] / 'backup' / row['id'])
            if not row['had_old']:
                if backup.exists():
                    raise UpdateError('PREVIOUS_PROGRAM_INCOMPLETE')
                continue
            receipt = row.get('old_tree')
            if not isinstance(receipt, str) or len(receipt) != 64:
                raise UpdateError('PREVIOUS_PROGRAM_RECEIPT_REQUIRED')
            source = backup if backup.exists() else self.addons / row['id']
            if program_tree(source) != receipt:
                raise UpdateError('PREVIOUS_PROGRAM_INCOMPLETE')

    def _finish_restore(self, state):
        if state['phase'] == 'restore_pending':  # Intermediate CE2010 journal.
            state.update(phase='restored', host_pending='restore')
            self._write(state)
        self.host.refresh()
        self.host.restore(state.get('previous_skin'), state.get('enabled', []))
        if (set(self.host.enabled()) != set(state.get('enabled', []))
                or (state.get('previous_skin') and self.host.skin() != state['previous_skin'])):
            raise UpdateError('HOST_RESTORE_NOT_CONFIRMED')
        state['phase'] = 'restored'
        state.pop('host_pending', None)
        self._write(state)

    def _activate(self, state):
        self.host.activate(state['versions'])
        if not set(state['versions']).issubset(self.host.enabled()):
            raise UpdateError('HOST_ACTIVATION_NOT_CONFIRMED')
        state['phase'] = 'complete'
        self._write(state)
        from .ce_recovery import record_transaction
        try:
            record_transaction(self, state)
        except (OSError, ValueError, UpdateError):
            pass  # Missing retirement proof means protected, never disposable.

    def _check_idle(self):
        # New Kodi hosts reject known active playback before a completed
        # generation is replaced by a pending journal. Older host adapters
        # retain quiesce as their authoritative, mandatory replacement barrier.
        check = getattr(self.host, 'check_idle', None)
        if check is not None:
            check()

    def _undo_unstarted_journal(self, previous, state):
        # Only the typed, pre-effect quiesce refusal may reopen the old gate.
        # Keep the rejected attempt for diagnosis, including on first install.
        target = _safe_path(self.work / state['tx'] / ('refused-' + uuid.uuid4().hex + '.json'))
        _atomic(target, state)
        if previous is None:
            os.replace(self.state, target)
        else:
            self._write(previous)

    def recover(self):
        with _Lock(self.work / 'installation.lock'):
            state = self._read()
            if state and (state.get('host_pending') or state['phase'] not in ('complete', 'restored')):
                if state['phase'] == 'activation_pending':
                    self.host.refresh()
                    self.host.verify(state['versions'])
                    self._activate(state)
                elif state['phase'] == 'restore_pending' or state.get('host_pending') == 'restore':
                    self._finish_restore(state)
                else:
                    self._restore_preflight(state)
                    self.host.quiesce()
                    state['phase'] = 'restoring'
                    self._write(state)
                    self._restore(state)
                return True
        return False

    def rollback(self):
        with _Lock(self.work / 'installation.lock'):
            state = self._read()
            if not state or state['phase'] not in ('complete', 'activation_pending'):
                raise UpdateError('NO_PREVIOUS_PROGRAM_GENERATION')
            self._check_idle()
            self._restore_preflight(state)
            previous = dict(state)
            state['phase'] = 'restoring'
            self._write(state)
            try:
                self.host.quiesce()
            except PlaybackActive:
                self._undo_unstarted_journal(previous, state)
                raise
            self._restore(state)

    def plan_space(self, bundle):
        """Read-only preview; apply repeats it under its own transaction lock."""
        with _Lock(self.work / 'installation.lock'):
            previous = self._read()
            if previous and (previous.get('host_pending') or previous['phase'] not in ('complete', 'restored')):
                raise UpdateError('INSTALLATION_RECOVERY_REQUIRED')
            self._check_idle()
            with SignedBundle(bundle, self.trust, 'coreelec') as signed:
                signed.check_all()
                return install_plan(signed, self.addons, self.work, previous, MANAGED)

    def saved_generations(self):
        from .ce_recovery import RecoveryStore
        with _Lock(self.work / 'installation.lock'):
            state = self._read()
            if state and (state.get('host_pending') or state['phase'] not in ('complete', 'restored')):
                raise UpdateError('INSTALLATION_RECOVERY_REQUIRED')
            return RecoveryStore(self.work, self.trust).list()

    def restore_saved(self, name):
        from .ce_recovery import RecoveryStore
        # The private apply path repeats validation under the transaction lock.
        return self._apply(RecoveryStore(self.work, self.trust).path(name), restoring=True)

    def apply(self, bundle):
        return self._apply(bundle)

    def _apply(self, bundle, restoring=False):
        with _Lock(self.work / 'installation.lock'):
            previous = self._read()
            if previous and (previous.get('host_pending') or previous['phase'] not in ('complete', 'restored')):
                raise UpdateError('INSTALLATION_RECOVERY_REQUIRED')
            self._check_idle()
            with SignedBundle(bundle, self.trust, 'coreelec') as signed:
                manifest = signed.check_all()
                watermark = max(previous.get('high_watermark', 0),
                    previous['sequence'] if previous['phase'] == 'complete' else 0) if previous else 0
                if restoring:
                    from .ce_recovery import RecoveryStore
                    store = RecoveryStore(self.work, self.trust)
                    point = store.inspect(Path(bundle).name)
                    if not previous or point['sequence'] > watermark or store.path(point['name']) != Path(bundle):
                        raise UpdateError('RECOVERY_POINT_INVALID')
                elif manifest['sequence'] <= watermark:
                    raise UpdateError('GENERATION_NOT_NEWER')
                space = install_plan(signed, self.addons, self.work, previous, MANAGED)
                require_space(space)  # Refuse before creating an orphan transaction.
                txid = uuid.uuid4().hex
                tx = self.work / txid
                stage, backup = tx / 'stage', tx / 'backup'
                stage.mkdir(parents=True)
                backup.mkdir()
                # Reuse the existing archive parser (paths, file budgets, XML
                # identity, hashes); do not reuse its exclusive-host apply API.
                engine = UpdateEngine(self.addons, tx / 'validator', self.trust['components'],
                    'private-candidate', 'coreelec', lambda *_: False, lambda *_: None,
                    lambda: False, nullcontext, offline=True)
                for row in manifest['components']:
                    engine._extract(signed.read(row['file'], row['size']), row, stage)
                # Install absent signed originals without changing existing
                # upstream files/origins. Dependencies persist like Kodi's own
                # dependency installs even if the cinema transaction is rolled back.
                self.host.dependencies(stage)
                free = shutil.disk_usage(self.work).free
                require_space(dict(space, phase='after-dependencies', required_bytes=RESERVE,
                                   free_bytes=free, fits=free >= RESERVE))
                items = [dict(id=name, had_old=(self.addons / name).exists()) for name in sorted(MANAGED)]
                for item in items:
                    if item['had_old']:
                        item['old_tree'] = program_tree(self.addons / item['id'])
                state = dict(schema=1, phase='staged', tx=txid, items=items,
                    sequence=manifest['sequence'], high_watermark=watermark, previous_skin=self.host.skin(),
                    enabled=self.host.enabled(), versions={r['id']: r['version'] for r in manifest['components']
                        if r['id'] in MANAGED})
                if previous:
                    state['previous_tx'] = previous['tx']
                # Archive/dependency preparation can outlast the initial idle
                # observation. Recheck before replacing the previous journal;
                # quiesce still owns the final guarded replacement barrier.
                self._check_idle()
                self._write(state)  # Gate entrypoints before quiescing any code.
                quiesced = False
                try:
                    self.host.quiesce()
                    quiesced = True
                    self._restore_preflight(state)
                    state['phase'] = 'switching'
                    self._write(state)
                    for row in items:
                        name = row['id']
                        live = _safe_path(self.addons / name)
                        if row['had_old']:
                            os.replace(live, backup / name)
                        os.replace(stage / name, live)
                    self.host.refresh()
                    self.host.verify(state['versions'])
                    state['phase'] = 'activation_pending'
                    # The verified generation can now start; retain the high
                    # watermark even if activation or a later rollback fails.
                    state['high_watermark'] = max(watermark, manifest['sequence'])
                    self._write(state)
                except BaseException as error:
                    if isinstance(error, PlaybackActive) and not quiesced:
                        self._undo_unstarted_journal(previous, state)
                        raise
                    state['phase'] = 'restoring'
                    self._write(state)
                    self.host.quiesce()
                    self._restore(state)
                    raise
                # Transient RPC failure keeps activation pending, not a falsely
                # complete install or an unnecessary destructive swap-back.
                self._activate(state)
                # Optional complete-package retention cannot undo a successful
                # install. Original one-step rollback remains independent.
                from .ce_recovery import RecoveryStore
                import zipfile
                try:
                    state['recovery_archive'] = RecoveryStore(self.work, self.trust).remember(
                        signed, protected=((previous.get('recovery_archive') or {}).get('name'),) if previous else ())
                except (OSError, ValueError, UpdateError, zipfile.BadZipFile):
                    state['recovery_archive'] = dict(saved=False, reason='unavailable')
                self._write(state)
                return manifest
