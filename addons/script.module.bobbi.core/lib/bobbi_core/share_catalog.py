"""Explicit catalog routing for the one renewable share transport."""


def sharelib_enabled(source=None):
    from bobbi_core.source_library import SourceLibrary, cancellation
    return isinstance(source, SourceLibrary) and not cancellation(source)()


def catalog(body, source=None):
    locator, guid = body.get('locator', ''), body.get('guid', '')
    if locator.startswith('am6bqqdocs://') and guid.startswith('qqdocs:'):
        from bobbi_catalog import catalog as module
        return module
    if locator.startswith('am6bsharelib://') and guid.startswith('sharelib:') and sharelib_enabled(source):
        from bobbi_core import sharelib_catalog as module
        return module
    raise ValueError('SHARE_CATALOG_UNAVAILABLE')


def arguments(body):
    return tuple(body[key] for key in ('locator', 'guid', 'title', 'size', 'media'))


def selected(body, *, source=None, cache_path=None):
    return catalog(body, source).selected(*arguments(body), **_scope(body, source, cache_path))


def resolve(body, client=None, *, source=None, cache_path=None):
    return catalog(body, source).resolve(*arguments(body), client=client, **_scope(body, source, cache_path))


def _scope(body, source, cache_path):
    if not body.get('locator', '').startswith('am6bsharelib://'):
        return dict(cache_path=cache_path)
    from bobbi_core.source_library import cancellation
    if not sharelib_enabled(source):
        raise ValueError('SHARE_CATALOG_UNAVAILABLE')
    return dict(state=source.root, cancelled=cancellation(source))
