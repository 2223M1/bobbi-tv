"""Real signed files/journal/process loss; persistent Kodi RPC boundary double.

Subprocesses deliberately os._exit, so neither Python finally nor Installer's
exception recovery can conceal a missing durable transaction state.
"""
import json
import os
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'addons/script.module.bobbi.platform/lib'))
from bobbi_platform.ce_installer import Installer, MANAGED, blocked
from bobbi_platform.updates import _atomic


class Host:
    def __init__(self, root, fault=''):
        self.root, self.fault = Path(root), fault
        self.path = self.root / 'host.json'
        self.restore_fail = self.activate_fail = False
        if not self.path.exists():
            _atomic(self.path, dict(enabled=[], skin='skin.before'))

    def read(self): return json.loads(self.path.read_text())
    def write(self, data): _atomic(self.path, data)
    def skin(self): return self.read()['skin']
    def enabled(self): return self.read()['enabled']
    def dependencies(self, stage): pass
    def refresh(self): pass

    def quiesce(self):
        self.write(dict(enabled=[], skin='skin.estuary'))

    def verify(self, versions):
        for name, version in versions.items():
            assert ET.parse(self.root / 'addons' / name / 'addon.xml').getroot().get('version') == version

    def activate(self, versions):
        assert not blocked(self.root / 'work'), 'boot gate must admit verified code before enable'
        if self.activate_fail:
            self.activate_fail = False
            raise RuntimeError('one RPC failure')
        state = self.read()
        for i, name in enumerate(sorted(versions)):
            if name not in state['enabled']:
                state['enabled'].append(name)
            self.write(state)
            if self.fault == 'activate:%d' % i: os._exit(73)

    def restore(self, skin, enabled):
        assert not blocked(self.root / 'work'), 'restored files must boot while host restoration is pending'
        # Exact old CE2009 boot predicate. Using only today's blocked() here
        # would miss rollback-to-old-service compatibility.
        old_journal = json.loads((self.root / 'work/installation.json').read_text())
        assert old_journal['phase'] in ('complete', 'restored'), 'old generation boot gate blocks service'
        if self.restore_fail:
            self.restore_fail = False
            raise RuntimeError('one RPC failure')
        state = self.read()
        for i, name in enumerate(sorted(MANAGED)):
            if name in state['enabled']: state['enabled'].remove(name)
            if name in enabled: state['enabled'].append(name)
            self.write(state)
            if self.fault == 'restore:%d' % i: os._exit(73)
        state['skin'] = skin
        self.write(state)
        if self.fault == 'skin': os._exit(73)


def installer(root, fault=''):
    root = Path(root)
    class FaultInstaller(Installer):
        def _write(self, state):
            super()._write(state)
            if fault == 'phase:' + state['phase'] and not state.get('host_pending'): os._exit(73)
            if fault == 'host:restore' and state.get('host_pending') == 'restore': os._exit(73)
    return FaultInstaller(root / 'addons', root / 'work', Host(root, fault),
                          json.loads((root / 'trust.json').read_text()))


if __name__ == '__main__':
    root, operation, fault = sys.argv[1:]
    actor = installer(root, fault)
    if fault == 'move':
        original = os.replace
        def replace(src, dst):
            original(src, dst)
            if Path(dst).parent == actor.addons: os._exit(73)
        os.replace = replace
    if operation == 'apply': actor.apply(Path(root) / 'two.zip')
    else: actor.rollback()
