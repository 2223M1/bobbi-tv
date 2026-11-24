"""Regression coverage for R03 (SRC-R2-01): cloud pagination completeness proof."""
from contextlib import nullcontext
from threading import Event

import pytest

from bobbi_platform import pan_123, pan_guangya, pan_mobile, pan_tianyi
from bobbi_platform.account_manager import AccountManager
from bobbi_platform.catalog_service import CatalogService
from bobbi_platform.catalog_ui import SCAN_REASONS
from bobbi_platform.libraries import Registry
from bobbi_platform.pan_accounts import PanAccounts, PanError
from bobbi_platform.pan_quark_uc import Client as QuarkUCClient
from bobbi_platform.pan_service import PanService


class QuarkUCWire:
    operation = None

    def __init__(self):
        self.mode = 'complete_21'
        self.calls = []
        self.entered_page2 = Event()
        self.release_page2 = Event()
        self.release_page2.set()

    def budget(self, seconds):
        return nullcontext()

    def request(self, url, query=None, body=None):
        if self.operation is not None:
            self.operation.consume_request()
        page, size = query['_page'], query['_size']
        if page == 2:
            self.entered_page2.set()
            assert self.release_page2.wait(3)
        total = 21
        if self.mode == 'complete_20':
            total = 20
        indices = list(range((page - 1) * size, min(page * size, total)))
        if self.mode == 'short_first_page' and page == 1:
            indices = indices[:5]
        elif self.mode == 'total_drift' and page == 2:
            total = 22
            indices = [20, 21]
        elif self.mode == 'cross_page_duplicate' and page == 2:
            indices = [0]
        self.calls.append((page, size, len(indices), total))
        rows = [
            dict(fid='file%03d' % i, file_name='Film.%03d.2024.mkv' % i, file=True, size=1024)
            for i in indices
        ]
        return dict(code=0, status=200, data=dict(list=rows), metadata={'_total': total})


def _make_cloud_catalog(tmp_path, provider, profile_current=lambda: True):
    wire = QuarkUCWire()
    native = PanAccounts(tmp_path / 'native.json', {provider: lambda value: ('user-1', value)})
    expected = native.install({'synthetic': True}, native.snapshot(provider))
    pans = PanService(
        tmp_path,
        AccountManager(tmp_path / '115.json'),
        accounts=native,
        client_factory=lambda key, saved: QuarkUCClient(key, session=wire),
    )
    registry = Registry(tmp_path / 'libraries.sqlite3')
    directory = registry.save_directory('Cloud Movies', expected, '0')
    registry.close()
    catalog = CatalogService(tmp_path, pans, profile_current=profile_current)
    return catalog, pans, native, wire, expected, directory['id']


def _run_scan(catalog, expected, source_id):
    task = catalog.start_scan(expected, source_id)['task_id']
    catalog.worker.join(10)
    assert not catalog.worker.is_alive()
    job = catalog.index.jobs(expected, task=task)['items'][0]
    source = catalog.source_observation(expected, source_id)
    counts = dict(
        catalog.index.db.execute(
            'SELECT available, count(*) FROM memberships WHERE source=? GROUP BY available',
            (source_id,),
        ).fetchall()
    )
    return job, source, counts


