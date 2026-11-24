"""Load the optional CE renderer only for an explicitly verified product tuple."""
import hashlib
import json
import os
import re
import stat
from pathlib import Path
from xml.etree import ElementTree as ET

KODI = 'b0b6ffeeefdd464f36793fd55f24c1fcdf74c909db8729a9e0d3214280617d08'
STOCK_CE213_AMLOGIC_NG = '793194b0e506a61ab2f1a065fb7dd0395c80d281fe853e48f1150adbc2879b2e'
RENDERER = '489981a67e828f23ac866d22ca3ac4223c095d2382d23e684dc6a6c649b52dd7'
REFINED = 2026102159
REFINED_EOF = 2026102160
REFINED_OSD = 2026102161
REFINED_PICKER = 2026102162
REFINED_INSTALLER = 2026102163
REFINED_DIAGNOSTIC = 2026102164
REFINED_UPDATES = 2026102165
BRANDED = 2026102166
BRANDED_SELECTION = 2026102167
BRANDED_LABEL = 2026102168
OPTICS = 2026102169
SLATE = 2026102170
SURFACES = 2026102171
CONTROL_CENTER = 2026102172
CONTROL_CENTER_TYPE = 2026102173
APPROVED_CC = 2026102174
PACKAGED_GLASS = 2026102175
ZIP_UPDATE = 2026102177
ZIP_CRYPTO = 2026102178
ZIP_TEXTURE_KEYS = 2026102179
ZIP_OPT_IN = 2026102180
ZIP_STABLE = 2026102181
ZIP_UPDATE_FEED = 2026102182
ZIP_GITCODE = 2026102183
OPT_IN_SEQUENCES = (ZIP_OPT_IN, ZIP_STABLE, ZIP_UPDATE_FEED, ZIP_GITCODE)
STOCK_SEQUENCES = (ZIP_TEXTURE_KEYS, *OPT_IN_SEQUENCES)
PACKAGED_SEQUENCES = (PACKAGED_GLASS, ZIP_UPDATE, ZIP_CRYPTO, *STOCK_SEQUENCES)
PACKAGED_FILE = Path('script.module.bobbi.platform/resources/renderer/ce-armhf/libbobbi_liquid_glass.so')
BRANDED_SEQUENCES = (BRANDED, BRANDED_SELECTION, BRANDED_LABEL, OPTICS, SLATE, SURFACES, CONTROL_CENTER, CONTROL_CENTER_TYPE, APPROVED_CC, *PACKAGED_SEQUENCES)
REFINED_SEQUENCES = (REFINED, REFINED_EOF, REFINED_OSD, REFINED_PICKER, REFINED_INSTALLER, REFINED_DIAGNOSTIC, REFINED_UPDATES)
REFINED_RENDERER = 'd09f0df617dd7be20ccb6250c920a1c1d8433aac68ccac123a53ae176d99f330'
SIDEBAR_MARKER = 'fe299cbb759a663fc65df4c4eb45b58c29b7d9e6d00fd8a899f85a55e8fa7e07'
REFINED_FILES = {
    'skin.bobbi.cinema/media/bobi/atv/lg-barrier-sidebar.png': SIDEBAR_MARKER,
    'plugin.video.bobbi/resources/skins/Default/media/bobi/atv/lg-barrier-sidebar.png': SIDEBAR_MARKER,
    'skin.bobbi.cinema/1080p/Includes_Views.xml': '1bbbcd289a8288e001818050f69cb35ebaeea797e79bfd64fa4d5b4ba8935df7',
    'plugin.video.bobbi/resources/skins/Default/1080i/source_select.xml': '9f1abc8edebf6b7da0da730eae944f7f10581192d3c6b422adae6dc34b967840',
}
SOURCE_SELECT = 'plugin.video.bobbi/resources/skins/Default/1080i/source_select.xml'
BRANDED_FILES = {
    'skin.bobbi.cinema/media/bobbi/glass/lg-barrier-sidebar.png': SIDEBAR_MARKER,
    'plugin.video.bobbi/resources/skins/Default/media/bobbi/glass/lg-barrier-sidebar.png': SIDEBAR_MARKER,
    'skin.bobbi.cinema/1080p/Includes_Views.xml': '756f2f571ebd19f4acf3a846cf8a6e9f2c1e0e2e3098c7717ac45281130aed2d',
    SOURCE_SELECT: '326e8a92d6b5dd08db96b8b655acfcc9667f98e557b6b509dfef1e9a3548a431',
}
OPTICS_FILES = {**BRANDED_FILES, **{
    f'{prefix}/{name}': digest
    for prefix in ('skin.bobbi.cinema/media/bobbi/glass',
                   'plugin.video.bobbi/resources/skins/Default/media/bobbi/glass')
    for name, digest in (('lg-sidebar.png', 'b995b4a9297117d5faf2ab5ba3b0cee9ab758ab6099246ff78c6e89f32bff019'),
                         ('lg-cc-tile.png', '9aa6ea400aaa867a5736854b9e9b8a017939145273e8997324c6d0f1918234ca'),
                         ('lg-cc-pill.png', '716a96e409cdb355f77415e3ad710b921b54ba69359a4b2068eb7663b7fd2d96'),
                         ('sidebar-classic.png', '2970218656fe548e949b536d5d93d9d5ea6af824834c2ce5f9c427c3e63bf146'))
}}

