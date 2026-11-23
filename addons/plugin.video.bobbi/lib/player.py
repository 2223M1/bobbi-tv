"""One client for the measured host; stock fallback never emulates receipts."""
_CAPTURE_ADAPTER = object()


def JacktookPLayer(*args, playback_adapter=_CAPTURE_ADAPTER, **kwargs):
    if playback_adapter is _CAPTURE_ADAPTER:
        from lib.native_support import available
        playback_adapter = 'native' if available() else 'standard'
    if playback_adapter == 'native':
        from lib.native_player import JacktookPLayer as Player
    elif playback_adapter == 'standard':
        from lib.stock_player import JacktookPLayer as Player
        kwargs.pop('playback_client', None)  # Stock playback does not need native transport.
    else:
        raise ValueError('PLAYBACK_ADAPTER_UNAVAILABLE')
    return Player(*args, **kwargs)


def reserve_navigation_entry(data):
    """Only the two manual navigation entries compose this fixed Host here."""
    from uuid import uuid4
    from bobbi_platform.playback_client import capture_transport
    binding, client, host_call = capture_transport()
    status = host_call('status', {}, timeout=.25)
    adapter = status.get('playback_adapter') if isinstance(status, dict) else None
    if adapter == 'native':
        return client.reserve_ui_entry(data), client, dict(playback_adapter=adapter)
    if adapter != 'standard':
        raise ValueError('PLAYBACK_ADAPTER_UNAVAILABLE')
    selected = dict(data)
    options = dict(playback_adapter='standard', host_call=host_call, prepared_session=None)
    account = host_call('account_status', {})
    if selected.get('_account') is not None and selected['_account'] != account:
        raise ValueError('STANDARD_SELECTION_CHANGED')
    selected['_account'] = account
    request = uuid4().hex
    for key in ('_selection_context', '_parent_request_id', '_continuation_token'):
        selected.pop(key, None)
    selected.update(request_id=request, _ui_reserved_request=request, selection_policy='exact')
    try:
        result = host_call('standard_playback', dict(operation='select', request_id=request, account=account))
        if not isinstance(result, dict) or result.get('request_id') != request:
            raise ValueError('STANDARD_SELECTION_CHANGED')
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        cancel_navigation_entry(selected, options)
        raise
    if any(selected.get(key) for key in ('prepared_resource_id', 'direct_cloud_required', 'direct_cloud_key')):
        # Optional prepared IO is constructed from THIS Host/profile/account,
        # never a second locator capture and never required for ordinary media.
        try:
            from bobbi_platform.prepared_sessions import PreparedSession
            options['prepared_session'] = PreparedSession(binding.root('plugin.video.bobbi'),
                host_call, account, binding.is_current)
        except (AttributeError, OSError, RuntimeError, ValueError, TypeError):
            pass
    from bobbi_core.playback_request import unavailable
    return selected, unavailable(), options  # Standard grants no native resolver authority.


def play_standard_navigation(data, client, options, resolve):
    """Resolve and submit this selection once; failure stays on this Host."""
    from copy import deepcopy
    reserved = deepcopy(data)
    player = None
    try:
        resolved = resolve(data, playback_client=client)
        if not resolved:
            return False
        if not isinstance(resolved, dict) or any(resolved.get(key) != reserved[key]
                for key in ('request_id', '_ui_reserved_request', '_account')):
            raise ValueError('STANDARD_SELECTION_CHANGED')
        player = JacktookPLayer(playback_client=client, **options)
        player.run(data=resolved)
        return player._resolution_answered
    finally:
        if player is None or not player._resolution_answered:
            cancel_navigation_entry(reserved, options)


def cancel_navigation_entry(data, options):
    """Retire only this standard request; never rediscover or stop Kodi."""
    request = data.get('_ui_reserved_request')
    if options.get('playback_adapter') != 'standard' or not request:
        return
    try:
        options['host_call']('standard_playback', dict(operation='cancel', request_id=request))
    except (OSError, RuntimeError, ValueError, KeyError, TypeError):
        pass
