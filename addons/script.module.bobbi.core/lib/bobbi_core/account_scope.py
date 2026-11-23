"""IO-free 115 account identity contract shared by domain and host adapters.

Validation proves shape, not current authentication. Only AccountManager may
compare a captured generation with its live credentials and authorize work.
"""
import re


class AccountError(RuntimeError):
    pass


def validate_snapshot(value, authenticated=False):
    if (not isinstance(value, dict) or set(value) != {'account_id', 'epoch', 'authenticated'}
            or type(value['epoch']) is not int or not 0 <= value['epoch'] < 2**63
            or type(value['authenticated']) is not bool
            or not isinstance(value['account_id'], str)
            or (value['authenticated'] and not re.fullmatch(r'115:[0-9a-f]{64}', value['account_id']))
            or (not value['authenticated'] and value['account_id'])
            or (authenticated and not value['authenticated'])):
        raise AccountError('ACCOUNT_SCOPE_INVALID')
    return dict(value)