SLATE_FILES = {path: '394b449f1995bfcf318eed6d7c4772143dd1bb900658ec7c197754c12d56310a'
               if path.endswith('/sidebar-classic.png') else digest
               for path, digest in OPTICS_FILES.items()}


def material_checks(sequence):
    if sequence in (APPROVED_CC, *PACKAGED_SEQUENCES):
        checks = dict(material_checks(CONTROL_CENTER_TYPE))
        if sequence in PACKAGED_SEQUENCES:
            checks[SOURCE_SELECT] = '3c04f88eabef6cd8499faa86a3c478cf4818ce0dbf4f2c4d8cee0ed08c376481'
        checks['skin.bobbi.cinema/1080p/Includes_Views.xml'] = 'f0da6eab796428e857a5b340c4c55631ad71ece94075478fc135425febb1f984'
        checks['skin.bobbi.cinema/1080p/DialogButtonMenu.xml'] = 'ea95a719e0b8accaa56fff890579047bac8304d88a4c176c60ae574e57321ded'
        if sequence in OPT_IN_SEQUENCES:
            checks['skin.bobbi.cinema/1080p/DialogButtonMenu.xml'] = '23ef058a9bc0f9a520a76439032d3d76682c2d8751d847665b21514cd1509900'
        checks['skin.bobbi.cinema/1080p/Font.xml'] = 'ed4c81100eaffa640b1b39b658ef1ac8830534cd1cf8802515c2c3ba5a4ca73f'
        checks['skin.bobbi.cinema/fonts/BobbiTV-CCMedium.ttf'] = '66f0be92e169b502b43e078a796f887f56f98a5daecdb644167d133f4d0ab49d'
        for prefix in ('skin.bobbi.cinema/media/bobbi/glass/', 'plugin.video.bobbi/resources/skins/Default/media/bobbi/glass/'):
            for name, digest in (
                ('cc-power-208x208.png', '1ddbab0d677425456d5db302b1385439cfcfac8607d9f197f6ef17e979749fb2'),
                ('cc-pill-208x96.png', '0c38b103a60814de9b466900885425f70c0a0bb0ea270eef86b433815a5f2f28'),
                ('lg-cc-power-r48.png', 'd5f1c404281ad6d825324a2366a04ab76f810720d999c6e2ab2ba269d6625b6f'),
            ):
                checks[prefix + name] = digest
        return checks
    if sequence in (CONTROL_CENTER, CONTROL_CENTER_TYPE):
        return {**SLATE_FILES, **{
            path.replace('sidebar-classic.png', name): digest
            for path in SLATE_FILES if path.endswith('/sidebar-classic.png')
            for name, digest in (
                ('lg-barrier-cc-backdrop.png', '6684ba2c457564872cfc13ad5629f1b8cc2f601019c3711016328286bcc926fc'),
                ('lg-cc-matte-soften.png', 'd7d978a595b27286fcadbe13b15aea77edab49108bd2ef74552a990fefd1bf9e'),
                ('lg-cc-soften.png', '1b0d82a406f04a551e86261d1b59e1c17b885bde7bcc6b83dc87663ffdc77696'),
                ('lg-cc-power-r56.png', 'b0ab8285d0aa5c4f297316282f787dd25c0a0efd1826c2433a42204b57ab03ca'),
                ('cc-power-251x242.png', '475d672900c2b3951e19db61b2279b57163579ab675494e133f15ec5d6ac881f'),
                ('cc-pill-251x112.png', '61f007bfa9e5696d13ac1d741e82bd0163c4fcff728e9afa7246a9f6a6417df0'),
            )
        }}
    if sequence == SURFACES:
        return {**SLATE_FILES, **{
            path.replace('sidebar-classic.png', 'cc-power-251x238.png'):
                '4984a3c85ab0471f9f6ca491319f1414195a6d4c9447ff30c5feed7568a2dc5f'
            for path in SLATE_FILES if path.endswith('/sidebar-classic.png')
        }}
    if sequence == SLATE:
        return SLATE_FILES
    if sequence == OPTICS:
        return OPTICS_FILES
    return BRANDED_FILES if sequence in BRANDED_SEQUENCES else REFINED_FILES

