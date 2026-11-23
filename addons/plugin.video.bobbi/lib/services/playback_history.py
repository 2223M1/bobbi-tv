"""One native history submission boundary, reusing the existing writer lane.

Personal files need session sequencing and must never fall back to synchronous
disk IO when that lane is busy. Legacy title history keeps its prior policy.
Start facts use the captured Client's existing read-only local RPC. No new
playback owner, global observer, cloud network operation or writer lane lives here.
"""
from copy import deepcopy
from hashlib import sha256
from time import time, monotonic, sleep


def capture_start(data, client, owner_context, native_instance, binding, clock=time,
                  *, monotonic=monotonic, sleep=sleep, budget=.9, max_attempts=3):
    """Bounded start reads after owned AV_STARTED, before the STARTED snapshot.

    Browser reads never save facts. A reused data dictionary cannot inherit a
    previous instance. Only a transport timeout can retry; an unavailable view
    can also mean revoked identity or invalid metadata and stays unknown. No selection,
    owner capture, thread or additional history writer is created here.
    """
    data.pop('_file_start_observation', None)
    if (not data.get('_pan_file') or data.get('selection_policy') != 'exact' or binding is None
            or type(budget) not in (int, float) or not 0 < budget <= .9
            or type(max_attempts) is not int or not 1 <= max_attempts <= 3):
        return False
    deadline = monotonic() + budget
    try:
        from bobbi_core.catalog_query import opaque
        from bobbi_core.file_ref import validate, locator
        from bobbi_core.playback_request import digest
        from bobbi_core.playback_start_facts import observation
        from bobbi_core.server_ref import PROVIDERS
        context = deepcopy(data['_file_history'])
        account = deepcopy(data.get('_account'))
        owner = deepcopy(owner_context)
        request, url = data.get('request_id'), data['url']
        call = client.call  # Keep the original profile-bound transport.
        ref = validate(context['file_ref'])
        if ref['provider'] in PROVIDERS:
            return False  # Delivery/source/transcode relation is not proved.
        identity = 'transport:' + digest(locator(ref)) + '|transport:' + digest(url)
        if owner.get('file_identity') != identity or owner.get('request_id') != request:
            return False

        def current():
            binding.require_current()
            return (monotonic() < deadline and data.get('_pan_file') is True
                and data.get('selection_policy') == 'exact' and data.get('_file_history') == context
                and data.get('_account') == account and data.get('request_id') == request
                and data.get('url') == url and owner_context == owner)

        for attempt in range(max_attempts):
            if not current():
                return False
            remaining = deadline - monotonic()
            if remaining <= 0:
                return False
            timed_out = False
            try:
                view = call(dict(operation='playback_presentation', account_scope=deepcopy(account),
                                 include_start_facts=True), timeout=min(.3, remaining))
            except TimeoutError:
                view = None
                timed_out = True
            if not current():
                return False
            if not timed_out:
                scope = view.get('expected', {})
                if (view.get('available') is not True or any(scope.get(key) != owner.get(key)
                        for key in ('boot_id', 'epoch', 'request_id')) or scope.get('native_instance') != native_instance
                        or scope.get('file_sha256') != sha256(identity.encode()).hexdigest()):
                    return False
                value = observation(dict(schema=1, observation_key=opaque(ref), recorded_at=clock(), expected=scope,
                    generation=context['generation'], session_id=context['session_id'], facts=view['start_facts']), ref)
                if not current():
                    return False
                data['_file_start_observation'] = value
                return True
            if attempt + 1 < max_attempts:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return False
                sleep(min(.05, remaining))
        return False
    except (OSError, RuntimeError, ValueError, TypeError, KeyError, AttributeError, OverflowError):
        return False


def snapshot(data, reason=None):
    if data.get('_pan_file'):
        data['_file_history_sequence'] = data.get('_file_history_sequence', 0) + 1
    value = deepcopy(data)
    if reason is not None:
        value['terminal_reason'] = reason
        value['completed'] = reason == 'NATURAL_EOF'
    return value


def submit_native(data, deferred=False, reason=None, save=None, profile_binding=None):
    if save is None:
        from lib.utils.general.utils import set_watched_file
        save = set_watched_file
    value = snapshot(data, reason)
    if deferred or data.get('_pan_file'):
        from lib.db.deferred_history import defer_watched_file
        accepted = (defer_watched_file(value, profile_binding=profile_binding) if profile_binding is not None
                    else defer_watched_file(value))
        if accepted:
            return True
        if data.get('_pan_file'):
            from lib.jacktook.utils import kodilog
            kodilog('[FILE-HISTORY] HISTORY_QUEUE_FULL')
            return False
    return save(value)
