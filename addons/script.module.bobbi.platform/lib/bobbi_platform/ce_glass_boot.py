"""Load the optional CE renderer only for an explicitly verified product tuple."""
import hashlib
import json
import os
import re
import stat
import struct
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
ZIP_DYNAMIC_LIBRARY = 2026102184
ZIP_JUKU_CONVERGENCE = 2026102185
OPT_IN_SEQUENCES = (ZIP_OPT_IN, ZIP_STABLE, ZIP_UPDATE_FEED, ZIP_GITCODE, ZIP_DYNAMIC_LIBRARY, ZIP_JUKU_CONVERGENCE)
STOCK_SEQUENCES = (ZIP_TEXTURE_KEYS, *OPT_IN_SEQUENCES)
PACKAGED_SEQUENCES = (PACKAGED_GLASS, ZIP_UPDATE, ZIP_CRYPTO, *STOCK_SEQUENCES)
PACKAGED_FILE = Path('script.module.bobbi.platform/resources/renderer/ce-armhf/libbobbi_liquid_glass.so')
GLASS_ASSETS_FILE = Path('script.module.bobbi.platform/resources/renderer/glass_assets.json')
GLASS_PROTOCOL = 'bobilg-16x4-v2'
GLASS_REQUIRED_ADDONS = (
    'skin.bobbi.cinema',
    'plugin.video.bobbi',
    'script.module.bobbi.platform',
    'script.module.bobbi.core',
)
DEFAULT_LIB_DIRS = (Path('/usr/lib'), Path('/lib'))

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

KNOWN_NATIVE_LAUNCH_SHAS = frozenset({
    '087c9d344ff4e97a469bd82778ec2d262aee2514970096cf17fe040a51f33130',
    '5f0d942f9d79ee87f700601d4bb48d7d975b690024bdeb3f56518d3801abd51b',
    'b878104fae9ae9a0f823a0888db9f49658609c1860ac4fe51c6fe512f2fdafba',
    '8ef01e1eb6882f550e229b2791e285459fcfecafe0a13a0bfb4813afa976f42d',
    'd5e79b1b33053cdb811246fa4108ffdcb885b20657d8c4ce17951a60e0cf4195',
    '1865a5a768cfaa90f3a7029f05215f2b1a8b974f801be8f15c1464cb23377e2b',
    '19892f25bcaa7654f265a7a78348a2716be440c407fe7c9b8911df512170bb34',
    '0363e51e488cc1bf83319c5014ace55ff49f08f5f043c706260a06038dd942b2',
    'bade1c68f64d5388b4bb0854ed500a8b2cf7b327e3c888bd8a9991e312af63ea',
    '69d1ecc308758b2ecd04f74e79987c67c50595cde828bccc2127a9f5c4ece875',
    '4260bc887f91f003646dbd7cc38349fc86f92393767cced3d01c9e1b9cec5e6c',
    'ee10700212ad2f13811aecc4583cab8a4172bcc7af04d0fa342532798100893a',
})

REQUIRED_GLES2_SYMBOLS = (
    'glActiveTexture',
    'glAttachShader',
    'glBindAttribLocation',
    'glBindBuffer',
    'glBindFramebuffer',
    'glBindTexture',
    'glBlendFunc',
    'glBlendFuncSeparate',
    'glBufferData',
    'glBufferSubData',
    'glCheckFramebufferStatus',
    'glCompileShader',
    'glCompressedTexImage2D',
    'glCompressedTexSubImage2D',
    'glCopyTexImage2D',
    'glCopyTexSubImage2D',
    'glCreateProgram',
    'glCreateShader',
    'glDeleteBuffers',
    'glDeleteFramebuffers',
    'glDeleteProgram',
    'glDeleteShader',
    'glDeleteTextures',
    'glDisable',
    'glDisableVertexAttribArray',
    'glDrawArrays',
    'glDrawElements',
    'glEnable',
    'glEnableVertexAttribArray',
    'glFramebufferTexture2D',
    'glGenFramebuffers',
    'glGenTextures',
    'glGetAttribLocation',
    'glGetError',
    'glGetProgramInfoLog',
    'glGetProgramiv',
    'glGetShaderInfoLog',
    'glGetShaderiv',
    'glGetUniformLocation',
    'glIsProgram',
    'glLinkProgram',
    'glScissor',
    'glShaderSource',
    'glTexImage2D',
    'glTexParameteri',
    'glTexSubImage2D',
    'glUniform1f',
    'glUniform1i',
    'glUniform2f',
    'glUniform4f',
    'glUniformMatrix4fv',
    'glUseProgram',
    'glVertexAttribPointer',
    'glViewport',
)
OPTIONAL_GLES3_UBO_SYMBOL = 'glBindBufferBase'
REQUIRED_EGL_SYMBOLS = ('eglGetCurrentContext', 'eglSwapBuffers')

