"""One registry for stable, independently identity-checked 115 catalog sources.

Discovery only: these adapters cannot claim a prepared file or start playback.
The same provider names are retained in direct-source continuation receipts.
"""
from importlib import import_module


PROVIDERS = ('qqdocs', 'juku')


def _adapter(name):
    module_name = 'lib.clients.' + name + '_provider'
    try:
        return import_module(module_name)
    except ModuleNotFoundError as error:
        if error.name != module_name:
            raise
        return None  # An absent optional adapter cannot hide existing sources.


def provider_for(source):
    if getattr(source, 'type', '') != 'Direct':
        return None
    guid = str(getattr(source, 'guid', ''))
    for name in PROVIDERS:
        if guid.startswith(name + ':'):
            module = _adapter(name)
            return name if module is not None and module.is_source(source) else None
    return None


def resolve_source(source, item):
    name = provider_for(source)
    if name is None:
        raise ValueError('UNKNOWN_CATALOG_SOURCE')
    return _adapter(name).resolve_source(source, item)


def submit_catalogs(manager, ids, mode, season, episode, year, aliases, release_order,
                    movie_years=None):
    for name in PROVIDERS:
        module = _adapter(name)
        if module is None:
            continue
        # qqdocs keeps its longstanding empty-provider completion contract.
        # New optional integrations do not start work while disabled.
        if name != 'qqdocs' and not module.enabled():
            continue
        options = dict(movie_years=movie_years)
        if name == 'juku':
            options['_progressive'] = True
        manager.submit_task(module.SITE, name, module.find_sources,
            ids, mode, season, episode, year, aliases, release_order,
            manager.deadline, manager.cancelled, **options)
