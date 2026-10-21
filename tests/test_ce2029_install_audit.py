"""Real signed installer and Kodi preflight regression; no device writes."""
from types import SimpleNamespace

import pytest

from bobbi_platform.ce_install_ui import KodiHost
from bobbi_platform.ce_installer import MANAGED, blocked
from bobbi_platform.updates import UpdateError
from test_ce_general_installer import environment, signing, package


@pytest.mark.parametrize('operation', ['apply', 'rollback'])
def test_busy_player_does_not_convert_completed_install_into_pending_recovery(environment, signing, operation):
    env = environment
    env.installer.apply(package(env.root / 'one.zip', signing, 1))
    env.installer.apply(package(env.root / 'two.zip', signing, 2, '2.0.0'))
    bundle = package(env.root / 'three.zip', signing, 3, '3.0.0')
    before = env.installer.state.read_bytes()
    enabled = env.host.enabled()
    # Exercise the actual Kodi adapter's active-playback gate, not a generic
    # quiesce failure. This branch has no side effects before it raises.
    env.host.xbmc = SimpleNamespace(Player=lambda: SimpleNamespace(isPlaying=lambda: True))
    env.host.quiesce = lambda: KodiHost.quiesce(env.host)
    if hasattr(KodiHost, 'check_idle'):
        env.host.check_idle = lambda: KodiHost.check_idle(env.host)
    with pytest.raises(UpdateError, match='PLAYBACK_ACTIVE'):
        if operation == 'apply':
            env.installer.apply(bundle)
        else:
            env.installer.rollback()
    assert env.installer.state.read_bytes() == before
    assert not blocked(env.work)
    assert env.host.enabled() == enabled
    assert (env.user / 'watching').read_text() == 'user-history'
    assert all('2.0.0' in (env.addons / name / 'addon.xml').read_text() for name in MANAGED)


@pytest.mark.parametrize('operation', ['apply', 'rollback', 'first_install'])
def test_playback_at_first_quiesce_preserves_previous_journal(environment, signing, operation):
    env = environment
    if operation != 'first_install':
        env.installer.apply(package(env.root / 'one.zip', signing, 1))
        env.installer.apply(package(env.root / 'two.zip', signing, 2, '2.0.0'))
    before = env.installer.state.read_bytes() if env.installer.state.exists() else None
    enabled = env.host.enabled()
    playing = [False]
    quiesces = []
    env.host.xbmc = SimpleNamespace(Player=lambda: SimpleNamespace(isPlaying=lambda: playing[0]))
    env.host.check_idle = lambda: KodiHost.check_idle(env.host)
    def start_at_quiesce():
        quiesces.append(True)
        playing[0] = True
        KodiHost.quiesce(env.host)
    env.host.quiesce = start_at_quiesce
    with pytest.raises(UpdateError, match='PLAYBACK_ACTIVE'):
        if operation == 'rollback':
            env.installer.rollback()
        else:
            env.installer.apply(package(env.root / 'three.zip', signing, 3, '3.0.0'))
    after = env.installer.state.read_bytes() if env.installer.state.exists() else None
    assert after == before
    assert len(quiesces) == 1  # A known no-effect refusal must not retry quiescing.
    assert env.host.enabled() == enabled
    assert not blocked(env.work)
    assert not env.installer.recover()
    assert (env.user / 'watching').read_text() == 'user-history'
    if operation == 'first_install':
        assert not any((env.addons / name).exists() for name in MANAGED)
    else:
        assert all('2.0.0' in (env.addons / name / 'addon.xml').read_text() for name in MANAGED)


def test_playback_starting_during_dependency_preparation_preserves_completed_journal(environment, signing):
    env = environment
    env.installer.apply(package(env.root / 'one.zip', signing, 1))
    before = env.installer.state.read_bytes()
    playing = [False]
    env.host.xbmc = SimpleNamespace(Player=lambda: SimpleNamespace(isPlaying=lambda: playing[0]))
    env.host.check_idle = lambda: KodiHost.check_idle(env.host)
    env.host.quiesce = lambda: KodiHost.quiesce(env.host)
    env.host.dependencies = lambda stage: playing.__setitem__(0, True)
    with pytest.raises(UpdateError, match='PLAYBACK_ACTIVE'):
        env.installer.apply(package(env.root / 'two.zip', signing, 2, '2.0.0'))
    assert env.installer.state.read_bytes() == before
    assert not blocked(env.work)
    assert (env.user / 'watching').read_text() == 'user-history'
