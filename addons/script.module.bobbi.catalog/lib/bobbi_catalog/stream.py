"""Local stream registration; stable selected-file identity, never signed cache."""
import re
import time
from urllib.parse import urlsplit
from uuid import uuid4


def resolve(locator, guid, title, size, media, account=None):
    from bobbi_platform.runtime import call
    from bobbi_platform.account_manager import validate_snapshot
    from bobbi_catalog.api import ShareError
    try:
        account = validate_snapshot(account if account is not None else call('account_status', {}),
                                    authenticated=True)
    except (ValueError, OSError, RuntimeError):
        raise ShareError('login_required') from None
    body = dict(request_id=uuid4().hex, locator=locator, guid=guid, title=title, size=size, media=media,
                account=account)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        try:
            result = call('share_open', body, timeout=min(.3, max(.001, deadline - time.monotonic())))
        except OSError:
            # Lost local reply reuses the same id, not another signed download.
            time.sleep(.05)
            continue
        except ValueError:
            raise ShareError('refresh_required') from None
        try:
            url = urlsplit(result['url'])
            if (result.get('state') == 'ready' and result.get('request_id') == body['request_id']
                    and result.get('guid') == guid and result.get('media') == media and result.get('bytes') == size
                    and url.scheme == 'http' and url.hostname == '127.0.0.1' and url.port and not url.username
                    and not url.password and not url.query and not url.fragment
                    and re.fullmatch(r'/stream/[0-9a-f]{32}/video\.[a-z0-9]+', url.path)):
                return result['url']
        except (ValueError, KeyError, TypeError, AttributeError):
            pass
        raise ShareError('identity_changed')
    raise ShareError('network')
