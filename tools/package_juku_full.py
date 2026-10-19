"""Package generated static-analysis artifacts and verify their archive contents."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import zipfile


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("export", type=Path)
    args = parser.parse_args()
    root = args.export.resolve()
    manifest = root / "artifact-manifest.tsv"
    files = sorted(path for path in root.rglob("*") if path.is_file() and path != manifest)
    if any(path.is_symlink() for path in files):
        raise ValueError("Refusing symlinks in research export")
    rows = [{"path": path.relative_to(root).as_posix(), "bytes": path.stat().st_size, "sha256": digest(path)} for path in files]
    with manifest.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, ["path", "bytes", "sha256"], delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    output = root.parent / "archives"
    output.mkdir(exist_ok=True)
    archive_path = output / f"juku-0.80-{root.name}-full-static.zip"
    expected = {row["path"]: row["sha256"] for row in rows}
    expected[manifest.name] = digest(manifest)
    with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
        for path in [*files, manifest]:
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(root.name + "/" + relative, (2026, 10, 19, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, path.read_bytes(), compresslevel=6)
    with zipfile.ZipFile(archive_path) as archive:
        if len(archive.infolist()) != len(expected):
            raise ValueError("Archive count mismatch")
        for entry in archive.infolist():
            relative = entry.filename.removeprefix(root.name + "/")
            if hashlib.sha256(archive.read(entry)).hexdigest() != expected[relative]:
                raise ValueError(f"Archive content mismatch: {relative}")
    result = {"architecture": root.name, "archive": archive_path.name, "bytes": archive_path.stat().st_size,
              "sha256": digest(archive_path), "archive_entries": len(expected), "verified_all_entry_sha256": True,
              "manifest": str(manifest.relative_to(root.parent)), "manifest_sha256": expected[manifest.name],
              "uncompressed_bytes_without_manifest": sum(row["bytes"] for row in rows),
              "scope": "All architecture export files; original input package and binary are not included"}
    (output / f"{root.name}-archive.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
