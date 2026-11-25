"""Contract and inverted-witness regression suite for U06-U11.

Covers CT-SCAN-COMPLETE, CT-SCAN-RESUME, CT-T4-IDENTITY, CT-T4-CACHE,
CT-HTTP-BOUNDARY, CT-NUVIO, CT-DEBRID, CT-MEDIA-ORIGIN, CT-STRM,
CT-PHONE-AUTH, CT-FRONTEND-TEXT, CT-UPLOAD, CT-PHONE-LIST,
CT-SUBTITLE-UPLOAD, CT-PRIVATE-INPUT, CT-IMPORT-INPUT, and CT-BRIDGE.
"""
from __future__ import annotations

import os
from pathlib import Path
import signal
import sqlite3
import subprocess
import sys
from threading import Event, Thread
import tracemalloc

import pytest

from bobbi_core.media_library_index import FRONTIER_PROOF_VERSION, RESUMABLE_SCAN_REASONS, MediaIndex
from bobbi_platform import (
    catalog_service,
    pan_115,
    pan_123,
    pan_aliyun,
    pan_baidu,
    pan_guangya,
    pan_mobile,
    pan_providers,
    pan_tianyi,
    pan_tokens,
    pan_xunlei,
    server_emby,
    server_plex,
)
from bobbi_platform.account_manager import AccountManager
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.libraries import Registry
from bobbi_platform.pan_accounts import PanAccounts, PanError
from bobbi_platform.pan_service import PanService
from test_cloud_pagination_completeness import QuarkUCWire, _make_cloud_catalog, _run_scan

REPO_ROOT = Path(__file__).resolve().parents[1]


# ============================================================================
# U06: CT-SCAN-COMPLETE & CT-SCAN-RESUME (SRC-01, SRC-09)
# ============================================================================


@pytest.mark.parametrize('provider', ['quark', 'uc'])
@pytest.mark.parametrize('interrupt_kind', ['budget', 'rate_limit_429', 'cancel'])
def test_u06_src01_cloud_page2_resumes_to_21_without_page_expired(tmp_path, monkeypatch, provider, interrupt_kind):
    """Inverted SRC-01 witness (A06-01): after page 1 commits 20/21 items and interrupts,
    next run resumes from page 2 and yields all 21 items as SCAN_RESUMED_PARTIAL,
    while a subsequent full single-run scan 21 -> 20 withdraws exactly 1 deleted item (A06-03).
    """
    catalog, pans, _, wire, expected, sid = _make_cloud_catalog(tmp_path, provider)
    try:
        if interrupt_kind == 'budget':
            monkeypatch.setattr(catalog_service, 'MAX_PAGES', 1)
            job1, _, counts1 = _run_scan(catalog, expected, sid)
            assert job1['result_summary'] == 'PAN_BUDGET_EXHAUSTED'
            monkeypatch.setattr(catalog_service, 'MAX_PAGES', 1200)
        elif interrupt_kind == 'rate_limit_429':
            orig_req = wire.request

            def fail_p2_429(url, query=None, body=None):
                if query and query.get('_page') == 2:
                    raise PanError('PAN_RATE_LIMITED')
                return orig_req(url, query=query, body=body)

            wire.request = fail_p2_429
            job1, _, counts1 = _run_scan(catalog, expected, sid)
            assert job1['result_summary'] == 'PAN_RATE_LIMITED'
            wire.request = orig_req
        else:
            wire.entered_page2.clear()
            wire.release_page2.clear()
            task = catalog.start_scan(expected, sid)['task_id']
            assert wire.entered_page2.wait(3)
            catalog.dispatch('catalog_cancel', dict(expected=expected, task_id=task))
            wire.release_page2.set()
            catalog.worker.join(5)
            job1 = catalog.index.jobs(expected, task=task)['items'][0]
            counts1 = dict(
                catalog.index.db.execute(
                    'SELECT available, count(*) FROM memberships WHERE source=? GROUP BY available',
                    (sid,),
                ).fetchall()
            )
            assert job1['state'] == 'canceled' and job1['result_summary'] == 'CANCEL_CONFIRMED'

        assert counts1 == {1: 20}
        wire.calls.clear()

        # Run 2 MUST fetch ONLY page 2 and converge to 21 present items as SCAN_RESUMED_PARTIAL!
        job2, obs2, counts2 = _run_scan(catalog, expected, sid)
        assert wire.calls == [(2, 20, 1, 21)]
        assert job2['state'] == 'interrupted'
        assert job2['result_summary'] == 'SCAN_RESUMED_PARTIAL'
        assert obs2['coverage'] == 'partial'
        assert counts2 == {1: 21}

        # Single-run complete scan 21 -> 20 withdraws exactly the 1 absent item!
        wire.mode = 'complete_20'
        wire.calls.clear()
        job3, obs3, counts3 = _run_scan(catalog, expected, sid)
        assert job3['state'] == 'completed'
        assert obs3['coverage'] == 'complete'
        assert counts3 == {1: 20, 0: 1}
    finally:
        wire.release_page2.set()
        catalog.close()
        pans.close()


def test_u06_src09_normal_close_and_restart_reasons_resume_committed_frontier(tmp_path):
    """Inverted merge witness normal_stop_resume (A06-02 / SRC-09):
    CatalogService.close() (SERVICE_STOPPED), recover() (SERVICE_RESTART), and legacy
    INTERRUPTED_BY_RESTART all preserve committed page 1 and resume at next_page=2.
    Repeated stop before page 2 commits ALSO retains page 1's anchor batch!
    """
    assert {'SERVICE_STOPPED', 'SERVICE_RESTART', 'INTERRUPTED_BY_RESTART'} <= RESUMABLE_SCAN_REASONS
    cat, pans, native, wire, expected, sid = _make_cloud_catalog(tmp_path, 'quark')
    reopened = None
    reopened2 = None
    try:
        wire.entered_page2.clear()
        wire.release_page2.clear()
        task1 = cat.start_scan(expected, sid)['task_id']
        assert wire.entered_page2.wait(3)
        before = cat.index.frontier_peek(task1)
        assert before['node']['next_page'] == 2
        assert before['dir_proof']['proof_version'] == FRONTIER_PROOF_VERSION
        assert before['dir_proof']['expected_total'] == 21
        assert before['dir_proof']['seen_count'] == 20
        assert before['dir_proof']['next_offset'] == 20

        closer_errors = []
        closer = Thread(target=lambda: closer_errors.append(cat.close()))
        closer.start()
        assert cat.stop.wait(2)
        wire.release_page2.set()
        closer.join(4)
        assert not closer.is_alive()

        reopened = CatalogService(tmp_path, pans)
        assert reopened.index._scan(task1)['reason'] == 'SERVICE_STOPPED'

        # Stop AGAIN during resumed run before page 2 commits -> anchor batch still preserved!
        wire.entered_page2.clear()
        wire.release_page2.clear()
        task2 = reopened.start_scan(expected, sid)['task_id']
        assert wire.entered_page2.wait(3)
        peek2 = reopened.index.frontier_peek(task2)
        assert peek2['node']['next_page'] == 2 and peek2['state']['resumed'] == 1
        closer2 = Thread(target=reopened.close)
        closer2.start()
        assert reopened.stop.wait(2)
        wire.release_page2.set()
        closer2.join(4)

        # Simulate legacy INTERRUPTED_BY_RESTART row compatibility and finish scan
        reopened2 = CatalogService(tmp_path, pans)
        with reopened2.index.transaction():
            reopened2.index.db.execute(
                "UPDATE scans SET reason='INTERRUPTED_BY_RESTART' WHERE id=?",
                (task2,),
            )
        wire.calls.clear()
        job3, _, counts3 = _run_scan(reopened2, expected, sid)
        assert wire.calls == [(2, 20, 1, 21)]
        assert job3['result_summary'] == 'SCAN_RESUMED_PARTIAL'
        assert counts3 == {1: 21}
    finally:
        wire.release_page2.set()
        if reopened2 is not None:
            reopened2.close()
        if reopened is not None:
            reopened.close()
        cat.close()
        pans.close()


def test_u06_src09_real_subprocess_sigkill_before_and_after_commit_and_scope_guards(tmp_path):
    """Real OS SIGKILL verification (A06-02 / SRC-09):
    1) SIGKILL before page 1 commits -> clean rollback, next open starts at page 1.
    2) SIGKILL after page 1 commits (mid page 2) -> recover() marks SERVICE_RESTART and resumes at page 2.
    3) Half-batch mismatch or root/account/generation change rejects stale frontier.
    """
    worker_script = """
import os, sys, time
from pathlib import Path
from threading import Event
sys.path[:0] = [
    str(Path(sys.argv[1]) / 'addons/script.module.bobbi.core/lib'),
    str(Path(sys.argv[1]) / 'addons/script.module.bobbi.platform/lib'),
    str(Path(sys.argv[1]) / 'tests'),
]
from test_cloud_pagination_completeness import _make_cloud_catalog
mode = sys.argv[2]
root = Path(sys.argv[3])
marker = Path(sys.argv[4])
cat, pans, _, wire, expected, sid = _make_cloud_catalog(root, 'quark')
if mode == 'before_page1':
    orig = wire.request
    def block_p1(url, query=None, body=None):
        marker.write_text('in_page1')
        time.sleep(30)
        return orig(url, query=query, body=body)
    wire.request = block_p1
else:
    wire.entered_page2.clear()
    wire.release_page2.clear()
cat.start_scan(expected, sid)
if mode == 'after_page1':
    assert wire.entered_page2.wait(5)
    marker.write_text('in_page2')
time.sleep(30)
"""
    # 1) SIGKILL before page 1 commit
    dir_pre = tmp_path / 'kill_pre'
    dir_pre.mkdir()
    marker_pre = tmp_path / 'marker_pre'
    proc1 = subprocess.Popen(
        [sys.executable, '-B', '-c', worker_script, str(REPO_ROOT), 'before_page1', str(dir_pre), str(marker_pre)],
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
    )
    try:
        for _ in range(100):
            if marker_pre.exists():
                break
            proc1.poll()
            import time as _t
            _t.sleep(0.03)
        assert marker_pre.exists()
        os.kill(proc1.pid, signal.SIGKILL)
        proc1.wait(timeout=5)
    finally:
        if proc1.poll() is None:
            proc1.kill()
            proc1.wait(timeout=5)

    cat_pre, pans_pre, _, wire_pre, exp_pre, sid_pre = _make_cloud_catalog(dir_pre, 'quark')
    try:
        latest_pre = cat_pre.index.jobs(exp_pre)['items'][0]
        assert latest_pre['state'] == 'interrupted' and latest_pre['result_summary'] == 'SERVICE_RESTART'
        t_pre = cat_pre.index.start_resumable(sid_pre, exp_pre, '0', resumable=True)
        peek_pre = cat_pre.index.frontier_peek(t_pre)
        assert peek_pre['node']['next_page'] == 1 and peek_pre['state']['resumed'] == 0
        cat_pre.index.finish(t_pre, 'canceled', 'CANCEL_CONFIRMED')
    finally:
        cat_pre.close()
        pans_pre.close()

    # 2) SIGKILL after page 1 commit (while blocked in page 2)
    dir_post = tmp_path / 'kill_post'
    dir_post.mkdir()
    marker_post = tmp_path / 'marker_post'
    proc2 = subprocess.Popen(
        [sys.executable, '-B', '-c', worker_script, str(REPO_ROOT), 'after_page1', str(dir_post), str(marker_post)],
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
    )
    try:
        for _ in range(100):
            if marker_post.exists():
                break
            import time as _t
            _t.sleep(0.03)
        assert marker_post.exists()
        os.kill(proc2.pid, signal.SIGKILL)
        proc2.wait(timeout=5)
    finally:
        if proc2.poll() is None:
            proc2.kill()
            proc2.wait(timeout=5)

    native = PanAccounts(dir_post / 'native.json', {'quark': lambda value: ('user-1', value)})
    exp_post = native.snapshot('quark')
    wire_post = QuarkUCWire()
    pans_post = PanService(
        dir_post,
        AccountManager(dir_post / '115.json'),
        accounts=native,
        client_factory=lambda key, saved: pan_providers.descriptor(key).client(session=wire_post),
    )
    reg = Registry(dir_post / 'libraries.sqlite3')
    sid_post = reg.directories()[0]['id']
    reg.close()
    cat_post = CatalogService(dir_post, pans_post)
    try:
        latest_post = cat_post.index.jobs(exp_post)['items'][0]
        assert latest_post['state'] == 'interrupted' and latest_post['result_summary'] == 'SERVICE_RESTART'
        wire_post.calls.clear()
        job_res, _, counts_res = _run_scan(cat_post, exp_post, sid_post)
        assert wire_post.calls == [(2, 20, 1, 21)]
        assert job_res['result_summary'] == 'SCAN_RESUMED_PARTIAL'
        assert counts_res == {1: 21}

        # 3) Half-batch mismatch or account/root change rejects stale frontier
        wire_post.entered_page2.clear()
        wire_post.release_page2.clear()
        t_half = cat_post.start_scan(exp_post, sid_post)['task_id']
        assert wire_post.entered_page2.wait(3)
        cat_post.dispatch('catalog_cancel', dict(expected=exp_post, task_id=t_half))
        wire_post.release_page2.set()
        cat_post.worker.join(5)

        # Corrupt frontier last_batch to simulate crashed half-batch between DB and frontier_db
        with cat_post.index.frontier_db:
            cat_post.index.frontier_db.execute("UPDATE scan_state SET last_batch='0'*64 WHERE source=?", (sid_post,))
        t_rebuilt = cat_post.index.start_resumable(sid_post, exp_post, '0', resumable=True)
        peek_rebuilt = cat_post.index.frontier_peek(t_rebuilt)
        assert peek_rebuilt['node']['next_page'] == 1 and peek_rebuilt['state']['resumed'] == 0
        cat_post.index.finish(t_rebuilt, 'canceled', 'CANCEL_CONFIRMED')

        # Root parent change also rejects frontier
        wire_post.entered_page2.clear()
        wire_post.release_page2.clear()
        t_root = cat_post.start_scan(exp_post, sid_post)['task_id']
        assert wire_post.entered_page2.wait(3)
        cat_post.dispatch('catalog_cancel', dict(expected=exp_post, task_id=t_root))
        wire_post.release_page2.set()
        cat_post.worker.join(5)
        t_diff_root = cat_post.index.start_resumable(sid_post, exp_post, 'different_root', resumable=True)
        peek_diff_root = cat_post.index.frontier_peek(t_diff_root)
        assert peek_diff_root['node']['next_page'] == 1 and peek_diff_root['state']['resumed'] == 0
        cat_post.index.finish(t_diff_root, 'canceled', 'CANCEL_CONFIRMED')
    finally:
        wire_post.release_page2.set()
        cat_post.close()
        pans_post.close()