PRODUCTS = {
    ZIP_GITCODE: {'skin.bobbi.cinema': '0.1.39', 'plugin.video.bobbi': '0.1.97',
                  'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.97'},
    ZIP_UPDATE_FEED: {'skin.bobbi.cinema': '0.1.39', 'plugin.video.bobbi': '0.1.97',
                      'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.96'},
    ZIP_STABLE: {'skin.bobbi.cinema': '0.1.39', 'plugin.video.bobbi': '0.1.97',
                 'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.95'},
    ZIP_OPT_IN: {'skin.bobbi.cinema': '0.1.38', 'plugin.video.bobbi': '0.1.97',
                 'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.94'},
    ZIP_TEXTURE_KEYS: {'skin.bobbi.cinema': '0.1.37', 'plugin.video.bobbi': '0.1.96',
                       'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.93'},
    ZIP_CRYPTO: {'skin.bobbi.cinema': '0.1.36', 'plugin.video.bobbi': '0.1.96',
                 'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.93'},
    ZIP_UPDATE: {'skin.bobbi.cinema': '0.1.36', 'plugin.video.bobbi': '0.1.96',
                 'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.92'},
    PACKAGED_GLASS: {'skin.bobbi.cinema': '0.1.35', 'plugin.video.bobbi': '0.1.95',
                     'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.91'},
    APPROVED_CC: {'skin.bobbi.cinema': '0.1.35', 'plugin.video.bobbi': '0.1.95',
                  'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.90'},
    CONTROL_CENTER_TYPE: {'skin.bobbi.cinema': '0.1.34', 'plugin.video.bobbi': '0.1.94',
                          'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.90'},
    CONTROL_CENTER: {'skin.bobbi.cinema': '0.1.33', 'plugin.video.bobbi': '0.1.94',
                     'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.90'},
    SURFACES: {'skin.bobbi.cinema': '0.1.32', 'plugin.video.bobbi': '0.1.93',
               'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.90'},
    SLATE: {'skin.bobbi.cinema': '0.1.31', 'plugin.video.bobbi': '0.1.92',
            'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.90'},
    OPTICS: {'skin.bobbi.cinema': '0.1.30', 'plugin.video.bobbi': '0.1.91',
             'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.90'},
    BRANDED_LABEL: {'skin.bobbi.cinema': '0.1.29', 'plugin.video.bobbi': '0.1.90',
              'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.90'},
    BRANDED_SELECTION: {'skin.bobbi.cinema': '0.1.29', 'plugin.video.bobbi': '0.1.89',
              'script.module.bobbi.core': '0.1.87', 'script.module.bobbi.platform': '0.1.90'},
    BRANDED: {'skin.bobbi.cinema': '0.1.29', 'plugin.video.bobbi': '0.1.89',
              'script.module.bobbi.core': '0.1.86', 'script.module.bobbi.platform': '0.1.90'},
    2026102156: {'skin.bobbi.cinema': '0.1.25', 'plugin.video.bobbi': '0.1.82',
                 'script.module.bobbi.core': '0.1.83', 'script.module.bobbi.platform': '0.1.84'},
    2026102157: {'skin.bobbi.cinema': '0.1.25', 'plugin.video.bobbi': '0.1.83',
                 'script.module.bobbi.core': '0.1.84', 'script.module.bobbi.platform': '0.1.85'},
    2026102158: {'skin.bobbi.cinema': '0.1.25', 'plugin.video.bobbi': '0.1.83',
                 'script.module.bobbi.core': '0.1.84', 'script.module.bobbi.platform': '0.1.86'},
    REFINED: {'skin.bobbi.cinema': '0.1.26', 'plugin.video.bobbi': '0.1.84',
              'script.module.bobbi.core': '0.1.84', 'script.module.bobbi.platform': '0.1.86'},
    REFINED_EOF: {'skin.bobbi.cinema': '0.1.26', 'plugin.video.bobbi': '0.1.85',
                 'script.module.bobbi.core': '0.1.84', 'script.module.bobbi.platform': '0.1.86'},
    REFINED_OSD: {'skin.bobbi.cinema': '0.1.27', 'plugin.video.bobbi': '0.1.86',
                 'script.module.bobbi.core': '0.1.85', 'script.module.bobbi.platform': '0.1.86'},
    REFINED_PICKER: {'skin.bobbi.cinema': '0.1.28', 'plugin.video.bobbi': '0.1.87',
                 'script.module.bobbi.core': '0.1.85', 'script.module.bobbi.platform': '0.1.86'},
    REFINED_INSTALLER: {'skin.bobbi.cinema': '0.1.28', 'plugin.video.bobbi': '0.1.87',
                 'script.module.bobbi.core': '0.1.85', 'script.module.bobbi.platform': '0.1.87'},
    REFINED_DIAGNOSTIC: {'skin.bobbi.cinema': '0.1.28', 'plugin.video.bobbi': '0.1.87',
                 'script.module.bobbi.core': '0.1.85', 'script.module.bobbi.platform': '0.1.88'},
    REFINED_UPDATES: {'skin.bobbi.cinema': '0.1.28', 'plugin.video.bobbi': '0.1.88',
                 'script.module.bobbi.core': '0.1.85', 'script.module.bobbi.platform': '0.1.89'},
}
MODULE = Path('/storage/.local/share/bobbi-glass/2026102156/libbobi_liquid_glass.so')
REFINED_MODULE = MODULE.parent.parent / str(REFINED) / MODULE.name
BRANDED_MODULE = MODULE.parent.parent / str(BRANDED) / 'libbobbi_liquid_glass.so'
RUNTIME = Path('/run/bobbi-glass')


