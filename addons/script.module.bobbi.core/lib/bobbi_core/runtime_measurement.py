"""Small optional timing observer, independent of fonts and playback policy."""
from functools import wraps
import re
import time


def measured(phase):
    """Report stage duration without allowing diagnostics to fail the work."""
    def decorate(method):
        @wraps(method)
        def run(self, value, *args, **kwargs):
            started = time.monotonic()
            try:
                return method(self, value, *args, **kwargs)
            finally:
                if self.observer is not None:
                    body = value.get('body', value) if isinstance(value, dict) else {}
                    request = body.get('request_id') if isinstance(body, dict) else None
                    if isinstance(request, str) and re.fullmatch('[0-9a-f]{32}', request):
                        try:
                            self.observer(dict(request_id=request, phase=phase,
                                seconds=round(time.monotonic() - started, 6)))
                        except Exception:
                            pass  # Optional timing output is not admission.
        return run
    return decorate