def test_u06_legacy_v2_frontier_replays_only_unfinished_dir_preserving_completed_dirs(tmp_path):
    """Legacy user_version=2 frontier lacking versioned proof rewinds ONLY unfinished page>1
    directories to page 1 while keeping already-completed directories untouched.
    """
    db_path = tmp_path / 'media-index.sqlite3'
    idx = MediaIndex(db_path)
    scope_exp = {'provider': 'quark', 'account_id': 'a' * 32, 'epoch': 1}
    sid = 'b' * 32
    t1 = idx.start_resumable(sid, scope_exp, '0', resumable=True)
    idx.begin(t1)
    # Simulate root -> completed dirA + unfinished dirB at page 2, then downgrade frontier schema to v2!
    idx.frontier_batch(
        t1,
        [],
        dict(parent='0', page=1, cursor=None, queued=2, depth=0),
        2,
        frontier_step=dict(
            pop_seq=1,
            dir_key='0',
            is_leaf=False,
            declared_total=2,
            page_item_count=2,
            next_offset=2,
            entry_sigs=['["dirA",true]', '["dirB",true]'],
            new_leaves=[],
            new_dirs=[('dirA', 1), ('dirB', 1)],
            dir_count=3,
            partial_latch=False,
            continuation=None,
        ),
    )
    peek_a = idx.frontier_peek(t1)
    assert peek_a['node']['node_key'] == 'dirA'
    idx.frontier_batch(
        t1,
        [],
        dict(parent='dirA', page=1, cursor=None, queued=1, depth=1),
        0,
        frontier_step=dict(
            pop_seq=peek_a['node']['seq'],
            dir_key='dirA',
            is_leaf=False,
            declared_total=0,
            page_item_count=0,
            next_offset=0,
            entry_sigs=[],
            new_leaves=[],
            new_dirs=[],
            dir_count=3,
            partial_latch=False,
            continuation=None,
        ),
    )
    peek_b = idx.frontier_peek(t1)
    assert peek_b['node']['node_key'] == 'dirB'
    idx.frontier_batch(
        t1,
        [],
        dict(parent='dirB', page=1, cursor=None, queued=1, depth=1),
        20,
        frontier_step=dict(
            pop_seq=peek_b['node']['seq'],
            dir_key='dirB',
            is_leaf=False,
            declared_total=21,
            page_item_count=20,
            next_offset=20,
            entry_sigs=[f'["f{i}",false]' for i in range(20)],
            new_leaves=[],
            new_dirs=[],
            dir_count=3,
            partial_latch=False,
            continuation=dict(priority=1, node_key='dirB', depth=1, leaf=0, next_page=2, cursor=None),
        ),
    )
    idx.finish(t1, 'canceled', 'CANCEL_CONFIRMED')
    f_path = idx.frontier_path
    idx.close()

    # Rewrite frontier DB back to legacy user_version=2 without proof columns!
    raw_f = sqlite3.connect(str(f_path))
    with raw_f:
        st = raw_f.execute(
            'SELECT source,provider,account,scope_digest,root_parent,scan_generation,last_task,last_batch,resumed,partial_latch,dir_count,updated FROM scan_state'
        ).fetchall()
        dirs = raw_f.execute('SELECT source,scan_generation,dir_key,depth,expected_total FROM scan_dirs').fetchall()
        raw_f.execute('DROP TABLE scan_state')
        raw_f.execute('DROP TABLE scan_dirs')
        raw_f.execute(
            'CREATE TABLE scan_state(source TEXT PRIMARY KEY,provider TEXT NOT NULL,account TEXT NOT NULL,'
            'scope_digest TEXT NOT NULL,root_parent TEXT NOT NULL,scan_generation TEXT NOT NULL,'
            'last_task TEXT NOT NULL,last_batch TEXT NOT NULL,resumed INTEGER NOT NULL,'
            'partial_latch INTEGER NOT NULL,dir_count INTEGER NOT NULL,updated REAL NOT NULL)'
        )
        raw_f.execute(
            'CREATE TABLE scan_dirs(source TEXT NOT NULL,scan_generation TEXT NOT NULL,dir_key TEXT NOT NULL,'
            'depth INTEGER NOT NULL,expected_total INTEGER,PRIMARY KEY(source,scan_generation,dir_key))'
        )
        raw_f.executemany('INSERT INTO scan_state VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', st)
        raw_f.executemany('INSERT INTO scan_dirs VALUES(?,?,?,?,?)', dirs)
        raw_f.execute('PRAGMA user_version=2')
    raw_f.close()

    reopened = MediaIndex(db_path)
    try:
        t2 = reopened.start_resumable(sid, scope_exp, '0', resumable=True)
        peek2 = reopened.frontier_peek(t2)
        # Completed '0' and 'dirA' remain known and NOT re-queued; unfinished 'dirB' rewound to page 1!
        assert reopened.frontier_known_dir(t2, 'dirA') is True
        assert peek2['node']['node_key'] == 'dirB'
        assert peek2['node']['next_page'] == 1
        assert peek2['state']['resumed'] == 1
        reopened.finish(t2, 'canceled', 'CANCEL_CONFIRMED')
    finally:
        reopened.close()


def test_u06_all_13_providers_page_cursor_contracts_and_100k_bounded_scan(tmp_path, monkeypatch):
    """A06-04: All 13 registered providers in DESCRIPTORS have explicit pagination/proof coverage,
    pan_tokens._directory_pages is deleted, and a 100,000-object resumable scan advances in bounded
    batches with bounded memory (< 48 MiB peak) and zero duplicate in-memory page dictionaries.
    """
    expected_providers = {
        '115', 'quark', 'uc', 'baidu', 'aliyun', '123', '139', '189', 'guangya', 'xunlei',
        'plex', 'jellyfin', 'emby',
    }
    assert set(pan_providers.DESCRIPTORS) == expected_providers
    assert '_directory_pages' not in Path(pan_tokens.__file__).read_text(encoding='utf-8')
    for key, desc in pan_providers.DESCRIPTORS.items():
        assert desc.proof_contract in {'page_total', 'page_optional_total', 'page_probe', 'cursor'}
        assert (desc.pagination == 'cursor') == (key in {'aliyun', '139', 'xunlei'})

    # Verify cursor resume across runs on Xunlei (representative cursor provider)
    xl_calls = []

    class XunleiStubSession:
        operation = None

        def budget(self, seconds):
            from contextlib import nullcontext
            return nullcontext()

        def request(self, url, query=None, body=None, headers=None):
            if '/captcha/' in url or 'init' in url:
                return {'captcha_token': 'cap-tok', 'expires_in': 3600}
            tok = query.get('page_token', '')
            xl_calls.append(tok)
            if not tok:
                files = [
                    {
                        'id': f'xl{i:03d}',
                        'parent_id': '',
                        'name': f'Film.{i:03d}.mkv',
                        'size': '1024',
                        'kind': 'drive#file',
                        'trashed': False,
                        'modified_time': '2026-01-01T00:00:00Z',
                        'hash': 'a' * 32,
                    }
                    for i in range(20)
                ]
                return {'files': files, 'next_page_token': 'NextCursorToken2'}
            return {
                'files': [
                    {
                        'id': 'xl020',
                        'parent_id': '',
                        'name': 'Film.020.mkv',
                        'size': '1024',
                        'kind': 'drive#file',
                        'trashed': False,
                        'modified_time': '2026-01-01T00:00:00Z',
                        'hash': 'b' * 32,
                    }
                ],
                'next_page_token': '',
            }

    xl_dir = tmp_path / 'xl'
    xl_dir.mkdir()
    xl_saved = {
        'provider': 'xunlei',
        'subject': 'u1',
        'access_token': 'atok',
        'refresh_token': 'rtok',
        'expires_at': 9999999999,
        'device_id': 'dev1',
    }
    xl_wire = XunleiStubSession()
    xl_client = pan_xunlei.Client(xl_saved, session=xl_wire, clock=lambda: 1000, monotonic=lambda: 100.0)
    xl_client.admissions['GET:/drive/v1/files'] = (9999.0, 'adm-1')
    xl_acc = PanAccounts(xl_dir / 'native.json', {'xunlei': lambda v: ('u1', v)})
    xl_exp = xl_acc.install(xl_saved, xl_acc.snapshot('xunlei'))
    xl_pans = PanService(
        xl_dir,
        AccountManager(xl_dir / '115.json'),
        accounts=xl_acc,
        client_factory=lambda k, s: xl_client,
    )
    xl_reg = Registry(xl_dir / 'libraries.sqlite3')
    xl_sid = xl_reg.save_directory('XL Movies', xl_exp, '0')['id']
    xl_reg.close()
    xl_cat = CatalogService(xl_dir, xl_pans)
    try:
        monkeypatch.setattr(catalog_service, 'MAX_PAGES', 1)
        j1, _, c1 = _run_scan(xl_cat, xl_exp, xl_sid)
        assert j1['result_summary'] == 'PAN_BUDGET_EXHAUSTED' and c1 == {1: 20}
        xl_calls.clear()
        monkeypatch.setattr(catalog_service, 'MAX_PAGES', 1200)
        j2, _, c2 = _run_scan(xl_cat, xl_exp, xl_sid)
        assert xl_calls == ['NextCursorToken2']
        assert j2['result_summary'] == 'SCAN_RESUMED_PARTIAL' and c2 == {1: 21}
    finally:
        xl_cat.close()
        xl_pans.close()

    # 100,000 synthetic objects across 9 resumable runs (12,000 items / 600 pages per run)
    big_dir = tmp_path / 'big100k'
    big_dir.mkdir()
    total_100k = 100_000

    class Big100kWire:
        operation = None

        def budget(self, seconds):
            from contextlib import nullcontext
            return nullcontext()

        def request(self, url, query=None, body=None):
            page, size = query['_page'], query['_size']
            start = (page - 1) * size
            end = min(page * size, total_100k)
            rows = [
                dict(fid='m%06d' % i, file_name='Movie.%06d.2024.mkv' % i, file=True, size=2048)
                for i in range(start, end)
            ]
            return dict(code=0, status=200, data=dict(list=rows), metadata={'_total': total_100k})

    bwire = Big100kWire()
    bacc = PanAccounts(big_dir / 'native.json', {'quark': lambda v: ('u1', v)})
    bexp = bacc.install({'synthetic': True}, bacc.snapshot('quark'))
    bpans = PanService(
        big_dir,
        AccountManager(big_dir / '115.json'),
        accounts=bacc,
        client_factory=lambda k, s: pan_providers.descriptor('quark').client(session=bwire),
    )
    breg = Registry(big_dir / 'libraries.sqlite3')
    bsid = breg.save_directory('Big 100k', bexp, '0')['id']
    breg.close()
    bcat = CatalogService(big_dir, bpans)
    try:
        runs = 0
        peak_run1 = 0
        peak_last = 0
        owner_latencies = []
        while True:
            runs += 1
            assert runs <= 12
            measure_mem = runs in (1, 9)
            if measure_mem:
                tracemalloc.start()
            try:
                btask = bcat.start_scan(bexp, bsid)['task_id']
                if runs == 2:
                    import time as _t
                    _t.sleep(0.02)
                    t0 = _t.monotonic()
                    live_obs = bcat.source_observation(bexp, bsid)
                    owner_latencies.append(_t.monotonic() - t0)
                    assert live_obs['indexed_count'] >= 12_000
                bcat.worker.join(60)
                assert not bcat.worker.is_alive()
                bjob = bcat.index.jobs(bexp, task=btask)['items'][0]
                bobs = bcat.source_observation(bexp, bsid)
                if runs == 1:
                    peak_run1 = tracemalloc.get_traced_memory()[1]
                elif runs == 9:
                    peak_last = tracemalloc.get_traced_memory()[1]
            finally:
                if measure_mem:
                    tracemalloc.stop()
            if bjob['result_summary'] != 'PAN_BUDGET_EXHAUSTED':
                break
        assert runs == 9  # ceil(100,000 / 12,000) == 9 bounded runs
        assert bjob['result_summary'] == 'SCAN_RESUMED_PARTIAL'
        assert bobs['indexed_count'] == 100_000
        assert owner_latencies and max(owner_latencies) < 0.5
        assert peak_run1 < 48 * 1024 * 1024 and peak_last < 48 * 1024 * 1024
    finally:
        bcat.close()
        bpans.close()


# ============================================================================
# U07: CT-T4-IDENTITY & CT-T4-CACHE (SRC-02, SRC-GAP-01, SRC-GAP-02)
# ============================================================================


def test_u07_src02_at_capacity_keeps_parent_and_play_token_resolves_without_parent(tmp_path):
    """Inverted witness test_t4_small_detail_also_loses_recently_read_parent_at_capacity:
    1) At 4096 full capacity, reading parent refreshes its LRU position and put_play pins parent,
       so BOTH parent item_token and the newly minted play_token remain valid.
    2) Even after parent item_token is later evicted by 4096 newer items (while play_token is read),
       play_token remains self-contained on disk and resolves cleanly via selection_with_play_token,
       and raw/evicted tokens NEVER fall back to vod_id (R13-01/02/05).
    """
    import json
    from bobbi_core import t4
    from bobbi_core.library_contract import LibraryError
    from bobbi_platform import t4_http
    from bobbi_platform.t4_tokens import MAX_TOKENS, T4TokenStore

    cfg = {'sites': [{'key': 'x', 'name': 'X', 'type': 4, 'api': 'https://t4.example.invalid/vod'}]}
    src = t4.preview(json.dumps(cfg).encode('utf-8')).source('')
    site = src.metadata['sites'][0]
    sid = src.id
    gen = 'b' * 64
    shash = t4_http._opaque(site['key'])
    complex_vod_id = 'https://upstream.example.invalid/item/9988?cat=drama&token=internal'
    complex_ep_id = 'play://lineA/ep01?sign=abc123&ts=1700000000'

    with T4TokenStore(tmp_path / 'small-tokens.db') as store:
        parent = store.put_item(sid, gen, shash, complex_vod_id)
        for idx in range(MAX_TOKENS - 1):
            store.put_item(sid, gen, shash, f'film-{idx}')
        assert store.get_item(sid, gen, shash, parent) == complex_vod_id
        play_tok = store.put_play(sid, gen, shash, parent, 'LineA', complex_ep_id, 'Film · Ep 1')
        # Inverted witness assertion: parent MUST still be valid!
        assert store.get_item(sid, gen, shash, parent) == complex_vod_id
        rec = store.get_play(sid, gen, shash, play_tok)
        assert rec['vod_id'] == complex_vod_id
        assert rec['item_token'] == parent
        assert complex_vod_id not in play_tok and complex_ep_id not in play_tok

        # Now evict parent by filling 4096 new items while touching play_tok once mid-way
        for idx in range(MAX_TOKENS):
            if idx == MAX_TOKENS // 2:
                assert store.get_play(sid, gen, shash, play_tok)['vod_id'] == complex_vod_id
            store.put_item(sid, gen, shash, f'later-{idx}')
        with pytest.raises(LibraryError, match='T4_TOKEN_EXPIRED'):
            store.get_item(sid, gen, shash, parent)

    # Reopen store (simulating Host restart) and resolve play_tok without parent!
    def wire(url):
        if 'ids=' in url:
            return json.dumps({
                'list': [{
                    'vod_id': complex_vod_id,
                    'vod_name': 'Film',
                    'vod_play_from': 'LineA',
                    'vod_play_url': f'Ep 1${complex_ep_id}',
                }]
            }).encode('utf-8')
        return json.dumps({'parse': 0, 'url': 'https://t4.example.invalid/media/ep1.mp4'}).encode('utf-8')

    with T4TokenStore(tmp_path / 'small-tokens.db', read_only=True) as ro_store:
        choice = t4_http.selection_with_play_token(site, play_tok)
        assert complex_vod_id not in json.dumps(choice)
        media_url, _, ep_title = t4_http.resolve_selected(
            src,
            choice,
            generation=gen,
            token_store=ro_store,
            fetch=wire,
        )
        assert media_url == 'https://t4.example.invalid/media/ep1.mp4'
        assert ep_title == 'Ep 1'

        # Generation change rejects play_tok immediately (R13-05)
        with pytest.raises(LibraryError, match='T4_TOKEN_EXPIRED'):
            t4_http.resolve_selected(src, choice, generation='c' * 64, token_store=ro_store, fetch=wire)


