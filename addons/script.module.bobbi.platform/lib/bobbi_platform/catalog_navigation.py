"""Bounded descriptive joins at the existing Host boundary, never play admission."""
from collections import defaultdict
import re

from bobbi_core.catalog_query import REPLY_BYTES, wire
from bobbi_core.file_ref import same_file
from bobbi_core.file_ref import PROVIDERS
from .pan_accounts import scope


def history_links(catalog, pans, history_ids, history=None):
    if (type(history_ids) is not list or not 1 <= len(history_ids) <= 20 or
            any(type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value) for value in history_ids)):
        raise ValueError('CATALOG_PAGE_INVALID')
    if history is None:
        from lib.db.file_history import FileHistory
        history = FileHistory()
    wanted = set(history_ids)
    records = {row['id']: row for row in history.rows() if row['id'] in wanted}
    groups = defaultdict(list)
    for row in records.values():
        ref = row['file_ref']
        groups[(ref['provider'], ref['account_id'])].append(row['id'])
    result = dict(items=[], truncated=False)
    for (provider, account_id), ids in groups.items():
        current = pans.accounts.snapshot(provider)
        if not current.get('authenticated') or current.get('account_id') != account_id:
            continue
        expected = scope(current, authenticated=True)

        def describe():
            with catalog.index.lock:
                page = catalog.index.describe_files(expected, ids)
                items = []
                for card in page['items']:
                    if not card.get('parent_entity_id'):
                        continue
                    try:
                        exact = same_file(records[card['entity_id']]['file_ref'],
                                          catalog.index.trusted_file(expected, card['entity_id']))
                    except (ValueError, KeyError):
                        exact = False
                    if exact:
                        items.append(dict(card, expected=expected))
                return items

        for card in pans.accounts.run_if_current(expected, describe):
            if len(wire(dict(result, items=result['items'] + [card]))) > REPLY_BYTES:
                result['truncated'] = True
                break
            result['items'].append(card)
    # A later group's disk read must not republish an earlier revoked account.
    result['items'] = [card for card in result['items'] if pans.accounts.is_current(card['expected'])]
    return result


def public_holdings(catalog, pans, identities):
    """Auto-overlay only an unambiguous scope; selecting among scopes stays explicit."""
    if (type(identities) is not list or not 1 <= len(identities) <= 20 or
            any(type(key) is not str or not re.fullmatch(r'tmdb:(movie|tv):[1-9]\d{0,8}', key)
                for key in identities)):
        raise ValueError('CATALOG_PAGE_INVALID')
    accounts = [scope(current, authenticated=True) for current in
        (pans.accounts.snapshot(provider) for provider in sorted(PROVIDERS)) if current.get('authenticated')]
    mounted = (catalog.mounted.dispatch('catalog_mount_sources', {})['items'] +
               catalog.mounted.dispatch('catalog_local_sources', {})['items'])
    if len(accounts) + len(mounted) != 1:
        return dict(state='choose_scope' if accounts or mounted else 'unknown', items=[])
    expected = accounts[0] if accounts else catalog.mounted.port_for(mounted[0]).scope(mounted[0]['id'])
    def read():
        return dict(catalog.index.holdings(expected, identities), expected=expected, state='ready')
    return catalog.run_in_scope(expected, read)
