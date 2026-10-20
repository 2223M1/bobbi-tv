"""Recover explicitly named Go UI strings; no execution or arbitrary rodata dump."""
import hashlib
import json
from pathlib import Path
import struct

from index_juku_assets import REPO, PRIVATE, CREDENTIAL_LITERAL, save_json, digest

SOURCE = Path('C:/Users/theon/AppData/Local/Temp/am6b-juku080-audit-c1d94364ca0449caac433205113d487c/extracted')
NAMED = ([f'main.{section}HTMLPart{i}' for section in ('category','home','lists') for i in range(1,5)]
         + ['main.privateLibHTML', 'main.privateLibCSS', 'main.pushHTML', 'main.qrHTML', 'main.searchHTML', 'main.shareHTML']
         + ['main.js01Core','main.js02AuthEmby','main.js03Library','main.js04MoviesDetail','main.js05ExcelScan',
            'main.js06ShareSync','main.js07UnmatchedQueue','main.js08ApiDoc'])
FIXED = {
    'arm64': [('common-style.css',0xa5d6e0,0x3c71,'functions/007e/007ea950'),
              ('common-nav.html',0xa4a15c,0xf91,'functions/007e/007ea950'),
              ('common-ui.js',0xa95435,0xfdc5,'functions/007e/007ea950'),
              ('kodi-remote.css',0xa73428,0x5955,'functions/0075/0075ae00'),
              ('kodi-remote.js',0xb0476d,0x15308,'functions/0075/0075afe0')],
    'x64': [('common-style.css',0xf862c0,0x3c71,'functions/00cf/00cfc060'),
            ('common-nav.html',0xf72d32,0xf91,'functions/00cf/00cfc060'),
            ('common-ui.js',0xfbe015,0xfdc5,'functions/00cf/00cfc060'),
            # AMD64 handler copies the first five bytes from an immediate;
            # emit reconstructs that output and cross-checks this full range.
            ('kodi-remote.css',0xf9c008,0x5955,'functions/00c4/00c47b60'),
            ('kodi-remote.js',0x102d34d,0x15308,'functions/00c4/00c47d40')],
}
STYLE_TAGS = {'arm64': (0x9d7275, 0x9d9e5f), 'x64': (0xeffceb, 0xf02929)}


class ELF:
    def __init__(self, path):
        self.raw = path.read_bytes()
        if self.raw[:7] != b'\x7fELF\x02\x01\x01':
            raise ValueError('ELF64 little endian required')
        header = struct.unpack_from('<HHIQQQIHHHHHH', self.raw, 16)
        if header[10] != 64:
            raise ValueError('Unsupported section layout')
        self.sections = [struct.unpack_from('<IIQQQQIIQQ',self.raw,header[5]+i*64) for i in range(header[11])]
        self.symbols = {}
        for section in self.sections:
            if section[1] != 2:
                continue
            strings = self.section(self.sections[section[6]])
            values = self.section(section)
            if section[9] != 24:
                raise ValueError('Unsupported symbol table')
            for offset in range(0,len(values),24):
                name, info, _, index, address, size = struct.unpack_from('<IBBHQQ',values,offset)
                if info & 15 == 1 and index and address:
                    end = strings.index(b'\0',name)
                    self.symbols[strings[name:end].decode()] = dict(address=address,bytes=size)

    def section(self, item):
        if item[4]+item[5] > len(self.raw):
            raise ValueError('Section bounds')
        return self.raw[item[4]:item[4]+item[5]]

    def read(self, address, size):
        if not 0 < size <= 2*1024*1024:
            raise ValueError('UI asset bound')
        for section in self.sections:
            if section[1] != 8 and section[3] <= address and address+size <= section[3]+section[5]:
                offset = section[4]+address-section[3]
                return self.raw[offset:offset+size]
        raise ValueError('UI asset outside file-backed section')

    def string(self, name, sliced=False):
        symbol = self.symbols[name]
        need = 24 if sliced else 16
        if symbol['bytes'] != need:
            raise ValueError('Unexpected Go string/slice layout')
        header = struct.unpack('<'+('QQQ' if sliced else 'QQ'),self.read(symbol['address'],need))
        pointer, size = header[:2]
        if not pointer or not size:
            return None, dict(symbol=name, header_address=hex(symbol['address']), state='runtime-initialized')
        if sliced and header[2] < size:
            raise ValueError('Invalid slice bounds')
        return self.read(pointer,size), dict(symbol=name, header_address=hex(symbol['address']),
                                            data_address=hex(pointer), bytes=size, state='static-symbol')