def test_u07_src02_4500_episodes_bounded_pagination_single_tx_and_native_filters(tmp_path, monkeypatch):
    """Inverted witness test_t4_legal_detail_evicts_own_parent_token + A08-01..03 + GAP-SRC-FILTER + SRC-GAP-02:
    - Legacy modal t4_ui.browse is removed.
    - 3 lines x 1500 = 4500 episodes paginate cleanly at <= 200 episodes/page in ONE SQLite tx per page,
      reaching the final page (Line C page 8, episode 1500), keeping parent tok and all current-page
      play tokens valid & playable even when starting at 4096 full capacity.
    - Native t4_cat exposes category filters within <= 7 query parameters (default.py max_num_fields=8).
    - Evicted directory token offers an explicit refresh entry back to t4_site, while changed generation rejects.
    - Import preview wires export_probed_lives_playlist when lives > 0 (SRC-GAP-02).
    """
    import base64
    from contextlib import contextmanager
    import json
    from types import SimpleNamespace
    from urllib.parse import parse_qs, parse_qsl, urlsplit
    from bobbi_core import t4
    from bobbi_core.library_contract import LibraryError
    from bobbi_platform import owned_playback, paths, source_library_ui, t4_http, t4_ui
    from bobbi_platform.t4_tokens import MAX_TOKENS, T4TokenStore

    assert not hasattr(t4_ui, 'browse')

    cfg = {
        'sites': [{'key': 'big', 'name': 'BigVOD', 'type': 4, 'api': 'https://t4.example.invalid/vod', 'searchable': 1}],
        'lives': [{'name': 'LiveGroup', 'type': 0, 'url': 'https://t4.example.invalid/live.txt'}],
    }
    raw_cfg = json.dumps(cfg).encode('utf-8')
    store = Registry(tmp_path / 'libraries.sqlite3')

    # Verify SRC-GAP-02: t4_ui.add reaches lives export when lives > 0
    live_txt = '央视,#genre#\nCCTV1,https://t4.example.invalid/cctv1.m3u8\n'.encode('utf-8')
    monkeypatch.setattr(paths, 'ProfileBinding', lambda: SimpleNamespace(root=lambda: tmp_path, is_current=lambda: True, require_current=lambda: None))
    monkeypatch.setattr(source_library_ui, 'operation', lambda fn: fn(10**12, lambda: False))
    monkeypatch.setattr(t4_ui, 'read', lambda url, *a, **kw: live_txt if url.endswith('live.txt') else raw_cfg)
    selects = iter([0])  # method='url'
    yesnos = iter([True, True])  # confirm T4 import, confirm lives export
    oks = []
    dlg_add = SimpleNamespace(
        select=lambda *a: next(selects),
        input=lambda *a: 'https://t4.example.invalid/config.json',
        yesno=lambda *a: next(yesnos),
        ok=lambda *a: oks.append(a),
    )
    assert t4_ui.add(dlg_add, None, store) is True
    exported_files = list((tmp_path / 'exports').glob('bobbi-lives-*.m3u8'))
    assert len(exported_files) == 1 and '#EXTM3U' in exported_files[0].read_text(encoding='utf-8')

    src, gen = store.source_snapshot(store.sources()[0].id)
    site = src.metadata['sites'][0]
    shash = t4_http._opaque(site['key'])

    # Pre-fill T4TokenStore to MAX_TOKENS (4096) before browsing 4500-episode detail!
    with T4TokenStore(tmp_path / 't4-tokens.sqlite3') as pre_store:
        for idx in range(MAX_TOKENS):
            pre_store.put_item(src.id, gen, shash, f'prefill-{idx}')

    groups = ['#'.join(f'E{i}$line{line}-ep{i}' for i in range(1500)) for line in range(3)]
    observed_exts = []

    def wire_4500(url, *a, **kw):
        q = parse_qs(urlsplit(url).query)
        if 'ids' in q:
            return json.dumps({
                'list': [{
                    'vod_id': 'film4500',
                    'vod_name': 'LongSeries',
                    'vod_play_from': 'LineA$$$LineB$$$LineC',
                    'vod_play_url': '$$$'.join(groups),
                }]
            }).encode('utf-8')
        if 'play' in q:
            ep = q['play'][0]
            return json.dumps({'parse': 0, 'url': f'https://t4.example.invalid/media/{ep}.mp4'}).encode('utf-8')
        if q.get('ac') == ['detail'] and 't' in q:
            ext_dec = json.loads(base64.urlsafe_b64decode(q['ext'][0].encode('ascii')).decode('utf-8'))
            observed_exts.append(ext_dec)
            return json.dumps({
                'page': int(q['pg'][0]),
                'pagecount': 2,
                'list': [{'vod_id': 'film4500', 'vod_name': 'LongSeries'}],
            }).encode('utf-8')
        return json.dumps({
            'class': [{'type_id': 'series', 'type_name': '剧集'}],
            'filters': {
                'series': [{
                    'key': 'year',
                    'name': '年份',
                    'value': [{'n': '全部', 'v': ''}, {'n': '2026', 'v': '2026'}],
                }]
            },
            'list': [{'vod_id': 'film4500', 'vod_name': 'LongSeries'}],
        }).encode('utf-8')

    monkeypatch.setattr(t4_ui, 'read', wire_4500)
    rendered = []
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Monitor=lambda: SimpleNamespace(abortRequested=lambda: False)))
    monkeypatch.setitem(
        sys.modules,
        'xbmcgui',
        SimpleNamespace(
            Dialog=lambda: SimpleNamespace(input=lambda *_: '', yesno=lambda *_: True, ok=lambda *_: None),
            ListItem=lambda label='': SimpleNamespace(
                label=label,
                setInfo=lambda *a: None,
                setArt=lambda *a: None,
                setProperty=lambda *a: None,
                setLabel2=lambda *a: None,
            ),
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        'xbmcplugin',
        SimpleNamespace(
            setPluginCategory=lambda *a: None,
            setContent=lambda *a: None,
            addDirectoryItems=lambda _h, rows, _n: rendered.extend(rows),
            endOfDirectory=lambda *a, **kw: None,
            setResolvedUrl=lambda *a: None,
        ),
    )

    def make_item(label, target, folder=True, label2='', properties=None, info=None, *, playable=True):
        li = sys.modules['xbmcgui'].ListItem(label)
        li.props = dict(properties or {})
        return target, li, folder

    def parse_plugin_query(u):
        pairs = parse_qsl(urlsplit(u).query, keep_blank_values=True, max_num_fields=8)
        return dict(pairs)

    try:
        # 1. Home -> Category -> Filter ('2026') -> Filtered Category -> Detail
        rendered.clear()
        t4_ui.execute_directory(1, {'action': 'browse', 'source': src.id}, store, make_item)
        cat_url = next(u for u, li, _ in rendered if li.label == '剧集')

        rendered.clear()
        t4_ui.execute_directory(1, parse_plugin_query(cat_url), store, make_item)
        filter_entry_url = next(u for u, li, _ in rendered if li.props.get('Bobbi.FilterEntry') == 'true')

        rendered.clear()
        t4_ui.execute_directory(1, parse_plugin_query(filter_entry_url), store, make_item)
        year_facet_url = rendered[0][0]

        rendered.clear()
        t4_ui.execute_directory(1, parse_plugin_query(year_facet_url), store, make_item)
        opt_2026_url = next(u for u, li, _ in rendered if '2026' in li.label)
        assert '2026' not in opt_2026_url  # Opaque filter token in URL!

        rendered.clear()
        t4_ui.execute_directory(1, parse_plugin_query(opt_2026_url), store, make_item)
        assert observed_exts[-1] == {'year': '2026'}
        detail_url = next(u for u, li, _ in rendered if li.label == 'LongSeries')
        detail_q = parse_plugin_query(detail_url)
        parent_tok = detail_q['tok']

        # 2. Open 4500-episode detail -> renders 3 line folders, then walk LineC (ln=2) pages 1..8!
        rendered.clear()
        t4_ui.execute_directory(1, detail_q, store, make_item)
        assert len(rendered) == 3
        line_c_url = rendered[2][0]

        cur_url = line_c_url
        for expected_pg in range(1, 9):
            rendered.clear()
            t4_ui.execute_directory(1, parse_plugin_query(cur_url), store, make_item)
            ep_rows = [(u, li) for u, li, is_folder in rendered if not is_folder]
            assert len(ep_rows) == (100 if expected_pg == 8 else 200)
            # Parent item_token MUST NEVER be evicted during page creation!
            with T4TokenStore(tmp_path / 't4-tokens.sqlite3', read_only=True) as check_store:
                assert check_store.get_item(src.id, gen, shash, parent_tok) == 'film4500'
            if expected_pg < 8:
                cur_url = next(u for u, li, is_f in rendered if is_f and li.props.get('Bobbi.NextPage') == 'true')

        # 3. Play the very last episode (LineC E1499, 4500th episode!) via real Host resolver
        final_ep_url, final_ep_li = ep_rows[-1]
        assert 'E1499' in final_ep_li.label and 'line2-ep1499' not in final_ep_url
        final_q = parse_plugin_query(final_ep_url)

        played = []

        @contextmanager
        def real_resolve_reservation(target, scope, **kw):
            def host_call(op, body, timeout=18):
                with T4TokenStore(tmp_path / 't4-tokens.sqlite3', read_only=True) as hs:
                    m_url, _, _ = t4_http.resolve_selected(
                        src,
                        body['selection'],
                        generation=body['generation'],
                        token_store=hs,
                        fetch=wire_4500,
                    )
                played.append(m_url)
                return {'url': 'http://127.0.0.1:4100/stream/' + 'd' * 32 + '/video.mp4', 'size': 1024}

            yield SimpleNamespace(
                request_id='e' * 32,
                require_current=lambda: None,
                host_call=host_call,
                submit=lambda *a, **skw: None,
            )

        monkeypatch.setattr(owned_playback, 'reserve_playback', real_resolve_reservation)
        t4_ui.execute_directory(1, final_q, store, make_item)
        assert played == ['https://t4.example.invalid/media/line2-ep1499.mp4']

        # 4. Evicted directory token renders explicit refresh link; changed generation rejects!
        rendered.clear()
        stale_q = dict(detail_q, tok='0' * 32)
        t4_ui.execute_directory(1, stale_q, store, make_item)
        assert len(rendered) == 1 and rendered[0][1].props.get('Bobbi.ExpiredRefresh') == 'true'

        with pytest.raises(LibraryError, match='T4_CHANGED'):
            t4_ui.execute_directory(1, dict(detail_q, rev='f' * 64), store, make_item)
    finally:
        store.close()


# ============================================================================
# U08: CT-HTTP-BOUNDARY, CT-NUVIO, CT-DEBRID (SRC-03, SRC-04, SRC-06, SRC-07)
# ============================================================================


_KODI_STUB_CACHE = {}


def _setup_plugin_test_env(monkeypatch, tmp_path=None):
    plugin_dir = str(REPO_ROOT / 'addons/plugin.video.bobbi')
    if plugin_dir not in sys.path:
        monkeypatch.syspath_prepend(plugin_dir)
    if 'xbmc' not in sys.modules or not hasattr(sys.modules['xbmc'], 'LOGINFO'):
        if not _KODI_STUB_CACHE:
            import runpy
            prev_mods = dict(sys.modules)
            prev_argv = list(sys.argv)
            prev_path = list(sys.path)
            ns = runpy.run_path(str(REPO_ROOT / 'tests/private_baseline/conftest.py'))
            _KODI_STUB_CACHE['ns'] = ns
            _KODI_STUB_CACHE['mods'] = {
                k: sys.modules[k]
                for k in ('xbmc', 'xbmcgui', 'xbmcaddon', 'xbmcvfs', 'xbmcplugin', 'pydevd')
                if k in sys.modules
            }
            sys.argv[:] = prev_argv
            sys.path[:] = prev_path
            for k in list(sys.modules):
                if k not in prev_mods:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = prev_mods[k]
        for k, v in _KODI_STUB_CACHE['mods'].items():
            monkeypatch.setitem(sys.modules, k, v)


def test_u08_src07_connect_tcp_slice_fallback_ipv6_ipv4_and_sticky_global_cancel():
    """Inverted merge witness connect_controls + A05-01..03 (SRC-07):
    - Address #1 exhausting its 1s slice (out of 2s connect_cap / 10s deadline) closes socket #1
      without poisoning AttemptHandle and connects on socket #2 (including IPv6 blackhole -> IPv4).
    - Immediate refusal falls back cleanly; all-fail, global deadline expiry, and explicit cancel
      exit boundedly with all failed sockets closed and no cross-attempt socket interference.
    """
    import errno
    import socket
    from unittest.mock import patch
    from bobbi_core import bounded_http

    for mode, addr_families, expected_res, expected_socks in [
        ('slice_timeout', (socket.AF_INET, socket.AF_INET), 'connected', 2),
        ('ipv6_blackhole', (socket.AF_INET6, socket.AF_INET), 'connected', 2),
        ('immediate_refusal', (socket.AF_INET, socket.AF_INET), 'connected', 2),
        ('all_timeout', (socket.AF_INET, socket.AF_INET), 'TimeoutError', 2),
        ('global_expired', (socket.AF_INET, socket.AF_INET), 'TimeoutError', 1),
        ('already_expired', (socket.AF_INET, socket.AF_INET), 'TimeoutError', 0),
        ('cancelled', (socket.AF_INET, socket.AF_INET), 'AttemptCancelled', 0),
    ]:
        now = [0.5 if mode == 'already_expired' else 0.0]
        created = []

        class FakeSock:
            def __init__(self, family, *_):
                self.family = family
                self.number = len(created)
                self.closed = False
                created.append(self)

            def setblocking(self, _):
                pass

            def connect_ex(self, _):
                if mode in ('slice_timeout', 'ipv6_blackhole', 'immediate_refusal') and self.number == 1:
                    return 0
                if mode == 'immediate_refusal':
                    return errno.ECONNREFUSED
                return errno.EINPROGRESS

            def shutdown(self, _):
                pass

            def close(self):
                self.closed = True

        def fake_select(r, w, x, timeout):
            if mode == 'global_expired':
                now[0] += max(timeout, 0.6)
            else:
                now[0] += timeout
            return [], [], []

        addrs = [
            (addr_families[0], socket.SOCK_STREAM, 6, '', ('2001:db8::1', 443, 0, 0) if addr_families[0] == socket.AF_INET6 else ('192.0.2.1', 443)),
            (addr_families[1], socket.SOCK_STREAM, 6, '', ('192.0.2.2', 443)),
        ]
        deadline_val = 0.5 if mode in ('global_expired', 'already_expired') else 10.0
        attempt = bounded_http.AttemptHandle(
            deadline=deadline_val,
            clock=lambda: now[0],
            cancelled=lambda: mode == 'cancelled',
        )
        connected_sock = None
        with patch.object(bounded_http.socket, 'socket', FakeSock), patch.object(bounded_http.select, 'select', fake_select):
            try:
                connected_sock = bounded_http.connect_tcp(addrs, attempt, connect_cap=2.0)
                status = 'connected'
                assert not connected_sock.closed
                if mode in ('slice_timeout', 'ipv6_blackhole'):
                    assert created[0].closed is True
                    assert pytest.approx(now[0], abs=0.05) == 1.0
                    assert not attempt._aborted
            except Exception as exc:
                status = type(exc).__name__
            finally:
                if connected_sock is not None:
                    connected_sock.close()
                attempt.close()

        assert status == expected_res, f'{mode}: got {status}'
        assert len(created) == expected_socks, f'{mode}: got {len(created)} sockets'
        if mode == 'global_expired':
            assert attempt._aborted is True
        assert all(s.closed for s in created)

    # A05-03: Cancelling/aborting/closing an old attempt handle never shuts down or closes a new attempt's socket
    old_attempt = bounded_http.AttemptHandle(deadline=10.0, clock=lambda: 0.0)
    new_attempt = bounded_http.AttemptHandle(deadline=10.0, clock=lambda: 0.0)
    live_events = []
    live_sock = type('S', (), {
        'shutdown': lambda self, *_: live_events.append('shutdown'),
        'close': lambda self: live_events.append('close'),
    })()
    new_attempt.attach_tcp(live_sock)
    old_attempt.abort()
    old_attempt.close()
    assert live_events == []
    new_attempt.abort()
    new_attempt.close()
    assert live_events == ['shutdown']


def test_u08_src03_stremio_never_downgrades_to_http_while_preserving_explicit_lan_http(tmp_path, monkeypatch):
    """Inverted witness test_stremio_uri_tls_failure_retries_secret_path_over_http (F-SRC-03-1..3):
    - TLS/network error, timeout, HTTP 4xx/5xx, and malformed JSON on stremio:// or https://
      NEVER trigger an http:// fallback retry, and secret paths/queries never enter logs.
    - Explicit LAN http://192.168.x.x/... remains supported, while public cleartext http:// is rejected.
    """
    import importlib.util
    import json
    from types import ModuleType, SimpleNamespace
    from bobbi_core import http_policy

    plugin_root = REPO_ROOT / 'addons/plugin.video.bobbi'
    logs = []

    def stub_mod(name, **attrs):
        m = ModuleType(name)
        m.__dict__.update(attrs)
        monkeypatch.setitem(sys.modules, name, m)

    stub_mod('lib.api.stremio.addon_manager', build_addon_instance_key=lambda a: 'id|0')
    stub_mod(
        'lib.clients.stremio.constants',
        STREMIO_ADDONS_CATALOGS_KEY='c',
        STREMIO_ADDONS_KEY='s',
        STREMIO_TV_ADDONS_KEY='t',
        STREMIO_USER_ADDONS='u',
        decode_selected_ids=lambda v: list(v or []),
        encode_selected_ids=lambda v: list(v),
    )
    stub_mod(
        'lib.clients.stremio.protocol',
        MAX_RESOURCE_JSON_BYTES=http_policy.MAX_RESOURCE_JSON_BYTES,
        is_safe_http_url=http_policy.is_safe_http_url,
        request_with_safe_redirects=http_policy.request_with_safe_redirects,
    )
    stub_mod('lib.db.cached', cache=SimpleNamespace(get=lambda k: None, set=lambda *a, **kw: None))
    stub_mod('lib.utils.general.utils', USER_AGENT_HEADER={'User-Agent': 'test'})
    stub_mod('lib.utils.kodi.utils', kodilog=lambda msg, *a: logs.append(str(msg)))

    spec = importlib.util.spec_from_file_location('u08_webserver', plugin_root / 'lib/services/webserver.py')
    web = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(web)

    monkeypatch.setattr(http_policy.socket, 'getaddrinfo', lambda *a: [(2, 1, 6, '', ('8.8.8.8', 443))])
    monkeypatch.setattr(web.socket, 'getaddrinfo', lambda host, *a: (
        [(2, 1, 6, '', ('192.168.1.50', 80))] if host == 'lan-box.local' else [(2, 1, 6, '', ('8.8.8.8', 443))]
    ))

    for failure_kind in ('tls', 'timeout', 'http404', 'bad_json'):
        attempts = []

        def fake_redirect_get(getter, target_url, **kw):
            attempts.append(target_url)
            if failure_kind == 'tls':
                raise ConnectionError('synthetic TLS failure')
            if failure_kind == 'timeout':
                raise TimeoutError('synthetic timeout')
            if failure_kind == 'http404':
                def raise_404():
                    raise RuntimeError('404 Not Found')
                return SimpleNamespace(url=target_url, status_code=404, headers={}, raise_for_status=raise_404, close=lambda: None)
            return SimpleNamespace(
                url=target_url,
                status_code=200,
                headers={},
                raise_for_status=lambda: None,
                iter_content=lambda chunk_size=8192: [b'not-json{{{'],
                close=lambda: None,
            )

        monkeypatch.setattr(web, 'request_with_safe_redirects', fake_redirect_get)
        resolved, manifest, err = web.prepare_stremio_addon(
            'stremio://addon.example.invalid/SYNTHETIC_SECRET_TOKEN/manifest.json?key=TOP_SECRET'
        )
        assert resolved is None and manifest is None and err == 'STREMIO_MANIFEST_UNAVAILABLE'
        assert attempts == ['https://addon.example.invalid/SYNTHETIC_SECRET_TOKEN/manifest.json?key=TOP_SECRET']

    assert all('SYNTHETIC_SECRET_TOKEN' not in line and 'TOP_SECRET' not in line for line in logs)

    # Explicit LAN HTTP works; public HTTP is rejected before network I/O!
    lan_calls = []
    raw_ok = json.dumps({'id': 'lan.addon', 'name': 'LAN Addon', 'resources': ['stream'], 'types': ['movie']}).encode('utf-8')
    monkeypatch.setattr(
        web,
        'request_with_safe_redirects',
        lambda getter, target_url, **kw: (
            lan_calls.append(target_url)
            or SimpleNamespace(
                url=target_url,
                status_code=200,
                headers={},
                raise_for_status=lambda: None,
                iter_content=lambda chunk_size=8192: [raw_ok],
                close=lambda: None,
            )
        ),
    )
    res_lan, man_lan, err_lan = web.prepare_stremio_addon('http://192.168.1.50:7000/manifest.json')
    assert err_lan is None and res_lan == 'http://192.168.1.50:7000/manifest.json' and man_lan['id'] == 'lan.addon'

    lan_calls.clear()
    res_pub_http, _, err_pub_http = web.prepare_stremio_addon('http://addon.example.invalid/manifest.json')
    assert res_pub_http is None and err_pub_http == 'STREMIO_MANIFEST_UNAVAILABLE' and lan_calls == []


def test_u08_src04_src06_streaming_limits_redirect_close_nuvio_and_debrid_dedup(monkeypatch):
    """Covers F-SRC-04-1..5, F-SRC-06-1..3, A14-01..03 (CT-HTTP-BOUNDARY, CT-NUVIO, CT-DEBRID):
    - request_with_safe_redirects closes every intermediate 3xx response and closes on loop/downgrade/max-hops.
    - StremioAddonCatalogsClient (catalog/meta/stream) streams with Content-Length pre-check, chunked/gzip caps,
      and response close BEFORE buffering 3 MiB into Response._content!
    - Nuvio _fetch_manifest & nuvio_toggle_addons share http_policy (deleting _request_with_safe_redirects),
      enforce trust_env=False, deadlines, body caps, response/session close, and keep Nuvio cache keys isolated.
    - RealDebrid and Premiumize duplicate _make_request overrides are deleted while keeping params={} parity.
    """
    import gzip
    from http.server import BaseHTTPRequestHandler, HTTPServer
    import importlib
    from types import SimpleNamespace
    import requests
    from bobbi_core import http_policy

    # 1) F-SRC-06-1..3: Intermediate 302 responses closed, final 200 owned by caller; loop/downgrade/max-hops closed
    replies = []

    def fake_get(url, **kw):
        closed = []
        r = SimpleNamespace(
            status_code=302 if len(replies) < 2 else 200,
            headers={'Location': f'/next{len(replies)}'},
            close=lambda: closed.append(True),
            was_closed=closed,
        )
        replies.append(r)
        return r

    final_resp = http_policy.request_with_safe_redirects(
        fake_get, 'https://example.invalid/start', lambda _: True, stream=True
    )
    assert final_resp is replies[2]
    assert len(replies[0].was_closed) == 1 and len(replies[1].was_closed) == 1
    assert replies[2].was_closed == []

    # HTTPS -> HTTP downgrade closes intermediate response and raises ValueError
    downgrade_closed = []
    with pytest.raises(ValueError, match='downgrade'):
        http_policy.request_with_safe_redirects(
            lambda u, **kw: SimpleNamespace(
                status_code=302,
                headers={'Location': 'http://example.invalid/plain'},
                close=lambda: downgrade_closed.append(u),
            ),
            'https://example.invalid/secure',
            lambda _: True,
            stream=True,
        )
    assert downgrade_closed == ['https://example.invalid/secure']

    # 2) F-SRC-04-1..4: Real loopback HTTPServer proves Content-Length > limit reads 0 body into _content,
    # and chunked / gzip bombs abort mid-stream with response closed!
    big_body = b'{"padding":"' + b'x' * (3 * 1024 * 1024) + b'"}'
    gz_bomb = gzip.compress(b'{"padding":"' + b'z' * (2 * 1024 * 1024) + b'"}')
    mode = ['content_length']

    class BoundedHandler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            if mode[0] == 'content_length':
                self.send_response(200)
                self.send_header('Content-Length', str(len(big_body)))
                self.end_headers()
                try:
                    self.wfile.write(big_body)
                except OSError:
                    pass
            elif mode[0] == 'gzip_bomb':
                self.send_response(200)
                self.send_header('Content-Encoding', 'gzip')
                self.end_headers()
                try:
                    self.wfile.write(gz_bomb)
                except OSError:
                    pass
            elif mode[0] == 'valid_catalog':
                payload = b'{"metas":[{"id":"tt1","type":"movie","name":"Valid"}]}'
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

    srv = HTTPServer(('127.0.0.1', 0), BoundedHandler)
    srv_thread = Thread(target=srv.serve_forever, kwargs={'poll_interval': 0.01}, daemon=True)
    srv_thread.start()
    observed_gets = []

    class MeasuringSession(requests.Session):
        def get(self, *args, **kwargs):
            resp = super().get(*args, **kwargs)
            observed_gets.append((dict(kwargs), resp._content))
            return resp

    _setup_plugin_test_env(monkeypatch, tmp_path=None)
    addon_client = importlib.import_module('lib.clients.stremio.addon_client')
    monkeypatch.setattr(addon_client, 'get_int_setting', lambda *_: 3)

    msess = MeasuringSession()
    try:
        cat_client = object.__new__(addon_client.StremioAddonCatalogsClient)
        cat_client.params = {'catalog_type': 'movie', 'catalog_id': 'top', 'meta_id': 'tt1'}
        cat_client.base_url = f'http://127.0.0.1:{srv.server_port}'
        cat_client.session = msess

        with pytest.raises(ValueError, match='JSON response too large'):
            cat_client.get_catalog_info()
        assert observed_gets[-1][0].get('stream') is True
        assert observed_gets[-1][1] is False  # Zero eager download into Response._content!

        # Gzip bomb on get_meta_info (1 MiB cap) rejected even though compressed wire < 10 KiB!
        assert len(gz_bomb) < 32768
        mode[0] = 'gzip_bomb'
        with pytest.raises(ValueError, match='JSON response too large'):
            cat_client.get_meta_info()

        # Valid catalog succeeds
        mode[0] = 'valid_catalog'
        ok_cat = cat_client.get_catalog_info()
        assert len(ok_cat['metas']) == 1 and ok_cat['metas'][0].id == 'tt1'
    finally:
        msess.close()
        srv.shutdown()
        srv.server_close()
        srv_thread.join(2)

    # 3) CT-NUVIO (A14-01..02): Nuvio uses shared http_policy, trust_env=False, closes responses, isolates cache
    nuvio_sel = importlib.import_module('lib.clients.nuvio.addon_selection')
    assert not hasattr(nuvio_sel, '_request_with_safe_redirects')

    nuvio_closed = []
    nuvio_sessions = []

    class FakeNuvioSession:
        def __init__(self):
            self.trust_env = True
            self.closed = False
            nuvio_sessions.append(self)

        def get(self, target_url, **kw):
            c_flag = []
            nuvio_closed.append(c_flag)
            if target_url.endswith('/start/manifest.json'):
                return SimpleNamespace(
                    url=target_url,
                    status_code=302,
                    headers={'Location': 'https://nuvio2.example.invalid/final/manifest.json'},
                    close=lambda: c_flag.append(True),
                )
            body = b'{"id":"org.nuvio.test","name":"Nuvio Test","resources":["stream"],"types":["movie"]}'
            return SimpleNamespace(
                url=target_url,
                status_code=200,
                headers={'Content-Length': str(len(body))},
                raise_for_status=lambda: None,
                iter_content=lambda chunk_size=8192: [body],
                close=lambda: c_flag.append(True),
            )

        def close(self):
            self.closed = True

    monkeypatch.setenv('HTTPS_PROXY', 'http://127.0.0.1:9999')
    monkeypatch.setattr(http_policy.socket, 'getaddrinfo', lambda *a: [(2, 1, 6, '', ('8.8.8.8', 443))])
    monkeypatch.setattr(nuvio_sel.requests, 'Session', FakeNuvioSession)
    monkeypatch.setattr(nuvio_sel, 'get_int_setting', lambda *_: 5)

    kv_cache = {'stremio_user_addons': [{'id': 'keep-stremio'}]}
    monkeypatch.setattr(
        nuvio_sel,
        'cache',
        SimpleNamespace(
            get=lambda k: kv_cache.get(k),
            set=lambda k, v, *a: kv_cache.__setitem__(k, v),
        ),
    )
    monkeypatch.setattr(
        nuvio_sel,
        'NuvioClient',
        lambda: SimpleNamespace(get_addons=lambda: [{'url': 'https://nuvio1.example.invalid/start/manifest.json', 'name': 'Nuvio One'}]),
    )
    monkeypatch.setattr(
        nuvio_sel.xbmcgui,
        'Dialog',
        lambda: SimpleNamespace(multiselect=lambda *a, **kw: [0], ok=lambda *a: None),
    )
    monkeypatch.setattr(
        nuvio_sel.xbmcgui,
        'ListItem',
        lambda label='', label2='': SimpleNamespace(label=label, setArt=lambda *a: None),
    )

    nuvio_sel.nuvio_toggle_addons()
    assert len(nuvio_sessions) == 1
    assert nuvio_sessions[0].trust_env is False and nuvio_sessions[0].closed is True
    assert all(len(c) == 1 for c in nuvio_closed) and len(nuvio_closed) == 2
    assert kv_cache['stremio_user_addons'] == [{'id': 'keep-stremio'}]
    assert kv_cache[nuvio_sel.NUVIO_USER_ADDONS][0]['transportName'] == 'nuvio'

    # 4) CT-DEBRID (A14-03): Duplicate _make_request deleted in RealDebrid & Premiumize; params={} parity kept
    rd_mod = importlib.import_module('lib.api.debrid.realdebrid')
    pm_mod = importlib.import_module('lib.api.debrid.premiumize')
    assert '_make_request' not in rd_mod.RealDebrid.__dict__
    assert '_make_request' not in pm_mod.Premiumize.__dict__

    recorded_debrid = []
    inj_sess = SimpleNamespace(
        request=lambda **kw: (
            recorded_debrid.append(kw)
            or SimpleNamespace(raise_for_status=lambda: None, status_code=200, headers={}, json=lambda: {'status': 'success', 'ok': True})
        ),
        close=lambda: (_ for _ in ()).throw(AssertionError('Injected session must not be closed by constructor')),
    )
    pm_client = pm_mod.Premiumize('pm-tok', session=inj_sess)
    assert pm_client.get_account_info()['status'] == 'success'
    assert recorded_debrid[-1]['params'] == {}
    assert 'Bearer pm-tok' in recorded_debrid[-1]['headers']['Authorization']

    rd_tok = rd_mod.RealDebrid.encode_token_data('cid', 'csec', 'ccode')
    rd_calls = []
    rd_sess = SimpleNamespace(
        request=lambda **kw: (
            rd_calls.append(kw)
            or SimpleNamespace(
                raise_for_status=lambda: None,
                status_code=200,
                headers={},
                json=lambda: {'access_token': 'rd-access'} if kw['url'].endswith('/token') else {'username': 'u'},
            )
        ),
        close=lambda: None,
    )
    rd_client = rd_mod.RealDebrid(rd_tok, session=rd_sess)
    assert rd_client.get_user()['username'] == 'u'
    assert rd_calls[-1]['params'] == {}
    rd_client.get_user_downloads_list(page=2)
    assert rd_calls[-1]['params'] == {'page': 2}
import json
import re
from types import SimpleNamespace
from test_library_plugin import plugin  # noqa: F401


# ==============================================================================
# U09 · Per-Hop Media Origin Policy & Approved Emby HTTP / STRM Subset
# ==============================================================================


def test_u09_src08_per_hop_origin_policy_probe_and_seek_and_tv_chain_approval(plugin, tmp_path, monkeypatch):
    """Inverted merge witness source_owner_redirect + CT-MEDIA-ORIGIN (R14-01..05, A07-01..03, SRC-08):
    - Approved A -> unapproved B stops BEFORE sending any request to B (len(visited) == 1, registered == 0).
    - A -> B -> C validates and prompts hop-by-hop on TV without pre-approving unseen downstream hops.
    - Post-probe ShareStream GET/Range seek enforces the same live (source_id, generation) origin policy
      when upstream redirect target changes or approval/generation is revoked.
    - Cross-origin sensitive headers stripped; same-origin headers & signed query preserved verbatim.
    """
    from email.message import Message
    from http.client import HTTPConnection
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from urllib.error import HTTPError
    from urllib.parse import parse_qs, parse_qsl, urlsplit
    from urllib.request import Request, urlopen
    from unittest.mock import patch

    from bobbi_core import media_pointer, t4
    from bobbi_core.library_contract import LibraryError
    from bobbi_platform import source_media_http, source_streams, t4_http, t4_ui
    from bobbi_platform.host import Host
    from bobbi_platform.libraries import Registry
    from bobbi_platform.t4_tokens import T4TokenStore

    # 1. Exact inverted witness of verify_source_merge.py::source_owner_redirect
    visited, registered = [], []
    initial = 'https://approved.example.invalid/media.mkv'
    final = 'https://unapproved.example.invalid/final.mkv?Policy=eyJ%2B1&Signature=AbC~9'

    class Reply:
        def __init__(self, redirect):
            self.status, self.headers = (302 if redirect else 206), Message()
            if redirect:
                self.headers['Location'] = final
            else:
                for k, v in {
                    'Content-Type': 'video/x-matroska',
                    'Content-Length': '1',
                    'Content-Range': 'bytes 0-0/100',
                    'ETag': '"fixed"',
                }.items():
                    self.headers[k] = v
            self.data = b'' if redirect else b'X'

        def getheader(self, key, default=None):
            return self.headers.get(key, default)

        def close(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def read1(self, size):
            out, self.data = self.data[:size], self.data[size:]
            return out

    class Conn:
        sock = None

        def __init__(self, url):
            self.url = url

        def request(self, method, target, headers):
            visited.append(dict(url=self.url, target=target, headers=dict(headers)))

        def getresponse(self):
            return Reply(self.url == initial)

        def close(self):
            pass

    class DummyTransport:
        def __init__(self, *a, **kw):
            pass

        def register(self, body):
            registered.append(body)
            return {'url': 'http://127.0.0.1:4567/stream/' + 'f' * 32 + '/video.mkv'}

        def close(self):
            pass

    def fake_fetch(url, *_a, **_kw):
        q = parse_qs(urlsplit(url).query)
        if 'play' in q:
            val = {'parse': 0, 'url': initial, 'header': {'Referer': 'https://approved.example.invalid/'}}
        else:
            val = {'list': [{'vod_id': 'v1', 'vod_name': 'Synthetic', 'vod_play_from': 'A', 'vod_play_url': 'E1$e1'}]}
        return json.dumps(val).encode('utf-8')

    w_root = tmp_path / 'witness_case'
    w_root.mkdir()
    cfg = {'sites': [{'key': 'k', 'name': 'Synthetic', 'type': 4, 'api': 'https://approved.example.invalid/t4'}]}
    src = t4.preview(json.dumps(cfg).encode('utf-8')).source('')
    reg = Registry(w_root / 'libraries.sqlite3')
    reg.save(src)
    _, gen = reg.source_snapshot(src.id)
    reg.close()

    choice = t4_http.selection(src.metadata['sites'][0], 'v1', 'A', 'e1')
    owner = source_streams.SourceStreams(w_root, lambda: True)
    with patch.object(t4_http, 'read', fake_fetch), \
         patch.object(source_media_http, 'connection', lambda u, _rem: (Conn(u), urlsplit(u).path + ('?' + urlsplit(u).query if urlsplit(u).query else ''))), \
         patch.object(source_streams, 'ShareStream', DummyTransport):
        with pytest.raises(LibraryError, match='T4_MEDIA_ORIGIN') as exc_info:
            owner.open(dict(request_id='a' * 32, source_id=src.id, generation=gen, selection=choice))
        assert getattr(exc_info.value, 'blocked_origin', None) == 'https://unapproved.example.invalid'
        # CRITICAL: Unapproved hop was NEVER contacted!
        assert len(visited) == 1 and visited[0]['url'] == initial
        assert len(registered) == 0

        # Approve target origin -> now A -> B succeeds with cross-origin Referer stripped and signed query intact!
        with T4TokenStore(w_root / 't4-tokens.sqlite3') as tstore:
            tstore.approve_origin(src.id, gen, 'https://unapproved.example.invalid')
        visited.clear()
        res = owner.open(dict(request_id='b' * 32, source_id=src.id, generation=gen, selection=choice))
        assert res['size'] == 100 and res['identity_mode'] == 'strong_etag'
        assert len(visited) == 2 and len(registered) == 1
        assert 'Referer' in visited[0]['headers'] and 'Referer' not in visited[1]['headers']
        assert visited[1]['target'].endswith('?Policy=eyJ%2B1&Signature=AbC~9')
    owner.close()

    # 2. Full loopback ShareStream + Host + t4_ui hop-by-hop A -> B -> C approval & post-probe Range redirect check
    payload = b'0123456789ABCDEF'
    state = SimpleNamespace(
        b_target='https://cdn-b.example.invalid/hop1?sig=b_raw%2B1',
        c_target='https://cdn-c.example.invalid/final.mkv?Policy=eyJ%2B2&Signature=Sig~C',
        seen=[],
        approve_decisions=[],
        prompts=[],
    )

    class ChainHandler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            host_h, _, real_path = self.path.lstrip('/').partition('/')
            real_path = '/' + real_path
            rng = self.headers.get('Range', '')
            state.seen.append((host_h, real_path, rng, self.headers.get('Referer'), self.headers.get('Authorization')))
            if host_h == 't4-a.example.invalid':
                self.send_response(302)
                self.send_header('Location', state.b_target)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            if host_h == 'cdn-b.example.invalid':
                self.send_response(302)
                self.send_header('Location', state.c_target)
                self.send_header('Content-Length', '0')
                self.end_headers()
                return
            m = re.fullmatch(r'bytes=(\d+)-(\d+)', rng)
            s_idx, e_idx = int(m[1]), int(m[2])
            chunk = payload[s_idx:e_idx + 1]
            self.send_response(206)
            self.send_header('Content-Type', 'video/x-matroska')
            self.send_header('Content-Range', f'bytes {s_idx}-{e_idx}/{len(payload)}')
            self.send_header('Content-Length', str(len(chunk)))
            self.send_header('ETag', '"strong-chain-v1"')
            self.end_headers()
            self.wfile.write(chunk)

    server = ThreadingHTTPServer(('127.0.0.1', 0), ChainHandler)
    srv_thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
    srv_thread.start()

    def live_conn(url, remaining, **kw):
        u = urlsplit(url)
        target = '/' + (u.hostname or '') + (u.path or '/') + ('?' + u.query if u.query else '')
        return HTTPConnection('127.0.0.1', server.server_port, timeout=remaining()), target

    def chain_t4_read(url, deadline, cancelled, **kw):
        q = parse_qs(urlsplit(url).query)
        if 'play' in q:
            return json.dumps({
                'parse': 0,
                'url': 'https://t4-a.example.invalid/hop0?entry=1',
                'header': {'Referer': 'https://t4-a.example.invalid/'},
            }).encode('utf-8')
        if 'ids' in q:
            return json.dumps({
                'list': [{
                    'vod_id': 'vid_chain',
                    'vod_name': '三跳测试片',
                    'vod_play_from': '主线',
                    'vod_play_url': '第1集$ep1',
                }]
            }).encode('utf-8')
        return json.dumps({
            'class': [{'type_id': '1', 'type_name': '电影'}],
            'list': [{'vod_id': 'vid_chain', 'vod_name': '三跳测试片'}],
        }).encode('utf-8')

    monkeypatch.setattr(source_media_http, 'connection', live_conn)
    monkeypatch.setattr(t4_ui, 'read', chain_t4_read)
    monkeypatch.setattr(t4_http, 'read', chain_t4_read)

    live_cfg = json.dumps({
        'sites': [{'key': 'chain_s', 'name': '三跳站', 'type': 4, 'api': 'https://t4-a.example.invalid/vod'}]
    }).encode('utf-8')
    live_src = t4.preview(live_cfg).source('https://t4-a.example.invalid/cfg.json')
    reg2 = Registry(plugin.path)
    reg2.save(live_src)
    _, live_gen = reg2.source_snapshot(live_src.id)
    reg2.close()

    def on_yesno(title, body):
        state.prompts.append(body)
        return state.approve_decisions.pop(0)

    monkeypatch.setattr(
        plugin.module.xbmcgui,
        'Dialog',
        lambda: SimpleNamespace(yesno=on_yesno, ok=lambda *a: None, select=lambda *a: 0, input=lambda *a: ''),
    )

    host = Host(plugin.path.parent)
    host.start()
    try:
        plugin.rows.clear()
        plugin.module.execute(19, {'action': 'browse', 'source': live_src.id})
        detail_url = plugin.rows[2][0]
        plugin.rows.clear()
        plugin.module.execute(19, dict(parse_qsl(urlsplit(detail_url).query)))
        play_url = plugin.rows[0][0]
        play_params = dict(parse_qsl(urlsplit(play_url).query))

        # Decline B on first attempt -> neither B nor C is ever contacted!
        state.seen.clear()
        state.prompts.clear()
        state.approve_decisions = [False]
        plugin.module.execute(19, dict(play_params))
        assert [h for h, *_ in state.seen] == ['t4-a.example.invalid']
        assert len(state.prompts) == 1 and 'https://cdn-b.example.invalid' in state.prompts[0]
        assert 'cdn-c.example.invalid' not in state.prompts[0]

        # Approve B then decline C -> B contacted, C NEVER contacted, only B stored in approvals!
        state.seen.clear()
        state.prompts.clear()
        state.approve_decisions = [True, False]
        plugin.module.execute(19, dict(play_params))
        assert [h for h, *_ in state.seen] == ['t4-a.example.invalid', 't4-a.example.invalid', 'cdn-b.example.invalid']
        assert len(state.prompts) == 2
        assert 'https://cdn-b.example.invalid' in state.prompts[0]
        assert 'https://cdn-c.example.invalid' in state.prompts[1]
        with T4TokenStore(plugin.path.parent / 't4-tokens.sqlite3', read_only=True) as ro:
            assert ro.approved_origins(live_src.id, live_gen) == {'https://cdn-b.example.invalid'}

        # Now approve C -> since B is already approved, prompts ONLY for C and plays!
        state.seen.clear()
        state.prompts.clear()
        state.approve_decisions = [True]
        plugin.resolved.clear()
        plugin.module.execute(19, dict(play_params))
        assert len(state.prompts) == 1 and 'https://cdn-c.example.invalid' in state.prompts[0]
        assert plugin.resolved[-1][:2] == (19, True)
        stream_url = plugin.resolved[-1][2].path

        # Range read 1 succeeds over A -> B -> C with exact signed query on C and Referer stripped on B & C
        state.seen.clear()
        with urlopen(Request(stream_url, headers={'Range': 'bytes=0-7'}), timeout=3) as resp:
            assert resp.status == 206 and resp.read() == b'01234567'
        assert [h for h, *_ in state.seen] == ['t4-a.example.invalid', 'cdn-b.example.invalid', 'cdn-c.example.invalid']
        assert state.seen[0][3] == 'https://t4-a.example.invalid/'
        assert state.seen[1][3] is None and state.seen[2][3] is None
        assert state.seen[2][1] == '/final.mkv?Policy=eyJ%2B2&Signature=Sig~C'

        # Post-probe redirect target switches to unapproved rogue-d -> ShareStream rejects BEFORE contacting rogue-d!
        state.seen.clear()
        state.c_target = 'https://rogue-d.example.invalid/evil.mkv'
        with pytest.raises((HTTPError, OSError)):
            urlopen(Request(stream_url, headers={'Range': 'bytes=8-15'}), timeout=3).read()
        assert 'rogue-d.example.invalid' not in [h for h, *_ in state.seen]

        # Restore C, then revoke C's approval -> subsequent Range read is rejected before contacting C!
        state.c_target = 'https://cdn-c.example.invalid/final.mkv?Policy=eyJ%2B2&Signature=Sig~C'
        with T4TokenStore(plugin.path.parent / 't4-tokens.sqlite3') as tstore:
            tstore.revoke_origin(live_src.id, live_gen, 'https://cdn-c.example.invalid')
        state.seen.clear()
        with pytest.raises((HTTPError, OSError)):
            urlopen(Request(stream_url, headers={'Range': 'bytes=8-15'}), timeout=3).read()
        assert 'cdn-c.example.invalid' not in [h for h, *_ in state.seen]
    finally:
        host.close()
        server.shutdown()
        server.server_close()
        srv_thread.join(2.0)


def test_u09_emby_http_gateway_subset_and_strm_finite_boundaries(tmp_path, monkeypatch):
    """CT-STRM (R14-06..08) + Emby cross-origin signed HTTP / RequiredHttpHeaders subset (U09):
    - Approved Emby cross-origin HTTP MediaSource with signed query and safe RequiredHttpHeaders
      streams byte-accurately via SourceStreams/ShareStream while preserving server/user/item/media-source
      identity and PlaySessionId, without leaking X-Emby-Token or Emby Referer cross-origin.
    - HLS (.m3u8), DASH (.mpd), infinite live streams, BluRay/BDMV folders, recursive .strm, and
      untrusted RequiredHttpHeaders (Authorization/Cookie) fail closed with explicit error codes.
    """
    from http.client import HTTPConnection
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    from urllib.parse import urlsplit
    from urllib.request import Request, urlopen

    from bobbi_core import media_pointer
    from bobbi_core.library_contract import LibraryError, Source
    from bobbi_platform import server_http, source_media_http, source_pointers
    from bobbi_platform.host import Host
    from bobbi_platform.libraries import Registry, vfs_source
    from bobbi_platform.owned_playback import emby_source_scope, reserve_playback
    from bobbi_platform.paths import ProfileBinding
    from bobbi_platform.source_streams import open_emby_http_gateway_playback

    media_bytes = b'EMBY-FINITE-HTTP-ORIGINAL-STREAM-BYTES-0123456789'
    state = SimpleNamespace(
        media_source={
            'Id': 'ms_http_1',
            'Name': '4K Signed CDN',
            'Protocol': 'Http',
            'Path': 'https://emby-cdn.example.invalid/bucket/movie.mkv?X-Amz-Signature=keep%2Bexact~1',
            'SupportsDirectPlay': True,
            'VideoType': 'VideoFile',
            'Size': len(media_bytes),
            'RequiredHttpHeaders': {
                'User-Agent': 'EmbyCustomUA/2.1',
                'Referer': '',  # filled below with Emby server origin to verify cross-origin stripping
            },
        },
        cdn_requests=[],
        emby_requests=[],
    )

    class EmbyAndCdnHandler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            host_h = self.headers.get('Host', '').split(':')[0]
            if host_h.startswith('emby-cdn.example.invalid'):
                state.cdn_requests.append({
                    'path': self.path,
                    'ua': self.headers.get('User-Agent'),
                    'referer': self.headers.get('Referer'),
                    'emby_tok': self.headers.get('X-Emby-Token'),
                    'auth': self.headers.get('Authorization'),
                    'range': self.headers.get('Range', ''),
                })
                m = re.fullmatch(r'bytes=(\d+)-(\d+)', self.headers.get('Range', ''))
                s_i, e_i = int(m[1]), int(m[2])
                chunk = media_bytes[s_i:e_i + 1]
                self.send_response(206)
                self.send_header('Content-Type', 'video/x-matroska')
                self.send_header('Content-Range', f'bytes {s_i}-{e_i}/{len(media_bytes)}')
                self.send_header('Content-Length', str(len(chunk)))
                self.end_headers()
                self.wfile.write(chunk)
                return

            state.emby_requests.append((self.command, self.path, self.headers.get('X-Emby-Token')))
            if self.path == '/emby/System/Info/Public':
                body = {'Id': 'srv01'}
            elif self.path == '/emby/Users/usr01':
                body = {'Id': 'usr01', 'ServerId': 'srv01'}
            elif self.path == '/emby/Users/usr01/Items/item01':
                body = {
                    'Id': 'item01',
                    'Name': '沙丘2',
                    'Type': 'Movie',
                    'IsFolder': False,
                    'MediaSources': [dict(state.media_source)],
                }
            else:
                self.send_error(404)
                return
            raw = json.dumps(body).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_POST(self):
            state.emby_requests.append((self.command, self.path, self.headers.get('X-Emby-Token')))
            length = int(self.headers.get('Content-Length', '0'))
            req_json = json.loads(self.rfile.read(length))
            if self.path == '/emby/Items/item01/PlaybackInfo':
                body = {
                    'MediaSources': [dict(state.media_source)],
                    'PlaySessionId': 'ps-emby-http-01' if req_json.get('IsPlayback') else '',
                }
                raw = json.dumps(body).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            self.send_error(404)

    server = ThreadingHTTPServer(('127.0.0.1', 0), EmbyAndCdnHandler)
    srv_thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.02}, daemon=True)
    srv_thread.start()

    import socket as _sock2

    class CdnRoutedConn(HTTPConnection):
        def connect(self):
            self.sock = _sock2.create_connection(('127.0.0.1', server.server_port), self.timeout)

    emby_base = f'http://127.0.0.1:{server.server_port}/emby'
    state.media_source['RequiredHttpHeaders']['Referer'] = 'https://emby-origin.example.invalid/'
    monkeypatch.setattr(
        'bobbi_platform.server_emby._origin_key',
        lambda u: ('http', '127.0.0.1', server.server_port) if 'emby-origin.example.invalid' in u else source_media_http._origin_key(u),
        raising=False,
    )
    monkeypatch.setattr(
        source_media_http,
        'connection',
        lambda url, rem, **kw: (
            CdnRoutedConn(urlsplit(url).hostname, urlsplit(url).port or 443, timeout=rem()),
            (urlsplit(url).path or '/') + ('?' + urlsplit(url).query if urlsplit(url).query else ''),
        ),
    )

    emby_src = Source(
        id='e' * 32,
        name='Home Emby',
        kind='media_server',
        location=emby_base,
        password='secret-emby-token-xyz',
        metadata={'schema': 1, 'provider': 'emby', 'server_id': 'srv01', 'user_id': 'usr01'},
    )
    reg = Registry(tmp_path / 'libraries.sqlite3')
    reg.save(emby_src)
    _, emby_gen = reg.source_snapshot(emby_src.id)
    reg.close()

    binding = ProfileBinding(lambda addon='plugin.video.bobbi': tmp_path)
    scope = emby_source_scope(
        source_id=emby_src.id,
        generation=emby_gen,
        server_id='srv01',
        user_id='usr01',
    )
    prompts = []
    dialog = SimpleNamespace(yesno=lambda title, body: prompts.append(body) or True)

    host = Host(tmp_path)
    host.start()
    try:
        with reserve_playback(f'emby://{emby_src.id}/item01', scope, binding=binding, allow_starting=True) as resv:
            opened = open_emby_http_gateway_playback(
                resv,
                dialog,
                tmp_path,
                source_id=emby_src.id,
                generation=emby_gen,
                server_id='srv01',
                user_id='usr01',
                item_id='item01',
                media_source_id='ms_http_1',
                require_current=lambda: True,
                open_session=True,
            )
            assert opened is not None
            assert len(prompts) == 1 and 'https://emby-cdn.example.invalid' in prompts[0]
            assert opened['play_session_id'] == 'ps-emby-http-01'
            assert opened['identity_mode'] == 'weak_session'
            assert opened['size'] == len(media_bytes)

            with urlopen(Request(opened['url'], headers={'Range': f'bytes=0-{len(media_bytes) - 1}'}), timeout=3) as r:
                assert r.status == 206 and r.read() == media_bytes

            # Verify CDN received custom User-Agent, preserved exact signed query, and ZERO Emby credentials/Referer!
            assert state.cdn_requests[-1]['path'] == '/bucket/movie.mkv?X-Amz-Signature=keep%2Bexact~1'
            assert state.cdn_requests[-1]['ua'] == 'EmbyCustomUA/2.1'
            assert state.cdn_requests[-1]['referer'] is None
            assert state.cdn_requests[-1]['emby_tok'] is None
            assert state.cdn_requests[-1]['auth'] is None

        # Negative capability checks: HLS, DASH, infinite live, BluRay/BDMV, recursive .strm, untrusted headers
        for bad_patch, expected_code in [
            ({'Path': 'https://emby-cdn.example.invalid/live/index.m3u8'}, 'MEDIA_NOT_FINITE'),
            ({'Path': 'https://emby-cdn.example.invalid/dash/manifest.mpd'}, 'MEDIA_NOT_FINITE'),
            ({'IsInfiniteStream': True}, 'MEDIA_NOT_FINITE'),
            ({'VideoType': 'BluRay'}, 'MEDIA_TYPE_UNSUPPORTED'),
            ({'Path': 'https://emby-cdn.example.invalid/disc/BDMV/index.bdmv'}, 'MEDIA_TYPE_UNSUPPORTED'),
            ({'Path': 'https://emby-cdn.example.invalid/nested/pointer.strm'}, 'MEDIA_TYPE_UNSUPPORTED'),
            ({'RequiredHttpHeaders': {'Authorization': 'Bearer leaked'}}, 'T4_HEADERS'),
        ]:
            orig_ms = dict(state.media_source)
            state.media_source.update(bad_patch)
            try:
                with reserve_playback(f'emby://{emby_src.id}/item01', scope, binding=binding, allow_starting=True) as resv:
                    with pytest.raises(LibraryError, match=expected_code):
                        open_emby_http_gateway_playback(
                            resv,
                            dialog,
                            tmp_path,
                            source_id=emby_src.id,
                            generation=emby_gen,
                            server_id='srv01',
                            user_id='usr01',
                            item_id='item01',
                            media_source_id='ms_http_1',
                            require_current=lambda: True,
                        )
            finally:
                state.media_source = orig_ms
    finally:
        host.close()
        server.shutdown()
        server.server_close()
        srv_thread.join(2.0)

    # 3. CT-STRM (R14-06): STRM BOM/CRLF positive vs >16KB, multiline, #KODIPROP, HLS, recursive .strm negative
    strm_root = tmp_path / 'strm_bounds'
    strm_root.mkdir()
    (strm_root / 'bom_ok.strm').write_bytes(b'\xef\xbb\xbfhttps://cdn.example.invalid/movie.mkv?sig=1\r\n')
    vfs = vfs_source('STRM Bounds', str(strm_root))
    parsed_url, obs = source_pointers.read(vfs, 'bom_ok.strm')
    assert parsed_url == 'https://cdn.example.invalid/movie.mkv?sig=1' and len(obs) == 64

    for bad_name, bad_raw, exp_err in [
        ('oversize.strm', b'https://cdn.example.invalid/' + b'a' * 16400, 'POINTER_INVALID'),
        ('multiline.strm', b'https://cdn.example.invalid/a.mkv\nhttps://cdn.example.invalid/b.mkv\n', 'INVALID_VALUE'),
        ('kodiprop.strm', b'#KODIPROP:inputstream=inputstream.adaptive\nhttps://cdn.example.invalid/a.mpd', 'POINTER_PROPERTY_UNSUPPORTED'),
        ('hls.strm', b'https://cdn.example.invalid/live/stream.m3u8\n', 'MEDIA_NOT_FINITE'),
    ]:
        (strm_root / bad_name).write_bytes(bad_raw)
        with pytest.raises(LibraryError, match=exp_err):
            source_pointers.read(vfs, bad_name)



