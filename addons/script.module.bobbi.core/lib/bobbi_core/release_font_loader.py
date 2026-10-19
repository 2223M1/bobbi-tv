"""Exact-release font IO on the existing preparation lane, never a daemon.

The same metadata selector, cloud mapper and pinned 7-Zip child are reused.
Outputs remain candidates; this module cannot write the ledger or native Fonts.
"""
import hashlib
import json
from itertools import islice
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

from bobbi_core.cloud_mapping import map_torrent_file
from bobbi_core.font_archive import release_assets, EXPANSION_LIMIT, FONT_LIMIT
from bobbi_core.font_cache import safe_directory
from bobbi_core.font_extract_worker import TOOL_HASH
from bobbi_core.fonts import inspect_font_file, select_fonts


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


class ReleaseFontLoader:
    def __init__(self, provider, qualifier, root, tool, allowed):
        self.provider, self.qualifier = provider, qualifier
        self.root, self.tool = safe_directory(root), Path(tool)
        self.allowed = allowed

    def _guard(self):
        if self.allowed() is not True:
            raise InterruptedError('Font work paused for playback or shutdown')

    def _download(self, item, target):
        self._guard()
        url = self.qualifier.download_url(self.provider, item)
        started, checked, count = time.monotonic(), 0.0, 0
        result = hashlib.sha256()
        with self.provider.session.get(url, stream=True, allow_redirects=False, timeout=(3.05, 8),
                headers={'Accept-Encoding': 'identity'}) as response:
            if response.status_code != 200:
                raise ValueError('Font source did not return complete bytes')
            with target.open('xb') as stream:
                for chunk in response.iter_content(65536):
                    now = time.monotonic()
                    if now - started >= 40 or count + len(chunk) > item['bytes']:
                        raise ValueError('Font source byte/time budget')
                    if now - checked >= .5:
                        self._guard()
                        checked = now
                    stream.write(chunk)
                    result.update(chunk)
                    count += len(chunk)
                stream.flush()
                os.fsync(stream.fileno())
        if count != item['bytes']:
            raise ValueError('Font source truncated')
        return result.hexdigest()

    def _decode(self, archive, sha256, output):
        self._guard()
        if (any(p.is_symlink() for p in (self.tool, *self.tool.parents))
                or not self.tool.is_file() or self.tool.stat().st_size > 4*1024*1024
                or digest(self.tool) != TOOL_HASH):
            raise ValueError('Pinned archive helper changed')
        worker = Path(__file__).with_name('font_extract_worker.py')
        argv = [sys.executable, '-B', str(worker), '--tool', str(self.tool), '--archive', str(archive),
                '--sha256', sha256, '--output', str(output)]
        with output.with_suffix('.stdout').open('xb') as out, output.with_suffix('.stderr').open('xb') as err:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                       start_new_session=True)
            started = time.monotonic()
            try:
                while process.poll() is None:
                    self._guard()
                    if time.monotonic() - started >= 40:
                        raise TimeoutError('Font decoder wall budget')
                    try:
                        process.wait(timeout=.2)
                    except subprocess.TimeoutExpired:
                        pass
            except BaseException:
                # The worker and its 7-Zip child belong to this private session.
                # Kill only that group, not unrelated decoders or Kodi.
                import signal
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
                raise
            if process.returncode:
                raise ValueError('Font decoder rejected archive')
        report = output/'result.json'
        if report.is_symlink() or report.stat().st_size > 2*1024*1024:
            raise ValueError('Font decoder report budget')
        result = json.loads(report.read_bytes())
        if (result.get('state') != 'EXTRACTED_FONTS_NOT_BOUND_OR_LOADED'
                or result.get('archive_sha256') != sha256 or result.get('tool_sha256') != TOOL_HASH
                or not 1 <= len(result.get('fonts', [])) <= 128):
            raise ValueError('Incomplete font decoder evidence')
        fonts = []
        for candidate in result['fonts']:
            self._guard()
            path = Path(candidate['path'])
            if (output/'unpacked').resolve() not in path.resolve().parents or path.stat().st_size > FONT_LIMIT:
                raise ValueError('Decoder output outside private extraction root')
            actual = inspect_font_file(path)
            if any(actual[key] != candidate.get(key) for key in actual):
                raise ValueError('Font decoder metadata differs from actual bytes')
            fonts.append(dict(actual, path=str(path), origin='same_release_pack'))
        self._guard()
        return fonts

    def perform(self, plan):
        """No cloud mutation and no manual, title-specific source fallback."""
        self._guard()
        assets = release_assets(plan['video'], plan['metadata'])
        if not assets:
            return dict(state='NO_RELEASE_FONT_ASSETS', fonts=[], evidence=[])
        if (shutil.disk_usage(self.root).free < 512*1024*1024
                or len(list(islice(self.root.iterdir(), 64))) >= 64):
            raise ValueError('Font workspace capacity; preserve old diagnostics')
        work = self.root/uuid4().hex
        work.mkdir(mode=0o700)
        evidence, fonts = [], []
        try:
            if self.provider.account_scope() != plan['account']:
                raise ValueError('Font cloud account changed')
            tasks = [row for row in self.provider.offline_tasks(plan['destination'])
                     if row['info_hash'] == plan['video']['selected']['source_info_hash']]
            prior = plan['observation']
            if (len(tasks) != 1 or tasks[0]['status'] != 2 or prior['state'] != 'finished'
                    or any(tasks[0][key] != prior[key] for key in ('file_id', 'parent_id'))):
                raise ValueError('Font cloud task changed')
            for number, asset in enumerate(assets):
                self._guard()
                item = map_torrent_file(self.provider, plan['destination'], tasks[0], asset)
                extension = Path(asset['path']).suffix.casefold()
                target = work/(str(number)+extension)
                sha256 = self._download(item, target)
                evidence.append(dict(asset=asset, cloud={k:item[k] for k in ('file_id','path','bytes')},
                                     sha256=sha256, local=str(target)))
                self._guard()
                if extension in {'.7z', '.zip'}:
                    fonts.extend(self._decode(target, sha256, work/('decoded-'+str(number))))
                else:
                    parsed = inspect_font_file(target)
                    if parsed['sha256'] != sha256:
                        raise ValueError('Direct font changed after download')
                    fonts.append(dict(parsed, path=str(target), origin='same_release_pack'))
                if len(fonts) > 128 or sum(f['bytes'] for f in fonts) > EXPANSION_LIMIT:
                    raise ValueError('Combined release font budget')
            self._guard()
            if self.provider.account_scope() != plan['account']:
                raise ValueError('Font cloud account changed after read')
            self._guard()
            selection = select_fonts(plan['requirements'], fonts)
            required = {row['sha256'] for row in selection['selected']}
            return dict(state='FONT_INPUTS_NOT_NATIVE_OR_VISUAL_PROOF',
                        fonts=[row for row in fonts if row['sha256'] in required],
                        selection=selection, evidence=evidence, workspace=str(work))
        finally:
            # Exact download identities, no URL/credential. Keep failed partials.
            (work/'inputs.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
