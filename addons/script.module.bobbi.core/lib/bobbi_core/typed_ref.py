"""Strict dispatch for the two supported path observations, not a provider API."""
from . import local_ref, mounted_ref
from .mounted_ref import digest, hexid, relative

KINDS = ('mounted_path', 'local_path')


def _format(value):
    if type(value) is dict:
        if value.get('reference_kind') == mounted_ref.KIND:
            return mounted_ref
        if value.get('reference_kind') == local_ref.KIND:
            return local_ref
    raise ValueError('CATALOG_REFERENCE_INVALID')


def validate(reference):
    return _format(reference).validate(reference)


def observed(authority, path, stat):
    scope_key(authority)
    return _format(authority).observed(authority, path, stat)


def same_observation(saved, current):
    if _format(saved) is not _format(current):
        return False
    return _format(saved).same_observation(saved, current)


def scope_key(expected):
    fields = {'reference_kind', 'source_id', 'namespace', 'generation'}
    if type(expected) is dict and expected.get('reference_kind') == local_ref.KIND and 'root_signature' in expected:
        local_ref.root_signature(expected['root_signature'])
        fields.add('root_signature')
    if (type(expected) is not dict or
            set(expected) != fields or
            expected.get('reference_kind') not in KINDS or
            not hexid(expected.get('source_id'), 32) or not hexid(expected.get('namespace')) or
            expected.get('generation') != '' and not hexid(expected.get('generation'))):
        raise ValueError('CATALOG_SCOPE_INVALID')
    return expected['reference_kind'], expected['source_id'], expected['namespace']