_NATIVE_60_RE = re.compile(
    r'^\[Service\]\n'
    r'BindReadOnlyPaths=(?P<base1>/[^\n:]+)/kodi\.bin:/usr/lib/kodi/kodi\.bin\n'
    r'ExecStart=\n'
    r'ExecStart=/usr/bin/python3 (?P<base2>/[^\n ]+)/launch\.py --standalone -fs \$KODI_ARGS \$KODI_DEBUG\n$'
)


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
                ('lg-barrier-cc-backdrop.png', '6684ba2c457564872cfc13ad5629f1b8cc2f601019c3711019c3711016328286bcc926fc'[:64] if False else '6684ba2c457564872cfc13ad5629f1b8cc2f601019c3711016328286bcc926fc'),
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
    ZIP_JUKU_CONVERGENCE: {'skin.bobbi.cinema': '0.1.40', 'plugin.video.bobbi': '0.1.98',
                           'script.module.bobbi.core': '0.1.89', 'script.module.bobbi.platform': '0.1.99'},
    ZIP_DYNAMIC_LIBRARY: {'skin.bobbi.cinema': '0.1.39', 'plugin.video.bobbi': '0.1.97',
                          'script.module.bobbi.core': '0.1.88', 'script.module.bobbi.platform': '0.1.98'},
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


def _ordinary_file(path, limit=None):
    if path.is_symlink() or any(p.is_symlink() for p in path.parents):
        return None
    try:
        info = path.stat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size <= 0:
        return None
    if limit is not None and info.st_size > limit:
        return None
    return info


def _record(path, limit=1024 * 1024):
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


