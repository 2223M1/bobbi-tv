"""Explicit catalog routing for the one renewable share transport."""
from pathlib import Path
import xml.etree.ElementTree as ET


def juku_enabled(settings=None):
    if settings is None:
        from .juku_api import STATE, state_path
        settings = state_path(STATE).parent / 'settings.xml'
    try:
        with Path(settings).open('rb') as stream:
            raw = stream.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            return False
        root = ET.fromstring(raw)
        values = [node.text or node.get('value', '') for node in root.findall('setting')
                  if node.get('id') == 'juku_enabled']
        return not values or (len(values) == 1 and values[0].strip().lower() == 'true')
    except FileNotFoundError:
        return True  # Public integration is authorised; every install owns its keys.
    except (OSError, ET.ParseError):
        return False


def catalog(body):
    locator, guid = body.get('locator', ''), body.get('guid', '')
    if locator.startswith('am6bqqdocs://') and guid.startswith('qqdocs:'):
        from bobbi_catalog import catalog as module
        return module
    if locator.startswith('am6bjuku://') and guid.startswith('juku:') and juku_enabled():
        from . import juku_catalog as module
        return module
    raise ValueError('SHARE_CATALOG_UNAVAILABLE')


def arguments(body):
    return tuple(body[key] for key in ('locator', 'guid', 'title', 'size', 'media'))


def selected(body):
    return catalog(body).selected(*arguments(body))


def resolve(body, client=None):
    return catalog(body).resolve(*arguments(body), client=client)
