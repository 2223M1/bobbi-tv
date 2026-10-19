#!/usr/bin/env python3
"""Create private review attachments from a deliberately narrow allowlist.

No device, Git, network, external executable, or installer is invoked. Originals
remain untouched. Objects are deduplicated by SHA-256, with every original path
retained in the manifest. ZIP/APK members (including nested component ZIPs) are
read and checked before inclusion; suspicious artifacts are quarantined, not
silently omitted. This is a packaging check, not a malware/security attestation.
"""

import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile
import zipfile


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist/web-review-20261019"
MANIFEST = ROOT / "review-evidence/web-artifact-manifest-20261019.json"
LIMIT = 1_450_000_000
CHUNK = 4 * 1024 * 1024
JUKU = (
    "docs/research/juku-full-20261019/archives/juku-0.80-arm64-full-static.zip",
    "docs/research/juku-full-20261019/archives/juku-0.80-amd64-full-static.zip",
)
PRIVATE_PEM = re.compile(
    rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA |ENCRYPTED )?PRIVATE KEY-----"
    rb"\s+[A-Za-z0-9+/=\r\n]{80,}"
)
PRIVATE_NAMES = {
    "device.pem", "device_key.pem", "session.json", "accounts.json",
    "credentials.json", "cookies.json", "cookies.txt", "cookies.dat",
    "token.json", "tokens.json", "id_rsa", "id_ed25519", ".env",
}
PRIVATE_DIRS = {"profile", "profiles", "userdata", ".ssh"}
PRIVATE_EXTENSIONS = {".key", ".p12", ".pfx", ".jks", ".keystore"}
TEXT_EXTENSIONS = {".json", ".xml", ".txt", ".log", ".pem", ".py", ".sh", ".conf", ".ini", ".yaml", ".yml"}
# Manually reviewed native/.work/kodi/userdata defaults, not user profiles.
# Each pair is the original CRLF source and its byte-equivalent LF form.
KODI_TEMPLATE_HASHES = {
    "ModeLines_template.xml": {"b8493e17701e900448865f7ee2ad88e675e0de13e47a70898e837c5d955a0d07", "625ddc55809d2de0155feecf4a8fe634fe1e6bf82b113047fb3004a0eed463f3"},
    "RssFeeds.xml": {"3ba3b17f5d6a22e104ce8972e6bf176620f40d2b7ad816538030ae6ccb2b95f7", "2285b92ce536efbc0d9a494db80fa12c81ff10ed0c86079cdb891f1b59aa14a0"},
    "iOS/sources.xml": {"ad8c0a7b49c41585f277e85ffefd30bfb53a6e2478b08b8e783dcb1b0834e6ea", "1d1a210425fe6df8cc024938038d17400d6860839aa46ce2a76849a8d7e99eb0"},
}


def relative(path):
    return path.relative_to(ROOT).as_posix()


def digest_stream(stream, inspect_text=False, copy_to=None):
    sha = hashlib.sha256()
    size = 0
    tail = b""
    private_key = False
    while True:
        block = stream.read(CHUNK)
        if not block:
            break
        sha.update(block)
        size += len(block)
        if copy_to is not None:
            copy_to.write(block)
        if inspect_text:
            private_key |= bool(PRIVATE_PEM.search(tail + block))
            tail = block[-4096:]
    return sha.hexdigest(), size, private_key


def path_problem(name, digest=None):
    path = PurePosixPath(name.replace("\\", "/"))
    parts = [part.lower() for part in path.parts]
    if path.is_absolute() or ".." in parts or any(":" in part for part in parts):
        return "unsafe_archive_path"
    if any(part in PRIVATE_DIRS for part in parts):
        # Only distribution defaults at these exact locations can bypass the
        # userdata gate, and only with reviewed content. Profiles never can.
        template = None
        if name.startswith("assets/userdata/"):
            template = name[len("assets/userdata/"):]
        elif re.fullmatch(r"bobbi-TV-[^/]+/host/userdata/.+", name):
            template = name.split("/host/userdata/", 1)[1]
        if template is None or digest not in KODI_TEMPLATE_HASHES.get(template, set()):
            return "profile_or_userdata_directory"
    if parts and (parts[-1] in PRIVATE_NAMES or path.suffix.lower() in PRIVATE_EXTENSIONS):
        return "private_or_account_filename"
    if parts and path.suffix.lower() == ".pem" and parts[-1] not in {
        "cacert.pem", "public.pem", "public_key.pem", "public-key.pem",
    }:
        return "unreviewed_pem"
    return None


def regular_file(path):
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
        raise ValueError("Non-regular/reparse input: " + relative(path))
    path.resolve().relative_to(ROOT)
    return info


