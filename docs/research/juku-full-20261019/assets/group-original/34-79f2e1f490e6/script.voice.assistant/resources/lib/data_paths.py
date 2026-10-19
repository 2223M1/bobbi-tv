"""One private userdata layout shared by UI, service and native agents.

Logical names keep call sites consistent; entry points upgrade legacy userdata
before any agent, service or UI can create files in the new layout.
"""
from pathlib import Path


class LayoutError(RuntimeError):
    """Safe to show to the user without credentials or private file contents."""


LAYOUT_MARKER = 'config/data-layout-v1.complete'


LOCATIONS = {
    'codex-home': 'agents/codex/home',
    'codex-work': 'agents/codex/work',
    'codex-restricted-models.json': 'agents/codex/restricted-models.json',
    'codebuddy-home': 'agents/codebuddy/external/home',
    'codebuddy-work': 'agents/codebuddy/external/work',
    'codebuddy-home-internal': 'agents/codebuddy/internal/home',
    'codebuddy-work-internal': 'agents/codebuddy/internal/work',
    'codebuddy-auth-external.json': 'agents/codebuddy/external/auth-revision.json',
    'codebuddy-auth-internal.json': 'agents/codebuddy/internal/auth-revision.json',
    'conversation.json': 'history/conversation.json',
    'chat-history.json': 'history/chat-history.json',
    'last_agent.json': 'diagnostics/last_agent.json',
    'last_session.json': 'diagnostics/last_session.json',
    'asr': 'runtime/asr',
    'speech': 'runtime/speech',
    'asr-library-hotwords': 'cache/asr-library-hotwords',
    'captures': 'runtime/captures',
    'voice-binding.json': 'config/voice-binding.json',
    'sleep-timer.json': 'runtime/sleep-timer.json',
    'asr/lifecycle.json': 'diagnostics/asr/lifecycle.json',
}


def relative_path(name):
    logical = Path(name)
    if logical.is_absolute() or '..' in logical.parts or not logical.parts:
        raise ValueError('无效的数据文件名。')
    if logical.as_posix() in LOCATIONS:
        return Path(LOCATIONS[logical.as_posix()])
    head, *tail = logical.parts
    if head in LOCATIONS:
        return Path(LOCATIONS[head]).joinpath(*tail)
    if head.endswith(('.sock', '.lock', '.flag')) or head.startswith('codex-resident'):
        return Path('runtime').joinpath(head, *tail)
    if head.startswith(('configuration-', 'codex-login-')) and head.endswith('.png'):
        return Path('runtime/qr').joinpath(head, *tail)
    return logical


def data_path(profile, name):
    """Return a canonical path and create its private parent directories."""
    profile = Path(profile)
    relative = relative_path(name)
    directory = profile
    for part in relative.parts[:-1]:
        directory /= part
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return profile / relative


def ensure_profile(profile, cancelled=lambda: False, stop_service=False):
    """Keep ordinary voice startup free of SQLite/backup migration imports."""
    profile = Path(profile)
    if (profile / LAYOUT_MARKER).is_file():
        return False
    from .profile_migration import ensure
    return ensure(profile, cancelled, stop_service=stop_service)