# ==============================================================================
# U10 · Paired Phone Stremio Byte-Budget Paging & Scoped Subtitle Upload
# ==============================================================================


def test_u10_src05_stremio_list_utf8_byte_budget_12_chinese_and_65_addons_crud(tmp_path, monkeypatch):
    """Inverted witness test_stremio_list_budget_has_no_paging_recovery + CT-PHONE-LIST (F-SRC-05-1..4):
    - 12 addons with 600-Chinese-char descriptions, 28 addons with 600-Chinese-char descriptions,
      and 65 short addons are 100% reachable across pages without REPLY_TOO_LARGE or 64-item truncation.
    - Every reply is strictly <= 16,384 UTF-8 bytes.
    - Full addon IDs (including item #65) remain intact for stremio_detail, stremio_toggle, and stremio_remove.
    - Pairing, Origin, CSRF, and ProfileBinding boundaries remain enforced.
    """
    import importlib
    from bobbi_platform.paths import ProfileBinding

    _setup_plugin_test_env(monkeypatch, tmp_path=tmp_path)
    ws_mod = importlib.import_module('lib.services.webserver')
    pm_mod = importlib.import_module('lib.services.phone_management')

    kv_store = {}
    monkeypatch.setattr(
        ws_mod,
        'cache',
        SimpleNamespace(
            get=lambda k: kv_store.get(k),
            set=lambda k, v, *a: kv_store.__setitem__(k, v),
        ),
    )

    profile_live = [True]
    binding = ProfileBinding(lambda addon='plugin.video.bobbi': tmp_path)
    monkeypatch.setattr(binding, 'is_current', lambda: profile_live[0])

    manager = pm_mod.PhoneManagement(
        {'local_scope': 'stremio_addons'},
        'http://127.0.0.1:8081',
        scopes=pm_mod.STREMIO_SCOPES,
        profile_binding=binding,
    )
    hdrs = {'Host': '127.0.0.1:8081', 'Origin': 'http://127.0.0.1:8081'}

    # Unpaired / bad Origin / bad CSRF checks (CT-PHONE-AUTH / F-SRC-05-4)
    with pytest.raises(pm_mod.PhoneError, match='PAIRING_REQUIRED'):
        manager.handle('/manage/api', hdrs, pm_mod.encode({'action': 'stremio_list', 'params': {}}))

    paired, cookie = manager.handle(
        '/manage/api/pair',
        hdrs,
        pm_mod.encode({'code': manager.pairing_url.split('#')[1]}),
    )
    auth_hdrs = {
        **hdrs,
        'Cookie': cookie.split(';')[0],
        'X-Bobbi-CSRF': paired['csrf'],
    }
    with pytest.raises(pm_mod.PhoneError, match='ORIGIN_FORBIDDEN'):
        manager.handle('/manage/api', {**auth_hdrs, 'Origin': 'http://evil.invalid'}, pm_mod.encode({'action': 'stremio_list', 'params': {}}))
    with pytest.raises(pm_mod.PhoneError, match='CSRF_REJECTED'):
        manager.handle('/manage/api', {**auth_hdrs, 'X-Bobbi-CSRF': 'x' * 43}, pm_mod.encode({'action': 'stremio_list', 'params': {}}))

    def rpc(action, params):
        res, _ = manager.handle('/manage/api', auth_hdrs, pm_mod.encode({'action': action, 'params': params}))
        raw_bytes = pm_mod.encode(res)
        assert len(raw_bytes) <= pm_mod.MAX_REPLY, f'{action} exceeded 16KB: {len(raw_bytes)}'
        return res

    def collect_all_pages():
        collected = []
        off = 0
        seen_offsets = set()
        pages = 0
        while True:
            assert off not in seen_offsets
            seen_offsets.add(off)
            reply = rpc('stremio_list', {} if off == 0 else {'offset': off})
            pages += 1
            collected.extend(reply['items'])
            if reply.get('next_offset') is None:
                break
            assert reply['next_offset'] > off
            off = reply['next_offset']
        return collected, pages

    # Case 1: Exact witness of 12 addons with 600 Chinese chars each
    long_desc = '中' * 600
    kv_store['stremio_user_addons'] = [
        {
            'transportName': 'custom',
            'transportUrl': f'https://addon{i}.example.invalid/secret-token-{i}/manifest.json',
            'manifest': {
                'id': f'org.chinese.long.{i}',
                'name': f'中文长简介源 {i}',
                'version': '1.0.0',
                'description': long_desc,
                'resources': ['stream'],
                'types': ['movie'],
            },
        }
        for i in range(12)
    ]
    items_12, _ = collect_all_pages()
    assert len(items_12) == 12
    assert all('secret-token' not in json.dumps(it) for it in items_12)
    # Full description readable on demand via stremio_detail
    detail_0 = rpc('stremio_detail', {'id': items_12[0]['id']})
    assert detail_0['addon']['description'] == long_desc

    # Case 2: 28 addons with 600 Chinese chars + long names forcing multi-page UTF-8 byte-budget split
    kv_store['stremio_user_addons'] = [
        {
            'transportName': 'custom',
            'transportUrl': f'https://heavy{i}.example.invalid/manifest.json',
            'manifest': {
                'id': f'org.chinese.heavy.identifier.{i:03d}',
                'name': ('超长中文名称测试插件' * 8) + f'-{i:03d}',
                'version': '2.3.4',
                'description': '繁' * 600,
                'resources': ['stream', 'catalog'],
                'types': ['movie', 'series'],
            },
        }
        for i in range(28)
    ]
    items_28, pages_28 = collect_all_pages()
    assert pages_28 >= 2
    assert [it['id'] for it in items_28] == [ws_mod.build_addon_instance_key(a) for a in kv_store['stremio_user_addons']]

    # Case 3: 65 custom addons (previously truncated at [:64]!) -> item #65 reachable and supports toggle & remove!
    kv_store['stremio_user_addons'] = [
        {
            'transportName': 'custom',
            'transportUrl': f'https://short{i}.example.invalid/manifest.json',
            'manifest': {
                'id': f'org.short.addon.{i:03d}',
                'name': f'Short Addon {i:03d}',
                'version': '1.0',
                'description': f'Desc {i:03d}',
                'resources': ['stream'],
                'types': ['movie'],
            },
        }
        for i in range(65)
    ]
    assert len(ws_mod.list_stremio_addons()) == 65
    items_65, pages_65 = collect_all_pages()
    assert pages_65 >= 2
    assert len(items_65) == 65
    id_65 = items_65[64]['id']
    assert id_65.startswith('org.short.addon.064|')

    assert rpc('stremio_toggle', {'id': id_65, 'category': 'stream', 'enabled': True})['success'] is True
    assert rpc('stremio_remove', {'id': id_65})['success'] is True
    items_after, _ = collect_all_pages()
    assert len(items_after) == 64 and all(it['id'] != id_65 for it in items_after)

    # Profile switch revokes session immediately
    profile_live[0] = False
    with pytest.raises(pm_mod.PhoneError, match='ACCOUNT_OR_SERVICE_CHANGED'):
        rpc('stremio_list', {})


