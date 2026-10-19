"""Region-specific CodeBuddy credentials, native histories and model choices."""
from .data_paths import data_path
from pathlib import Path

REGIONS = {'external': '国际版', 'internal': '国内版'}


def validate_region(value):
    if not isinstance(value, str) or value not in REGIONS:
        raise ValueError('CodeBuddy 区域无效。')
    return value


def home_path(profile, region='external'):
    validate_region(region)
    # Preserve the existing international login in place.
    return data_path(profile, 'codebuddy-home' if region == 'external' else 'codebuddy-home-internal')


def work_path(profile, region='external'):
    validate_region(region)
    return data_path(profile, 'codebuddy-work' if region == 'external' else 'codebuddy-work-internal')


def selected_model(values, region=None):
    region = validate_region(region if region is not None else values.get('codebuddy_region', 'external'))
    return values.get('codebuddy_model' if region == 'external' else 'codebuddy_internal_model', '')


def auth_revision(profile, region):
    from .storage import read_json
    return read_json(data_path(profile, 'codebuddy-auth-' + validate_region(region) + '.json'), '')


def invalidate_auth(profile, region):
    from .storage import write_json
    import uuid
    write_json(data_path(profile, 'codebuddy-auth-' + validate_region(region) + '.json'), uuid.uuid4().hex)


def account_busy(profile):
    import fcntl
    with (data_path(Path(profile), 'codebuddy-account.lock')).open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return False
        except BlockingIOError:
            return True