@pytest.mark.parametrize('provider', ['quark', 'uc'])
def test_r03_01_02_03_short_page_preserves_members_and_complete_scan_withdraws_deleted(tmp_path, provider):
    catalog, pans, _, wire, expected, source_id = _make_cloud_catalog(tmp_path, provider)
    try:
        job1, source1, counts1 = _run_scan(catalog, expected, source_id)
        assert job1['state'] == 'completed'
        assert source1['coverage'] == 'complete'
        assert counts1 == {1: 21}

        first_id = catalog.index.query(expected)['items'][0]['entity_id']
        catalog.index.apply(
            expected,
            'a' * 32,
            [
                dict(
                    action='confirm',
                    file_id=first_id,
                    expected_revision=0,
                    mapping=dict(
                        kind='custom',
                        title='Pinned Manual Title',
                        tmdb_id=None,
                        season=None,
                        episode=None,
                        version=None,
                    ),
                )
            ],
        )

        wire.mode = 'short_first_page'
        job2, source2, counts2 = _run_scan(catalog, expected, source_id)
        assert job2['state'] == 'interrupted'
        assert job2['result_summary'] == 'PAN_INCOMPLETE_PAGE'
        assert source2['coverage'] == 'partial'
        assert counts2 == {1: 21}
        assert catalog.index.item(expected, first_id)['mapping']['title'] == 'Pinned Manual Title'

        wire.mode = 'complete_20'
        job3, source3, counts3 = _run_scan(catalog, expected, source_id)
        assert job3['state'] == 'completed'
        assert source3['coverage'] == 'complete'
        assert counts3 == {1: 20, 0: 1}
    finally:
        catalog.close()
        pans.close()


@pytest.mark.parametrize('fault,expected_state,expected_reason', [
    ('total_drift', 'interrupted', 'PAN_PAGE_EXPIRED'),
    ('cross_page_duplicate', 'interrupted', 'PAN_PAGE_EXPIRED'),
])
def test_r03_04_duplicate_and_total_drift_never_withdraw_unseen_members(tmp_path, fault, expected_state, expected_reason):
    catalog, pans, _, wire, expected, source_id = _make_cloud_catalog(tmp_path, 'quark')
    try:
        job1, _, counts1 = _run_scan(catalog, expected, source_id)
        assert job1['state'] == 'completed' and counts1 == {1: 21}

        wire.mode = fault
        job2, source2, counts2 = _run_scan(catalog, expected, source_id)
        assert job2['state'] == expected_state
        assert job2['result_summary'] == expected_reason
        assert expected_reason in SCAN_REASONS and SCAN_REASONS[expected_reason]
        assert source2['coverage'] == 'partial'
        assert counts2 == {1: 21}
    finally:
        catalog.close()
        pans.close()