def sha(path):
    with path.open('rb') as fd:
        h = hashlib.sha256()
        for block in iter(lambda: fd.read(1 << 20), b''):
            h.update(block)
        return h.hexdigest()


def _record(path, limit=1024*1024):
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('Indirect installation record')
    try:
        info = path.stat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
        raise ValueError('Invalid installation record')
    with path.open('rb') as stream:
        raw = stream.read(limit + 1)
    if len(raw) != info.st_size:
        raise ValueError('Installation record changed')
    data = json.loads(raw)
    if not isinstance(data, dict) or type(data.get('sequence')) is not int or data['sequence'] < 1:
        raise ValueError('Invalid installation sequence')
    return data


def _release(state, installation):
    """Never borrow an older tuple when the authoritative install is in doubt."""
    maintained = _record(state)
    user = _record(installation) if installation is not None else None
    if user is None:
        return maintained
    if (type(user.get('schema')) is not int or user['schema'] != 1 or user.get('host_pending') is not None
            or user.get('phase') not in ('complete', 'restored')):
        return None
    # A rolled-back journal describes the attempted version, not the live one.
    if user['phase'] == 'restored' or (maintained and maintained['sequence'] > user['sequence']):
        return maintained
    seq, tx, versions = user['sequence'], user.get('tx'), user.get('versions')
    items = user.get('items')
    if (not isinstance(tx, str) or not re.fullmatch('[a-f0-9]{32}', tx)
            or type(user.get('high_watermark')) is not int or user['high_watermark'] < seq
            or not isinstance(versions, dict) or not isinstance(items, list)
            or len(items) != len(versions) or not 1 <= len(items) <= 64
            or any(not isinstance(i, dict) or type(i.get('had_old')) is not bool for i in items)
            or {i.get('id') for i in items} != set(versions)):
        return None
    proof = _record(installation.parent / tx / 'complete.json', 8192)
    if (not proof or type(proof.get('schema')) is not int or proof['schema'] != 1
            or proof['sequence'] != seq or proof.get('tx') != tx
            or not isinstance(proof.get('trees'), dict) or not proof['trees']
            or set(proof['trees']) - {'stage', 'backup', 'validator', 'abandoned'}
            or any(not isinstance(v, str) or not re.fullmatch('[a-f0-9]{64}', v)
                   for v in proof['trees'].values())):
        return None
    if maintained and maintained['sequence'] == seq:
        if any(maintained['versions'].get(k) != v for k, v in versions.items()):
            return None
    return user


