"""Regression suite for R11 (SRC-R2-02 & REV-07): leaf separation and resumable frontier."""
from contextlib import nullcontext
from threading import Event
import pytest

from bobbi_platform import catalog_service as cs_mod
from bobbi_platform.account_manager import AccountManager
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.libraries import Registry
from bobbi_platform.pan_service import PanService
from bobbi_platform.server_accounts import Accounts
from bobbi_platform.server_emby import Client


class _EmbyScanWire:
    base = 'https://synthetic.example/emby'
    operation = None

    def __init__(self, count: int, *, mixed: bool = False, real_folders: int = 0, on_page=None):
        self.count = count
        self.mixed = mixed
        self.real_folders = real_folders
        self.on_page = on_page
        self.calls = []
        self.id_prefix = 'movie'

    def budget(self, seconds):
        return nullcontext()

    def headers(self):
        return {'User-Agent': 'Bobbi-MediaServer/1', 'X-Emby-Token': 'synthetic-token'}

    def request(self, path, **kw):
        self.calls.append((path, kw.get('query')))
        if self.operation:
            self.operation.consume_request()
            self.operation.check()
        if path == '/System/Info/Public':
            return {'Id': 'srv-r11'}
        if path in ('/Users/Me', '/Users/usr-r11'):
            return {'Id': 'usr-r11'}
        if path.endswith('/Views'):
            return {'Items': [{'Id': 'movies', 'Name': 'Movies', 'IsFolder': True}], 'TotalRecordCount': 1}
        if path == '/Users/usr-r11/Items':
            parent = kw['query']['ParentId']
            offset, limit = kw['query']['StartIndex'], kw['query']['Limit']
            if self.on_page is not None:
                self.on_page(parent, offset, limit)
            if parent == 'movies' and self.real_folders > 0:
                total = self.real_folders + self.count
                items = []
                for idx in range(offset, min(total, offset + limit)):
                    if idx < self.count:
                        items.append({'Id': f'{self.id_prefix}{idx:05d}', 'Name': f'Film {idx:05d}', 'IsFolder': False})
                    else:
                        fidx = idx - self.count
                        items.append({'Id': f'sub{fidx:04d}', 'Name': f'Sub {fidx:04d}', 'IsFolder': True})
                return {'Items': items, 'TotalRecordCount': total}
            if parent.startswith('sub'):
                return {'Items': [], 'TotalRecordCount': 0}
            return {
                'Items': [
                    {'Id': f'{self.id_prefix}{i:05d}', 'Name': f'Film {i:05d}', 'IsFolder': False}
                    for i in range(offset, min(self.count, offset + limit))
                ],
                'TotalRecordCount': self.count,
            }
        if '/Users/usr-r11/Items/' in path:
            entry = path.rsplit('/', 1)[-1]
            sources = [{
                'Id': entry + '_file',
                'Protocol': 'File',
                'Path': f'/movies/{entry}.mkv',
                'Size': 4096,
                'SupportsDirectPlay': True,
            }]
            if self.mixed:
                sources.append({
                    'Id': entry + '_http',
                    'Protocol': 'Http',
                    'Path': f'{self.base}/media/{entry}.mkv',
                    'Size': 4096,
                    'SupportsDirectPlay': True,
                })
                sources.append({
                    'Id': entry + '_live',
                    'Protocol': 'File',
                    'Path': f'/movies/{entry}_live.mkv',
                    'Size': 4096,
                    'RequiresOpening': True,
                })
            return {'Id': entry, 'PartCount': 1, 'Name': f'Title {entry}', 'Type': 'Movie', 'MediaSources': sources}
        raise AssertionError(path)


def _setup_env(tmp_path, wire):
    factory = lambda key, saved: Client(key, saved, wire)
    accounts = Accounts(tmp_path)
    expected = accounts.register('emby', 'R11 Emby', wire.base, 'synthetic-token', client_factory=factory)
    pans = PanService(tmp_path, AccountManager(tmp_path / '115.json'), servers=accounts, client_factory=factory)
    reg = Registry(tmp_path / 'libraries.sqlite3')
    directory = reg.save_directory('Movies', expected, 'root')
    reg.close()
    catalog = CatalogService(tmp_path, pans)
    return accounts, expected, pans, directory, catalog


def _run_once(catalog, expected, dir_id, timeout=60):
    task = catalog.start_scan(expected, dir_id)['task_id']
    catalog.worker.join(timeout)
    assert not catalog.worker.is_alive()
    job = catalog.index.jobs(expected, task=task)['items'][0]
    obs = catalog.index.source_observation(expected, dir_id)
    return job, obs


@pytest.mark.parametrize('count', [1022, 1023])
def test_r11_01_1022_and_1023_movies_complete_in_single_run(tmp_path, count):
    wire = _EmbyScanWire(count)
    _, expected, pans, directory, catalog = _setup_env(tmp_path, wire)
    try:
        job, obs = _run_once(catalog, expected, directory['id'])
        assert job['state'] == 'completed'
        assert obs['coverage'] == 'complete'
        assert obs['indexed_count'] == count
        assert obs['present_count'] == count
    finally:
        catalog.close()
        pans.close()


