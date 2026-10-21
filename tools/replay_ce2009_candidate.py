"""Replay immutable Web assertions against the actual candidate modules.

Only module routing and crash injection are adapted: the old 'complete before
activate' write has been replaced by 'activation_pending'. Frozen sources and
expected behaviors are never edited. Full signed-file process fault tests live
in tests/test_ce_install_recovery.py; this replay retains the Web IO doubles.
"""
import importlib.util
import os
from pathlib import Path
import sys
from threading import Event

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / 'review-evidence/ce2009-prealpha/BobiTV-CE2009-PreAlpha-1d421b1-Review-20261020/run_review.py'
spec = importlib.util.spec_from_file_location('ce2009_web_review', REVIEW)
review = importlib.util.module_from_spec(spec)
spec.loader.exec_module(review)


def setup_packages():
    for name, path in [('bobbi_platform', ROOT / 'addons/script.module.bobbi.platform/lib/bobbi_platform'),
                       ('lib', ROOT / 'addons/plugin.video.bobbi/lib'),
                       ('lib.services', ROOT / 'addons/plugin.video.bobbi/lib/services')]:
        package = review.module(name)
        package.__path__ = [str(path)]


original_atomic = review.atomic
def atomic(path, value):
    original_atomic(path, value)
    if os.environ.get('REVIEW_CRASH') == 'before_activation' and value.get('phase') == 'activation_pending':
        os._exit(73)


original_run = review.subprocess.run
def child_run(command, **kwargs):
    if '--child' in command:
        command = [str(Path(__file__).resolve()) if arg == str(REVIEW) else arg for arg in command]
    return original_run(command, **kwargs)


original_module = review.module
def module(name, **attributes):
    # The old resident-host IO double predates the cooperative stop signal.
    # Supply an unset Event, not a successful stop or replacement decision.
    if name == 'bobbi_platform.host' and 'Host' in attributes:
        factory = attributes['Host']
        def host(*args, **kwargs):
            value = factory(*args, **kwargs)
            if not hasattr(value, 'stopping'):
                value.stopping = Event()
            return value
        attributes['Host'] = host
    return original_module(name, **attributes)


if __name__ == '__main__':
    review.setup_packages = setup_packages
    review.atomic = atomic
    review.subprocess.run = child_run
    review.module = module
    raise SystemExit(review.main())