def main():
    out = REPO/'docs/research/juku-full-20261019/assets/embedded'
    all_rows, contents = [], {}
    for arch in ('arm64','x64'):
        binary = SOURCE/('plugin.video.juku-0.80-linux-'+arch)/'plugin.video.juku/bin'/('daemon-linux-'+('amd64' if arch=='x64' else arch))
        elf, rows, values = ELF(binary), [], {}
        def emit(name, raw, record):
            if PRIVATE.search(raw) or CREDENTIAL_LITERAL.search(raw):
                raise ValueError('Unexpected credential marker in UI allowlist')
            if not name.endswith('.ico'):
                raw.decode('utf-8')  # Never silently replace bytes.
            target = out/arch/name
            target.parent.mkdir(parents=True,exist_ok=True)
            target.write_bytes(raw)
            record.update(file=str(target.relative_to(out)).replace('\\','/'),sha256=digest(raw),bytes=len(raw))
            rows.append(record)
            values[name] = raw
        for name in NAMED:
            raw, info = elf.string(name)
            ext = '.css' if name.endswith('CSS') else '.js' if '.js' in name else '.html'
            emit(name[5:]+ext,raw,info)
        for name,address,size,evidence in FIXED[arch]:
            folder = REPO/'docs/research/juku-full-20261019'/('amd64' if arch=='x64' else arch)
            proofs = []
            for ext in ('.c','.asm'):
                proof=folder/(evidence+ext)
                proofs.append(dict(file=str(proof.relative_to(REPO)).replace('\\','/'),sha256=digest(proof.read_bytes())))
            raw = elf.read(address,size)
            info = dict(state='explicit-handler-or-init-range',data_address=hex(address),evidence=proofs)
            if arch == 'x64' and name == 'kodi-remote.css':
                actual = struct.pack('<Q', 0x3d3d3d3d202a2f0a)[:5]+elf.read(0xf9c00d,0x5950)
                if actual != raw:
                    raise ValueError('AMD64 handler immediate/tail differ from contiguous constant')
                info.update(state='reconstructed-handler-output',
                    recipe='little-endian immediate 0x3d3d3d3d202a2f0a first 5 bytes + [0xf9c00d, 0x5950 bytes]',
                    contiguous_constant_crosscheck=True)
                raw = actual
            emit(name,raw,info)
        raw, info = elf.string('main.faviconBytes',sliced=True)
        if not raw.startswith(b'\x00\x00\x01\x00'):
            raise ValueError('Expected ICO file header')
        emit('favicon.ico',raw,info)
        # Deterministic reconstruction only of concatenations visible in main.init.
        for section in ('category','home','lists'):
            parts=[values[f'{section}HTMLPart{i}.html'] for i in range(1,5)]
            style=values['common-style.css']
            if section=='lists':
                begin,end=STYLE_TAGS[arch]
                opening,closing=elf.read(begin,7),elf.read(end,8)
                if opening != b'<style>' or closing != b'</style>':
                    raise ValueError('Unexpected original lists style wrapper')
                style=opening+style+closing
            raw=parts[0]+style+parts[1]+values['common-nav.html']+parts[2]+values['common-ui.js']+parts[3]
            emit(section+'-assembled.html',raw,dict(state='reconstructed-concatenation',
                recipe='part1 + common-style (lists wraps style tags) + part2 + common-nav + part3 + common-ui + part4'))
        js_names=[name[5:]+'.js' for name in NAMED if '.js' in name]
        emit('privateLib-assembled.js',b'\n\n'.join(values[name] for name in js_names),
             dict(state='reconstructed-concatenation',recipe='main.init.0: js01..js08 joined by two newline bytes',parts=js_names))
        all_rows.append(dict(architecture=arch,binary=str(binary),binary_sha256=digest(elf.raw),assets=rows))
        contents[arch]={r['file'].split('/',1)[1]:r['sha256'] for r in rows}
    differences=[]
    for name in contents['arm64']:
        if contents['arm64'][name] != contents['x64'][name]:
            differences.append(dict(file=name,arm64_sha256=contents['arm64'][name],x64_sha256=contents['x64'][name]))
    save_json(out/'index.json',dict(binaries=all_rows,all_cross_arch_assets_identical=contents['arm64']==contents['x64'],
                                  cross_arch_differences=differences,
                                  limitation='Only explicit UI symbols/handler ranges; no arbitrary rodata, execution or remote-service source recovery'))
    print(json.dumps(dict(assets_per_arch=len(all_rows[0]['assets']),cross_arch_identical=contents['arm64']==contents['x64'],
                         total_unique_bytes=sum(r['bytes'] for r in all_rows[0]['assets'])),indent=2))


if __name__=='__main__':
    main()
