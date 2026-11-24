"""Read-only validator for TVBox / T4 configurations and live T4 HTTP bridges (R19 / REV-12).

Never executes arbitrary type-3 Spider JAR/JS/Python payloads and never mutates local settings.
"""
from __future__ import annotations

import argparse
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


def probe_t4_site(site: dict, *, fetch_fn=None, media_probe_fn=None, timeout_sec: float = 12.0) -> dict:
    """Validate one type-4 site across home, category, detail, optional search, and play."""
    deadline = time.monotonic() + timeout_sec
    site_headers = site.get('headers')
    fetcher = fetch_fn or (
        lambda url: t4_http.read(
            url,
            deadline,
            lambda: False,
            headers=site_headers,
            expected_origin=site['api'],
        )
    )
    media_prober = media_probe_fn or (
        lambda url, hdrs: source_media_http.probe_stream(
            url,
            {'User-Agent': 'BobbiTV', **hdrs},
            max_redirects=3,
            deadline=time.monotonic() + 8.0,
        )
    )
    client = t4.Client(site, fetcher)
    steps = {
        'home': 'SKIPPED',
        'category': 'SKIPPED',
        'search': 'SKIPPED' if not site.get('searchable') else 'PENDING',
        'detail': 'SKIPPED',
        'play': 'SKIPPED',
    }
    error_code = None

    try:
        home = client.home()
        classes = home.get('class') if isinstance(home.get('class'), list) else []
        home_list = home.get('list') if isinstance(home.get('list'), list) else []
        steps['home'] = 'PASS'

        sample_vod = None
        if classes and isinstance(classes[0], dict) and classes[0].get('type_id') is not None:
            cat_doc = client.category(t4.identifier(classes[0]['type_id']), 1)
            cat_list = cat_doc.get('list') if isinstance(cat_doc.get('list'), list) else []
            steps['category'] = 'PASS'
            if cat_list and isinstance(cat_list[0], dict):
                sample_vod = t4.identifier(cat_list[0].get('vod_id'))
        if sample_vod is None and home_list and isinstance(home_list[0], dict):
            sample_vod = t4.identifier(home_list[0].get('vod_id'))

        if site.get('searchable'):
            client.search('a', 1)
            steps['search'] = 'PASS'

        if sample_vod is not None:
            lines = client.detail(sample_vod)
            steps['detail'] = 'PASS'
            if lines and lines[0][1]:
                line_name, episodes = lines[0]
                _, ep_id = episodes[0]
                play_url, play_hdrs = client.play(line_name, ep_id)
                probed = media_prober(play_url, play_hdrs)
                steps['play'] = f"PASS ({probed['identity_mode']}, {probed['size']}B)"
    except LibraryError as exc:
        error_code = exc.code
        for k, v in steps.items():
            if v in ('PENDING', 'SKIPPED') and k != 'search':
                steps[k] = f'FAIL:{exc.code}'
                break
            if k == 'search' and v == 'PENDING':
                steps[k] = f'FAIL:{exc.code}'
                break

    u = urlsplit(site['api'])
    return {
        'key': site['key'],
        'name': site['name'],
        'origin': f'{u.scheme}://{u.netloc}',
        'searchable': bool(site.get('searchable')),
        'steps': steps,
        'error_code': error_code,
    }


def run_check(config_source: str, *, base_url: str = '', probe_live: bool = False) -> dict:
    if config_source.startswith(('http://', 'https://')):
        norm_url = t4.endpoint(config_source)
        raw = t4_http.read(norm_url, time.monotonic() + 12.0, lambda: False)
        effective_base = base_url or norm_url
    else:
        raw = Path(config_source).read_bytes()
        effective_base = base_url

    diagnosis = t4.diagnose_config(raw, base_url=effective_base)
    live_results = []
    if probe_live and diagnosis.get('can_save_t4'):
        parsed = t4.preview(raw, effective_base)
        for site in parsed.sites:
            live_results.append(probe_t4_site(site))
    return {
        'diagnosis': diagnosis,
        'live_probes': live_results,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Validate TVBox / T4 JSON configs and optional live T4 bridges.')
    parser.add_argument('--config', required=True, help='Local JSON file path or HTTP(S) config URL')
    parser.add_argument('--base-url', default='', help='Optional base URL for resolving relative paths')
    parser.add_argument('--probe-live', action='store_true', help='Probe live T4 endpoints (read-only)')
    args = parser.parse_args(argv)

    result = run_check(args.config, base_url=args.base_url, probe_live=args.probe_live)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['diagnosis'].get('ok') else 1


if __name__ == '__main__':
    raise SystemExit(main())