def test_r11_02_10000_movies_resumable_across_restart_and_preserves_unseen_without_snapshot(tmp_path):
    wire = _EmbyScanWire(1)
    wire.id_prefix = 'legacy'
    accounts, expected, pans, directory, catalog = _setup_env(tmp_path, wire)
    try:
        # Seed 1 legacy movie from an earlier closed generation
        job0, obs0 = _run_once(catalog, expected, directory['id'])
        assert job0['state'] == 'completed' and obs0['present_count'] == 1

        # Switch library content to 10,000 movies (legacy00000 absent upstream)
        wire.id_prefix = 'movie'
        wire.count = 10000

        # Run 1 hits request budget, commits >1000 movies immediately visible
        job1, obs1 = _run_once(catalog, expected, directory['id'])
        assert job1['state'] in ('failed', 'interrupted')
        assert job1['result_summary'] == 'PAN_BUDGET_EXHAUSTED'
        assert obs1['indexed_count'] > 1000
        assert obs1['present_count'] == obs1['indexed_count']
    finally:
        catalog.close()

    # Simulate Host/service restart before continuing remaining runs
    catalog = CatalogService(tmp_path, pans)
    try:
        runs = 1
        while True:
            runs += 1
            assert runs <= 12
            job, obs = _run_once(catalog, expected, directory['id'])
            if job['result_summary'] != 'PAN_BUDGET_EXHAUSTED':
                break

        # All 10,000 movies + 1 legacy movie are present with 0 duplicates;
        # multi-run non-snapshot scan marks SCAN_RESUMED_PARTIAL and never deletes legacy00000!
        assert obs['indexed_count'] == 10001
        assert obs['present_count'] == 10001
        assert obs['absent_count'] == 0
        assert obs['coverage'] == 'partial'
        assert job['result_summary'] == 'SCAN_RESUMED_PARTIAL'

        # Now shrink library to 5 movies so a single-run closed generation proves absence
        wire.count = 5
        job_closed, obs_closed = _run_once(catalog, expected, directory['id'])
        assert job_closed['state'] == 'completed'
        assert obs_closed['coverage'] == 'complete'
        assert obs_closed['present_count'] == 5
        assert obs_closed['absent_count'] == 9996
    finally:
        catalog.close()
        pans.close()


def test_r11_03_cancel_resumes_cleanly_and_total_change_invalidates_frontier(tmp_path):
    hit_gate = [False]
    catalog_ref = [None]

    def on_page(parent, offset, limit):
        if parent == 'movies' and offset >= 60 and not hit_gate[0]:
            hit_gate[0] = True
            catalog_ref[0].cancel_event.set()

    wire = _EmbyScanWire(120, on_page=on_page)
    _, expected, pans, directory, catalog = _setup_env(tmp_path, wire)
    catalog_ref[0] = catalog
    try:
        job_cancel, obs_cancel = _run_once(catalog, expected, directory['id'])
        assert job_cancel['state'] == 'canceled'
        assert 40 <= obs_cancel['present_count'] < 120

        # Resume completes all 120 items without losing committed batches
        wire.on_page = None
        job_resumed, obs_resumed = _run_once(catalog, expected, directory['id'])
        assert obs_resumed['present_count'] == 120
        assert job_resumed['result_summary'] == 'SCAN_RESUMED_PARTIAL'

        # Now test upstream total change mid-resume: invalidates frontier instead of trusting stale offset
        cancel_second = [False]
        def cancel_at_40(parent, offset, limit):
            if parent == 'movies' and offset >= 40 and not cancel_second[0]:
                cancel_second[0] = True
                catalog.cancel_event.set()

        wire.on_page = cancel_at_40
        j1, _ = _run_once(catalog, expected, directory['id'])
        assert j1['state'] == 'canceled'

        wire.on_page = None
        wire.count = 119  # Upstream total mutated while paused!
        j2, obs2 = _run_once(catalog, expected, directory['id'])
        assert j2['state'] == 'interrupted'
        assert j2['result_summary'] == 'SCAN_TOTAL_CHANGED'
        assert obs2['present_count'] == 119 or obs2['present_count'] == 120
    finally:
        catalog.close()
        pans.close()


def test_r11_04_05_real_directory_limit_and_mixed_versions_stay_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(cs_mod, 'MAX_DIRECTORIES', 6)
    wire = _EmbyScanWire(25, mixed=False, real_folders=10)
    _, expected, pans, directory, catalog = _setup_env(tmp_path, wire)
    try:
        job, obs = _run_once(catalog, expected, directory['id'])
        assert job['state'] == 'interrupted'
        assert job['result_summary'] == 'SCAN_DIRECTORY_LIMIT'
        assert obs['coverage'] == 'partial'
        assert obs['present_count'] == 20
    finally:
        catalog.close()
        pans.close()

    # R11-05: Mixed File + Http + RequiresOpening keeps File version and marks partial
    wire_mixed = _EmbyScanWire(4, mixed=True)
    _, exp_m, pans_m, dir_m, cat_m = _setup_env(tmp_path / 'mixed', wire_mixed)
    try:
        job_m, obs_m = _run_once(cat_m, exp_m, dir_m['id'])
        assert job_m['state'] == 'interrupted'
        assert job_m['result_summary'] == 'SERVER_VERSIONS_EXCLUDED'
        assert obs_m['coverage'] == 'partial'
        assert obs_m['present_count'] == 4
        assert cat_m.index.db.execute('PRAGMA main.user_version').fetchone()[0] == 4
    finally:
        cat_m.close()
        pans_m.close()
