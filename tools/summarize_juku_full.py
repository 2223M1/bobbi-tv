"""Audit full Ghidra exports without executing the analyzed program.

The function inventory is authoritative; no package/name filter controls coverage.
Only generated research outputs are read and written.
"""
from __future__ import annotations

import argparse
import collections
import csv
import json
from pathlib import Path


def read_tsv(path):
    with path.open(encoding="utf-8", newline="") as stream:
        return list(csv.DictReader(stream, delimiter="\t"))


def write_tsv(path, fields, rows):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def module_name(name):
    if name.startswith(("type:", "go:")):
        return name.split(":", 1)[0] + ":compiler-generated"
    name = name.split("[", 1)[0]
    slash = name.rfind("/")
    dot = name.find(".", slash + 1)
    return name[:dot] if dot >= 0 else name.split("::", 1)[0]


def category(module):
    if module == "main" or module.startswith("mv-daemon/"):
        return "juku"
    if module == "runtime" or module.startswith(("runtime/", "internal/runtime/")):
        return "go-runtime"
    if "." in module or module.startswith(("vendor/", "golang.org/")):
        return "third-party"
    if module.startswith(("FUN_", "LAB_", "_", "go:", "type:", "thunk_")):
        return "compiler-or-unclassified"
    return "standard-library-or-unclassified"


def summarize(root):
    inventory = read_tsv(root / "functions.tsv")
    results = {}
    attempts = collections.Counter()
    for journal in sorted((root / "journals").glob("*.tsv")):
        for row in read_tsv(journal):
            if row.get("completed_utc") and row.get("status"):
                attempts[row["address"]] += 1
                if row["completed_utc"] > results.get(row["address"], {}).get("completed_utc", ""):
                    results[row["address"]] = row
    rows, failures, calls = [], [], []
    module_counts = collections.defaultdict(collections.Counter)
    module_edges = collections.Counter()
    status_counts, category_counts = collections.Counter(), collections.Counter()
    total_bytes = collections.Counter()
    addresses = set()
    for function in inventory:
        address = function["address"]
        if address in addresses:
            raise ValueError(f"Duplicate inventory address {address}")
        addresses.add(address)
        result = results.get(address, {})
        directory = root / "functions" / address[:4]
        stem = directory / address
        asm, cfile, edges = (stem.with_suffix(extension) for extension in (".asm", ".c", ".calls.tsv"))
        module = module_name(function["name"])
        group = category(module)
        state = result.get("status", "NOT_ATTEMPTED")
        missing = []
        for label, path in (("asm", asm), ("calls", edges), ("c", cfile)):
            if path.exists():
                total_bytes[label] += path.stat().st_size
            else:
                missing.append(label)
        if missing and state == "OK":
            state = "INCOMPLETE_FILES"
        row = {**function, "module": module, "category": group, "status": state,
               "attempts": attempts[address], "elapsed_ms": result.get("elapsed_ms", ""),
               "pseudocode": cfile.relative_to(root).as_posix() if cfile.exists() else "",
               "assembly": asm.relative_to(root).as_posix() if asm.exists() else "",
               "missing_files": ",".join(missing), "error": result.get("error", "")}
        rows.append(row)
        if state != "OK":
            failures.append(row)
        status_counts[state] += 1
        category_counts[group] += 1
        module_counts[module]["identified"] += 1
        module_counts[module][state] += 1
        module_counts[module]["body_bytes"] += int(function["body_bytes"])
        if edges.exists():
            for edge in read_tsv(edges):
                calls.append(edge)
                module_edges[(module, module_name(edge["callee_name"]))] += 1
    fields = list(rows[0])
    write_tsv(root / "index.tsv", fields, rows)
    write_tsv(root / "failures.tsv", fields, failures)
    call_fields = ["caller_address", "caller_name", "callee_address", "callee_name"]
    calls.sort(key=lambda row: (row["caller_address"], row["callee_address"]))
    write_tsv(root / "calls.tsv", call_fields, calls)
    write_tsv(root / "callers.tsv", call_fields, sorted(calls, key=lambda row: (row["callee_address"], row["caller_address"])))
    write_tsv(root / "modules.tsv", ["module", "category", "identified", "ok", "not_ok", "body_bytes"],
              ({"module": module, "category": category(module), "identified": values["identified"],
                "ok": values["OK"], "not_ok": values["identified"] - values["OK"], "body_bytes": values["body_bytes"]}
               for module, values in sorted(module_counts.items())))
    write_tsv(root / "module-calls.tsv", ["caller_module", "callee_module", "direct_function_edges"],
              ({"caller_module": source, "callee_module": target, "direct_function_edges": count}
               for (source, target), count in sorted(module_edges.items())))
    summary = {"architecture": root.name, "identified_functions": len(inventory),
               "attempted_functions": sum(value > 0 for value in attempts.values()),
               "all_identified_attempted": all(attempts[address] > 0 for address in addresses),
               "status_counts": dict(status_counts), "category_counts": dict(category_counts),
               "direct_call_edges": len(calls), "modules": len(module_counts),
               "file_bytes": dict(total_bytes), "total_attempt_records": sum(attempts.values()),
               "function_coverage_denominator": "All internal and external functions identified in the existing Ghidra program",
               "limitations": ["Not original Go source", "Coverage is of identified functions, not proof every executable byte is code",
                               "Direct call graph omits unresolved interface/function-pointer dispatch",
                               "OK means Ghidra emitted C, not semantic correctness or recompilable source"]}
    (root / "coverage.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(summarize(args.root), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