def walk_regular(directory):
    if not directory.is_dir():
        raise ValueError("Missing required directory: " + relative(directory))
    for current, dirs, files in os.walk(str(directory), followlinks=False):
        dirs[:] = sorted(name for name in dirs if name != "__pycache__")
        for name in dirs:
            node = Path(current) / name
            info = node.lstat()
            if node.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise ValueError("Reparse directory is not eligible: " + relative(node))
        for name in sorted(files):
            node = Path(current) / name
            regular_file(node)
            yield node


def inventory():
    selected = {}
    excluded = []

    def add(path, category):
        regular_file(path)
        selected[relative(path)] = {"path": relative(path), "category": category}

    releases = list(walk_regular(ROOT / "dist/private-releases"))
    if len(releases) != 17 or any(not p.name.endswith(".bobbi-update.zip") for p in releases):
        raise ValueError("Expected exactly 17 complete private release ZIPs")
    for path in releases:
        add(path, "signed_private_release")
    components = sorted((ROOT / "dist").glob("private-components*"))
    if not components or any(not path.is_dir() for path in components):
        raise ValueError("Missing/unexpected component roots")
    for directory in components:
        for path in walk_regular(directory):
            if path.suffix.lower() in {".json", ".xml", ".md5", ".sha256", ".zip"}:
                add(path, "frozen_component_or_manifest")
            else:
                excluded.append({"path": relative(path), "reason": "component_artwork_already_inside_component_zip"})
    for path in sorted((ROOT / "dist/native").iterdir()):
        if path.is_file() and (path.suffix.lower() in {".apk", ".exe", ".zip", ".idsig"} or path.name.endswith(".verification.json")):
            add(path, "native_distribution")
    for path in walk_regular(ROOT / "native/ce-directory-lifetime-20261019"):
        add(path, "ce_directory_lifetime_source_and_build")
    for path in walk_regular(ROOT / "native/build/logs"):
        if path.suffix.lower() in {".log", ".txt", ".json"}:
            add(path, "native_build_log")
        else:
            excluded.append({"path": relative(path), "reason": "not_an_ordinary_log"})
    for name in JUKU:
        add(ROOT / name, "existing_juku_full_static_archive")
    return [selected[name] for name in sorted(selected)], excluded


