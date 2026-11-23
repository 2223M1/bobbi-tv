"""HTTP-to-115 provider lane. Never download a complete movie onto the box."""
import hashlib
import time
from urllib.parse import urljoin, urlsplit

from bobbi_core.cd2 import field, fields
from bobbi_core.direct_cloud import encode, validate_catalog
from bobbi_core.media_probe import http_range_reader, probe


class DirectIO:
    def __init__(self, provider, provider_factory, qualifier, cancelled=lambda: False, address=None):
        self.provider, self.factory, self.qualifier, self.cancelled = provider, provider_factory, qualifier, cancelled
        self.address = address

    def _guard(self, provider, account):
        if self.cancelled() or provider.account_scope() != account:
            raise ValueError('DIRECT_SCOPE_UNAVAILABLE')

    @staticmethod
    def source_sample(url, size, start, end):
        import requests
        # The origin itself comes from the reviewed catalogue. Every subsequent
        # host must still belong to the provider's observed public storage chain.
        roots = ('pan.mdsub.top', 'microsoftpersonalcontent.com', '1drv.com', 'live.com', 'sharepoint.com')
        deadline = time.monotonic() + 12
        with requests.Session() as session:
            session.trust_env = False
            for _ in range(6):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError('DIRECT_SOURCE_DEADLINE')
                target = urlsplit(url)
                if (target.scheme != 'https' or target.username or target.password or target.port not in (None, 443)
                        or not any(target.hostname == root or (target.hostname or '').endswith('.' + root) for root in roots)):
                    raise ValueError('DIRECT_REDIRECT_UNRECOGNIZED')
                with session.get(url, headers={'Range': 'bytes={}-{}'.format(start, end), 'User-Agent': 'Kodi/21.2',
                    'Accept-Encoding': 'identity'}, stream=True, allow_redirects=False,
                    timeout=(min(3.05, remaining), min(6, remaining))) as response:
                    if response.status_code in (301, 302, 303, 307, 308):
                        url = urljoin(url, response.headers['Location'])
                        continue
                    if (response.status_code != 206 or response.headers.get('Content-Range') != 'bytes {}-{}/{}'.format(start, end, size)
                            or response.headers.get('Content-Encoding', 'identity') != 'identity'):
                        raise ValueError('DIRECT_SOURCE_RANGE_UNAVAILABLE')
                    data = bytearray()
                    for chunk in response.iter_content(1024):
                        if time.monotonic() > deadline:
                            raise ValueError('DIRECT_SOURCE_DEADLINE')
                        data.extend(chunk)
                        if len(data) >= end - start + 1:
                            break
                    if len(data) != end - start + 1:
                        raise ValueError('DIRECT_SOURCE_TRUNCATED')
                    return hashlib.sha256(data).hexdigest()
        raise ValueError('DIRECT_REDIRECT_BUDGET')

    @staticmethod
    def matching(provider, destination, source):
        rows = [row for row in provider.identified_files(destination) if row['name'] == source['title']]
        if len(rows) > 1 or rows and (rows[0]['bytes'] != source['size'] or rows[0]['directory'] or rows[0]['forbidden']):
            raise ValueError('DIRECT_DESTINATION_CONFLICT')
        if rows:
            row = rows[0]
            if row['path'] != destination + '/' + source['title'] or not row.get('file_id'):
                raise ValueError('DIRECT_CLOUD_IDENTITY')
            return {k: row[k] for k in ('file_id', 'path', 'name', 'bytes', 'hashes')}
        return None

    def perform(self, action):
        provider = self.provider
        self._guard(provider, action['account'])
        source = validate_catalog(action['body'])
        kind, destination = action['kind'], action['destination']
        if kind == 'inspect':
            existing = self.matching(provider, destination, source)
            if not existing and provider.space('/115open')['free'] < source['size'] + 1024**3:
                raise ValueError('DIRECT_INSUFFICIENT_SPACE')
            samples = [dict(start=start, end=start + 1023,
                sha256=self.source_sample(source['locator'], source['size'], start, start + 1023))
                for start in (0, source['size'] - 1024)]
            return dict(state='qualify' if existing else 'submit_ready', evidence=dict(samples=samples, file=existing))
        if kind == 'submit':
            # Reconcile once more before the mutation; a concurrent external
            # transfer can only be reused after the same qualification checks.
            existing = self.matching(provider, destination, source)
            if existing:
                return dict(state='qualify', evidence=dict(file=existing))
            if self.cancelled():
                raise RuntimeError('DIRECT_STOPPING')
            response = provider.rpc('AddOfflineFiles', field(1, source['locator']) + field(2, destination) + field(3, 5))
            accepted = len(response) == 1 and fields(response[0]).get(1, [0])[0] == 1
            return dict(state='waiting' if accepted else 'rejected')
        if kind == 'poll':
            existing = self.matching(provider, destination, source)
            if existing:
                return dict(state='qualify', evidence=dict(file=existing))
            tasks = [row for row in provider.offline_tasks(destination)
                     if row['name'] == source['title'] and row['bytes'] in (0, source['size'])]
            return dict(state='failed' if tasks and all(row['status'] == 3 for row in tasks) else 'waiting')
        if kind == 'qualify':
            item = self.matching(provider, destination, source)
            if item is None or item != action['evidence']['file']:
                raise ValueError('DIRECT_FILE_CHANGED')
            url = self.qualifier.download_url(provider, item)
            read = http_range_reader(provider.session, url, item['bytes'])
            for sample in action['evidence']['samples']:
                raw = b''.join(read(sample['start'], sample['end']))
                if hashlib.sha256(raw).hexdigest() != sample['sha256']:
                    raise ValueError('DIRECT_CONTENT_MISMATCH')
            result = probe(self.qualifier.binary, item['bytes'], read, self.cancelled)
            videos = [s for s in result['streams'] if s.get('codec_type') == 'video' and not s.get('disposition', {}).get('attached_pic')]
            if not videos or not any(s.get('codec_type') == 'audio' for s in result['streams']):
                raise ValueError('DIRECT_MEDIA_INCOMPLETE')
            video = dict(duration=result['duration'], codec=videos[0]['codec_name'], width=videos[0]['width'], height=videos[0]['height'],
                         probe_bytes=result['read_bytes'])
            proof = hashlib.sha256(encode(dict(source=source, media=action['body']['media'], account=action['account'],
                file=item, samples=action['evidence']['samples'], video=video)).encode()).hexdigest()
            return dict(state='ready', evidence=dict(file=item, proof=proof, video=video))
        raise ValueError('DIRECT_UNKNOWN_ACTION')

    def verify(self, plan):
        provider = self.factory()
        try:
            self._guard(provider, plan['account'])
            source = validate_catalog(plan['intent'])
            item = self.matching(provider, plan['destination'], source)
            if item != plan['evidence']['file']:
                return False
            if self.address is None:
                return True
            url = self.address(provider, item)
            self._guard(provider, plan['account'])
            return {'playback_url': url}
        finally:
            provider.session.close()