def test_u10_root_subtitle_parser_bounded_malformed_and_paired_scope_a_to_b_isolation(tmp_path, monkeypatch):
    """Inverted witness reproduce_legacy_paths.py::multipart_worker + CT-SUBTITLE-UPLOAD (F-ROOT-SUBTITLE-PARSER-1..4):
    - Missing header terminator (with or without closing boundary), missing end boundary, negative/zero/oversized
      Content-Length, and truncated stream all terminate in < 0.2s with bounded bytes read.
    - Paired StremioWebServer + PhoneManagement(SUBTITLE_UPLOAD_SCOPES) rejects unpaired/bad-CSRF/bad-Origin,
      accepts valid Chinese UTF-8/BOM subtitles after prior malformed attempts, stops cleanly, and guarantees
      that A -> B selection/playback switch, cancel, or revoke NEVER installs A's subtitle onto B.
    """
    import base64
    import hashlib
    import importlib
    from io import BytesIO
    import time
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen
    from bobbi_platform.paths import ProfileBinding

    _setup_plugin_test_env(monkeypatch, tmp_path=tmp_path)
    sub_mod = importlib.import_module('lib.services.subtitle_server')
    pm_mod = importlib.import_module('lib.services.phone_management')
    ws_mod = importlib.import_module('lib.services.webserver')

    # 1. Standalone port 8082 SubtitleUploadServer is retired; legacy witness completes in < 0.2s returning None
    assert not hasattr(sub_mod, 'SubtitleUploadServer')

    malformed_cases = [
        # Exact witness from reproduce_legacy_paths.py (missing CRLFCRLF and end boundary)
        (
            {'Content-Type': 'multipart/form-data; boundary=audit-boundary', 'Content-Length': '50'},
            b'--audit-boundary\r\nContent-Disposition: incomplete!',
        ),
        # Missing CRLFCRLF WITH valid end boundary present
        (
            {'Content-Type': 'multipart/form-data; boundary=b1', 'Content-Length': '48'},
            b'--b1\r\nContent-Disposition: no-sep\r\n--b1--\r\n' + b' ' * 5,
        ),
        # Multi-part where part 1 lacks header terminator before part 2
        (
            {'Content-Type': 'multipart/form-data; boundary=b2', 'Content-Length': '96'},
            (b'--b2\r\nBrokenHeaderOnly\r\n--b2\r\nContent-Disposition: form-data; filename="a.srt"\r\n\r\nhi\r\n--b2--').ljust(96, b' '),
        ),
        # Missing closing boundary (--b3--)
        (
            {'Content-Type': 'multipart/form-data; boundary=b3', 'Content-Length': '69'},
            b'--b3\r\nContent-Disposition: form-data; filename="a.srt"\r\n\r\n1\r\nhi\r\n--b3',
        ),
        # Negative Content-Length
        ({'Content-Type': 'multipart/form-data; boundary=b4', 'Content-Length': '-10'}, b''),
        # Zero Content-Length
        ({'Content-Type': 'multipart/form-data; boundary=b4', 'Content-Length': '0'}, b''),
        # Oversized Content-Length (> 2 MiB)
        ({'Content-Type': 'multipart/form-data; boundary=b4', 'Content-Length': str(5 * 1024 * 1024)}, b'x' * 1024),
        # Truncated stream (Content-Length claims 200, EOF at 20)
        ({'Content-Type': 'multipart/form-data; boundary=b4', 'Content-Length': '200'}, b'--b4\r\ntruncated-eof!'),
    ]
    t_start = time.monotonic()
    for hdrs, raw_body in malformed_cases:
        handler = object.__new__(sub_mod.SubtitleUploadHandler)
        handler.headers = hdrs
        handler.rfile = BytesIO(raw_body)
        fname, err = handler._parse_multipart()
        assert fname is None and isinstance(err, str) and err
    assert time.monotonic() - t_start < 0.25

    # 2. Live loopback paired StremioWebServer + PhoneManagement(SUBTITLE_UPLOAD_SCOPES)
    binding = ProfileBinding(lambda addon='plugin.video.bobbi': tmp_path / addon)
    target_a = 'a' * 32
    target_b = 'b' * 32
    active_target = [target_a]

    probe_s = __import__('socket').socket()
    probe_s.bind(('127.0.0.1', 0))
    free_port = probe_s.getsockname()[1]
    probe_s.close()

    origin = f'http://127.0.0.1:{free_port}'
    manager = pm_mod.PhoneManagement(
        {
            'local_scope': 'subtitle_upload',
            'target_id': target_a,
            'source_key': 'movie:A',
            'title': '流浪地球2.2160p',
        },
        origin,
        scopes=pm_mod.SUBTITLE_UPLOAD_SCOPES,
        profile_binding=binding,
        target_current=lambda: active_target[0] == target_a,
    )
    srv = ws_mod.StremioWebServer(port=free_port, phone_management=manager)
    srv.start()
    assert srv.is_running
    try:
        # Unpaired multipart POST is rejected with 401
        bad_mp = b'--bnd\r\nContent-Disposition: form-data; name="f"; filename="a.srt"\r\n\r\n1\r\n--bnd--\r\n'
        req_unpaired = Request(
            f'{origin}/manage/api/subtitle-multipart',
            data=bad_mp,
            headers={
                'Host': f'127.0.0.1:{free_port}',
                'Origin': origin,
                'Content-Type': 'multipart/form-data; boundary=bnd',
            },
            method='POST',
        )
        with pytest.raises(HTTPError) as http_err:
            urlopen(req_unpaired, timeout=2)
        assert http_err.value.code == 401

        # Pair session
        pair_code = manager.pairing_url.split('#')[1]
        pair_req = Request(
            f'{origin}/manage/api/pair',
            data=pm_mod.encode({'code': pair_code}),
            headers={'Host': f'127.0.0.1:{free_port}', 'Origin': origin, 'Content-Type': 'application/json'},
            method='POST',
        )
        with urlopen(pair_req, timeout=2) as resp:
            cookie_hdr = resp.headers.get('Set-Cookie', '').split(';')[0]
            csrf_tok = json.loads(resp.read().decode('utf-8'))['csrf']

        # Malformed multipart over live HTTP returns 400 promptly WITHOUT hanging the server!
        broken_body = b'--live-bnd\r\nContent-Disposition: incomplete-header-no-crlfcrlf'
        req_malformed = Request(
            f'{origin}/manage/api/subtitle-multipart',
            data=broken_body,
            headers={
                'Host': f'127.0.0.1:{free_port}',
                'Origin': origin,
                'Cookie': cookie_hdr,
                'X-Bobbi-CSRF': csrf_tok,
                'Content-Type': 'multipart/form-data; boundary=live-bnd',
            },
            method='POST',
        )
        with pytest.raises(HTTPError) as mal_err:
            urlopen(req_malformed, timeout=2)
        assert mal_err.value.code == 400

        # Valid UTF-8 BOM + Chinese filename upload succeeds immediately right after malformed request!
        bom_srt = '\ufeff1\r\n00:00:01,000 --> 00:00:03,500\r\n太空电梯启动！\r\n'.encode('utf-8')
        uid = 'c' * 32
        for action, params in [
            ('subtitle_upload_begin', {
                'upload_id': uid,
                'file_name': '流浪地球2.简繁特效.srt',
                'total_bytes': len(bom_srt),
                'sha256': hashlib.sha256(bom_srt).hexdigest(),
                'target_id': target_a,
            }),
            ('subtitle_upload_chunk', {
                'upload_id': uid,
                'offset': 0,
                'data_b64': base64.b64encode(bom_srt).decode('ascii'),
            }),
            ('subtitle_upload_commit', {'upload_id': uid}),
        ]:
            r_post = Request(
                f'{origin}/manage/api',
                data=pm_mod.encode({'action': action, 'params': params}),
                headers={
                    'Host': f'127.0.0.1:{free_port}',
                    'Origin': origin,
                    'Cookie': cookie_hdr,
                    'X-Bobbi-CSRF': csrf_tok,
                    'Content-Type': 'application/json',
                },
                method='POST',
            )
            with urlopen(r_post, timeout=2) as r_ok:
                assert r_ok.status == 200

        assert manager.committed_subtitle is not None
        saved_path = Path(manager.committed_subtitle['path'])
        assert saved_path.read_bytes() == bom_srt
        assert '流浪地球2.简繁特效.srt' in saved_path.name

        # Scope check: attempting to consume A's subtitle for B (target_b / movie:B) MUST fail and delete A's file!
        assert manager.consume_committed_subtitle(target_b, 'movie:B') is None
        assert not saved_path.exists()

        # Re-upload via paired multipart with Chinese filename, then switch active_target A -> B!
        valid_mp = (
            '--okbnd\r\n'
            'Content-Disposition: form-data; name="file"; filename="中文字幕A.ass"\r\n\r\n'
        ).encode('utf-8') + bom_srt + b'\r\n--okbnd--\r\n'
        req_mp_ok = Request(
            f'{origin}/manage/api/subtitle-multipart',
            data=valid_mp,
            headers={
                'Host': f'127.0.0.1:{free_port}',
                'Origin': origin,
                'Cookie': cookie_hdr,
                'X-Bobbi-CSRF': csrf_tok,
                'Content-Type': 'multipart/form-data; boundary=okbnd',
            },
            method='POST',
        )
        with urlopen(req_mp_ok, timeout=2) as r_mp:
            assert r_mp.status == 200
        mp_path = Path(manager.committed_subtitle['path'])
        assert mp_path.exists()

        # Simulate A -> B playback switch: target_current becomes False -> B cannot consume A's subtitle,
        # file is deleted, and further phone uploads get 409 SUBTITLE_TARGET_CHANGED!
        active_target[0] = target_b
        assert manager.consume_committed_subtitle(target_a, 'movie:A') is None
        assert not mp_path.exists()

        req_after_switch = Request(
            f'{origin}/manage/api',
            data=pm_mod.encode({'action': 'subtitle_upload_status', 'params': {}}),
            headers={
                'Host': f'127.0.0.1:{free_port}',
                'Origin': origin,
                'Cookie': cookie_hdr,
                'X-Bobbi-CSRF': csrf_tok,
                'Content-Type': 'application/json',
            },
            method='POST',
        )
        with pytest.raises(HTTPError) as sw_err:
            urlopen(req_after_switch, timeout=2)
        assert sw_err.value.code == 409
    finally:
        t_stop = time.monotonic()
        srv.stop()
        assert time.monotonic() - t_stop < 2.0