def _read_uleb128(buf, pos, end):
    result = 0
    shift = 0
    while pos < end:
        byte = buf[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return result, pos
        shift += 7
        if shift > 35:
            raise ValueError('ULEB128_OVERFLOW')
    raise ValueError('ULEB128_TRUNCATED')


def _read_ntbs(buf, pos, end):
    nul = buf.find(b'\x00', pos, end)
    if nul < 0:
        raise ValueError('NTBS_TRUNCATED')
    return buf[pos:nul].decode('latin1'), nul + 1


def _parse_arm_attributes(section_bytes):
    if not section_bytes or section_bytes[0] != 0x41:
        return None
    attrs = {}
    pos = 1
    total = len(section_bytes)
    while pos + 4 <= total:
        sec_len = struct.unpack_from('<I', section_bytes, pos)[0]
        if sec_len < 5 or pos + sec_len > total:
            break
        sec_end = pos + sec_len
        vendor, cur = _read_ntbs(section_bytes, pos + 4, sec_end)
        if vendor == 'aeabi':
            while cur < sec_end:
                sub_tag, next_cur = _read_uleb128(section_bytes, cur, sec_end)
                if next_cur + 4 > sec_end:
                    break
                sub_size = struct.unpack_from('<I', section_bytes, next_cur)[0]
                sub_end = cur + sub_size
                if sub_size < (next_cur + 4 - cur) or sub_end > sec_end:
                    break
                p = next_cur + 4
                if sub_tag in (2, 3):  # Section / Symbol scope carry ULEB128 index list until 0
                    while p < sub_end:
                        idx, p = _read_uleb128(section_bytes, p, sub_end)
                        if idx == 0:
                            break
                while p < sub_end:
                    tag, p = _read_uleb128(section_bytes, p, sub_end)
                    if tag in (4, 5, 65, 67) or (tag > 32 and (tag & 1) == 1):
                        val, p = _read_ntbs(section_bytes, p, sub_end)
                    elif tag == 32:
                        flag, p = _read_uleb128(section_bytes, p, sub_end)
                        name, p = _read_ntbs(section_bytes, p, sub_end)
                        val = (flag, name)
                    else:
                        val, p = _read_uleb128(section_bytes, p, sub_end)
                    if sub_tag == 1 or tag not in attrs:
                        attrs[tag] = val
                cur = sub_end
        pos = sec_end
    return attrs


def inspect_elf32_arm(path, *, require_sections=False):
    """Inspect an ELF32 little-endian ARM hard-float binary and its dynamic tables."""
    with path.open('rb') as handle:
        raw = handle.read()
    if len(raw) < 52 or raw[:4] != b'\x7fELF':
        return {'ok': False, 'reason': 'NOT_ELF'}
    if raw[4] != 1:
        return {'ok': False, 'reason': 'ELF_NOT_32BIT'}
    if raw[5] != 1:
        return {'ok': False, 'reason': 'ELF_NOT_LITTLE_ENDIAN'}
    (e_type, e_machine, _e_version, _e_entry, e_phoff, e_shoff, e_flags,
     _e_ehsize, e_phentsize, e_phnum, e_shentsize, e_shnum, _e_shstrndx) = struct.unpack_from(
        '<HHIIIIIHHHHHH', raw, 16
    )
    if e_machine != 40 or e_type not in (2, 3):
        return {'ok': False, 'reason': 'ELF_NOT_ARM_EXEC_OR_DYN'}
    if (e_flags & 0xFF000000) != 0x05000000:
        return {'ok': False, 'reason': 'ELF_BAD_EABI'}
    if (e_flags & 0x00000200) != 0 or (e_flags & 0x00000400) == 0:
        return {'ok': False, 'reason': 'ELF_NOT_HARD_FLOAT'}

    sections = []
    if e_shoff and e_shnum and e_shentsize >= 40 and e_shoff + e_shnum * e_shentsize <= len(raw):
        for idx in range(e_shnum):
            sh = struct.unpack_from('<10I', raw, e_shoff + idx * e_shentsize)
            sections.append(sh)
    elif require_sections:
        return {'ok': False, 'reason': 'ELF_MISSING_SECTIONS'}

    def slice_section(sh):
        off, size = sh[4], sh[5]
        if off + size > len(raw):
            raise ValueError('ELF_SECTION_TRUNCATED')
        return raw[off:off + size]

    def cstr(tab, off):
        if off < 0 or off >= len(tab):
            return ''
        end = tab.find(b'\x00', off)
        return tab[off:(len(tab) if end < 0 else end)].decode('ascii', 'replace')

    arm_attrs = None
    dt_needed = []
    exported_symbols = set()
    verdef = set()
    verneed = {}

    try:
        for sh in sections:
            sh_type = sh[1]
            if sh_type == 0x70000003:  # SHT_ARM_ATTRIBUTES
                arm_attrs = _parse_arm_attributes(slice_section(sh))
            elif sh_type == 6:  # SHT_DYNAMIC
                if sh[6] < len(sections):
                    dynstr = slice_section(sections[sh[6]])
                    dyn = slice_section(sh)
                    for off in range(0, len(dyn) - 7, 8):
                        d_tag, d_val = struct.unpack_from('<iI', dyn, off)
                        if d_tag == 0:
                            break
                        if d_tag == 1:
                            name = cstr(dynstr, d_val)
                            if name:
                                dt_needed.append(name)
            elif sh_type == 11:  # SHT_DYNSYM
                if sh[6] < len(sections):
                    strtab = slice_section(sections[sh[6]])
                    symtab = slice_section(sh)
                    entsize = sh[9] or 16
                    for off in range(0, len(symtab) - entsize + 1, entsize):
                        st_name, _val, _sz, st_info, _oth, st_shndx = struct.unpack_from('<IIIBBH', symtab, off)
                        bind = st_info >> 4
                        if st_name != 0 and st_shndx != 0 and bind in (1, 2, 10):
                            sym = cstr(strtab, st_name)
                            if sym:
                                exported_symbols.add(sym)
            elif sh_type == 0x6FFFFFFD:  # SHT_GNU_verdef
                if sh[6] < len(sections):
                    dynstr = slice_section(sections[sh[6]])
                    vd_buf = slice_section(sh)
                    pos = 0
                    while 0 <= pos <= len(vd_buf) - 20:
                        _ver, vd_flags, _ndx, vd_cnt, _hash, vd_aux, vd_next = struct.unpack_from('<HHHHIII', vd_buf, pos)
                        if vd_cnt > 0 and (vd_flags & 0x1) == 0 and pos + vd_aux <= len(vd_buf) - 8:
                            vda_name, _vda_next = struct.unpack_from('<II', vd_buf, pos + vd_aux)
                            vname = cstr(dynstr, vda_name)
                            if vname:
                                verdef.add(vname)
                        if vd_next == 0:
                            break
                        pos += vd_next
            elif sh_type == 0x6FFFFFFE:  # SHT_GNU_verneed
                if sh[6] < len(sections):
                    dynstr = slice_section(sections[sh[6]])
                    vn_buf = slice_section(sh)
                    pos = 0
                    while 0 <= pos <= len(vn_buf) - 16:
                        _ver, vn_cnt, vn_file, vn_aux, vn_next = struct.unpack_from('<HHIII', vn_buf, pos)
                        fname = cstr(dynstr, vn_file)
                        reqs = verneed.setdefault(fname, set()) if fname else set()
                        aux_pos = pos + vn_aux
                        for _ in range(vn_cnt):
                            if aux_pos > len(vn_buf) - 16:
                                break
                            _vhash, vna_flags, _voth, vna_name, vna_next = struct.unpack_from('<IHHII', vn_buf, aux_pos)
                            if (vna_flags & 0x2) == 0:  # ignore VER_FLG_WEAK
                                req_name = cstr(dynstr, vna_name)
                                if req_name:
                                    reqs.add(req_name)
                            if vna_next == 0:
                                break
                            aux_pos += vna_next
                        if vn_next == 0:
                            break
                        pos += vn_next
    except (ValueError, struct.error):
        return {'ok': False, 'reason': 'ELF_CORRUPT_TABLES'}

    return {
        'ok': True,
        'reason': 'OK',
        'sha256': hashlib.sha256(raw).hexdigest(),
        'e_flags': e_flags,
        'arm_attrs': arm_attrs,
        'dt_needed': dt_needed,
        'exported_symbols': exported_symbols,
        'verdef': verdef,
        'verneed': verneed,
    }


def qualify_host(executable, renderer, *, lib_dirs=None, expected_renderer_sha=REFINED_RENDERER):
    """Verify host ELF32/ARMv8/hard-float, DT_NEEDED resolution, GLIBC_2.34, and GLES2/EGL symbols."""
    try:
        exe_path = Path(executable)
        ren_path = Path(renderer)
        if _ordinary_file(ren_path, limit=512 * 1024) is None:
            return {'ok': False, 'reason': 'RENDERER_NOT_ORDINARY'}
        try:
            exe_stat = exe_path.stat()
        except OSError:
            return {'ok': False, 'reason': 'EXECUTABLE_MISSING'}
        if not stat.S_ISREG(exe_stat.st_mode) or exe_stat.st_size <= 0:
            return {'ok': False, 'reason': 'EXECUTABLE_NOT_REGULAR'}

        ren_elf = inspect_elf32_arm(ren_path, require_sections=True)
        if not ren_elf['ok']:
            return {'ok': False, 'reason': 'RENDERER_' + ren_elf['reason']}
        if expected_renderer_sha is not None and ren_elf['sha256'] != expected_renderer_sha:
            return {'ok': False, 'reason': 'RENDERER_SHA_MISMATCH'}
        ren_attrs = ren_elf['arm_attrs'] or {}
        if ren_attrs.get(6, 0) < 14 or ren_attrs.get(12, 0) < 1 or ren_attrs.get(28, 1) != 1:
            return {'ok': False, 'reason': 'RENDERER_ABI_MISMATCH'}

        exe_elf = inspect_elf32_arm(exe_path, require_sections=False)
        if not exe_elf['ok']:
            return {'ok': False, 'reason': exe_elf['reason']}
        exe_attrs = exe_elf['arm_attrs']
        cpu_arch = None
        if exe_attrs is not None:
            cpu_arch = exe_attrs.get(6)
            if type(cpu_arch) is not int or cpu_arch < 14:
                return {'ok': False, 'reason': 'ELF_CPU_ARCH_UNSUPPORTED'}
            if 12 in exe_attrs and (type(exe_attrs[12]) is not int or exe_attrs[12] < 1):
                return {'ok': False, 'reason': 'ELF_SIMD_MISSING'}
            if 28 in exe_attrs and exe_attrs[28] != 1:
                return {'ok': False, 'reason': 'ELF_VFP_ARGS_MISMATCH'}
        elif exe_elf['sha256'] not in (KODI, STOCK_CE213_AMLOGIC_NG):
            return {'ok': False, 'reason': 'ELF_MISSING_ARM_ATTRIBUTES'}

        needed = list(ren_elf['dt_needed'])
        for must_have in ('libGLESv2.so', 'libEGL.so', 'libc.so.6'):
            if must_have not in needed:
                return {'ok': False, 'reason': f'RENDERER_MISSING_NEEDED:{must_have}'}

        search_dirs = tuple(Path(d) for d in (lib_dirs if lib_dirs is not None else DEFAULT_LIB_DIRS))
        resolved_libs = {}
        lib_shas = {}
        lib_elfs = {}
        for soname in needed:
            if '/' in soname or '\\' in soname or soname in ('', '.', '..'):
                return {'ok': False, 'reason': f'INVALID_SONAME:{soname}'}
            found = None
            for folder in search_dirs:
                candidate = folder / soname
                try:
                    st = candidate.stat()
                except OSError:
                    continue
                if stat.S_ISREG(st.st_mode) and st.st_size > 0:
                    found = candidate
                    break
            if found is None:
                return {'ok': False, 'reason': f'MISSING_DT_NEEDED:{soname}'}
            dep_elf = inspect_elf32_arm(found, require_sections=False)
            if not dep_elf['ok']:
                return {'ok': False, 'reason': f'INVALID_DEP_ELF:{soname}:{dep_elf["reason"]}'}
            resolved_libs[soname] = str(found)
            lib_shas[soname] = dep_elf['sha256']
            lib_elfs[soname] = dep_elf

        verneed = dict(ren_elf['verneed'])
        libc_reqs = set(verneed.get('libc.so.6', set())) | {'GLIBC_2.34'}
        verneed['libc.so.6'] = libc_reqs
        for soname, req_versions in sorted(verneed.items()):
            dep_elf = lib_elfs.get(soname)
            if dep_elf is None:
                return {'ok': False, 'reason': f'MISSING_VERNEED_TARGET:{soname}'}
            missing_vers = sorted(req_versions - dep_elf['verdef'])
            if missing_vers:
                return {'ok': False, 'reason': f'MISSING_VERSION:{soname}:{missing_vers[0]}'}

        gles_exports = lib_elfs['libGLESv2.so']['exported_symbols']
        for sym in REQUIRED_GLES2_SYMBOLS:
            if sym not in gles_exports:
                return {'ok': False, 'reason': f'MISSING_GLES_SYMBOL:{sym}'}

        egl_exports = lib_elfs['libEGL.so']['exported_symbols']
        for sym in REQUIRED_EGL_SYMBOLS:
            if sym not in egl_exports:
                return {'ok': False, 'reason': f'MISSING_EGL_SYMBOL:{sym}'}

        return {
            'ok': True,
            'reason': 'QUALIFIED',
            'exe_sha256': exe_elf['sha256'],
            'renderer_sha256': ren_elf['sha256'],
            'cpu_arch': cpu_arch,
            'resolved_libs': resolved_libs,
            'lib_shas': lib_shas,
            'glibc_versions': sorted(lib_elfs['libc.so.6']['verdef']),
            'ubo_supported': OPTIONAL_GLES3_UBO_SYMBOL in gles_exports,
        }
    except OSError as exc:
        return {'ok': False, 'reason': f'IO_ERROR:{exc.__class__.__name__}'}


def verify_glass_assets(addons):
    """Validate packaged glass_assets.json and every material digest against addons/."""
    manifest_path = Path(addons) / GLASS_ASSETS_FILE
    if _ordinary_file(manifest_path, limit=512 * 1024) is None:
        return None
    raw = manifest_path.read_bytes()
    manifest_sha = hashlib.sha256(raw).hexdigest()
    data = json.loads(raw.decode('utf-8'))
    if (not isinstance(data, dict)
            or type(data.get('schema')) is not int or data['schema'] != 1
            or data.get('protocol') != GLASS_PROTOCOL
            or data.get('renderer') != PACKAGED_FILE.as_posix()
            or data.get('renderer_sha256') != REFINED_RENDERER):
        return None
    materials = data.get('materials')
    if not isinstance(materials, dict) or len(materials) < 33:
        return None
    addons_root = Path(addons)
    for rel, expected in materials.items():
        if (not isinstance(rel, str) or not isinstance(expected, str)
                or not re.fullmatch('[a-f0-9]{64}', expected)
                or rel.startswith('/') or '\\' in rel
                or any(part in ('', '.', '..') for part in rel.split('/'))):
            return None
        target = addons_root / rel
        if _ordinary_file(target, limit=32 * 1024 * 1024) is None or sha(target) != expected:
            return None
    return data, manifest_sha


def verify_native_60_dropin(conf_path, storage=Path('/storage')):
    """Verify exact Bobbi 60-am6b-subtitle284.conf + receipt.json + launch.py + kodi.bin ownership."""
    conf_path = Path(conf_path)
    storage = Path(storage)
    if _ordinary_file(conf_path, limit=4096) is None:
        return None
    try:
        raw = conf_path.read_bytes()
        text = raw.decode('ascii')
    except (OSError, UnicodeDecodeError):
        return None
    match = _NATIVE_60_RE.fullmatch(text)
    if not match or match.group('base1') != match.group('base2'):
        return None
    base_str = match.group('base1')
    storage_posix = storage.as_posix().rstrip('/')
    allowed_prefixes = ('/storage/.local/share/bobbi-native/', f'{storage_posix}/.local/share/bobbi-native/')
    gen_name = None
    for prefix in allowed_prefixes:
        if base_str.startswith(prefix):
            tail = base_str[len(prefix):]
            if re.fullmatch(r'[A-Za-z0-9._-]+', tail):
                gen_name = tail
                break
    if gen_name is None:
        return None

    base_dir = storage / '.local/share/bobbi-native' / gen_name
    if base_dir.is_symlink() or any(p.is_symlink() for p in base_dir.parents) or not base_dir.is_dir():
        return None
    receipt_path = base_dir / 'receipt.json'
    launch_path = base_dir / 'launch.py'
    kodi_path = base_dir / 'kodi.bin'
    if (_ordinary_file(receipt_path, limit=16384) is None
            or _ordinary_file(launch_path, limit=16384) is None
            or _ordinary_file(kodi_path, limit=128 * 1024 * 1024) is None):
        return None
    try:
        receipt = json.loads(receipt_path.read_bytes().decode('utf-8'))
        launch_bytes = launch_path.read_bytes()
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(receipt, dict) or receipt.get('state') != 'applied':
        return None
    conf_sha = hashlib.sha256(raw).hexdigest()
    if receipt.get('new_conf_sha256') != conf_sha or receipt.get('new_sha256') != KODI:
        return None
    launch_sha = hashlib.sha256(launch_bytes).hexdigest()
    if (launch_sha not in KNOWN_NATIVE_LAUNCH_SHAS
            or b"os.execv('/usr/lib/kodi/kodi.sh'" not in launch_bytes
            or b'LD_PRELOAD' in launch_bytes):
        return None
    kodi_sha = sha(kodi_path)
    if kodi_sha != KODI:
        return None
    return {
        'generation': gen_name,
        'base_dir': str(base_dir),
        'conf_sha256': conf_sha,
        'launch_sha256': launch_sha,
        'kodi_sha256': kodi_sha,
    }


def _dropins_safe_for_boot(dropin_dir, storage):
    if not dropin_dir.exists():
        return True
    if dropin_dir.is_symlink() or any(p.is_symlink() for p in dropin_dir.parents):
        return False
    try:
        entries = sorted(dropin_dir.glob('*.conf'))
    except OSError:
        return False
    for conf in entries:
        if conf.name == '86-bobbi-opt-in-glass.conf':
            continue
        if _ordinary_file(conf, limit=32768) is None:
            return False
        if conf.name == '60-am6b-subtitle284.conf':
            if verify_native_60_dropin(conf, storage) is None:
                return False
            continue
        content = conf.read_bytes()
        if any(tok in content for tok in (b'LD_PRELOAD', b'bobbi-glass', b'EnvironmentFile', b'ExecStart', b'ExecStartPre')):
            return False
    return True


def verified_module(state, addons, executable, module=None, *, installation=None, lib_dirs=None):
    """Select the renderer from one snapshot; the legacy ABI cannot draw the new tags."""
    try:
        data = _release(state, installation)
        if data is None:
            return None
        sequence = data['sequence']
        if type(sequence) is not int:
            return None

        if sequence > ZIP_JUKU_CONVERGENCE:
            if (installation is None or data.get('phase') != 'complete'
                    or _record(installation) != data):
                return None
            versions = data.get('versions')
            if not isinstance(versions, dict) or any(req not in versions for req in GLASS_REQUIRED_ADDONS):
                return None
            for ident, version in versions.items():
                if not isinstance(ident, str) or not isinstance(version, str):
                    return None
                row = ET.parse(addons / ident / 'addon.xml').getroot()
                if (row.get('id'), row.get('version')) != (ident, version):
                    return None
            if verify_glass_assets(addons) is None:
                return None
            packaged = addons / PACKAGED_FILE
            if module is not None and module != packaged:
                return None
            if _ordinary_file(packaged, limit=512 * 1024) is None or sha(packaged) != REFINED_RENDERER:
                return None
            qual = qualify_host(executable, packaged, lib_dirs=lib_dirs)
            if not qual['ok']:
                return None
            if _release(state, installation) == data:
                return packaged
            return None

        versions = PRODUCTS.get(sequence)
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

        with Path(executable).open('rb') as handle:
            exe_magic = handle.read(4)
        use_elf_qual = lib_dirs is not None or (sequence in OPT_IN_SEQUENCES and exe_magic == b'\x7fELF')
        if use_elf_qual:
            completed_install = (
                sequence in STOCK_SEQUENCES
                and installation is not None
                and data.get('phase') == 'complete'
                and _record(installation) == data
            )
            host = sha(executable)
            if not (host == KODI or completed_install):
                return None
            if not qualify_host(executable, module, lib_dirs=lib_dirs,
                                expected_renderer_sha=(REFINED_RENDERER if refined else RENDERER))['ok']:
                return None
            if _release(state, installation) == data:
                return module
            return None

        host = sha(executable)
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


def main(*, opt_in=False, stock_opt_in=False, storage=Path('/storage'),
         exe=Path('/usr/lib/kodi/kodi.bin'), runtime=None, lib_dirs=None):
    runtime = Path(runtime) if runtime is not None else RUNTIME
    storage = Path(storage)
    exe = Path(exe)
    env = runtime / 'loader.env'
    env.unlink(missing_ok=True)
    if os.environ.get('LD_PRELOAD'):
        return
    user_opt_in = bool(opt_in or stock_opt_in)
    if user_opt_in:
        if not opted_in(storage / '.kodi/userdata'):
            return
        if not _dropins_safe_for_boot(storage / '.config/system.d/kodi.service.d', storage):
            return
    addons = storage / '.kodi/addons'
    module = verified_module(
        storage / '.local/share/bobbi-private-updates/state.json',
        addons,
        exe,
        installation=storage / '.kodi/userdata/addon_data/script.bobbi.start/installation.json',
        lib_dirs=lib_dirs,
    )
    packaged = addons / PACKAGED_FILE
    if user_opt_in and module != packaged:
        return
    if module == packaged:
        try:
            module = runtime_copy(module, runtime)
        except OSError:
            return  # Missing optional optics must never prevent Kodi starting.
    if module is not None:
        with env.open('x', encoding='ascii') as fd:
            fd.write('LD_PRELOAD=' + str(module) + '\n')


if __name__ == '__main__':
    import sys
    if sys.argv[1:] in ([], ['--opt-in'], ['--stock-opt-in']):
        main(
            opt_in=(sys.argv[1:] == ['--opt-in']),
            stock_opt_in=(sys.argv[1:] == ['--stock-opt-in']),
        )
