"""Explicit catalog routing for the one renewable share transport."""


def juku_enabled(settings=None):
    from bobbi_core.source_library import current
    return current() is not None


def catalog(body):
    locator, guid = body.get('locator', ''), body.get('guid', '')
    if locator.startswith('am6bqqdocs://') and guid.startswith('qqdocs:'):
        from bobbi_catalog import catalog as module
        return module
    if locator.startswith('am6bjuku://') and guid.startswith('juku:') and juku_enabled():
        from bobbi_core import juku_catalog as module
        return module
    raise ValueError('SHARE_CATALOG_UNAVAILABLE')


def arguments(body):
    return tuple(body[key] for key in ('locator', 'guid', 'title', 'size', 'media'))


def selected(body):
    return catalog(body).selected(*arguments(body), **_scope(body))


def resolve(body, client=None):
    return catalog(body).resolve(*arguments(body), client=client, **_scope(body))


def _scope(body):
    if not body.get('locator', '').startswith('am6bjuku://'):
        return {}
    from bobbi_core.source_library import current, cancellation
    source = current()
    if source is None:
        raise ValueError('SHARE_CATALOG_UNAVAILABLE')
    return dict(state=source.root, cancelled=cancellation(source))
