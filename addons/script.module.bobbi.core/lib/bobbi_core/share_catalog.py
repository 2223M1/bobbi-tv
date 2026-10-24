"""Explicit catalog routing for the one renewable share transport."""


def juku_enabled(settings=None):
    # Kept for older callers, but no stored setting can enable this provider.
    return False


def catalog(body):
    locator, guid = body.get('locator', ''), body.get('guid', '')
    if locator.startswith('am6bqqdocs://') and guid.startswith('qqdocs:'):
        from bobbi_catalog import catalog as module
        return module
    raise ValueError('SHARE_CATALOG_UNAVAILABLE')


def arguments(body):
    return tuple(body[key] for key in ('locator', 'guid', 'title', 'size', 'media'))


def selected(body):
    return catalog(body).selected(*arguments(body))


def resolve(body, client=None):
    return catalog(body).resolve(*arguments(body), client=client)
