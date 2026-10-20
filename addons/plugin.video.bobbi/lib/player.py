"""One client for the measured host; stock fallback never emulates receipts."""


def JacktookPLayer(*args, **kwargs):
    from lib.native_support import available
    if available():
        from lib.native_player import JacktookPLayer as Player
    else:
        from lib.stock_player import JacktookPLayer as Player
    return Player(*args, **kwargs)
