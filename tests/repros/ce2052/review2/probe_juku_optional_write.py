"""Independent Juku post-resolve metadata boundary; real SQLite and Binding.

The nine primary cases use a remote resolve double and a scheduling/IO pause
after an optional Cache open. No local error is injected; production guards
decide the observed exception. Five separate controls use actual
Client.get/resolve, AccountManager and Binding, with only the remote opener
response and scheduling pause replaced. Credentials are generated test values
in temporary files, never real accounts. No device/network/playback is used.
"""
import argparse
from contextlib import closing
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from unittest.mock import patch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect', choices=('current-bug', 'fixed'), default='current-bug')
    parser.add_argument('--include-default-budget', action='store_true')
    args = parser.parse_args()
    root = args.repo.resolve()
    for name in ('script.module.bobbi.core', 'script.module.bobbi.catalog', 'script.module.bobbi.platform'):
        sys.path.insert(0, str(root / 'addons' / name / 'lib'))
    from bobbi_core import juku_catalog as cat
    from bobbi_catalog.api import ShareError, Client, valid_cdn
    from bobbi_core.share_stream import Binding
    from bobbi_platform.account_manager import AccountManager
    source = root / 'addons/script.module.bobbi.core/lib/bobbi_core/juku_catalog.py'
    receipt = dict(schema=1, head=subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip(),
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), scope=__doc__, cases=[], controls=[])
    experiments = [('success', 0, 0.3, 0), ('share_revoked', 0, 0.3, 0),
                   ('identity_changed', 0, 0.3, 0), ('network_timeout', 0, 0.3, 0),
                   ('success', 0.4, 0.3, 1), ('success', 0.4, 0.3, 2),
                   ('share_revoked', 0.4, 0.3, 1), ('identity_changed', 0.4, 0.3, 1)]
    if args.include_default_budget:
        experiments.append(('success', 8.1, None, 1))
    with tempfile.TemporaryDirectory(prefix='ce2051-juku-write-') as temporary:
        for index, (mode, pause, budget, pause_open) in enumerate(experiments):
            state = Path(temporary) / str(index)
            spec = cat._spec(dict(tmdb_id=101, mode='movies', year=2024, aliases=['Audit Fixture']))
            raw = dict(tmdbId=101, typeId=1, year=2024, title='Audit Fixture', id=1, vodId=1)
            link = dict(url='https://115.com/s/sfixture', fileId='123',
                fileName='Audit.Fixture.2024.1080p.mkv', fileSize=1024, parentFolderId='8')
            row = cat._bound(cat._row(raw, link, 'shared:fixture'), spec)
            with closing(cat.Cache(state)) as cache:
                cache.replace_library('fixture', 1, [row])
                cache.remember([row], spec)
            identity = dict(locator='am6bjuku://' + row['key'], guid='juku:' + row['key'],
                title=row['name'], size=row['size'], media=spec['media_key'])
            observations = dict(api_calls=0, post_api_cache_opens=0, pauses=0)
            real_init = cat.Cache.__init__
            class API:
                account_scope = dict(account_id='fixture', epoch=1, authenticated=True)
                def resolve(self, *unused):
                    observations['api_calls'] += 1
                    observations['remote_finished'] = time.monotonic()
                    if mode != 'success':
                        raise ShareError(mode, http_status=403, api_code=4100010)
                    return 'https://fixture.115cdn.com/video.mkv|User-Agent=fixture'
            def delayed_init(cache, *pos, **kw):
                real_init(cache, *pos, **kw)
                if observations['api_calls']:
                    observations['post_api_cache_opens'] += 1
                    if pause and observations['post_api_cache_opens'] == pause_open:
                        observations['pauses'] += 1
                        time.sleep(pause)
            def resolve(body):
                kwargs = dict(state=state, client=API())
                if budget is not None:
                    kwargs['deadline'] = time.monotonic() + budget
                return cat.resolve(**identity, **kwargs)
            binding = Binding(dict(identity, request_id='a' * 32), resolve,
                              lambda value:value.startswith('https://fixture.115cdn.com/'))
            started = time.monotonic()
            with patch.object(cat.Cache, '__init__', delayed_init):
                try:
                    result = binding.grant()
                    outcome, exception_type, api_code = ('success' if result == 'https://fixture.115cdn.com/video.mkv|User-Agent=fixture' else 'wrong_url'), None, None
                except Exception as error:
                    outcome = getattr(error, 'code', type(error).__name__)
                    exception_type, api_code = type(error).__name__, getattr(error, 'api_code', None)
            observations['remote_completed_after_seconds'] = observations.pop('remote_finished') - started
            receipt['cases'].append(dict(api_outcome=mode, pause_seconds=pause,
                explicit_deadline_seconds=budget, default_product_deadline_used=budget is None,
                pause_on_post_api_cache_open=pause_open, observed=outcome,
                exception_type=exception_type, api_code=api_code,
                elapsed_seconds=time.monotonic()-started, binding_address_set=binding.address is not None,
                binding_outcome=binding.grant_outcome(), **observations))
        # Separate controls use the actual Client.get/resolve and AccountManager.
        # Only the HTTP opener response and deliberate scheduling pause are doubles.
        for mode in ('remote_deadline', 'cancel', 'switch', 'logout', 'renew'):
            state = Path(temporary) / ('control-' + mode)
            def credential(user='123', suffix='A1'):
                return dict(app='os_linux', cookies=dict(UID=user+'_'+suffix,
                    CID='fixture-cid', SEID='fixture-seid'))
            manager = AccountManager(state / 'account.json')
            scope = manager.install(credential(), manager.snapshot())
            spec = cat._spec(dict(tmdb_id=101, mode='movies', year=2024, aliases=['Audit Fixture']))
            row = cat._bound(cat._row(dict(tmdbId=101, typeId=1, year=2024,
                title='Audit Fixture', id=1, vodId=1), dict(url='https://115.com/s/sfixture',
                fileId='123', fileName='Audit.Fixture.2024.1080p.mkv', fileSize=1024,
                parentFolderId='8'), 'shared:fixture'), spec)
            with closing(cat.Cache(state)) as cache:
                cache.replace_library('fixture', 1, [row])
                cache.remember([row], spec)
            identity = dict(locator='am6bjuku://' + row['key'], guid='juku:' + row['key'],
                title=row['name'], size=row['size'], media=spec['media_key'])
            observations = dict(api_calls=0, post_api_cache_opens=0)
            body = json.dumps(dict(state=True, data=dict(fid='123', fn=row['name'],
                fs=1024, url='https://fixture.115cdn.com/video.mkv'))).encode()
            class Response(io.BytesIO):
                headers = {'Content-Length': str(len(body))}
                def read1(self, size=-1):
                    if mode == 'remote_deadline' and self.tell() == 0:
                        time.sleep(.4)
                    return self.read(size)
            class Opener:
                def open(self, request, timeout):
                    observations['api_calls'] += 1
                    return Response(body)
            api = Client(session=manager.credentials(scope), account_scope=scope, opener=Opener())
            def resolve(body, captured_scope):
                return cat.resolve(**identity, state=state, client=api, deadline=time.monotonic()+.3)
            binding = Binding(dict(identity, request_id='b'*32), resolve,
                              valid_cdn, account=manager, scope=scope)
            real_init = cat.Cache.__init__
            def transition_init(cache, *pos, **kw):
                real_init(cache, *pos, **kw)
                if observations['api_calls']:
                    observations['post_api_cache_opens'] += 1
                    if observations['post_api_cache_opens'] == 1:
                        if mode == 'cancel': binding.revoke()
                        elif mode == 'switch': manager.install(credential('456'), scope)
                        elif mode == 'logout': manager.logout(scope)
                        elif mode == 'renew': manager.install(credential(suffix='A2'), scope)
                        time.sleep(.4 if mode in ('cancel', 'switch', 'logout') else .05)
            started = time.monotonic()
            with patch.object(cat.Cache, '__init__', transition_init):
                try:
                    result = binding.grant()
                    outcome, exception_type = 'success', None
                except Exception as error:
                    outcome = getattr(error, 'code', str(error))
                    exception_type = type(error).__name__
            address_set = binding.address is not None
            if mode == 'remote_deadline':
                passed = outcome == 'deadline' and not address_set and observations['post_api_cache_opens'] == 0
            elif mode == 'renew':
                passed = outcome == 'success' and address_set and manager.is_current(scope)
            else:
                passed = outcome != 'success' and not address_set and binding.cancelled()
            receipt['controls'].append(dict(mode=mode, observed=outcome,
                exception_type=exception_type, binding_address_set=address_set,
                current_scope_matches=manager.is_current(scope), binding_cancelled=binding.cancelled(),
                elapsed_seconds=time.monotonic()-started, passed=passed, **observations))
    violations = [index for index, row in enumerate(receipt['cases'])
        if row['observed'] != row['api_outcome'] or row['api_calls'] != 1
        or (row['api_outcome'] == 'success' and not row['binding_address_set'])
        or (row['api_outcome'] != 'success' and (row['exception_type'] != 'ShareError'
            or row['api_code'] != 4100010 or row['binding_address_set']))]
    receipt['violations'] = violations
    receipt['expect'] = args.expect
    receipt['contract_passed'] = not violations and all(row['passed'] and row['api_calls'] == 1 for row in receipt['controls'])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(receipt, indent=2))
    if args.expect == 'fixed':
        return int(not receipt['contract_passed'])
    return int(not (4 in violations and all(row['api_calls'] == 1 for row in receipt['cases'])
                   and all(row['passed'] and row['api_calls'] == 1 for row in receipt['controls'])))


if __name__ == '__main__':
    raise SystemExit(main())
