"""Named descriptive queries in the existing profile store, not another library."""
import copy
import re
from uuid import uuid4

from bobbi_core.catalog_query import parameters
from bobbi_core.file_ref import PROVIDERS

KEY = 'bobbi:catalog_views:v1'
MAX_VIEWS = 32


def text(value, maximum):
    if (type(value) is not str or not value.strip() or len(value) > maximum or
            re.search(r'[\x00-\x1f\x7f]', value) or '://' in value):
        raise ValueError('CATALOG_VIEW_INVALID')
    return value.strip()


def owner(expected):
    if expected.get('reference_kind') in ('mounted_path', 'local_path'):
        value = {key: expected[key] for key in ('reference_kind', 'source_id', 'namespace')}
        if (not re.fullmatch('[0-9a-f]{32}', value['source_id']) or
                not re.fullmatch('[0-9a-f]{64}', value['namespace'])):
            raise ValueError('CATALOG_VIEW_INVALID')
        return value
    provider, account = expected.get('provider'), expected.get('account_id')
    if provider not in PROVIDERS or type(account) is not str or not re.fullmatch(provider + ':[0-9a-f]{64}', account):
        raise ValueError('CATALOG_VIEW_INVALID')
    return dict(provider=provider, account_id=account)


def parent(value):
    if value is None:
        return None
    if (type(value) is not dict or set(value) != {'entity_id', 'entity_kind', 'metadata_key', 'season', 'episode'} or
            not re.fullmatch('[0-9a-f]{64}', str(value['entity_id'])) or
            not re.fullmatch(r'tmdb:(movie|tv):[1-9]\d{0,8}', str(value['metadata_key'])) or
            value['entity_kind'] not in ('work', 'season', 'episode')):
        raise ValueError('CATALOG_VIEW_INVALID')
    for field in ('season', 'episode'):
        number = value[field]
        if number is not None and (type(number) is not int or not 0 <= number <= 9999):
            raise ValueError('CATALOG_VIEW_INVALID')
    return dict(value)


def record(value):
    if (type(value) is not dict or set(value) != {'id', 'title', 'owner', 'query', 'parent'} or
            not re.fullmatch('[0-9a-f]{32}', str(value['id']))):
        raise ValueError('CATALOG_VIEW_INVALID')
    checked = dict(id=value['id'], title=text(value['title'], 80), owner=owner(value['owner']),
                   query=parameters(value['query']), parent=parent(value['parent']))
    if set(value['owner']) != set(checked['owner']):
        raise ValueError('CATALOG_VIEW_INVALID')
    if checked['query']['parent_entity_id'] != (checked['parent'] or {}).get('entity_id'):
        raise ValueError('CATALOG_VIEW_INVALID')
    return checked


def state(value):
    if value is None:
        return dict(schema=1, items=[], active=None)
    if (type(value) is not dict or set(value) != {'schema', 'items', 'active'} or
            type(value['schema']) is not int or value['schema'] != 1 or type(value['items']) is not list or
            len(value['items']) > MAX_VIEWS):
        raise ValueError('CATALOG_VIEW_SCHEMA_UNSUPPORTED')
    rows = [record(row) for row in value['items']]
    ids = [row['id'] for row in rows]
    if len(set(ids)) != len(ids) or value['active'] is not None and value['active'] not in ids:
        raise ValueError('CATALOG_VIEW_SCHEMA_UNSUPPORTED')
    return dict(schema=1, items=rows, active=value['active'])


class CatalogViews:
    def __init__(self, database=None):
        self.binding = None
        if database is None:
            from .pickle_db import PickleDatabase
            from bobbi_platform.paths import ProfileBinding
            self.binding = ProfileBinding()
            database = PickleDatabase(profile_root=self.binding.root('plugin.video.bobbi'))
        self.database = database

    def snapshot(self):
        if self.binding:
            self.binding.require_current()
        raw = self.database.get_key_checked(KEY)
        if self.binding:
            self.binding.require_current()
        return raw, state(raw)

    def change(self, snapshot, action, *, identifier=None, title=None, expected=None, query=None, descriptor=None):
        raw, before = snapshot
        after = copy.deepcopy(before)
        rows = after['items']
        selected = next((row for row in rows if row['id'] == identifier), None)
        if action == 'create':
            if len(rows) >= MAX_VIEWS:
                raise ValueError('CATALOG_VIEW_LIMIT')
            selected = record(dict(id=uuid4().hex, title=title, owner=owner(expected),
                query=parameters(query), parent=descriptor))
            rows.append(selected)
        elif action == 'default':
            after['active'] = None
        elif selected is None:
            raise ValueError('CATALOG_VIEW_CHANGED')
        elif action == 'rename':
            selected['title'] = text(title, 80)
        elif action == 'update':
            selected.update(owner=owner(expected), query=parameters(query), parent=descriptor)
        elif action == 'delete':
            rows.remove(selected)
            if after['active'] == identifier:
                after['active'] = None
        elif action == 'home':
            after['active'] = identifier
        elif action in ('up', 'down'):
            position = rows.index(selected)
            other = position + (-1 if action == 'up' else 1)
            if 0 <= other < len(rows):
                rows[position], rows[other] = rows[other], rows[position]
        else:
            raise ValueError('CATALOG_VIEW_INVALID')
        after = state(after)
        if self.binding:
            self.binding.require_current()
        if not self.database.compare_and_set_key(KEY, raw, after):
            raise ValueError('CATALOG_VIEW_CONFLICT')
        if self.binding:
            self.binding.require_current()
        return selected['id'] if selected else None
