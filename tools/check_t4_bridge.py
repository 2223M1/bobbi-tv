"""Read-only validator for TVBox / T4 configurations and live T4 HTTP bridges (R19 / REV-12 / U11).

Never executes arbitrary type-3 Spider JAR/JS/Python payloads and never mutates local settings.
Separates DIAGNOSED, IMPORTABLE, PROTOCOL_VERIFIED, MEDIA_VERIFIED, INCOMPLETE, FAILED, and BLOCKED_INPUT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
for rel in ('addons/script.module.bobbi.core/lib', 'addons/script.module.bobbi.platform/lib'):
    p = str(ROOT / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from bobbi_core import t4  # noqa: E402
from bobbi_core.library_contract import LibraryError  # noqa: E402
from bobbi_platform import source_media_http, t4_http  # noqa: E402


def _require_budget(deadline: float) -> float:
    rem = deadline - time.monotonic()
    if rem <= 0:
        raise LibraryError('T4_TIMEOUT')
    return rem


def probe_t4_site(site: dict, *, fetch_fn=None, media_probe_fn=None, timeout_sec: float = 12.0) -> dict:
    """Validate one type-4 site across home, category, optional search, detail, play, and media under one deadline."""
    deadline = time.monotonic() + float(timeout_sec)
    site_headers = site.get('headers')

    def default_fetch(url: str) -> bytes:
        _require_budget(deadline)
        return t4_http.read(
            url,
            deadline,
            lambda: False,
            headers=site_headers,
            expected_origin=site['api'],
        )

    def run_fetch(url: str) -> bytes:
        _require_budget(deadline)
        if fetch_fn is not None:
            return fetch_fn(url)
        return default_fetch(url)

    def run_media_probe(url: str, hdrs: dict) -> dict:
        _require_budget(deadline)
        if media_probe_fn is not None:
            return media_probe_fn(url, hdrs)
        return source_media_http.probe_stream(
            url,
            {'User-Agent': 'BobbiTV', **hdrs},
            max_redirects=3,
            deadline=deadline,
        )

    client = t4.Client(site, run_fetch)
    searchable = bool(site.get('searchable'))
    steps = {
        'home': 'PENDING',
        'category': 'PENDING',
        'search': 'PENDING' if searchable else 'SKIPPED',
        'detail': 'PENDING',
        'play': 'PENDING',
    }
    current_stage = 'home'
    failed_stage = None
    error_code = None
    incomplete_reason = None
    protocol_verified = False
    media_verified = False
    media_step = 'PENDING'

    try:
        current_stage = 'home'
        home = client.home()
        classes = home.get('class') if isinstance(home.get('class'), list) else []
        home_list = home.get('list') if isinstance(home.get('list'), list) else []
        steps['home'] = 'PASS'

        sample_vod = None
        if classes and isinstance(classes[0], dict) and classes[0].get('type_id') is not None:
            current_stage = 'category'
            cat_doc = client.category(t4.identifier(classes[0]['type_id']), 1)
            cat_list = cat_doc.get('list') if isinstance(cat_doc.get('list'), list) else []
            steps['category'] = 'PASS'
            if cat_list and isinstance(cat_list[0], dict) and cat_list[0].get('vod_id') is not None:
                sample_vod = t4.identifier(cat_list[0].get('vod_id'))
        else:
            steps['category'] = 'SKIPPED'

        if sample_vod is None and home_list and isinstance(home_list[0], dict) and home_list[0].get('vod_id') is not None:
            sample_vod = t4.identifier(home_list[0].get('vod_id'))

        if searchable:
            current_stage = 'search'
            search_doc = client.search('a', 1)
            search_list = search_doc.get('list') if isinstance(search_doc, dict) and isinstance(search_doc.get('list'), list) else []
            steps['search'] = 'PASS'
            if sample_vod is None and search_list and isinstance(search_list[0], dict) and search_list[0].get('vod_id') is not None:
                sample_vod = t4.identifier(search_list[0].get('vod_id'))

        if not classes and not home_list and sample_vod is None:
            incomplete_reason = 'EMPTY_HOME'
            steps['detail'] = 'INCOMPLETE:EMPTY_HOME'
            steps['play'] = 'INCOMPLETE:EMPTY_HOME'
            media_step = 'SKIPPED'
        elif sample_vod is None:
            incomplete_reason = 'NO_SAMPLE_VOD'
            steps['detail'] = 'INCOMPLETE:NO_SAMPLE'
            steps['play'] = 'INCOMPLETE:NO_SAMPLE'
            media_step = 'SKIPPED'
        else:
            current_stage = 'detail'
            lines = client.detail(sample_vod)
            steps['detail'] = 'PASS'
            if not lines or not lines[0][1]:
                incomplete_reason = 'NO_PLAYABLE_EPISODE'
                steps['play'] = 'INCOMPLETE:NO_EPISODES'
                media_step = 'SKIPPED'
            else:
                line_name, episodes = lines[0]
                _, ep_id = episodes[0]
                current_stage = 'play'
                play_url, play_hdrs = client.play(line_name, ep_id)
                protocol_verified = True

                current_stage = 'media'
                probed = run_media_probe(play_url, play_hdrs)
                media_verified = True
                media_step = f"PASS ({probed['identity_mode']}, {probed['size']}B)"
                steps['play'] = f"PASS ({probed['identity_mode']}, {probed['size']}B)"
    except LibraryError as exc:
        error_code = exc.code
        failed_stage = current_stage
        if current_stage == 'media':
            media_step = f'FAIL:{exc.code}'
            steps['play'] = f'FAIL_MEDIA:{exc.code}'
        elif current_stage in steps:
            steps[current_stage] = f'FAIL:{exc.code}'

    if media_verified:
        site_status = 'MEDIA_VERIFIED'
    elif protocol_verified and failed_stage == 'media':
        site_status = 'PROTOCOL_VERIFIED'
    elif incomplete_reason is not None and error_code is None:
        site_status = 'INCOMPLETE'
    else:
        site_status = 'FAILED'

    u = urlsplit(site['api'])
    return {
        'key': site['key'],
        'name': site['name'],
        'origin': f'{u.scheme}://{u.netloc}',
        'searchable': searchable,
        'status': site_status,
        'protocol_verified': protocol_verified,
        'media_verified': media_verified,
        'failed_stage': failed_stage,
        'incomplete_reason': incomplete_reason,
        'media_step': media_step,
        'steps': steps,
        'error_code': error_code,
    }


def run_check(
    config_source: str,
    *,
    base_url: str = '',
    probe_live: bool = False,
    expected_sha256: str = '',
    timeout_sec: float = 12.0,
    fetch_fn=None,
    media_probe_fn=None,
) -> dict:
    if config_source.startswith(('http://', 'https://')):
        try:
            norm_url = t4.endpoint(config_source)
            raw = (fetch_fn(norm_url) if fetch_fn is not None else t4_http.read(norm_url, time.monotonic() + timeout_sec, lambda: False))
        except LibraryError as exc:
            return {
                'status': 'FAILED',
                'probe_live': bool(probe_live),
                'importable': False,
                'protocol_verified': False,
                'media_verified': False,
                'error_code': exc.code,
                'diagnosis': {'ok': False, 'can_save_t4': False, 'error_code': exc.code},
                'live_probes': [],
            }
        effective_base = base_url or norm_url
    else:
        cfg_path = Path(config_source)
        if not cfg_path.is_file():
            return {
                'status': 'BLOCKED_INPUT',
                'probe_live': bool(probe_live),
                'importable': False,
                'protocol_verified': False,
                'media_verified': False,
                'error_code': 'INPUT_NOT_FOUND',
                'diagnosis': {'ok': False, 'can_save_t4': False, 'error_code': 'INPUT_NOT_FOUND'},
                'live_probes': [],
            }
        raw = cfg_path.read_bytes()
        effective_base = base_url

    if expected_sha256:
        actual_sha = hashlib.sha256(raw).hexdigest()
        if actual_sha.lower() != expected_sha256.strip().lower():
            return {
                'status': 'BLOCKED_INPUT',
                'probe_live': bool(probe_live),
                'importable': False,
                'protocol_verified': False,
                'media_verified': False,
                'error_code': 'INPUT_SHA256_MISMATCH',
                'actual_sha256': actual_sha,
                'expected_sha256': expected_sha256.strip().lower(),
                'diagnosis': {'ok': False, 'can_save_t4': False, 'error_code': 'INPUT_SHA256_MISMATCH'},
                'live_probes': [],
            }

    diagnosis = t4.diagnose_config(raw, base_url=effective_base)
    if not diagnosis.get('ok'):
        return {
            'status': 'FAILED',
            'probe_live': bool(probe_live),
            'importable': False,
            'protocol_verified': False,
            'media_verified': False,
            'error_code': diagnosis.get('error_code') or 'INVALID_DOCUMENT',
            'diagnosis': diagnosis,
            'live_probes': [],
        }

    can_save = bool(diagnosis.get('can_save_t4'))
    if not probe_live:
        return {
            'status': 'IMPORTABLE' if can_save else 'DIAGNOSED',
            'probe_live': False,
            'importable': can_save,
            'protocol_verified': False,
            'media_verified': False,
            'error_code': None,
            'diagnosis': diagnosis,
            'live_probes': [],
        }

    if not can_save:
        return {
            'status': 'DIAGNOSED',
            'probe_live': True,
            'importable': False,
            'protocol_verified': False,
            'media_verified': False,
            'error_code': 'T4_NO_SITES',
            'diagnosis': diagnosis,
            'live_probes': [],
        }

    parsed = t4.preview(raw, effective_base)
    live_results = [
        probe_t4_site(
            site,
            fetch_fn=fetch_fn,
            media_probe_fn=media_probe_fn,
            timeout_sec=timeout_sec,
        )
        for site in parsed.sites
    ]
    if not live_results:
        agg_status = 'DIAGNOSED'
    elif all(r['status'] == 'MEDIA_VERIFIED' for r in live_results):
        agg_status = 'MEDIA_VERIFIED'
    elif all(r['protocol_verified'] for r in live_results):
        agg_status = 'PROTOCOL_VERIFIED'
    elif any(r['status'] == 'FAILED' for r in live_results):
        agg_status = 'FAILED'
    else:
        agg_status = 'INCOMPLETE'

    return {
        'status': agg_status,
        'probe_live': True,
        'importable': True,
        'protocol_verified': bool(live_results) and all(r['protocol_verified'] for r in live_results),
        'media_verified': agg_status == 'MEDIA_VERIFIED',
        'error_code': next((r['error_code'] for r in live_results if r.get('error_code')), None),
        'diagnosis': diagnosis,
        'live_probes': live_results,
    }


def exit_code_for_result(result: dict, *, probe_live: bool = False) -> int:
    status = result.get('status')
    if status == 'BLOCKED_INPUT':
        return 2
    if probe_live or result.get('probe_live'):
        return 0 if status == 'MEDIA_VERIFIED' else 1
    return 0 if status in ('DIAGNOSED', 'IMPORTABLE') else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Validate TVBox / T4 JSON configs and optional live T4 bridges.')
    parser.add_argument('--config', required=True, help='Local JSON file path or HTTP(S) config URL')
    parser.add_argument('--base-url', default='', help='Optional base URL for resolving relative paths')
    parser.add_argument('--expected-sha256', default='', help='Optional SHA-256 guard for exact input verification')
    parser.add_argument('--timeout', type=float, default=12.0, help='Per-site live verification budget in seconds')
    parser.add_argument('--probe-live', action='store_true', help='Probe live T4 endpoints and media stream (read-only)')
    args = parser.parse_args(argv)

    result = run_check(
        args.config,
        base_url=args.base_url,
        probe_live=args.probe_live,
        expected_sha256=args.expected_sha256,
        timeout_sec=args.timeout,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code_for_result(result, probe_live=args.probe_live)


if __name__ == '__main__':
    raise SystemExit(main())