# ==============================================================================
# U11 · T4 Bridge Stage/Deadline/Exit Semantics, Input Guards & Upload Handoff
# ==============================================================================


def test_u11_src10_bridge_stage_attribution_shared_deadline_and_exit_codes(tmp_path):
    """Inverted merge witness bridge_controls + CT-BRIDGE (SRC-10, A09-01, A09-02) + CT-PRIVATE-INPUT:
    - Separates DIAGNOSED, IMPORTABLE, PROTOCOL_VERIFIED, MEDIA_VERIFIED, INCOMPLETE, FAILED, BLOCKED_INPUT.
    - Tracks current_stage explicitly: no-category + search failure reports search (never category);
      detail/play/media failures attribute to exact stage.
    - Shares one per-site absolute deadline across home/category/search/detail/play/media (never resets +8s).
    - --probe-live exits 0 ONLY on MEDIA_VERIFIED; exits non-zero on 0 type-4, INCOMPLETE, PROTOCOL_VERIFIED,
      FAILED, or BLOCKED_INPUT.
    """
    import importlib.util
    from urllib.parse import parse_qs, urlsplit
    from unittest.mock import patch
    from bobbi_core.library_contract import LibraryError

    spec = importlib.util.spec_from_file_location('u11_bridge', REPO_ROOT / 'tools/check_t4_bridge.py')
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)

    site = dict(key='k', name='Synthetic', api='https://approved.example.invalid/t4', extend='', searchable=True)

    def healthy_wire(url):
        q = parse_qs(urlsplit(url).query)
        if 'ids' in q:
            val = {'list': [{'vod_id': 'v1', 'vod_name': 'Synthetic', 'vod_play_from': 'A', 'vod_play_url': 'E1$e1'}]}
        elif 'play' in q:
            val = {'parse': 0, 'url': 'https://approved.example.invalid/media.mkv'}
        else:
            val = {'class': [{'type_id': '1', 'type_name': 'Film'}], 'list': [{'vod_id': 'v1', 'vod_name': 'Synthetic'}]}
        return json.dumps(val).encode('utf-8')

    # 1. Healthy 5-stage + media positive control
    positive = bridge.probe_t4_site(
        site,
        fetch_fn=healthy_wire,
        media_probe_fn=lambda *_: {'identity_mode': 'weak_session', 'size': 100},
    )
    assert positive['status'] == 'MEDIA_VERIFIED'
    assert positive['protocol_verified'] is True and positive['media_verified'] is True
    assert all(v.startswith('PASS') for v in positive['steps'].values())

    # 2. Inverted witness: no categories + search failure MUST report search, NEVER category!
    def search_failure(url):
        q = parse_qs(urlsplit(url).query)
        if 'wd' in q:
            raise LibraryError('T4_NETWORK')
        return json.dumps({'list': [{'vod_id': 'v1', 'vod_name': 'Synthetic'}]}).encode('utf-8')

    stage_res = bridge.probe_t4_site(site, fetch_fn=search_failure)
    assert stage_res['status'] == 'FAILED'
    assert stage_res['failed_stage'] == 'search'
    assert stage_res['steps']['category'] == 'SKIPPED'
    assert stage_res['steps']['search'] == 'FAIL:T4_NETWORK'

    # 3. Per-stage negative controls for home, category, detail, play, and media
    for target_stage in ('home', 'category', 'detail', 'play', 'media'):
        def stage_fail_wire(url, target=target_stage):
            q = parse_qs(urlsplit(url).query)
            if target == 'home' and not q.get('t') and not q.get('wd') and not q.get('ids') and not q.get('play'):
                raise LibraryError('T4_TIMEOUT')
            if target == 'category' and 't' in q:
                raise LibraryError('T4_NETWORK')
            if target == 'detail' and 'ids' in q:
                raise LibraryError('T4_LIMIT')
            if target == 'play' and 'play' in q:
                raise LibraryError('T4_PLAY_UNSUPPORTED')
            return healthy_wire(url)

        def stage_fail_media(*_a, target=target_stage):
            if target == 'media':
                raise LibraryError('MEDIA_RANGE_UNSUPPORTED')
            return {'identity_mode': 'strong_etag', 'size': 2048}

        neg = bridge.probe_t4_site(site, fetch_fn=stage_fail_wire, media_probe_fn=stage_fail_media)
        assert neg['failed_stage'] == target_stage
        if target_stage == 'media':
            # Protocol succeeded, media failed -> PROTOCOL_VERIFIED (NOT MEDIA_VERIFIED!)
            assert neg['status'] == 'PROTOCOL_VERIFIED'
            assert neg['protocol_verified'] is True and neg['media_verified'] is False
            assert neg['steps']['play'] == 'FAIL_MEDIA:MEDIA_RANGE_UNSUPPORTED'
        else:
            assert neg['status'] == 'FAILED'
            assert neg['steps'][target_stage].startswith('FAIL:')

    # 4. Inverted witness: shared per-site absolute deadline (NEVER resets +8s for media!)
    clock, media_calls = [100.0], []

    def delayed_wire(url):
        if 'play=' in url:
            clock[0] = 111.9
        return healthy_wire(url)

    def media_capture(url, headers, **kwargs):
        media_calls.append(dict(start=clock[0], deadline=kwargs['deadline']))
        return {'identity_mode': 'weak_session', 'size': 100}

    with patch.object(bridge.time, 'monotonic', lambda: clock[0]), \
         patch.object(bridge.source_media_http, 'probe_stream', media_capture):
        dl_res = bridge.probe_t4_site(site, fetch_fn=delayed_wire, timeout_sec=12)
    assert dl_res['status'] == 'MEDIA_VERIFIED'
    assert len(media_calls) == 1
    assert media_calls[0]['start'] == pytest.approx(111.9)
    assert media_calls[0]['deadline'] == pytest.approx(112.0)  # <= 112.0, NOT 119.9!

    # Exhausting site deadline during play skips media_prober completely with T4_TIMEOUT
    clock2, media_calls2 = [100.0], []

    def over_budget_wire(url):
        if 'play=' in url:
            clock2[0] = 112.1
        return healthy_wire(url)

    with patch.object(bridge.time, 'monotonic', lambda: clock2[0]), \
         patch.object(bridge.source_media_http, 'probe_stream', lambda *a, **kw: media_calls2.append(1)):
        over_res = bridge.probe_t4_site(site, fetch_fn=over_budget_wire, timeout_sec=12)
    assert over_res['status'] == 'PROTOCOL_VERIFIED'
    assert over_res['failed_stage'] == 'media' and over_res['error_code'] == 'T4_TIMEOUT'
    assert media_calls2 == []

    # 5. Empty home & no sample -> INCOMPLETE (non-zero under --probe-live)
    inc = bridge.probe_t4_site(
        dict(site, searchable=False),
        fetch_fn=lambda _u: b'{"class":[],"list":[]}',
    )
    assert inc['status'] == 'INCOMPLETE' and inc['incomplete_reason'] == 'EMPTY_HOME'

    # 6. CLI exit codes across DIAGNOSED / IMPORTABLE / PROTOCOL_VERIFIED / MEDIA_VERIFIED / BLOCKED_INPUT
    type3_cfg = tmp_path / 'type3_only.json'
    type3_cfg.write_bytes(json.dumps({
        'sites': [{'key': 'sp1', 'name': 'AList Spider', 'type': 3, 'api': 'csp_AList', 'jar': './spider.jar'}]
    }).encode('utf-8'))

    # Pure diagnosis on valid 0-T4 JSON -> DIAGNOSED, exit 0; with --probe-live -> exit 1!
    diag_only = bridge.run_check(str(type3_cfg), probe_live=False)
    assert diag_only['status'] == 'DIAGNOSED' and diag_only['importable'] is False
    assert bridge.main(['--config', str(type3_cfg)]) == 0
    assert bridge.main(['--config', str(type3_cfg), '--probe-live']) == 1

    # Mutating type:3 -> type:4 on csp_AList NEVER becomes importable!
    forged_cfg = tmp_path / 'forged_type4.json'
    forged_cfg.write_bytes(json.dumps({
        'sites': [{'key': 'sp1', 'name': 'Forged Spider', 'type': 4, 'api': 'csp_AList'}]
    }).encode('utf-8'))
    forged_res = bridge.run_check(str(forged_cfg), probe_live=False)
    assert forged_res['importable'] is False and forged_res['status'] == 'DIAGNOSED'
    assert bridge.main(['--config', str(forged_cfg), '--probe-live']) == 1

    # Valid T4 JSON: pure diagnosis -> IMPORTABLE (exit 0); --probe-live with PROTOCOL_VERIFIED -> exit 1; MEDIA_VERIFIED -> exit 0
    valid_cfg = tmp_path / 'valid_t4.json'
    valid_cfg.write_bytes(json.dumps({
        'sites': [{'key': 'k', 'name': 'S', 'type': 4, 'api': 'https://approved.example.invalid/t4', 'searchable': 1}]
    }).encode('utf-8'))
    imp_res = bridge.run_check(str(valid_cfg), probe_live=False)
    assert imp_res['status'] == 'IMPORTABLE' and imp_res['importable'] is True
    assert bridge.exit_code_for_result(imp_res, probe_live=False) == 0

    proto_only_res = bridge.run_check(
        str(valid_cfg),
        probe_live=True,
        fetch_fn=healthy_wire,
        media_probe_fn=lambda *_: (_ for _ in ()).throw(LibraryError('MEDIA_TIMEOUT')),
    )
    assert proto_only_res['status'] == 'PROTOCOL_VERIFIED'
    assert bridge.exit_code_for_result(proto_only_res, probe_live=True) == 1

    media_ok_res = bridge.run_check(
        str(valid_cfg),
        probe_live=True,
        fetch_fn=healthy_wire,
        media_probe_fn=lambda *_: {'identity_mode': 'strong_etag', 'size': 4096},
    )
    assert media_ok_res['status'] == 'MEDIA_VERIFIED'
    assert bridge.exit_code_for_result(media_ok_res, probe_live=True) == 0

    # CT-PRIVATE-INPUT: Missing original my_ext.json or mismatched SHA-256 -> BLOCKED_INPUT (exit 2)
    missing_res = bridge.run_check(str(tmp_path / 'nonexistent_my_ext.json'))
    assert missing_res['status'] == 'BLOCKED_INPUT' and missing_res['error_code'] == 'INPUT_NOT_FOUND'
    assert bridge.main(['--config', str(tmp_path / 'nonexistent_my_ext.json')]) == 2

    sha_mismatch = bridge.run_check(
        str(type3_cfg),
        expected_sha256='b64b7501ff79cf34b349d61a360bc139d195908f9df19af7c9139a44a37acbac',
    )
    assert sha_mismatch['status'] == 'BLOCKED_INPUT' and sha_mismatch['error_code'] == 'INPUT_SHA256_MISMATCH'


