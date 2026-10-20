import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import zipfile

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa, padding

from bobbi_platform.ce_installer import Installer, MANAGED, blocked
from bobbi_platform.upstream_addons import FULL_COMPONENTS, UPSTREAM_COMPONENTS
from bobbi_platform.updates import UpdateError
from test_updates import archive


@pytest.fixture(scope='module')
def signing():
    key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
    numbers = key.public_key().public_numbers()
    return key, dict(schema=1, components=sorted(FULL_COMPONENTS),
        key=dict(algorithm='RSA3072-SHA256', e=65537, n=format(numbers.n, 'x')))


def package(path, signing, sequence=1, version='1.0.0', profile='coreelec'):
    items, content = [], {}
    for name in sorted(FULL_COMPONENTS):
        raw = archive(name, version)
        filename = name + '/' + name + '-' + version + '.zip'
        content[filename] = raw
        items.append(dict(id=name, version=version, file=filename, size=len(raw),
                          sha256=hashlib.sha256(raw).hexdigest()))
    raw = json.dumps(dict(schema=2, channel='private-candidate', profile=profile,
                         sequence=sequence, components=items), sort_keys=True).encode()
    signature = base64.b64encode(signing[0].sign(raw, padding.PKCS1v15(), hashes.SHA256()))
    with zipfile.ZipFile(path, 'w') as target:
        target.writestr('release.json', raw)
        target.writestr('release.sig', signature)
        for name, data in content.items():
            target.writestr(name, data)
    return path


@pytest.fixture
def environment(tmp_path, signing):
    addons, work = tmp_path / 'addons', tmp_path / 'userdata/addon_data/script.bobbi.start'
    calls = []
    vector = set()
    def activate(versions):
        calls.append('activate')
        vector.update(versions)
    def restore(skin, enabled):
        calls.append(('restore', skin))
        vector.clear()
        vector.update(enabled)
    host = SimpleNamespace(dependencies=lambda stage: calls.append('dependencies'),
        skin=lambda: 'skin.user.original', enabled=lambda: sorted(vector),
        quiesce=lambda: calls.append('quiesce'), refresh=lambda: calls.append('refresh'),
        verify=lambda versions: calls.append('verify'), activate=activate, restore=restore)
    installer = Installer(addons, work, host, signing[1])
    other = addons / 'plugin.user.other'
    other.mkdir()
    (other / 'keep').write_text('other-addon')
    user = tmp_path / 'userdata/addon_data/plugin.video.bobbi'
    user.mkdir()
    (user / 'watching').write_text('user-history')
    for name in UPSTREAM_COMPONENTS:
        path = addons / name
        path.mkdir()
        (path / 'origin').write_text('original-kodi-repository')
    return SimpleNamespace(installer=installer, host=host, calls=calls, root=tmp_path,
                           user=user, addons=addons, work=work)


@pytest.mark.parametrize('model,sha,tested', [('AM6B', 'a'*64, True),
    ('unknown-board', 'b'*64, False), ('', '', False)])
def test_actual_signed_install_does_not_consume_device_qualification(environment, signing, model, sha, tested):
    env = environment
    env.host.model, env.host.native_sha, env.host.tested = model, sha, tested
    env.installer.apply(package(env.root / 'input.zip', signing))
    assert env.calls == ['dependencies', 'quiesce', 'refresh', 'verify', 'activate']
    assert not blocked(env.work)
    assert all((env.addons / name / 'addon.xml').is_file() for name in MANAGED)
    assert (env.user / 'watching').read_text() == 'user-history'
    assert all((env.addons / name / 'origin').read_text() == 'original-kodi-repository' for name in UPSTREAM_COMPONENTS)
    assert (env.addons / 'plugin.user.other/keep').read_text() == 'other-addon'
    assert not list(env.root.rglob('LOGIN'))


