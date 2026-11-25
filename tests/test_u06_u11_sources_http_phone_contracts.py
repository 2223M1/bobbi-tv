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

    # Bootstrap Kodi doubles via private_baseline conftest if not already loaded
    if 'xbmc' not in sys.modules or not hasattr(sys.modules['xbmc'], 'LOGINFO'):
        import runpy
        runpy.run_path(str(REPO_ROOT / 'tests/private_baseline/conftest.py'))
    sys.path.insert(0, str(REPO_ROOT / 'addons/plugin.video.bobbi'))
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