def test_r03_05_shared_token_adapters_total_proof_and_cursor_short_page():
    class StubSession:
        def __init__(self, *replies, operation=None):
            self.replies = list(replies)
            self.operation = operation

        def request(self, *args, **kwargs):
            return self.replies.pop(0)

    c123_short = dict(
        code=0,
        data=dict(
            Total=21,
            InfoList=[dict(FileId=i + 1, FileName='Ep%d.mkv' % i, Size=100, Type=0, Etag='a' * 32) for i in range(5)],
        ),
    )
    client_123 = pan_123.Client(
        dict(provider='123', subject='12345', access_token='tok', device_id='dev1'),
        session=StubSession(c123_short),
    )
    with pytest.raises(PanError, match='PAN_INCOMPLETE_PAGE'):
        client_123.list_files(page=1, size=20)

    tianyi_short = dict(
        res_code=0,
        fileListAO=dict(
            count=21,
            folderList=[],
            fileList=[dict(id=i + 1, name='Ep%d.mkv' % i, size=100) for i in range(5)],
        ),
    )
    client_189 = pan_tianyi.Client(
        dict(
            provider='189',
            subject='user189',
            session_key='sk',
            cookies=[dict(name='COOKIE_LOGIN_USER', value='fixture', domain='.cloud.189.cn', path='/')],
        ),
        session=StubSession(tianyi_short),
    )
    with pytest.raises(PanError, match='PAN_INCOMPLETE_PAGE'):
        client_189.list_files(page=1, size=20)

    guangya_short = dict(
        code=0,
        data=dict(
            total=21,
            list=[dict(fileId='f%d' % i, fileName='Ep%d.mkv' % i, fileSize=100, resType=1, utime=1) for i in range(5)],
        ),
    )
    client_gy = pan_guangya.Client(
        dict(provider='guangya', subject='u1', access_token='tok', refresh_token='ref', expires_at=9999999999, device_id='d1'),
        session=StubSession(guangya_short),
        clock=lambda: 1000,
    )
    with pytest.raises(PanError, match='PAN_INCOMPLETE_PAGE'):
        client_gy.list_files(page=1, size=20)

    class ScanOp:
        kind = 'scan'

    op = ScanOp()
    pds_saved = dict(
        provider='139',
        subject='13800000000',
        auth_token='tok',
        device_id='dev139',
        pds=True,
        route='https://personal-kd-njs.yun.139.com/hcy',
        user_domain_id='uid1',
    )
    pds_page1 = dict(
        code='0000',
        data=dict(
            nextPageCursor='cursor-2',
            items=[dict(fileId='m%d' % i, name='Ep%d.mkv' % i, size=100, type='file', updatedAt='2026-11-24T00:00:00Z') for i in range(5)],
        ),
    )
    pds_page2 = dict(
        code='0000',
        data=dict(
            nextPageCursor='',
            items=[dict(fileId='m9', name='Ep9.mkv', size=100, type='file', updatedAt='2026-11-24T00:00:00Z')],
        ),
    )
    pds_dup = dict(
        code='0000',
        data=dict(
            nextPageCursor='',
            items=[dict(fileId='m0', name='Ep0.mkv', size=100, type='file', updatedAt='2026-11-24T00:00:00Z')],
        ),
    )
    mobile_ok = pan_mobile.Client(pds_saved, session=StubSession(pds_page1, pds_page2, operation=op))
    first = mobile_ok.list_files(page=1, size=20)
    assert len(first['items']) == 5 and first['has_more'] is True and first['next_cursor'] == 'cursor-2'
    second = mobile_ok.list_files(page=2, size=20, cursor='cursor-2')
    assert len(second['items']) == 1 and second['has_more'] is False

    op_dup = ScanOp()
    mobile_dup = pan_mobile.Client(pds_saved, session=StubSession(pds_page1, pds_dup, operation=op_dup))
    mobile_dup.list_files(page=1, size=20)
    with pytest.raises(PanError, match='PAN_PAGE_EXPIRED'):
        mobile_dup.list_files(page=2, size=20, cursor='cursor-2')


@pytest.mark.parametrize('interruption', ['cancel', 'profile_switch', 'account_revoke'])
def test_r03_06_cancel_profile_and_revoke_mid_pagination_isolate_scopes(tmp_path, interruption):
    active_profile = [True]
    catalog, pans, native, wire, expected, source_id = _make_cloud_catalog(
        tmp_path, 'quark', profile_current=lambda: active_profile[0]
    )
    try:
        job1, _, counts1 = _run_scan(catalog, expected, source_id)
        assert job1['state'] == 'completed' and counts1 == {1: 21}

        wire.mode = 'complete_20'
        wire.entered_page2.clear()
        wire.release_page2.clear()
        wire.mode = 'complete_21'
        task = catalog.start_scan(expected, source_id)['task_id']
        assert wire.entered_page2.wait(3)

        if interruption == 'cancel':
            catalog.dispatch('catalog_cancel', dict(expected=expected, task_id=task))
        elif interruption == 'profile_switch':
            active_profile[0] = False
        else:
            native.logout(expected)

        wire.release_page2.set()
        catalog.worker.join(5)
        assert not catalog.worker.is_alive()

        state_row = catalog.index._scan(task)
        if interruption == 'cancel':
            assert state_row['state'] == 'canceled'
        else:
            assert state_row['state'] == 'interrupted'
        counts_after = dict(
            catalog.index.db.execute(
                'SELECT available, count(*) FROM memberships WHERE source=? GROUP BY available',
                (source_id,),
            ).fetchall()
        )
        assert counts_after == {1: 21}
    finally:
        wire.release_page2.set()
        catalog.close()
        pans.close()