def test_missing_dependency_leaves_existing_ui_and_programs_unchanged(environment, signing):
    env = environment
    def unavailable(stage):
        raise UpdateError('DEPENDENCY_UNAVAILABLE:script.module.pycryptodome')
    env.host.dependencies = unavailable
    with pytest.raises(UpdateError, match='DEPENDENCY_UNAVAILABLE'):
        env.installer.apply(package(env.root / 'input.zip', signing))
    assert env.calls == [] and not blocked(env.work)
    assert not (env.addons / 'plugin.video.bobbi').exists()


def test_program_only_upgrade_and_rollback(environment, signing):
    env = environment
    env.installer.apply(package(env.root / 'one.zip', signing))
    env.installer.apply(package(env.root / 'two.zip', signing, 2, '2.0.0'))
    env.installer.rollback()
    for name in MANAGED:
        assert '1.0.0' in (env.addons / name / 'addon.xml').read_text()
    assert (env.user / 'watching').read_text() == 'user-history'


def test_verification_failure_never_activates_partial_generation(environment, signing):
    env = environment
    def failed(versions):
        assert blocked(env.work)
        raise UpdateError('COMPONENT_REGISTRATION_FAILED')
    env.host.verify = failed
    with pytest.raises(UpdateError, match='COMPONENT_REGISTRATION_FAILED'):
        env.installer.apply(package(env.root / 'one.zip', signing))
    assert 'activate' not in env.calls and not blocked(env.work)
    assert not any((env.addons / name).exists() for name in MANAGED)
    assert (env.user / 'watching').read_text() == 'user-history'


def test_wrong_platform_is_rejected_before_quiescing(environment, signing):
    env = environment
    with pytest.raises(UpdateError):
        env.installer.apply(package(env.root / 'wrong.zip', signing, profile='android'))
    assert env.calls == []


def test_recovery_after_interrupted_swap_restores_exact_previous_program(environment, signing, monkeypatch):
    env = environment
    env.installer.apply(package(env.root / 'one.zip', signing))
    real_restore = env.installer._restore
    def crash(versions):
        raise SystemExit('simulated process exit')
    def lost_process(state):
        raise SystemExit('process no longer able to recover')
    env.host.verify = crash
    monkeypatch.setattr(env.installer, '_restore', lost_process)
    with pytest.raises(SystemExit):
        env.installer.apply(package(env.root / 'two.zip', signing, 2, '2.0.0'))
    assert blocked(env.work)
    monkeypatch.setattr(env.installer, '_restore', real_restore)
    assert env.installer.recover()
    assert not blocked(env.work)
    assert all('1.0.0' in (env.addons / name / 'addon.xml').read_text() for name in MANAGED)


def test_rollback_does_not_allow_signed_downgrade_replay(environment, signing):
    env = environment
    env.installer.apply(package(env.root / 'one.zip', signing))
    env.installer.apply(package(env.root / 'two.zip', signing, 2, '2.0.0'))
    env.installer.rollback()
    with pytest.raises(UpdateError, match='GENERATION_NOT_NEWER'):
        env.installer.apply(env.root / 'one.zip')
    env.installer.apply(package(env.root / 'three.zip', signing, 3, '3.0.0'))


def test_failed_generation_can_be_retried_without_relaxing_prior_watermark(environment, signing):
    env = environment
    env.installer.apply(package(env.root / 'one.zip', signing))
    path = package(env.root / 'two.zip', signing, 2, '2.0.0')
    def failed(versions): raise UpdateError('registration failed')
    good, env.host.verify = env.host.verify, failed
    with pytest.raises(UpdateError): env.installer.apply(path)
    env.host.verify = good
    env.installer.apply(path)
    assert env.installer._read()['phase'] == 'complete'