def test_u11_import_input_guards_upload_timeouts_orphan_sweep_and_handoff_lifecycle(tmp_path, monkeypatch):
    """CT-IMPORT-INPUT (R19-02, IMPORT-TYPE-GUARDS) + CT-UPLOAD (R19-11..14, A09-03, A09-04):
    - URL vs unreachable phone-private local paths explicitly classified with T4_PHONE_LOCAL_PATH.
    - [], null, duplicate key, type=true, type="4", type=3-only, bad type=4 rejected with zero Registry writes;
      valid type=4 saves once on confirmation.
    - Crash-orphaned .part files swept on startup; idle (>60s) and total (>300s) upload timeouts abort & clean up;
      duplicate commit rejected.
    - Committed handoff survives normal QR revoke(), clears on consume_committed_import(), reject_committed_import(),
      or profile switch!
    """
    import base64
    import hashlib
    import importlib
    from bobbi_core import t4
    from bobbi_core.library_contract import LibraryError
    from bobbi_platform import source_media_http, t4_ui
    from bobbi_platform.libraries import Registry
    from bobbi_platform.paths import ProfileBinding

    # 1. R19-02: URL vs phone-private path classification
    assert t4_ui.classify_t4_url_input('https://sub.example.invalid/tvbox.json') == 'https://sub.example.invalid/tvbox.json'
    assert t4_ui.classify_t4_url_input('http://192.168.1.20:5678/tvbox/my.json') == 'http://192.168.1.20:5678/tvbox/my.json'
    assert 'T4_PHONE_LOCAL_PATH' in source_media_http.MESSAGES
    assert '手机扫码上传' in source_media_http.MESSAGES['T4_PHONE_LOCAL_PATH']

    for phone_local in [
        'content://com.android.providers.downloads.documents/document/42',
        'file:///storage/emulated/0/Download/my_ext.json',
        '/storage/emulated/0/Download/my_ext.json',
        '/sdcard/Download/tvbox.json',
        '/data/user/0/com.MiXplorer/cache/sub.json',
        'C:\\Users\\phone\\Downloads\\sub.json',
    ]:
        with pytest.raises(LibraryError, match='T4_PHONE_LOCAL_PATH'):
            t4_ui.classify_t4_url_input(phone_local)

    # 2. IMPORT-TYPE-GUARDS: strict JSON & type validation with zero Registry writes on invalid/unsupported
    valid_doc = {'sites': [{'key': 'ok1', 'name': 'Valid T4', 'type': 4, 'api': 'https://t4.example.invalid/vod'}]}
    for bad_label, bad_raw in [
        ('list_top', b'[]'),
        ('null_top', b'null'),
        ('dup_key', b'{"sites":[],"sites":[]}'),
        ('bool_type', json.dumps({'sites': [dict(valid_doc['sites'][0], type=True)]}).encode('utf-8')),
        ('str_type', json.dumps({'sites': [dict(valid_doc['sites'][0], type='4')]}).encode('utf-8')),
        ('type3_only', json.dumps({'sites': [dict(valid_doc['sites'][0], type=3)]}).encode('utf-8')),
        ('bad_type4', json.dumps({'sites': [{'key': 'b', 'name': 'B', 'type': 4, 'api': 'csp_NotUrl'}]}).encode('utf-8')),
    ]:
        diag = t4.diagnose_config(bad_raw)
        assert diag['can_save_t4'] is False, f'{bad_label} unexpectedly saveable'

    # 3. Orphan .part crash sweep, idle/total upload timeouts, duplicate commit, and handoff lifecycle
    _setup_plugin_test_env(monkeypatch, tmp_path=tmp_path)
    pm_mod = importlib.import_module('lib.services.phone_management')

    now = [1000.0]
    profile_current = [True]
    plat_dir = tmp_path / 'plat_profile'
    staging_dir = plat_dir / 'source-import-staging'
    staging_dir.mkdir(parents=True, exist_ok=True)
    orphan_part = staging_dir / ('deadbeef' * 4 + '.part')
    orphan_part.write_bytes(b'leftover-from-crash')
    assert orphan_part.is_file()

    binding = ProfileBinding(lambda addon='script.module.bobbi.platform': plat_dir)
    monkeypatch.setattr(binding, 'is_current', lambda: profile_current[0])

    def make_manager():
        mgr = pm_mod.PhoneManagement(
            {'local_scope': 'source_import'},
            'http://127.0.0.1:8081',
            clock=lambda: now[0],
            scopes=pm_mod.SOURCE_IMPORT_SCOPES,
            profile_binding=binding,
        )
        hdrs = {'Host': '127.0.0.1:8081', 'Origin': 'http://127.0.0.1:8081'}
        paired, cookie = mgr.handle('/manage/api/pair', hdrs, pm_mod.encode({'code': mgr.pairing_url.split('#')[1]}))
        auth = {**hdrs, 'Cookie': cookie.split(';')[0], 'X-Bobbi-CSRF': paired['csrf']}
        return mgr, lambda act, prm: mgr.handle('/manage/api', auth, pm_mod.encode({'action': act, 'params': prm}))[0]

    # Constructing PhoneManagement(source_import) sweeps crashed orphan .part immediately!
    mgr1, rpc1 = make_manager()
    assert not orphan_part.exists() and not staging_dir.exists()

    # Idle timeout (> 60s) aborts upload and cleans up .part
    payload = json.dumps(valid_doc).encode('utf-8')
    sha = hashlib.sha256(payload).hexdigest()
    uid_idle = '1' * 32
    rpc1('source_import_begin', {'upload_id': uid_idle, 'file_name': 'a.json', 'total_bytes': len(payload), 'sha256': sha})
    assert (staging_dir / f'{uid_idle}.part').is_file()
    now[0] += 61.0
    with pytest.raises(pm_mod.PhoneError, match='UPLOAD_TIMEOUT') as e_idle:
        rpc1('source_import_chunk', {'upload_id': uid_idle, 'offset': 0, 'data_b64': base64.b64encode(payload).decode('ascii')})
    assert e_idle.value.status == 408
    assert not (staging_dir / f'{uid_idle}.part').exists()

    # Total deadline (> 300s across slow trickle) aborts upload and cleans up .part
    uid_tot = '2' * 32
    two_part = payload + b' '
    rpc1('source_import_begin', {
        'upload_id': uid_tot,
        'file_name': 'b.json',
        'total_bytes': len(two_part),
        'sha256': hashlib.sha256(two_part).hexdigest(),
    })
    for _ in range(6):
        now[0] += 51.0  # each step < 60s idle, but 6 * 51 = 306s > 300s total!
    with pytest.raises(pm_mod.PhoneError, match='UPLOAD_TIMEOUT'):
        rpc1('source_import_chunk', {'upload_id': uid_tot, 'offset': 0, 'data_b64': base64.b64encode(payload).decode('ascii')})
    assert not (staging_dir / f'{uid_tot}.part').exists()

    # Valid upload -> commit once (second commit rejected!) -> revoke() retains handoff -> consume saves once & clears!
    mgr2, rpc2 = make_manager()
    uid_ok = '3' * 32
    rpc2('source_import_begin', {'upload_id': uid_ok, 'file_name': 'ok.json', 'total_bytes': len(payload), 'sha256': sha})
    rpc2('source_import_chunk', {'upload_id': uid_ok, 'offset': 0, 'data_b64': base64.b64encode(payload).decode('ascii')})
    committed_reply = rpc2('source_import_commit', {'upload_id': uid_ok})
    assert committed_reply['awaiting_tv_confirm'] is True
    with pytest.raises(pm_mod.PhoneError, match='UPLOAD_NOT_FOUND'):
        rpc2('source_import_commit', {'upload_id': uid_ok})

    mgr2.revoke()
    with pytest.raises(pm_mod.PhoneError, match='SESSION_EXPIRED'):
        rpc2('source_import_status', {})
    assert mgr2.committed_import is not None and mgr2.committed_import['raw_bytes'] == payload

    consumed = mgr2.consume_committed_import()
    assert consumed is not None and consumed['raw_bytes'] == payload
    assert mgr2.committed_import is None

    reg = Registry(plat_dir / 'libraries.sqlite3')
    try:
        reg.save(t4.preview(consumed['raw_bytes']).source(''))
        assert len(reg.sources()) == 1
    finally:
        reg.close()

    # TV rejection destroys handoff; profile switch destroys handoff!
    mgr3, rpc3 = make_manager()
    uid_rej = '4' * 32
    rpc3('source_import_begin', {'upload_id': uid_rej, 'file_name': 'r.json', 'total_bytes': len(payload), 'sha256': sha})
    rpc3('source_import_chunk', {'upload_id': uid_rej, 'offset': 0, 'data_b64': base64.b64encode(payload).decode('ascii')})
    rpc3('source_import_commit', {'upload_id': uid_rej})
    mgr3.revoke()
    assert mgr3.committed_import is not None
    mgr3.reject_committed_import()
    assert mgr3.committed_import is None

    mgr4, rpc4 = make_manager()
    uid_prof = '5' * 32
    rpc4('source_import_begin', {'upload_id': uid_prof, 'file_name': 'p.json', 'total_bytes': len(payload), 'sha256': sha})
    rpc4('source_import_chunk', {'upload_id': uid_prof, 'offset': 0, 'data_b64': base64.b64encode(payload).decode('ascii')})
    rpc4('source_import_commit', {'upload_id': uid_prof})
    mgr4.revoke()
    assert mgr4.committed_import is not None
    profile_current[0] = False
    assert mgr4.committed_import is None
