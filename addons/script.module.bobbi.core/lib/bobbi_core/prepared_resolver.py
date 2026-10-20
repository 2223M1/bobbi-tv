"""Fresh account/file validation before converting an exact selection to 115."""
import re
from bobbi_core.prepared_qualification import qualification_token
from bobbi_core.runtime_measurement import measured


class PreparedResolver:
    def __init__(self, queue, account, provider, protection=None, observer=None):
        self.queue, self.account, self.provider = queue, account, provider
        self.protection = protection
        self.observer = observer

    @measured('resolve_owner_plan')
    def plan(self, body):
        required = {'request_id', 'verification_id', 'resource_id', 'generation', 'account', 'source_info_hash', 'media_id'}
        if not isinstance(body, dict) or set(body) not in (required, required | {'qualification'}):
            raise ValueError('Exact prepared resolve request required')
        if not isinstance(body['request_id'], str) or not re.fullmatch('[0-9a-f]{32}', body['request_id']):
            raise ValueError('Playback request identity required')
        if not isinstance(body['verification_id'], str) or not re.fullmatch('[0-9a-f]{32}', body['verification_id']):
            raise ValueError('Fresh verification identity required')
        scoped = 'qualification' in body
        if scoped and (not isinstance(body['qualification'], str) or not re.fullmatch('[0-9a-f]{64}', body['qualification'])):
            raise ValueError('Exact resource qualification required')
        if (body['account'] != self.account or type(body['generation']) is not int or body['generation'] < 0
                or body['generation'] > self.queue.generation()
                or (not scoped and body['generation'] != self.queue.generation())):
            raise ValueError('Prepared snapshot account/generation changed')
        item = self.queue.ledger.get(body['resource_id'])
        if (item['state'] != 'ready' or item['suppressed'] or item['account'] != self.account
                or item['media_id'] != body['media_id']):
            raise ValueError('Prepared resource no longer belongs to requested playback')
        bound = self.queue.db.execute('''SELECT 1 FROM prepared_bindings b JOIN tasks t ON t.id=b.task
            WHERE b.resource=? AND t.account=? AND t.source_hash=? LIMIT 1''',
            (item['resource_id'], self.account, body['source_info_hash'])).fetchone()
        if not bound:
            raise ValueError('Prepared source does not match the selected torrent')
        qualification = qualification_token(self.queue, item, body['source_info_hash'])
        if scoped and qualification != body['qualification']:
            raise ValueError('Prepared resource qualification changed')
        self.queue.ledger.acquire(item['resource_id'], body['verification_id'], 'probe', ttl=90)
        return dict(body=dict(body), file=item, qualification=qualification)

    @measured('resolve_identity_io')
    def perform(self, plan):
        item = plan['file']
        if self.provider.account_scope() != self.account:
            return False
        parent = item['cloud_path'].rsplit('/', 1)[0]
        values = [row for row in self.provider.identified_files(parent)
                  if row.get('file_id') == item['file_id'] and row.get('path') == item['cloud_path']
                  and row.get('bytes') == item['bytes'] and not row.get('directory') and not row.get('forbidden')]
        return len(values) == 1 and self.provider.account_scope() == self.account

    @measured('resolve_owner_finish')
    def finish(self, plan, verified):
        try:
            return self._finish(plan, verified)
        finally:
            # Covers successful transfer, qualification failure and rejected
            # video context equally. Never release the separate play lease.
            self.queue.ledger.release(plan['file']['resource_id'], plan['body']['verification_id'])

    def _finish(self, plan, verified):
        body, old = plan['body'], plan['file']
        try:
            current = self.queue.ledger.get(old['resource_id'])
            same = qualification_token(self.queue, current, body['source_info_hash']) == plan['qualification']
        except (KeyError, ValueError):
            current, same = old, False
        if (verified is not True or not same
                or ('qualification' not in body and self.queue.generation() != body['generation'])
                or current['state'] != 'ready' or current['suppressed']
                or any(current[key] != old[key] for key in ('account', 'file_id', 'cloud_path', 'bytes', 'version_key', 'media_id'))):
            return {'state': 'unavailable'}
        result = dict(state='ready', request_id=body['request_id'], verification_id=body['verification_id'], resource_id=current['resource_id'],
                    account=self.account, generation=body['generation'], file_id=current['file_id'],
                    path=current['cloud_path'], bytes=current['bytes'], version_key=current['version_key'])
        if 'qualification' in body:
            result['qualification'] = plan['qualification']
        from bobbi_core.video_context import prepared_video
        result['video_context'] = prepared_video(self.queue, current['resource_id'], body['source_info_hash'])
        if self.protection is not None:
            # Establish durable protection before finish releases the probe.
            self.protection.arm(plan)
        return result
