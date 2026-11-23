"""Service-private exact mapping and real header qualification adapter."""
from urllib.parse import quote, urlsplit

from bobbi_core.cloud_mapping import map_torrent_file
from bobbi_core.media_probe import http_range_reader, probe


class CloudQualifier:
    def __init__(self, binary, endpoint, capability, cancelled=lambda: False, inspect=probe):
        parsed = urlsplit(endpoint)
        if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1', '::1')
                or parsed.username or parsed.password or parsed.path not in ('', '/')
                or parsed.query or parsed.fragment or not parsed.port):
            raise ValueError('Pinned loopback CD2 endpoint required')
        if capability not in {'observed-0.8.20', 'GetDownloadUrlPath'}:
            raise ValueError('Download capability must be verified, not guessed')
        self.binary, self.endpoint, self.capability = binary, endpoint.rstrip('/'), capability
        self.cancelled, self.inspect = cancelled, inspect

    def __call__(self, provider, request):
        if self.cancelled() or len(request.get('targets', [])) != 1:
            return None
        target = request['targets'][0]
        selection = target.get('_selection')
        if not selection:
            return None
        observations = [item for item in provider.offline_tasks(request['destination'])
                        if item['info_hash'] == request['source_hash']]
        if len(observations) != 1:
            return None
        observation = observations[0]
        old = request['observation']
        if (old.get('state') != 'finished' or observation['status'] != 2
                or any(observation[key] != old[key] for key in ('file_id', 'parent_id'))):
            return None
        item = map_torrent_file(provider, request['destination'], observation, selection['file'])
        if self.cancelled():
            return None
        url = self.download_url(provider, item)
        result = self.inspect(self.binary, item['bytes'], http_range_reader(provider.session, url, item['bytes']), self.cancelled)
        if self.cancelled() or result['duration'] < 300:
            return None
        video = [stream for stream in result['streams'] if stream.get('codec_type') == 'video'
                 and not stream.get('disposition', {}).get('attached_pic')]
        if not video or not video[0].get('codec_name'):
            return None
        file = dict(provider='115', account=request['account'], file_id=item['file_id'], cloud_path=item['path'],
                    bytes=item['bytes'], kind='video', media_id=target['media_id'], version_key=target['version_key'])
        qualification = dict(file_id=item['file_id'], bytes=item['bytes'], version_key=target['version_key'],
                             source_binding=True, duration=result['duration'], video_codec=video[0]['codec_name'],
                             read_bytes=result['read_bytes'], probe_sha256=result['probe_sha256'])
        # Existing probe output has no pair. Explicit null/partial/unknown
        # pairs are rejected, never mistaken for that legacy full-demux path.
        if 'method' not in result and 'coverage' not in result:
            method,coverage='ffprobe','bounded_demux'
        else:
            method,coverage=result.get('method'),result.get('coverage')
        if (type(method) is not str or type(coverage) is not str or (method,coverage) not in
                {('ffprobe','bounded_demux'),('matroska_container_header','prefix_to_first_cluster')}):
            return None
        qualification.update(probe_method=method,probe_coverage=coverage)
        if method != 'matroska_container_header':
            from bobbi_core.release_media_profile import media_profile
            try:
                qualification['media_profile'] = media_profile(result['streams'])
            except ValueError:
                # Ordinary playback qualification is unchanged. Missing facts must
                # not grant the stronger permission to reconcile release variants.
                pass
        elif result.get('coverage') != 'prefix_to_first_cluster':
            return None  # Unknown weaker methods cannot impersonate covered facts.
        mapping = dict(source_info_hash=request['source_hash'], cloud_root_id=observation['file_id'],
                       cloud_file_id=item['file_id'], cloud_path=item['path'], torrent_path=item['torrent_path'],
                       torrent_file_id=item['torrent_file_id'], bytes=item['bytes'])
        return dict(file=file, qualification=qualification, mapping=mapping)

    def download_url(self, provider, item):
        """Reuse the observed/declared CD2 route for exact files; never log it."""
        if self.capability == 'observed-0.8.20':
            if not provider.runtime_info()['version'].startswith('0.8.20 '):
                raise ValueError('Observed route cannot be reused on another CD2 version')
            url = self.endpoint + '/static/http/' + urlsplit(self.endpoint).netloc + '/False/' + quote(item['path'], safe='')
        else:
            route = provider.download_path(item['path'])
            if not route.startswith('/') or route.startswith('//') or '\\' in route:
                raise ValueError('Unrecognized download route')
            route = route.replace('{SCHEME}', 'http').replace('{HOST}', urlsplit(self.endpoint).netloc).replace('{PREVIEW}', 'false')
            if '{' in route or '}' in route:
                raise ValueError('Unknown route placeholders')
            url = self.endpoint + route
        return url