def verified_module(state, addons, executable, module=None, *, installation=None):
    """Select the renderer from one snapshot; the legacy ABI cannot draw the new tags."""
    try:
        data = _release(state, installation)
        if data is None:
            return None
        sequence = data['sequence']
        versions = PRODUCTS.get(sequence) if type(sequence) is int else None
        if not versions or any(data['versions'].get(k) != v for k, v in versions.items()):
            return None
        for ident, version in versions.items():
            row = ET.parse(addons / ident / 'addon.xml').getroot()
            if (row.get('id'), row.get('version')) != (ident, version):
                return None
        refined = sequence in REFINED_SEQUENCES or sequence in BRANDED_SEQUENCES
        materials = material_checks(sequence)
        if refined and any(sha(addons / name) != expected for name, expected in materials.items()):
            return None
        if sequence in PACKAGED_SEQUENCES:
            packaged = addons / PACKAGED_FILE
            if module is not None and module != packaged:
                return None
            if packaged.is_symlink() or any(p.is_symlink() for p in packaged.parents):
                return None
            module = packaged
        else:
            module = module or (BRANDED_MODULE if sequence in BRANDED_SEQUENCES else REFINED_MODULE if refined else MODULE)
        host = sha(executable)
        # This stock Omega host has its own qualification lane. Never extend
        # support to a whole CPU/CE family, to a legacy system module, or to a
        # maintenance record without a completed ordinary ZIP installation.
        stock_install = (host == STOCK_CE213_AMLOGIC_NG and sequence in STOCK_SEQUENCES
                         and installation is not None and data.get('phase') == 'complete'
                         and _record(installation) == data)
        if (sha(module) == (REFINED_RENDERER if refined else RENDERER) and (host == KODI or stock_install)
                and _release(state, installation) == data):
            return module
    except (OSError, ET.ParseError, ValueError, KeyError, TypeError, AttributeError):
        pass
    return None


def eligible(state, addons, executable, module):
    return verified_module(state, addons, executable, module) is not None


def runtime_copy(module, runtime):
    # The signed addon can be replaced during an update. Only load a verified
    # snapshot in systemd's private RuntimeDirectory, never the writable addon.
    with module.open('rb') as stream:
        data = stream.read(128 * 1024 + 1)
    if len(data) > 128 * 1024 or hashlib.sha256(data).hexdigest() != REFINED_RENDERER:
        return None
    dest = runtime / 'libbobbi_liquid_glass.so'
    dest.unlink(missing_ok=True)
    with dest.open('xb') as output:
        output.write(data)
    dest.chmod(0o500)
    return dest


def opted_in(userdata):
    """A reset, uninstall or missing master-profile choice must fail closed."""
    pref = userdata / 'addon_data/skin.bobbi.cinema/settings.xml'
    try:
        if pref.is_symlink() or any(p.is_symlink() for p in pref.parents) or pref.stat().st_size > 256 * 1024:
            return False
        flags = [n for n in ET.parse(pref).getroot().iter('setting')
                 if n.get('id', '').casefold() == 'bobbiliquidglassenabled']
        return len(flags) == 1 and flags[0].text == 'true'
    except (OSError, ET.ParseError):
        return False


def main(*, stock_opt_in=False):
    # systemd created the private tmpfs directory, and will remove it at stop.
    # Clear any prior preload even when a later start has mismatching inputs.
    env = RUNTIME / 'loader.env'
    env.unlink(missing_ok=True)
    if os.environ.get('LD_PRELOAD'):
        return
    if stock_opt_in and (not opted_in(Path('/storage/.kodi/userdata'))
                         or sha(Path('/usr/lib/kodi/kodi.bin')) != STOCK_CE213_AMLOGIC_NG):
        return
    module = verified_module(Path('/storage/.local/share/bobbi-private-updates/state.json'),
                             Path('/storage/.kodi/addons'), Path('/usr/lib/kodi/kodi.bin'),
                             installation=Path('/storage/.kodi/userdata/addon_data/script.bobbi.start/installation.json'))
    packaged = Path('/storage/.kodi/addons') / PACKAGED_FILE
    if stock_opt_in and module != packaged:
        return
    if module == packaged:
        try:
            module = runtime_copy(module, RUNTIME)
        except OSError:
            return  # Missing optional optics must never prevent Kodi starting.
    if module is not None:
        with env.open('x', encoding='ascii') as fd:
            fd.write('LD_PRELOAD=' + str(module) + '\n')


if __name__ == '__main__':
    import sys
    if sys.argv[1:] in ([], ['--stock-opt-in']):
        main(stock_opt_in=bool(sys.argv[1:]))