def test_real_dependency_adapter_seeds_absent_original_without_overwriting_existing(tmp_path, monkeypatch):
    import sys
    import xml.etree.ElementTree as ET
    from bobbi_platform.ce_install_ui import KodiHost
    import bobbi_platform.ce_install_ui as ui
    stage, live = tmp_path / 'stage', tmp_path / 'addons'
    stage.mkdir(); live.mkdir()
    for name in FULL_COMPONENTS:
        target = stage / name
        target.mkdir()
        (target / 'addon.xml').write_text('<addon id="%s" version="1.0.0"><requires/></addon>' % name)
        (target / 'notice').write_text('original author')
    existing = live / 'script.module.requests'
    existing.mkdir()
    (existing / 'addon.xml').write_text('<addon id="script.module.requests" version="99.0.0"/>')
    (existing / 'origin').write_text('repository.xbmc.org')
    enabled, commands = set(), []
    def details(name):
        if name == 'script.module.pycryptodome':
            return dict(version='3.4.3', enabled=True)
        path = live / name / 'addon.xml'
        return dict(version=ET.parse(path).getroot().get('version'), enabled=name in enabled) if path.exists() else None
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace(Monitor=lambda: None,
        executebuiltin=lambda *args: commands.append(args)))
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(live)))
    monkeypatch.setattr(ui, 'rpc', lambda method, params: enabled.add(params['addonid']))
    host = KodiHost()
    monkeypatch.setattr(host, 'details', details)
    host.dependencies(stage)
    assert all(details(name)['enabled'] for name in UPSTREAM_COMPONENTS)
    assert (existing / 'origin').read_text() == 'repository.xbmc.org'
    assert details('script.module.requests')['version'] == '99.0.0'
    assert not (existing / 'notice').exists()
    assert all((live / name / 'notice').read_text() == 'original author'
        for name in UPSTREAM_COMPONENTS - {'script.module.requests'})
    assert not any('InstallAddon' in args[0] for args in commands)


@pytest.mark.parametrize('first,choice,expected', [(True, 0, 'embedded'),
    (False, 0, 'new'), (False, 1, 'embedded'), (False, -1, None)])
def test_real_update_menu_can_choose_new_package_instead_of_replaying_embedded(tmp_path, first, choice, expected):
    from bobbi_platform.ce_install_ui import choose_package
    embedded = tmp_path / 'embedded.zip'
    embedded.write_bytes(b'package chosen here; signature validation belongs to apply')
    dialog = SimpleNamespace(select=lambda *args: choice, browse=lambda *args, **kw: 'new')
    assert choose_package(dialog, embedded, first) == (str(embedded) if expected == 'embedded' else expected)


def test_actual_kodi_restore_restores_exact_vector_without_touching_other_addons(monkeypatch):
    from bobbi_platform.ce_install_ui import KodiHost
    import bobbi_platform.ce_install_ui as ui
    enabled = set(MANAGED) | {'plugin.user.other'}
    desired = sorted(MANAGED)[::2]
    skin = ['skin.estuary']
    def rpc(method, params):
        if method == 'Addons.SetAddonEnabled':
            assert params['addonid'] in MANAGED
            if params['enabled']: enabled.add(params['addonid'])
            else: enabled.discard(params['addonid'])
        elif method == 'Settings.SetSettingValue': skin[0] = params['value']
        else: raise AssertionError(method)
    monkeypatch.setattr(ui, 'rpc', rpc)
    host = KodiHost.__new__(KodiHost)
    host.details = lambda name: dict(enabled=name in enabled)
    host.skin = lambda: skin[0]
    host.restore('skin.user.original', desired)
    assert enabled == set(desired) | {'plugin.user.other'}
    assert skin == ['skin.user.original']


def test_entry_recovers_pending_activation_even_when_boot_is_allowed(tmp_path, monkeypatch):
    import sys
    import bobbi_platform.ce_install_ui as ui
    calls = []
    monkeypatch.setitem(sys.modules, 'xbmc', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'xbmcvfs', SimpleNamespace(translatePath=lambda _: str(tmp_path)))
    monkeypatch.setitem(sys.modules, 'xbmcgui', SimpleNamespace(Dialog=lambda: SimpleNamespace(select=lambda *a: -1)))
    monkeypatch.setattr(ui, 'profile', lambda *args: tmp_path)
    monkeypatch.setattr(ui, 'KodiHost', lambda: SimpleNamespace())
    monkeypatch.setattr(ui, 'Installer', lambda *args: SimpleNamespace(work=tmp_path,
        recover=lambda: calls.append('recover'), _read=lambda: dict(phase='activation_pending')))
    ui.main()
    assert calls == ['recover']
