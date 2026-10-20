"""Compare ELF64 Go pclntab, ELF STT_FUNC symbols and full Ghidra exports.

Reads only section metadata and function names/addresses; never executes the ELF
or dumps rodata, keys, credentials, arbitrary strings or embedded assets.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import struct


def string_at(data, offset):
    end = data.index(b"\0", offset)
    return data[offset:end].decode("utf-8", errors="replace")


def table(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write_table(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def ranges_without(whole, covered):
    merged = []
    for low, high in sorted(covered):
        low, high = max(low, whole[0]), min(high, whole[1])
        if high <= low:
            continue
        if merged and low <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(high, merged[-1][1]))
        else:
            merged.append((low, high))
    cursor = whole[0]
    gaps = []
    for low, high in merged:
        if cursor < low:
            gaps.append((cursor, low))
        cursor = high
    if cursor < whole[1]:
        gaps.append((cursor, whole[1]))
    return gaps


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("binary", type=Path)
    parser.add_argument("export", type=Path)
    args = parser.parse_args()
    data = args.binary.read_bytes()
    if data[:7] != b"\x7fELF\x02\x01\x01":
        raise ValueError("Expected little-endian ELF64")
    header = struct.unpack_from("<HHIQQQIHHHHHH", data, 16)
    section_offset, section_size, section_count, names_index = header[5], header[10], header[11], header[12]
    if section_size != 64:
        raise ValueError("Unexpected section header size")
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, section_offset + index * section_size)
                for index in range(section_count)]
    def content(section):
        offset, size = section[4:6]
        if offset + size > len(data):
            raise ValueError("Section exceeds file")
        return data[offset:offset + size]
    names = content(sections[names_index])
    by_name = {string_at(names, section[0]): section for section in sections}
    pcln = content(by_name[".gopclntab"])
    magic, pad1, pad2, quantum, pointer_size = struct.unpack_from("<IBBBB", pcln)
    if magic != 0xfffffff1 or pad1 or pad2 or pointer_size != 8:
        raise ValueError(f"Unsupported Go pclntab header {magic:x}, ptr={pointer_size}")
    count, files, text_start, func_names, _, _, _, pcln_offset = struct.unpack_from("<8Q", pcln, 8)
    header_text_start = text_start
    if not text_start:
        # This Go toolchain leaves pcHeader.textStart zero in the file. The
        # runtime supplies moduledata.text; for these ELF executables it equals
        # .text sh_addr, independently checked against ELF function symbols.
        text_start = by_name[".text"][3]
    functions = []
    for index in range(count):
        entry, function_offset = struct.unpack_from("<II", pcln, pcln_offset + index * 8)
        next_entry = struct.unpack_from("<I", pcln, pcln_offset + (index + 1) * 8)[0]
        metadata_entry, name_offset = struct.unpack_from("<Ii", pcln, pcln_offset + function_offset)
        if metadata_entry != entry or next_entry < entry:
            raise ValueError(f"Inconsistent Go function table entry {index}")
        functions.append({"address": f"{text_start + entry:08x}", "end_exclusive": f"{text_start + next_entry:08x}",
                          "name": string_at(pcln, func_names + name_offset), "table_span_bytes": next_entry - entry})
    symbol_functions = []
    for section in sections:
        if section[1] != 2:
            continue
        strings = content(sections[section[6]])
        symbols = content(section)
        if section[9] != 24:
            raise ValueError("Unexpected ELF64 symbol entry size")
        for offset in range(0, len(symbols), 24):
            name_at, info, _, section_index, address, size = struct.unpack_from("<IBBHQQ", symbols, offset)
            if info & 15 == 2 and section_index and address:
                symbol_functions.append({"address": f"{address:08x}", "name": string_at(strings, name_at), "size": size})
    ghidra = table(args.export / "functions.tsv")
    ghidra_by_address = {row["address"]: row for row in ghidra}
    go_addresses = {row["address"] for row in functions}
    symbol_addresses = {row["address"] for row in symbol_functions}
    symbol_names_by_address = {}
    for row in symbol_functions:
        symbol_names_by_address.setdefault(row["address"], set()).add(row["name"])
    name_and_address_matches = sum(row["name"] in symbol_names_by_address.get(row["address"], set()) for row in functions)
    aliases = [{"address": row["address"], "pclntab_name": row["name"],
                "elf_names": ";".join(sorted(symbol_names_by_address.get(row["address"], set())))}
               for row in functions if row["name"] not in symbol_names_by_address.get(row["address"], set())]
    normalized_name_matches = sum(any(row["name"].replace("·", ".") == symbol.removesuffix(".abi0")
                                     for symbol in symbol_names_by_address.get(row["address"], set())) for row in functions)
    missing_go = [row for row in functions if row["address"] not in ghidra_by_address]
    missing_symbol = [row for row in symbol_functions if row["address"] not in ghidra_by_address]
    extra_ghidra = [row for row in ghidra if row["address"] not in go_addresses]
    text_section = by_name[".text"]
    text_extent = (text_section[3], text_section[3] + text_section[5])
    go_gaps = ranges_without(text_extent, [(int(row["address"], 16), int(row["end_exclusive"], 16)) for row in functions])
    body_ranges = table(args.export / "function-body-ranges.tsv")
    ghidra_gaps = ranges_without(text_extent, [(int(row["start"], 16), int(row["end_inclusive"], 16) + 1) for row in body_ranges])
    gap_rows = []
    for start, end in ghidra_gaps:
        raw = data[text_section[4] + start - text_extent[0]:text_section[4] + end - text_extent[0]]
        if header[1] == 62:
            padding = all(byte in (0x90, 0xcc) for byte in raw)
        elif header[1] == 183:
            padding = start % 4 == 0 and len(raw) % 4 == 0 and all(
                raw[index:index + 4] in (b"\x00\x00\x00\x00", b"\x1f\x20\x03\xd5")
                for index in range(0, len(raw), 4))
        else:
            padding = False
        gap_rows.append({"start": f"{start:08x}", "end_exclusive": f"{end:08x}", "bytes": end - start,
                         "sha256": hashlib.sha256(raw).hexdigest(),
                         "classification": "padding-pattern" if padding else "unclassified-outside-function-body"})
    write_table(args.export / "go-pclntab-functions.tsv", list(functions[0]), functions)
    write_table(args.export / "elf-function-symbols.tsv", ["address", "name", "size"], symbol_functions)
    write_table(args.export / "pclntab-elf-name-aliases.tsv", ["address", "pclntab_name", "elf_names"], aliases)
    write_table(args.export / "go-functions-missing-in-ghidra.tsv", list(functions[0]), missing_go)
    write_table(args.export / "elf-functions-missing-in-ghidra.tsv", ["address", "name", "size"], missing_symbol)
    write_table(args.export / "ghidra-functions-not-in-pclntab.tsv", list(ghidra[0]), extra_ghidra)
    write_table(args.export / "text-unassigned-ranges.tsv", ["start", "end_exclusive", "bytes", "sha256", "classification"], gap_rows)
    summary = {"binary_sha256": hashlib.sha256(data).hexdigest(), "pclntab_magic": f"{magic:08x}",
               "pclntab_header_text_start": f"{header_text_start:08x}",
               "effective_text_base": f"{text_start:08x}",
               "text_base_source": "pcHeader.textStart" if header_text_start else "ELF .text sh_addr; pcHeader.textStart is zero",
               "pclntab_function_count": count, "pclntab_source_file_count": files,
               "elf_function_symbols": len(symbol_functions), "elf_distinct_function_addresses": len(symbol_addresses),
               "pclntab_entries_matching_elf_symbol_name_and_address": name_and_address_matches,
               "pclntab_entries_matching_elf_after_abi0_and_middle_dot_normalization": normalized_name_matches,
               "ghidra_identified_functions": len(ghidra), "pclntab_missing_in_ghidra": len(missing_go),
               "elf_function_addresses_missing_in_ghidra": len({row["address"] for row in missing_symbol}),
               "ghidra_functions_not_in_pclntab": len(extra_ghidra),
               "text_start": f"{text_extent[0]:08x}", "text_end_exclusive": f"{text_extent[1]:08x}",
               "text_bytes": text_extent[1] - text_extent[0],
               "text_bytes_outside_go_function_spans": sum(end - start for start, end in go_gaps),
               "text_ranges_outside_go_function_spans": [[f"{start:08x}", f"{end:08x}"] for start, end in go_gaps],
               "text_bytes_outside_ghidra_function_bodies": sum(end - start for start, end in ghidra_gaps),
               "text_ranges_outside_ghidra_function_bodies": len(ghidra_gaps),
               "unassigned_text_bytes_matching_padding_pattern": sum(row["bytes"] for row in gap_rows if row["classification"] == "padding-pattern"),
               "unassigned_text_bytes_not_classified": sum(row["bytes"] for row in gap_rows if row["classification"] != "padding-pattern"),
               "limitations": ["Function-table spans include alignment padding; they are not a decoded instruction coverage claim",
                               "Unassigned text ranges are preserved for review, not automatically classified as missing code",
                               "Inlined source functions do not necessarily have independent pclntab entries",
                               "Neither table coverage nor successful C emission recovers the original Go source"]}
    (args.export / "go-coverage-crosscheck.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