def inspect_archive(source, label, cache, depth=0):
    if depth > 12:
        raise ValueError("Nested archive depth limit exceeded: " + label)
    rows, problems = [], []
    with zipfile.ZipFile(source) as archive:
        seen = set()
        for info in archive.infolist():
            if info.filename in seen:
                problems.append({"member": info.filename, "reason": "duplicate_zip_member"})
            seen.add(info.filename)
            mode = (info.external_attr >> 16) & 0xFFFF
            if stat.S_ISLNK(mode):
                problems.append({"member": info.filename, "reason": "archive_symlink"})
            if info.is_dir():
                # A directory entry contains no user state. Its child files
                # still pass the exact path and content checks below.
                continue
            suffix = PurePosixPath(info.filename).suffix.lower()
            nested = suffix in {".zip", ".apk"}
            with tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024) as spool:
                with archive.open(info) as stream:
                    digest, size, key = digest_stream(stream, suffix in TEXT_EXTENSIONS, spool if nested else None)
                if key:
                    problems.append({"member": info.filename, "reason": "private_key_material"})
                if size != info.file_size:
                    raise ValueError("ZIP size mismatch: " + label + ":" + info.filename)
                row = {"path": info.filename, "bytes": size, "sha256": digest}
                reason = path_problem(info.filename, digest)
                if reason:
                    problems.append({"member": info.filename, "reason": reason})
                elif "/userdata/" in info.filename:
                    row["reviewed_exception"] = "exact_hash_pinned_kodi_distribution_template"
                if "/__pycache__/" in info.filename:
                    row["packaging_note"] = "existing_distribution_bytecode_retained_to_preserve_signature"
                if nested:
                    row["archive_audit_sha256"] = digest
                    if digest not in cache:
                        spool.seek(0)
                        cache[digest] = inspect_archive(spool, label + "!" + info.filename, cache, depth + 1)
                    if cache[digest]["problems"]:
                        problems.append({"member": info.filename, "reason": "nested_archive_quarantined", "archive_sha256": digest})
                rows.append(row)
    return {"members": rows, "problems": problems}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    if args.verify_only:
        with MANIFEST.open(encoding="utf-8") as stream:
            manifest = json.load(stream)
        verify(manifest)
        print(json.dumps({"verified": True, "attachments": len(manifest["attachments"]), "files": len(manifest["files"])}), flush=True)
        return
    if MANIFEST.exists() or (OUTPUT.exists() and any(OUTPUT.iterdir())):
        raise ValueError("Refusing to overwrite existing manifest/attachments; use --verify-only")
    files, excluded = inventory()
    cache, objects, quarantined = {}, {}, []
    for index, entry in enumerate(files, 1):
        path = ROOT / entry["path"]
        before = regular_file(path)
        with path.open("rb") as stream:
            digest, size, key = digest_stream(stream, path.suffix.lower() in TEXT_EXTENSIONS)
        after = regular_file(path)
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise ValueError("Input changed while hashing: " + entry["path"])
        entry.update(sha256=digest, bytes=size)
        problems = []
        reason = path_problem(entry["path"])
        if reason:
            problems.append({"reason": reason})
        if key:
            problems.append({"reason": "private_key_material"})
        if path.suffix.lower() in {".zip", ".apk"}:
            if digest not in cache:
                cache[digest] = inspect_archive(path, entry["path"], cache)
            entry["archive_audit_sha256"] = digest
            problems.extend(cache[digest]["problems"])
        if path.suffix.lower() == ".exe":
            counterpart = path.with_name(path.name.replace("-setup.exe", ".zip"))
            if counterpart.is_file():
                entry["not_executed_corresponding_zip"] = relative(counterpart)
                entry["inspection_limitation"] = "EXE hashed only; corresponding ZIP inspected independently; not binary equivalence attestation"
            else:
                problems.append({"reason": "missing_corresponding_windows_zip"})
        if problems:
            entry["status"] = "quarantined_not_packaged"
            quarantined.append({"path": entry["path"], "sha256": digest, "problems": problems})
        elif entry["category"] == "existing_juku_full_static_archive":
            entry["status"] = "existing_attachment"
        else:
            entry["status"] = "packaged"
            item = objects.setdefault(digest, {"sha256": digest, "bytes": size, "source": entry["path"], "original_paths": []})
            item["original_paths"].append(entry["path"])
        if index % 25 == 0 or index == len(files):
            print(json.dumps({"stage": "audit", "completed": index, "total": len(files), "unique_objects": len(objects), "quarantined": len(quarantined)}), flush=True)
    # Fail the EXE packaging gate too if its matching ZIP failed inspection.
    status = {entry["path"]: entry["status"] for entry in files}
    for entry in files:
        counterpart = entry.get("not_executed_corresponding_zip")
        if counterpart and status.get(counterpart) != "packaged":
            entry["status"] = "quarantined_not_packaged"
            quarantined.append({"path": entry["path"], "sha256": entry["sha256"], "problems": [{"reason": "corresponding_zip_quarantined"}]})
            item = objects[entry["sha256"]]
            item["original_paths"].remove(entry["path"])
            if not item["original_paths"]:
                del objects[entry["sha256"]]
    OUTPUT.mkdir(parents=True, exist_ok=True)
    groups = []
    for item in sorted(objects.values(), key=lambda row: (-row["bytes"], row["sha256"])):
        required = item["bytes"] + 512
        if required >= LIMIT:
            raise ValueError("Single artifact exceeds attachment limit: " + item["source"])
        group = next((g for g in groups if g["estimated_bytes"] + required < LIMIT - 4096), None)
        if group is None:
            group = {"estimated_bytes": 0, "objects": []}
            groups.append(group)
        group["objects"].append(item)
        group["estimated_bytes"] += required
    attachments = []
    for index, group in enumerate(groups, 1):
        target = OUTPUT / ("bobbi-web-artifacts-20261019-%02d.zip" % index)
        with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
            for item in group["objects"]:
                member = "objects/sha256/" + item["sha256"][:2] + "/" + item["sha256"]
                source = ROOT / item["source"]
                with source.open("rb") as stream, archive.open(member, "w", force_zip64=True) as out:
                    digest, size, _ = digest_stream(stream, copy_to=out)
                if digest != item["sha256"] or size != item["bytes"]:
                    raise ValueError("Source changed while packaging: " + item["source"])
                item.update(attachment=relative(target), member=member)
        with target.open("rb") as stream:
            digest, size, _ = digest_stream(stream)
        if size >= 1_500_000_000:
            raise ValueError("Attachment size ceiling exceeded")
        attachments.append({"path": relative(target), "bytes": size, "sha256": digest, "kind": "content_addressed_zip", "objects": len(group["objects"])})
        print(json.dumps({"stage": "packaged", "path": relative(target), "bytes": size, "objects": len(group["objects"])}), flush=True)
    for entry in files:
        if entry["status"] == "existing_attachment":
            attachments.append({"path": entry["path"], "bytes": entry["bytes"], "sha256": entry["sha256"], "kind": "existing_full_static_zip"})
        elif entry["status"] == "packaged":
            item = objects[entry["sha256"]]
            entry.update(attachment=item["attachment"], member=item["member"])
    manifest = {
        "schema": "bobbi.private-web-artifacts.v1",
        "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "private_only": True,
        "max_attachment_bytes_exclusive": 1_500_000_000,
        "instructions": "Private attachments only. For each packaged file, extract the specified attachment member and restore to its original path; verify its SHA-256 first. Existing Juku full-static ZIPs are separate unchanged attachments. Do not execute installers during review.",
        "scope": {"release_count_required": 17, "component_roots": sorted(set(entry["path"].split("/")[1] for entry in files if entry["category"] == "frozen_component_or_manifest")), "native_build_scope": "logs only; all other native/build content excluded", "excluded": ["device profiles/account state", "signing private keys", "raw Juku author ZIPs", "loose __pycache__ directories"], "reviewed_native_defaults": {key: sorted(values) for key, values in KODI_TEMPLATE_HASHES.items()}, "native_bytecode_policy": "Already shipped __pycache__ inside original signed APKs is retained, not a device profile."},
        "files": files,
        "objects": sorted(objects.values(), key=lambda row: row["sha256"]),
        "attachments": attachments,
        "archive_audits": cache,
        "explicitly_excluded": excluded,
        "quarantined_not_uploaded": quarantined,
        "statistics": {"input_paths": len(files), "input_bytes": sum(e["bytes"] for e in files), "packaged_original_paths": sum(e["status"] == "packaged" for e in files), "unique_packaged_objects": len(objects), "unique_packaged_bytes": sum(e["bytes"] for e in objects.values()), "existing_attachments": sum(e["status"] == "existing_attachment" for e in files), "quarantined_paths": len(quarantined), "archive_audits": len(cache)},
        "verification": {"all_attachment_hashes": False, "all_packaged_member_hashes": False, "all_original_path_hashes": False},
    }
    # Persist the audit even when a suspicious historical artifact is withheld.
    write_json(MANIFEST, manifest)
    verify(manifest)
    manifest["verification"] = {"all_attachment_hashes": True, "all_packaged_member_hashes": True, "all_original_path_hashes": True, "verified_utc": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    write_json(MANIFEST, manifest)
    print(json.dumps({"manifest": relative(MANIFEST), "statistics": manifest["statistics"], "attachments": attachments, "quarantined": [{"path": row["path"], "problems": len(row["problems"])} for row in quarantined]}, ensure_ascii=False), flush=True)


def verify(manifest):
    expected_objects = {row["sha256"]: row for row in manifest["objects"]}
    verified = set()
    for attachment in manifest["attachments"]:
        path = ROOT / attachment["path"]
        with path.open("rb") as stream:
            digest, size, _ = digest_stream(stream)
        if (digest, size) != (attachment["sha256"], attachment["bytes"]):
            raise ValueError("Attachment verification failed: " + attachment["path"])
        if size >= 1_500_000_000:
            raise ValueError("Attachment exceeds upload ceiling")
        if attachment["kind"] != "content_addressed_zip":
            continue
        with zipfile.ZipFile(path) as archive:
            members = archive.namelist()
            expected = [row for row in expected_objects.values() if row["attachment"] == attachment["path"]]
            if len(members) != len(expected) or set(members) != {row["member"] for row in expected}:
                raise ValueError("Missing or extra packaged member")
            for row in expected:
                with archive.open(row["member"]) as stream:
                    member_digest, member_size, _ = digest_stream(stream)
                if (member_digest, member_size) != (row["sha256"], row["bytes"]):
                    raise ValueError("Packaged member verification failed")
                verified.add(row["sha256"])
        print(json.dumps({"stage": "verified_attachment", "path": attachment["path"]}), flush=True)
    if verified != set(expected_objects):
        raise ValueError("Object missing from all attachments")
    current, _ = inventory()
    if {row["path"] for row in current} != {row["path"] for row in manifest["files"]}:
        raise ValueError("Whitelist changed since packaging")
    for row in manifest["files"]:
        with (ROOT / row["path"]).open("rb") as stream:
            digest, size, _ = digest_stream(stream)
        if (digest, size) != (row["sha256"], row["bytes"]):
            raise ValueError("Original changed/missing: " + row["path"])
        if row["status"] == "packaged" and digest not in verified:
            raise ValueError("Original has no verified object: " + row["path"])


if __name__ == "__main__":
    main()
