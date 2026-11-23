"""Bounded ASS font requirements and actual OpenType/TTC face identities.

This does not rewrite subtitles or replace their typeface with the UI font.
Font files are inspected during preparation, not on every Kodi browse action.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import struct
import unicodedata

MAX_FONT_BYTES = 128 * 1024 * 1024
MAX_SUBTITLE_BYTES = 2 * 1024 * 1024
FONT_CACHE_SOFT_BYTES = 512 * 1024 * 1024


def normalized_family(name):
    return unicodedata.normalize("NFKC", str(name)).strip().lstrip("@").casefold()


def _system_chinese_text(data):
    """Strict GB18030 fallback for Linux Python builds without _codecs_cn.

    Use the installed libc converter, not a shell, network service or a copied
    Python extension. Both buffers are bounded; invalid/truncated input fails.
    """
    import ctypes
    import sys
    if not sys.platform.startswith('linux') or not 0 < len(data) <= MAX_SUBTITLE_BYTES:
        raise ValueError('Chinese codec unavailable')
    try:
        library = ctypes.CDLL(None, use_errno=True)
        open_codec, convert, close_codec = library.iconv_open, library.iconv, library.iconv_close
        open_codec.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        open_codec.restype = ctypes.c_void_p
        convert.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_size_t),
                            ctypes.POINTER(ctypes.c_char_p), ctypes.POINTER(ctypes.c_size_t)]
        convert.restype = ctypes.c_size_t
        close_codec.argtypes = [ctypes.c_void_p]
        close_codec.restype = ctypes.c_int
        descriptor = open_codec(b'UTF-8', b'GB18030')
        if descriptor == ctypes.c_void_p(-1).value:
            raise ValueError('Chinese codec unavailable')
        try:
            source = ctypes.create_string_buffer(data)
            output = ctypes.create_string_buffer(len(data) * 4 + 4)
            source_pointer = ctypes.cast(source, ctypes.c_char_p)
            output_pointer = ctypes.cast(output, ctypes.c_char_p)
            source_left, output_left = ctypes.c_size_t(len(data)), ctypes.c_size_t(len(output))
            result = convert(descriptor, ctypes.byref(source_pointer), ctypes.byref(source_left),
                             ctypes.byref(output_pointer), ctypes.byref(output_left))
            # No //IGNORE or //TRANSLIT: lossy/partial conversion is not text evidence.
            if result != 0 or source_left.value:
                raise ValueError('Invalid Chinese subtitle encoding')
            return output.raw[:len(output) - output_left.value].decode('utf-8')
        finally:
            close_codec(descriptor)
    except (OSError, AttributeError) as error:
        raise ValueError('Chinese codec unavailable') from error


def subtitle_text(data):
    if not data or len(data) > MAX_SUBTITLE_BYTES:
        raise ValueError("Subtitle size budget")
    encodings = ("utf-16",) if data.startswith((b"\xff\xfe", b"\xfe\xff")) else ("utf-8-sig", "gb18030")
    for encoding in encodings:
        try:
            try:
                text = data.decode(encoding)
            except LookupError:
                if encoding != 'gb18030':
                    raise ValueError('Subtitle codec unavailable')
                text = _system_chinese_text(data)
            if "\x00" in text or "<html" in text[:1024].casefold():
                raise ValueError("Not a subtitle")
            return text
        except UnicodeError:
            pass
    raise ValueError("Unknown subtitle encoding")


def ass_font_requirements(data):
    text = subtitle_text(data)
    if "[script info]" not in text.casefold() or "[events]" not in text.casefold():
        raise ValueError("ASS/SSA header required")
    section, columns, requests, styles, dialogues = "", [], {}, {}, []

    def weight(value):
        number = int(value)
        if number == 0: return 400
        if number in (-1, 1): return 700
        if 100 <= number <= 1000: return number
        raise ValueError('Unsupported ASS font weight')

    def add(name, weight=400, italic=False):
        name = name.strip()
        if not name or len(name) > 256 or any(ord(char) < 32 for char in name):
            raise ValueError("Invalid ASS font family")
        key = (normalized_family(name), weight, bool(italic))
        requests[key] = {"family": name, "weight": weight, "italic": bool(italic)}
        if len(requests) > 128:
            raise ValueError("ASS font requirement budget")

    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line.casefold()
            columns = []
        elif section in {"[v4+ styles]", "[v4 styles]"}:
            if line.casefold().startswith("format:"):
                columns = [part.strip().casefold() for part in line.split(":", 1)[1].split(",")]
            elif line.casefold().startswith("style:"):
                values = line.split(":", 1)[1].split(",", len(columns) - 1)
                style = dict(zip(columns, values))
                if "fontname" not in style:
                    raise ValueError("ASS style has no declared font column")
                name = style.get('name', '').strip()
                if not name or name in styles:
                    raise ValueError('Missing/duplicate ASS style identity')
                styles[name] = dict(family=style['fontname'].strip(), weight=weight(style.get('bold', '0')),
                                    italic=int(style.get('italic', '0')) != 0)
                add(styles[name]['family'], styles[name]['weight'], styles[name]['italic'])
        elif section == "[events]":
            if line.casefold().startswith('format:'):
                columns = [part.strip().casefold() for part in line.split(':', 1)[1].split(',')]
            elif line.casefold().startswith('dialogue:'):
                if not columns or columns[-1] != 'text' or 'style' not in columns:
                    raise ValueError('ASS event style/text columns required')
                values = line.split(':', 1)[1].split(',', len(columns) - 1)
                if len(values) != len(columns):
                    raise ValueError('Truncated ASS event')
                dialogues.append(dict(zip(columns, values)))
    for dialogue in dialogues:
        # Match libass ass_lookup_style for event styles: legacy SSA permits
        # leading '*' and treats only Default case-insensitively. Reset tags
        # use libass's separate strict lookup and must not inherit this rule.
        name = dialogue['style'].strip().lstrip('*')
        if name.casefold() == 'default':
            name = 'Default'
        if name not in styles:
            raise ValueError('ASS event refers to an unknown style')
        base = dict(styles[name])
        current = dict(base)
        # Keep font/weight/italic state across blocks. \fn changes only family;
        # \r resets the style. Never rewrite the original subtitle bytes.
        for part in re.split(r'(\{[^{}]*\})', dialogue['text']):
            if not (part.startswith('{') and part.endswith('}')):
                if part.strip(): add(current['family'], current['weight'], current['italic'])
                continue
            block = part[1:-1]
            # A font selector inside an animation is not claimed as exact.
            # Preserve that script and report unsupported rather than guess
            # transform scope or silently activate an incomplete font set.
            for transform in re.finditer(r'\\t\(', block):
                depth, end = 1, transform.end()
                while end < len(block) and depth:
                    depth += (block[end] == '(') - (block[end] == ')')
                    end += 1
                if depth:
                    raise ValueError('Unclosed ASS transform')
                if re.search(r'\\(?:fn|b(?:-?\d)|i[01]|r)', block[transform.end():end - 1]):
                    raise ValueError('Animated ASS font selection needs renderer-level analysis')
            for match in re.finditer(r'\\(fn|b|i|r)([^\\]*)', block):
                tag, argument = match[1], match[2].strip()
                if tag == 'fn':
                    current['family'] = argument or base['family']
                elif tag == 'r':
                    reset = argument or name
                    if reset not in styles: raise ValueError('Unknown ASS reset style')
                    base = dict(styles[reset])
                    current = dict(base)
                elif re.fullmatch(r'-?\d*', argument):
                    key = 'weight' if tag == 'b' else 'italic'
                    current[key] = (base[key] if not argument else weight(argument) if tag == 'b'
                                    else int(argument) != 0)
    if not requests:
        raise ValueError("No declared ASS font requirements")
    return {"subtitle_sha256": hashlib.sha256(data).hexdigest(), "fonts": list(requests.values()),
            "style_override": False}


def inspect_font(data):
    """Read internal names/weight/italic for every bounded TTF/OTF/TTC face."""
    if not 12 <= len(data) <= MAX_FONT_BYTES:
        raise ValueError('Font size budget')
    return _inspect_font(data, hashlib.sha256(data).hexdigest())


class _FontFileView:
    """Seek only the small OpenType metadata spans requested by the parser."""
    def __init__(self, stream, size):
        self.stream, self.size = stream, size

    def __len__(self):
        return self.size

    def __getitem__(self, key):
        start, end, step = key.indices(self.size)
        if step != 1 or end - start > 65536:
            raise ValueError('Font metadata span budget')
        self.stream.seek(start)
        data = self.stream.read(end-start)
        if len(data) != end-start:
            raise ValueError('Font changed during metadata read')
        return data


def inspect_font_file(path):
    """Same parser and hash evidence, at most 1 MiB of font bytes in Python.

    This is preparation IO, not a GUI/playback operation. Metadata is not
    accepted from a decoder report; it is derived again from the actual file.
    """
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Font inputs cannot traverse links')
    entry_before = path.stat()
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0))
    with os.fdopen(descriptor, 'rb') as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or not 12 <= before.st_size <= MAX_FONT_BYTES:
            raise ValueError('Font file type/size budget')
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
        result = _inspect_font(_FontFileView(stream, before.st_size), digest.hexdigest())
        after = os.fstat(stream.fileno())
        current = path.stat()
        fields = ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
        # Windows Python 3.12 path.stat and fstat expose different ctime
        # semantics. Compare each API with itself, plus file identity across
        # both, rather than ignoring change-time checks on either platform.
        changed = {k for k in fields if getattr(before, k) != getattr(after, k)
                   or getattr(entry_before, k) != getattr(current, k)}
        changed.update(k for k in ('st_dev', 'st_ino', 'st_size', 'st_mtime_ns')
                       if getattr(before, k) != getattr(entry_before, k))
        if path.is_symlink() or changed:
            raise ValueError('Font changed during inspection: ' + repr(sorted(changed)))
        return result


def _inspect_font(data, digest):
    if not 12 <= len(data) <= MAX_FONT_BYTES:
        raise ValueError("Font size budget")

    def read(fmt, offset):
        size = struct.calcsize(fmt)
        if offset < 0 or offset + size > len(data):
            raise ValueError("Truncated font table")
        return struct.unpack(fmt, data[offset:offset + size])

    if data[:4] == b"ttcf":
        count = read(">I", 8)[0]
        if not 1 <= count <= 64:
            raise ValueError("TTC face count budget")
        offsets = read(">" + "I" * count, 12)
    else:
        offsets = (0,)
    faces = []
    for face, offset in enumerate(offsets):
        if data[offset:offset + 4] not in (b"\0\1\0\0", b"OTTO", b"true"):
            raise ValueError("Unsupported font signature")
        count = read(">H", offset + 4)[0]
        if not 1 <= count <= 256:
            raise ValueError("Font table count budget")
        tables = {}
        for index in range(count):
            tag, _, start, length = read(">4sIII", offset + 12 + index * 16)
            if start > len(data) or length > len(data) - start:
                raise ValueError("Font table outside file")
            if tag in tables:
                raise ValueError("Duplicate font table")
            tables[tag] = (start, length)
        if b"name" not in tables:
            raise ValueError("Font has no name table")
        start, length = tables[b"name"]
        fmt, count, strings = read(">HHH", start)
        if fmt not in (0, 1) or count > 4096 or 6 + count * 12 > length or strings > length:
            raise ValueError("Invalid font name directory")
        names = {}
        for index in range(count):
            platform, encoding, language, name_id, size, relative = read(">HHHHHH", start + 6 + index * 12)
            if name_id not in (1, 2, 4, 6, 16, 17):
                continue
            a = start + strings + relative
            if a + size > start + length:
                raise ValueError("Font name outside name table")
            codec = "utf-16-be" if platform in (0, 3) else "mac_roman" if platform == 1 and encoding == 0 else None
            if not codec:
                continue
            try:
                value = data[a:a + size].decode(codec).strip("\x00 ")
            except UnicodeError:
                continue
            if value and value not in names.setdefault(name_id, []):
                names[name_id].append(value)
        families = names.get(16, []) + names.get(1, [])
        if not families:
            raise ValueError("Font has no usable internal family")
        weight, italic = 400, False
        if b"OS/2" in tables:
            os2, size = tables[b"OS/2"]
            if size >= 6:
                weight = read(">H", os2 + 4)[0]
            if size >= 64:
                italic = bool(read(">H", os2 + 62)[0] & 1)
        elif b"head" in tables and tables[b"head"][1] >= 46:
            italic = bool(read(">H", tables[b"head"][0] + 44)[0] & 2)
        faces.append({"face_index": face, "families": sorted(set(families)), "full_names": names.get(4, []),
                      "postscript_names": names.get(6, []), "subfamilies": names.get(17, []) + names.get(2, []),
                      "weight": weight, "italic": italic, "variable": b"fvar" in tables})
    return {"sha256": digest, "bytes": len(data),
            "extension": ".ttc" if data[:4] == b"ttcf" else ".otf" if data[:4] == b"OTTO" else ".ttf", "faces": faces}


def select_fonts(requirements, candidates):
    """Exact internal-name matches only. Return unresolved requirements honestly."""
    selected, missing = [], []
    priorities = {"media_attachment": 0, "same_release_pack": 1, "local_exact": 2}
    for request in requirements["fonts"]:
        matches = []
        target = normalized_family(request["family"])
        for candidate in candidates:
            if candidate.get("origin") not in priorities:
                continue
            for face in candidate.get("faces", []):
                aliases = face["families"] + face.get("full_names", []) + face.get("postscript_names", [])
                if target not in {normalized_family(name) for name in aliases}:
                    continue
                matches.append((priorities[candidate["origin"]], face["italic"] != request["italic"],
                                abs(face["weight"] - request["weight"]), candidate["sha256"], candidate, face))
        if not matches:
            missing.append(request)
        else:
            _, _, _, _, candidate, face = min(matches, key=lambda match: match[:4])
            selected.append({"request": request, "sha256": candidate["sha256"], "bytes": candidate["bytes"],
                             "extension": candidate["extension"], "origin": candidate["origin"], "face": face,
                             "synthetic_style_may_be_needed": face["weight"] != request["weight"] or face["italic"] != request["italic"]})
    status = ('MISSING_FONTS' if missing else 'SYNTHETIC_STYLE_REQUIRED_NOT_VISUAL_PROOF'
              if any(item['synthetic_style_may_be_needed'] for item in selected)
              else 'EXACT_FONTS_READY_NOT_VISUAL_PROOF')
    return {"subtitle_sha256": requirements["subtitle_sha256"], "selected": selected, "missing": missing,
            "status": status}


def cache_eviction_candidates(entries, pinned_hashes, extra_bytes=0, limit=FONT_CACHE_SOFT_BYTES):
    """Only managed hash objects, never user fonts. Active/current/next pinned."""
    if type(extra_bytes) is not int or extra_bytes < 0:
        raise ValueError("Invalid font cache reservation")
    total = sum(entry["bytes"] for entry in entries) + extra_bytes
    selected = []
    for entry in sorted(entries, key=lambda item: (item["last_used"], -item["bytes"], item["sha256"])):
        if total <= limit:
            break
        if entry["sha256"] in pinned_hashes or not entry.get("managed"):
            continue
        selected.append(entry["sha256"])
        total -= entry["bytes"]
    return {"hashes": selected, "remaining_bytes": total, "soft_limit_exceeded_by_protected_items": total > limit}
