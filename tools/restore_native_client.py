"""Restore the complete client behind measured host capabilities, not OS names."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from prepare_candidate import rename

ROOT = Path(__file__).resolve().parents[1]
REV = 'ff530e09c34c6285ccb05c1d4179140b097174fb'
SOURCE = 'ui-redesign/backend/source/addons/plugin.video.jacktook/'


def restore(repo):
    target = ROOT / 'addons/plugin.video.bobbi/lib'
    stock = target / 'stock_player.py'
    if stock.exists():
        raise ValueError('One-time migration already applied')
    stock.write_bytes((target / 'player.py').read_bytes())
    records = []
    for name, dest in [('lib/player.py', target / 'native_player.py'),
                       ('lib/gui/source_select.py', target / 'gui/source_select.py')]:
        raw = subprocess.check_output(['git', '-C', str(repo), 'show', REV + ':' + SOURCE + name])
        text = rename(raw.decode('utf-8-sig'))
        if name.endswith('source_select.py'):
            text = text.replace('    def doModal(self) -> bool:\n',
                '    def doModal(self) -> bool:\n'
                '        from lib.native_support import available\n'
                '        self._native_owner = available()\n'
                '        if not self._native_owner:\n'
                '            from lib.portable import manual_modal\n'
                '            return manual_modal(self, lambda: super(SourceSelect, self).doModal())\n', 1)
            text = text.replace('        if not pack_select and not is_subtitle_download:\n',
                '        if not getattr(self, "_native_owner", False):\n'
                '            from lib.portable import queue_selected\n'
                '            return queue_selected(self, selected_source, pack_select, is_subtitle_download, local_subtitle_path)\n'
                '        if not pack_select and not is_subtitle_download:\n', 1)
            # Manual opening never schedules a preferred source on a timer.
            text = text.replace("self._auto_select_pending = self.item_information.get('auto_select_sources') is True",
                                'self._auto_select_pending = False  # Manual source selection is product policy.')
        dest.write_text(text, encoding='utf-8')
        records.append(dict(source=SOURCE + name, source_sha256=hashlib.sha256(raw).hexdigest(),
                            target=dest.relative_to(ROOT).as_posix(), sha256=hashlib.sha256(text.encode()).hexdigest()))
    (ROOT / 'release/native-client-integration.json').write_text(json.dumps(dict(commit=REV, files=records), indent=2) + '\n', encoding='utf-8')
    print('Restored complete native client, with stock fallback retained separately.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, required=True)
    restore(parser.parse_args().source)
