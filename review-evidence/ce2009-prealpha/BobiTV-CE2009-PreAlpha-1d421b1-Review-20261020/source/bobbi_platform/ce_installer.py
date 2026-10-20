"""Kodi-local, journalled component installation. Never copies a user profile.

Kodi owns upstream dependencies and enabling/disabling addons. This transaction
only stages signed Bobbi code, with a launch gate until the complete vector is
verified. It is intentionally not the exit-only native UpdateEngine lifecycle.
"""
from contextlib import nullcontext
import json
import os
from pathlib import Path
import shutil
import uuid

from .offline_updates import SignedBundle, load_trust
from .updates import UpdateEngine, UpdateError, _safe_path, _Lock, _atomic, _json
from .upstream_addons import OWNED_COMPONENTS, UPSTREAM_COMPONENTS, compare_versions

ENTRY = 'script.bobbi.start'
MANAGED = OWNED_COMPONENTS - {ENTRY}


def blocked(work):
    path = Path(work) / 'installation.json'
    if not path.exists():
        return False  # Existing legacy install, never adopted/migrated implicitly.
    try:
        value = _json(path.read_bytes())
        return value.get('phase') not in ('complete', 'restored')
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
                or value.get('phase') not in ('staged', 'switching', 'complete', 'restoring', 'restored')
                or type(value.get('sequence')) is not int or value['sequence'] < 1
                or type(value.get('high_watermark', 0)) is not int
                or value.get('high_watermark', 0) < 0):
            raise UpdateError('INSTALLATION_JOURNAL_INVALID')
        return value

    def _restore(self, state):
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
        self.host.refresh()
        state['phase'] = 'restored'
        self._write(state)
        self.host.restore(state.get('previous_skin'), state.get('enabled', []))

    def recover(self):
        with _Lock(self.work / 'installation.lock'):
            state = self._read()
            if state and state['phase'] not in ('complete', 'restored'):
                self.host.quiesce()
                self._restore(state)
                return True
        return False

    def rollback(self):
        with _Lock(self.work / 'installation.lock'):
            state = self._read()
            if not state or state['phase'] != 'complete':
                raise UpdateError('NO_PREVIOUS_PROGRAM_GENERATION')
            state['phase'] = 'restoring'
            self._write(state)
            self.host.quiesce()
            self._restore(state)

    def apply(self, bundle):
        with _Lock(self.work / 'installation.lock'):
            previous = self._read()
            if previous and previous['phase'] not in ('complete', 'restored'):
                raise UpdateError('INSTALLATION_RECOVERY_REQUIRED')
            with SignedBundle(bundle, self.trust, 'coreelec') as signed:
                manifest = signed.check_all()
                watermark = max(previous.get('high_watermark', 0),
                    previous['sequence'] if previous['phase'] == 'complete' else 0) if previous else 0
                if manifest['sequence'] <= watermark:
                    raise UpdateError('GENERATION_NOT_NEWER')
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
                if shutil.disk_usage(self.work).free < sum(r['size'] for r in manifest['components']) * 4:
                    raise UpdateError('INSTALLATION_SPACE_REQUIRED')
                for row in manifest['components']:
                    engine._extract(signed.read(row['file'], row['size']), row, stage)
                # Install absent signed originals without changing existing
                # upstream files/origins. Dependencies persist like Kodi's own
                # dependency installs even if the cinema transaction is rolled back.
                self.host.dependencies(stage)
                items = [dict(id=name, had_old=(self.addons / name).exists()) for name in sorted(MANAGED)]
                state = dict(schema=1, phase='staged', tx=txid, items=items,
                    sequence=manifest['sequence'], high_watermark=watermark, previous_skin=self.host.skin(),
                    enabled=self.host.enabled(), versions={r['id']: r['version'] for r in manifest['components']
                        if r['id'] in MANAGED})
                self._write(state)  # Gate entrypoints before quiescing any code.
                try:
                    self.host.quiesce()
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
                    state['phase'] = 'complete'
                    self._write(state)
                    self.host.activate(state['versions'])
                    state['high_watermark'] = manifest['sequence']
                    self._write(state)
                except BaseException:
                    state['phase'] = 'restoring'
                    self._write(state)
                    self.host.quiesce()
                    self._restore(state)
                    raise
                return manifest
