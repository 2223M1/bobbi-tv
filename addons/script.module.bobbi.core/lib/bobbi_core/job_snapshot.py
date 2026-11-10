"""Whitelisted read-only job projection, independent of executor ownership."""
from hashlib import sha256

PREPARATION_STATES = {
    'queued': 'queued', 'space_blocked': 'queued', 'reserved': 'running',
    'submitting': 'running', 'submitted': 'running', 'uncertain': 'uncertain',
    'downloading': 'running', 'mapping': 'running', 'checking': 'running',
    'ready': 'completed', 'failed': 'failed', 'suppressed': 'suppressed',
}


def owner(scope):
    return sha256((scope.get('provider', '115') + '\n' + scope['account_id']).encode()).hexdigest()


def preparation(row, scope):
    stage = row['state']
    return dict(schema=1, kind='preparation', task_id=row['id'], owner=owner(scope),
        epoch=scope['epoch'], state=PREPARATION_STATES.get(stage, 'unknown'), stage=stage,
        counts={}, updated_at=row['updated'], cancel_requested=False,
        result_summary='CANCEL_NOT_SUPPORTED')


def scan(row):
    return dict(schema=1, kind='scan', task_id=row['id'], owner=owner(row['scope']),
        epoch=row['scope']['epoch'], state=row['state'], stage='directory_scan',
        counts=dict(pages=row['pages'], scanned=row['scanned'], discovered=row['discovered']),
        updated_at=row['updated'], cancel_requested=bool(row['cancel_requested']),
        result_summary=row['reason'])
