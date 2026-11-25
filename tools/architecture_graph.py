#!/usr/bin/env python3
"""Evidence-labelled, offline architecture inventory. Never imports target code."""
from __future__ import annotations

import argparse
import ast
from bisect import bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field
import hashlib
import html
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tokenize
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET


SCHEMA = "bobbi-architecture-graph-v1"
STATUSES = {"confirmed", "candidate", "external", "unresolved"}
TEXT_SUFFIXES = {".py", ".js", ".mjs", ".ts", ".tsx", ".jsx", ".xml", ".json",
                 ".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".patch", ".diff"}
CPP_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".patch", ".diff"}
MAX_SOURCE_BYTES = 8 * 1024 * 1024
LIMITATIONS = [
    "confirmed means a literal/declared static binding, not runtime execution or reachability",
    "Python calls are candidates, never a whole-program resolved call graph; mutation, descriptors, sys.path and DI remain unknown",
    "JS/TS, XML/Kodi and C++ are conservative lexical/protocol extraction, not language/compiler or router execution",
    "native source snapshots and patch registrations do not prove the installed binary or applied patch series",
    "SCCs are file-level candidates, not proof of import-time cycles or deadlocks",
    "manifest state/storage/lifecycle/test edges are reviewed assertions, not inferred ownership or executed test results",
    "ignored untracked files, submodule contents and symlink targets are not traversed; all tracked entries remain inventoried",
]


def digest(value):
    return hashlib.sha256(value).hexdigest()


def stable(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def git(repo, *args, data=None):
    result = subprocess.run(["git", "-C", str(repo), *args], input=data,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    if result.returncode:
        raise ValueError("git failed: " + result.stderr.decode("utf-8", "replace").strip())
    return result.stdout


def source_text(raw, suffix):
    if suffix == ".py":
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        return raw.decode(encoding)
    return raw.decode("utf-8-sig")


@dataclass
class Snapshot:
    inventory: list
    texts: dict
    provenance: dict
    diagnostics: list = field(default_factory=list)


def read_snapshot(repo, revision=None):
    """Read tracked inventory + nonignored new source files, or immutable Git blobs."""
    repo = Path(repo).resolve()
    head = git(repo, "rev-parse", "HEAD").decode().strip()
    commit = (git(repo, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}")
              .decode().strip()) if revision else head
    entries = {}
    for record in git(repo, "ls-tree", "-r", "-z", "-l", "--full-tree", commit).split(b"\0"):
        if not record:
            continue
        meta, path = record.split(b"\t", 1)
        mode, kind, oid, size = meta.decode().split()
        name = path.decode("utf-8", "surrogateescape")
        entries[name] = dict(path=name, tracked=True, mode=mode, git_object=oid, git_type=kind,
                             git_size=None if size == "-" else int(size))
    before = b""
    if not revision:
        before = git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all")
        # Include staged additions and tracked deletions, not only HEAD's tree.
        for path in git(repo, "ls-files", "-z", "--cached").split(b"\0"):
            if path:
                name = path.decode("utf-8", "surrogateescape")
                entries.setdefault(name, dict(path=name, tracked=True, mode=None, git_object=None))
        for path in git(repo, "ls-files", "-z", "--others", "--exclude-standard").split(b"\0"):
            if path:
                name = path.decode("utf-8", "surrogateescape")
                if PurePosixPath(name).suffix.lower() in TEXT_SUFFIXES:
                    entries[name] = dict(path=name, tracked=False, mode=None, git_object=None)
    texts, diagnostics = {}, []
    blobs = {}
    if revision:
        wanted = sorted({row["git_object"] for row in entries.values()
                         if row.get("git_type") == "blob" and row["mode"] != "120000"
                         and row["git_size"] <= MAX_SOURCE_BYTES
                         and PurePosixPath(row["path"]).suffix.lower() in TEXT_SUFFIXES})
        # Batch Git reads: blobs are bytes only, never imported or executed.
        stream = io.BytesIO(git(repo, "cat-file", "--batch", data="".join(x + "\n" for x in wanted).encode()))
        for oid in wanted:
            parts = stream.readline().split()
            if len(parts) != 3 or parts[0].decode() != oid or parts[1] != b"blob":
                raise ValueError("unexpected git cat-file response")
            size = int(parts[2])
            raw = stream.read(size)
            if len(raw) != size or stream.read(1) != b"\n":
                raise ValueError("truncated git blob")
            blobs[oid] = raw
    for name, row in sorted(entries.items()):
        suffix = PurePosixPath(name).suffix.lower()
        raw = None
        if revision:
            if row.get("git_type") != "blob":
                row["analysis"] = "submodule_not_traversed"
            elif row["mode"] == "120000":
                row["analysis"] = "symlink_not_followed"
            elif suffix in TEXT_SUFFIXES and row["git_size"] > MAX_SOURCE_BYTES:
                row["analysis"] = "too_large"
            elif suffix in TEXT_SUFFIXES:
                raw = blobs[row["git_object"]]
            else:
                row["analysis"] = "inventory_only"
        else:
            path = repo / name
            # Refuse a symlink at ANY level, even if Git tracks a child below it.
            if any(p.is_symlink() for p in (path, *path.parents) if p != repo.parent):
                row["analysis"] = "symlink_not_followed"
            elif not path.is_file():
                row["analysis"] = "missing_or_non_file"
            else:
                try:
                    first = path.stat()
                    hasher = hashlib.sha256()
                    chunks = []
                    with path.open("rb") as reader:
                        while True:
                            chunk = reader.read(1024 * 1024)
                            if not chunk:
                                break
                            hasher.update(chunk)
                            if suffix in TEXT_SUFFIXES and first.st_size <= MAX_SOURCE_BYTES:
                                chunks.append(chunk)
                    last = path.stat()
                    row.update(size=last.st_size, sha256=hasher.hexdigest())
                    if (first.st_size, first.st_mtime_ns) != (last.st_size, last.st_mtime_ns):
                        diagnostics.append(dict(path=name, code="changed_during_read"))
                    if suffix in TEXT_SUFFIXES and first.st_size <= MAX_SOURCE_BYTES:
                        raw = b"".join(chunks)
                    else:
                        row["analysis"] = "too_large" if suffix in TEXT_SUFFIXES else "inventory_only"
                except OSError as error:
                    row["analysis"] = "read_error"
                    diagnostics.append(dict(path=name, code="read_error", detail=type(error).__name__))
        if raw is not None:
            row.update(size=len(raw), sha256=digest(raw))
            if len(raw) > MAX_SOURCE_BYTES:
                row["analysis"] = "too_large"
                continue
            try:
                texts[name] = source_text(raw, suffix)
                row["analysis"] = "loaded"
            except (UnicodeError, SyntaxError, LookupError):
                row["analysis"] = "decode_error"
                diagnostics.append(dict(path=name, code="decode_error"))
    changed = False
    if not revision:
        changed = before != git(repo, "status", "--porcelain=v1", "-z", "--untracked-files=all") or head != git(repo, "rev-parse", "HEAD").decode().strip()
        if changed:
            diagnostics.append(dict(code="worktree_changed_during_inventory"))
    inventory = list(entries[name] for name in sorted(entries))
    return Snapshot(inventory, texts, dict(mode="git_revision" if revision else "worktree",
        repository=str(repo), requested_revision=revision, commit=commit,
        tree=git(repo, "rev-parse", commit + "^{tree}").decode().strip(),
        input_fingerprint=digest(stable(inventory).encode("utf-8", "surrogateescape")),
        worktree_changed_during_inventory=changed), diagnostics)


def addon_context(path):
    parts = PurePosixPath(path).parts
    if "addons" in parts:
        i = parts.index("addons")
        if len(parts) > i + 1:
            return "/".join(parts[:i + 2])
    return ""


def literal(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = literal(node.left), literal(node.right)
        return left + right if left is not None and right is not None else None
    return None


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + "." + node.attr if base else ""
    return ""


def without_comments(text):
    """Mask C/JS comments without moving evidence line numbers or touching strings."""
    token = re.compile(r"('(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`)|//[^\n]*|/\*[\s\S]*?\*/")
    return token.sub(lambda m: m.group(0) if m.group(1) else re.sub(r"[^\n]", " ", m.group(0)), text)


@dataclass
class Scope:
    node: str
    qualname: str
    parent: object = None
    bindings: dict = field(default_factory=dict)
    blocked: set = field(default_factory=set)
    is_class: bool = False


class Graph:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.nodes, self.edges, self.symbols, self.scopes = {}, [], defaultdict(list), {}
        self.modules, self.names, self.trees = defaultdict(set), {}, {}
        self.diagnostics = list(snapshot.diagnostics)
        self.manifest_records, self.boundaries = [], []
        self.roots = {"", "tools", "tests"}
        for row in snapshot.inventory:
            path = row["path"]
            self.node("file:" + path, "file", path=path, tracked=row["tracked"])
            context = addon_context(path)
            if context:
                self.roots.add(context)
                self.roots.add(context + "/lib")
        for path, text in snapshot.texts.items():
            if path.endswith("/addon.xml"):
                try:
                    root = ET.fromstring(text)
                    for ext in root.findall("extension"):
                        if ext.get("point") == "xbmc.python.module" and ext.get("library"):
                            self.roots.add(str(PurePosixPath(path).parent / ext.get("library")))
                except ET.ParseError:
                    pass
        for path, text in snapshot.texts.items():
            if not path.endswith(".py"):
                continue
            names = set()
            for root in self.roots:
                prefix = root + "/" if root else ""
                if path.startswith(prefix):
                    parts = list(PurePosixPath(path[len(prefix):]).with_suffix("").parts)
                    if parts[-1] == "__init__":
                        parts.pop()
                    if parts and all(part.isidentifier() for part in parts):
                        names.add(".".join(parts))
            self.names[path] = sorted(names)
            self.nodes["file:" + path]["module_names"] = sorted(names)
            for name in names:
                self.modules[name].add(path)
            try:
                self.trees[path] = ast.parse(text, filename=path)
            except (SyntaxError, ValueError) as error:
                self.diagnostics.append(dict(path=path, code="python_parse_error", line=getattr(error, "lineno", None)))
        for path, tree in self.trees.items():
            self.collect(path, tree, Scope("file:" + path, "<module>"))

    def node(self, identifier, kind, **values):
        self.nodes.setdefault(identifier, dict(id=identifier, kind=kind, **values))
        return identifier

    def edge(self, source, target, kind, status, path, line, **values):
        if status not in STATUSES:
            raise ValueError("invalid edge status")
        self.edges.append(dict(source=source, target=target, kind=kind, status=status,
                               evidence=dict(path=path, line=line), **values))

    def reference(self, identifier, kind="unresolved"):
        return self.node(kind + ":" + identifier, kind, label=identifier)

    def protocol(self, kind, name):
        return self.node("protocol:" + kind + ":" + name, "protocol", protocol=kind, label=name)

    def resolve(self, name, path):
        """No suffix/basename guessing. Duplicate roots remain explicit candidates."""
        candidates = set(self.modules.get(name, ()))
        local = {p for p in candidates if addon_context(p) and addon_context(p) == addon_context(path)}
        if local:
            candidates = local
        if len(candidates) == 1:
            return "file:" + next(iter(candidates)), "confirmed", []
        if candidates:
            return self.reference("python:" + name), "unresolved", sorted("file:" + p for p in candidates)
        return self.reference("python:" + name, "external"), "external", []

    def relative(self, path, module, level):
        result = set()
        for name in self.names.get(path, ()):
            package = name.split(".") if path.endswith("/__init__.py") else name.split(".")[:-1]
            if level <= len(package):
                parts = package[:len(package) - level + 1]
                result.add(".".join(parts + ([module] if module else [])))
        return sorted(result)

    def resolve_import(self, names, member, path):
        options, externals = set(), []
        for name in names:
            full = name + ("." + member if member else "")
            if full in self.modules:
                target, status, candidates = self.resolve(full, path)
            else:
                target, status, candidates = self.resolve(name, path)
                if member and status == "confirmed":
                    symbols = self.symbols.get((target[5:], member), [])
                    if len(symbols) == 1:
                        target = symbols[0]
                    elif len(symbols) > 1:
                        candidates = symbols
                        status = "unresolved"
                    else:
                        # A statically visible package is known, but this export is not.
                        candidates = [target]
                        target = self.reference("python-export:" + full)
                        status = "unresolved"
            if status in ("confirmed", "unresolved"):
                options.update(candidates or [target])
            else:
                externals.append(target)
        if len(options) == 1:
            target = next(iter(options))
            # Do not upgrade an unresolved exported attribute into a resolved module.
            if member and all(name + "." + member not in self.modules and
                              not self.symbols.get((target.removeprefix("file:"), member)) for name in names) and target.startswith("file:"):
                return self.reference("python-export:" + "|".join(names) + "." + member), "unresolved", [target]
            return target, "confirmed", []
        if options:
            return self.reference("python:" + "|".join(names) + ("." + member if member else "")), "unresolved", sorted(options)
        if externals:
            return externals[0], "external", []
        return self.reference("python-relative:" + str(names)), "unresolved", []

    def collect(self, path, node, scope):
        self.scopes[id(node)] = scope
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualname = child.name if scope.qualname == "<module>" else scope.qualname + "." + child.name
                identifier = self.node("python:" + path + "#" + qualname + "@" + str(child.lineno),
                    "python_symbol", path=path, name=qualname, line=child.lineno,
                    symbol_kind="class" if isinstance(child, ast.ClassDef) else "function")
                self.symbols[(path, qualname)].append(identifier)
                scope.bindings[child.name] = ("symbol", identifier)
                nested = Scope(identifier, qualname, scope, is_class=isinstance(child, ast.ClassDef))
                if not nested.is_class:
                    nested.blocked.update(arg.arg for arg in (*child.args.posonlyargs, *child.args.args, *child.args.kwonlyargs))
                    nested.blocked.update(arg.arg for arg in (child.args.vararg, child.args.kwarg) if arg)
                self.collect(path, child, nested)
            else:
                self.collect(path, child, scope)
                if isinstance(child, ast.Import):
                    for alias in child.names:
                        scope.bindings[alias.asname or alias.name.split(".")[0]] = ("import", [alias.name if alias.asname else alias.name.split(".")[0]], None)
                elif isinstance(child, ast.ImportFrom):
                    bases = self.relative(path, child.module or "", child.level) if child.level else [child.module or ""]
                    for alias in child.names:
                        if alias.name != "*":
                            scope.bindings[alias.asname or alias.name] = ("import", bases, alias.name)
                elif isinstance(child, ast.Name) and isinstance(child.ctx, (ast.Store, ast.Del)):
                    scope.blocked.add(child.id)

    def binding(self, scope, name):
        current = scope
        while current:
            if name in current.blocked:
                return None
            if name in current.bindings:
                return current.bindings[name]
            current = current.parent
            if current and current.is_class and current is not scope:
                current = current.parent  # Python methods do not close over class locals.
        return None

    def qualified(self, expression, scope):
        name = dotted(expression)
        first, _, rest = name.partition(".")
        binding = self.binding(scope, first)
        if binding and binding[0] == "import" and len(binding[1]) == 1:
            base = binding[1][0] + ("." + binding[2] if binding[2] else "")
            return base + ("." + rest if rest else "")
        return name

    def call_target(self, path, node, scope):
        name = dotted(node.func)
        first, _, rest = name.partition(".")
        binding = self.binding(scope, first)
        if binding and binding[0] == "symbol" and not rest:
            return binding[1], "candidate", []
        if binding and binding[0] == "import":
            bases = binding[1]
            tail = ".".join(x for x in (binding[2], rest) if x)
            # Resolve the longest module prefix, then a declared symbol suffix.
            for split in range(len(tail.split(".")) if tail else 0, -1, -1):
                parts = tail.split(".") if tail else []
                names = [base + ("." + ".".join(parts[:split]) if split else "") for base in bases]
                if not any(value in self.modules for value in names):
                    continue
                target, status, candidates = self.resolve_import(names, None, path)
                symbol = ".".join(parts[split:])
                if status == "confirmed" and symbol:
                    found = self.symbols.get((target[5:], symbol), [])
                    if len(found) == 1:
                        return found[0], "candidate", []
                    return self.reference("python-call:" + self.qualified(node.func, scope)), "unresolved", found or [target]
                if status == "confirmed" and not symbol:
                    return self.reference("python-module-call:" + name), "unresolved", [target]
                return target, status, candidates
            return self.reference("python:" + self.qualified(node.func, scope), "external"), "external", []
        if first in ("self", "cls") and rest and scope.parent and scope.parent.is_class:
            found = self.symbols.get((path, scope.parent.qualname + "." + rest), [])
            if len(found) == 1:
                return found[0], "candidate", []
        return self.reference("python-call:" + path + ":" + (name or ast.unparse(node.func))), "unresolved", []

    def python(self, path, tree):
        for node in ast.walk(tree):
            scope = self.scopes[id(node)]
            values = dict(caller=scope.qualname, origin="python_ast")
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    bases = [alias.name] if isinstance(node, ast.Import) else (
                        self.relative(path, node.module or "", node.level) if node.level else [node.module or ""])
                    member = alias.name if isinstance(node, ast.ImportFrom) else None
                    target, status, options = self.resolve_import(bases, member, path)
                    self.edge(scope.node, target, "python_import", status, path, node.lineno,
                              spelling=ast.unparse(node), candidates=options, **values)
            elif isinstance(node, ast.Call):
                qualified = self.qualified(node.func, scope)
                dynamic = qualified in ("importlib.import_module", "__import__")
                if dynamic:
                    name = literal(node.args[0]) if node.args else None
                    bases = [name] if name and not name.startswith(".") else []
                    if name and name.startswith("."):
                        package = literal(node.args[1]) if len(node.args) > 1 else next((literal(k.value) for k in node.keywords if k.arg == "package"), None)
                        if package:
                            level = len(name) - len(name.lstrip("."))
                            parts = package.split(".")
                            if level <= len(parts):
                                bases = [".".join(parts[:len(parts) - level + 1] + ([name[level:]] if name[level:] else []))]
                    target, status, options = self.resolve_import(bases, None, path) if bases else (
                        self.reference("dynamic-import:" + path + ":" + str(node.lineno)), "unresolved", [])
                    self.edge(scope.node, target, "python_dynamic_import", status, path, node.lineno,
                              expression=ast.unparse(node)[:500], candidates=options, **values)
                target, status, options = self.call_target(path, node, scope)
                self.edge(scope.node, target, "python_call", status, path, node.lineno,
                          callee=ast.unparse(node.func)[:500], candidates=options, **values)
                first = literal(node.args[0]) if node.args else None
                leaf = dotted(node.func).rsplit(".", 1)[-1]
                if leaf in ("build_url", "route"):
                    action = next((literal(k.value) for k in node.keywords if k.arg == "action"), None)
                    action = action or (first if leaf == "build_url" else None)
                    if action:
                        addon = addon_context(path).rsplit("/", 1)[-1] or "unknown-addon"
                        self.edge(scope.node, self.protocol("kodi-action", addon + ":" + action), "kodi_action_request", "candidate", path, node.lineno, **values)
                if leaf in ("_spec", "RouteSpec") and addon_context(path).rsplit("/", 1)[-1].startswith("plugin."):
                    addon = addon_context(path).rsplit("/", 1)[-1]
                    targets_node = node.args[1] if leaf == "_spec" and len(node.args) > 1 else next((k.value for k in node.keywords if k.arg in ("actions", "targets")), None)
                    spec_actions = []
                    if isinstance(targets_node, (ast.Tuple, ast.List, ast.Set)):
                        spec_actions = [literal(x) for x in targets_node.elts]
                    elif isinstance(targets_node, ast.Dict):
                        spec_actions = [literal(k) for k in targets_node.keys]
                    for act_name in filter(None, spec_actions):
                        for kind, key in (("host-action", act_name), ("kodi-action", addon + ":" + act_name)):
                            self.edge(self.protocol(kind, key), scope.node, "dispatch_branch", "candidate", path, node.lineno, comparison=ast.unparse(node)[:200], **values)
                if "rpc" in leaf.lower() or leaf in ("invoke", "call"):
                    if first:
                        kind = "jsonrpc" if re.fullmatch(r"[A-Z]\w*\.\w+", first) else "host-action"
                        self.edge(scope.node, self.protocol(kind, first), kind.replace("-", "_") + "_request", "candidate", path, node.lineno, **values)
                if first and (first.startswith(("https://", "http://")) or leaf in ("get", "post", "fetch") and first.startswith("/")):
                    self.edge(scope.node, self.protocol("http", first), "http_request", "external" if "://" in first else "candidate", path, node.lineno, **values)
            elif isinstance(node, ast.Compare) and isinstance(node.left, ast.Name) and node.left.id in ("action", "operation", "method", "path"):
                for comparison in node.comparators:
                    literals = [literal(comparison)] if literal(comparison) is not None else [literal(x) for x in getattr(comparison, "elts", [])]
                    for value in filter(None, literals):
                        kinds = [("http", value)] if value.startswith("/") else [("host-action", value)]
                        if node.left.id == "action" and addon_context(path).rsplit("/", 1)[-1].startswith("plugin."):
                            kinds.append(("kodi-action", addon_context(path).rsplit("/", 1)[-1] + ":" + value))
                        for kind, key in kinds:
                            self.edge(self.protocol(kind, key), scope.node, "dispatch_branch", "candidate", path, node.lineno, comparison=ast.unparse(node), **values)
            elif isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if literal(key) == "method" and literal(value) and re.fullmatch(r"[A-Z]\w*\.\w+", literal(value)):
                        self.edge(scope.node, self.protocol("jsonrpc", literal(value)), "jsonrpc_literal", "candidate", path, node.lineno, **values)
            elif isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                if self.qualified(node.value.func, scope) != "importlib.import_module":
                    continue
                if any(isinstance(t, ast.Subscript) and self.qualified(t.value, scope) == "sys.modules" and isinstance(t.slice, ast.Name) and t.slice.id == "__name__" for t in node.targets):
                    name = literal(node.value.args[0]) if node.value.args else None
                    if name:
                        target, status, options = self.resolve(name, path)
                        self.edge("file:" + path, target, "compatibility_alias", status, path, node.lineno,
                                  candidates=options, duplicate_implementation=False, **values)
                        self.nodes["file:" + path]["compatibility_alias"] = name

    def lexical(self, path, text):
        suffix = PurePosixPath(path).suffix.lower()
        if suffix == ".xml":
            try:
                root = ET.fromstring(text)
                if root.tag == "addon":
                    tags = list(re.finditer(r"<extension\b[^>]*", text))
                    for index, ext in enumerate(root.findall("extension")):
                        library = ext.get("library")
                        if library:
                            target_path = str(PurePosixPath(path).parent / library)
                            target = "file:" + target_path
                            directory = [p for p in self.snapshot.texts if p.startswith(target_path.rstrip("/") + "/")]
                            if target in self.nodes:
                                status = "confirmed"
                            elif ext.get("point") == "xbmc.python.module" and directory:
                                target = self.node("directory:" + target_path, "import_root", path=target_path)
                                status = "confirmed"
                            else:
                                target, status = self.reference("addon-entry:" + target_path), "unresolved"
                            line = text[:tags[index].start()].count("\n") + 1 if index < len(tags) else 1
                            self.edge("file:" + path, target, "addon_entrypoint", status, path, line,
                                      extension=ext.get("point"), origin="xml_parser")
            except ET.ParseError:
                self.diagnostics.append(dict(path=path, code="xml_parse_error"))
            for match in re.finditer(r"plugin://[^\s<>\"')]+", text):
                url = html.unescape(match.group(0))
                parts = urlsplit(url)
                action = parse_qs(parts.query).get("action", [None])[0]
                line = text[:match.start()].count("\n") + 1
                target = self.protocol("kodi-action", parts.netloc + ":" + action) if action else self.reference("kodi-url:" + url)
                self.edge("file:" + path, target, "kodi_route", "candidate" if action else "unresolved", path, line, origin="xml_literal", spelling=url)
        elif suffix in (".js", ".mjs", ".ts", ".tsx", ".jsx"):
            code = without_comments(text)
            strings = list(re.finditer(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`", code))
            starts = [match.start() for match in strings]
            def is_code(position):
                index = bisect_right(starts, position) - 1
                return index < 0 or strings[index].end() <= position
            for match in re.finditer(r"\b(fetch|post|get|axios\.(?:get|post))\s*\(\s*(['\"])([^'\"\n]+)\2", code):
                if not is_code(match.start()):
                    continue
                url = match.group(3)
                if url.startswith(("/", "http://", "https://")):
                    self.edge("file:" + path, self.protocol("http", url), "http_request", "external" if "://" in url else "candidate", path, code[:match.start()].count("\n") + 1, origin="js_lexical", caller="<file>")
            patterns = (r"\b(?:rpc|invoke|call)\s*\(\s*(['\"])([\w.-]+)\1", r"\baction\s*:\s*(['\"])([\w.-]+)\1")
            for pattern in patterns:
                for match in re.finditer(pattern, code):
                    if not is_code(match.start()):
                        continue
                    self.edge("file:" + path, self.protocol("host-action", match.group(2)), "host_action_request", "candidate", path, code[:match.start()].count("\n") + 1, origin="js_lexical", caller="<file>")
            for match in re.finditer(r"\bfetch\s*\(\s*(?!['\"])([^)\n]+)", code):
                if not is_code(match.start()):
                    continue
                self.edge("file:" + path, self.reference("dynamic-http:" + path + ":" + str(match.start())), "http_request", "unresolved", path, code[:match.start()].count("\n") + 1, origin="js_lexical", expression=match.group(1)[:160])
        elif suffix in CPP_SUFFIXES:
            code = without_comments(text)
            if suffix in (".patch", ".diff"):
                code = "\n".join("" if line.startswith(("-", "@@", "diff ", "index ")) else line[1:] if line.startswith("+") else line for line in code.split("\n"))
            pattern = r'(?:\{\s*|\b(?:RegisterMethod|AddMethod|Register)\s*\(\s*)"([A-Z]\w*\.\w+)"\s*,\s*&?\s*([A-Za-z_]\w*(?:::\w+)+)'
            for match in re.finditer(pattern, code):
                target = self.node("native-symbol:" + path + "#" + match.group(2), "native_symbol_reference", path=path, name=match.group(2))
                self.edge(self.protocol("jsonrpc", match.group(1)), target, "native_registration", "candidate", path, code[:match.start()].count("\n") + 1, origin="cpp_lexical", patch_only=suffix in (".patch", ".diff"), note="registration text, not a compiled/binary binding")

    def manifest(self, value, label, sha256):
        if type(value) is not dict or value.get("schema") != 1 or set(value) - {"schema", "nodes", "edges", "boundaries"}:
            raise ValueError("invalid protocol manifest: " + label)
        self.manifest_records.append(dict(name=label, sha256=sha256))
        for node in value.get("nodes", []):
            if not isinstance(node, dict) or not isinstance(node.get("id"), str) or node.get("kind") not in ("state", "storage", "lifecycle", "protocol", "responsibility"):
                raise ValueError("invalid manifest node")
            if node["id"] in self.nodes:
                raise ValueError("manifest cannot redefine an extracted node")
            self.nodes[node["id"]] = dict(node, origin="manifest_assertion")
        for edge in value.get("edges", []):
            required = {"source", "target", "kind", "status", "evidence", "note"}
            if not isinstance(edge, dict) or not required <= edge.keys() or edge["status"] not in STATUSES or not edge["note"]:
                raise ValueError("manifest edge needs status, note and evidence")
            if edge["source"] not in self.nodes or edge["target"] not in self.nodes:
                raise ValueError("manifest edge endpoint does not exist")
            evidence = edge["evidence"]
            text = self.snapshot.texts.get(evidence.get("path")) if isinstance(evidence, dict) else None
            if text is None or type(evidence.get("line")) is not int or not 1 <= evidence["line"] <= len(text.splitlines()):
                raise ValueError("manifest evidence is outside the selected snapshot")
            self.edges.append(dict(edge, origin="manifest_assertion", manifest=label))
        for rule in value.get("boundaries", []):
            if not isinstance(rule, dict) or not {"id", "source_prefixes", "target_prefixes", "kinds", "note"} <= rule.keys():
                raise ValueError("invalid boundary rule")
            if any(not isinstance(rule[key], list) or not all(isinstance(x, str) for x in rule[key]) for key in ("source_prefixes", "target_prefixes", "kinds")):
                raise ValueError("invalid boundary selectors")
            self.boundaries.append(dict(rule, manifest=label))

    def finish(self):
        for path, tree in self.trees.items():
            self.python(path, tree)
        for path, text in self.snapshot.texts.items():
            self.lexical(path, text)

    def export(self):
        unique = {}
        for edge in self.edges:
            identifier = digest(stable(edge).encode("utf-8", "surrogateescape"))[:24]
            unique[identifier] = dict(id=identifier, **edge)
        edges = [unique[key] for key in sorted(unique)]
        findings = []
        for rule in self.boundaries:
            for edge in edges:
                source = self.nodes[edge["source"]].get("path", "")
                target = self.nodes[edge["target"]].get("path", "")
                if edge["kind"] in rule["kinds"] and any(source.startswith(p) for p in rule["source_prefixes"]) and any(target.startswith(p) for p in rule["target_prefixes"]):
                    allow = next((a for a in rule.get("allow", []) if a.get("source") == source and a.get("target") == target and a.get("reason")), None)
                    findings.append(dict(rule=rule["id"], edge=edge["id"], status="allowed" if allow else "review_required", note=allow["reason"] if allow else rule["note"]))
        counts = Counter(edge["status"] for edge in edges)
        return dict(schema=SCHEMA, provenance=self.snapshot.provenance, manifests=self.manifest_records,
            limitations=LIMITATIONS, inventory=self.snapshot.inventory,
            nodes=[self.nodes[key] for key in sorted(self.nodes)], edges=edges,
            module_collisions=[dict(module=name, paths=sorted(paths)) for name, paths in sorted(self.modules.items()) if len(paths) > 1],
            scc_candidates=scc_candidates(self.nodes, edges), boundary_findings=findings,
            diagnostics=sorted(self.diagnostics, key=stable), summary=dict(
                inventory_files=len(self.snapshot.inventory), loaded_sources=len(self.snapshot.texts),
                parsed_python_files=len(self.trees), nodes=len(self.nodes), edges=len(edges),
                edges_by_status=dict(sorted(counts.items())),
                edges_by_kind=dict(sorted(Counter(edge["kind"] for edge in edges).items())),
                inventory_by_analysis=dict(sorted(Counter(row.get("analysis", "loaded") for row in self.snapshot.inventory).items()))))


def scc_candidates(nodes, edges):
    adjacency, reverse = defaultdict(set), defaultdict(set)
    for edge in edges:
        if edge["kind"] not in ("python_import", "python_dynamic_import", "python_call", "compatibility_alias") or edge["status"] not in ("confirmed", "candidate"):
            continue
        source, target = nodes[edge["source"]].get("path"), nodes[edge["target"]].get("path")
        if source and target and source != target:
            adjacency[source].add(target)
            reverse[target].add(source)
    seen, order = set(), []
    for root in sorted(set(adjacency) | set(reverse)):
        stack = [(root, False)]
        while stack:
            node, visited = stack.pop()
            if visited:
                order.append(node)
            elif node not in seen:
                seen.add(node)
                stack.append((node, True))
                stack.extend((x, False) for x in sorted(adjacency[node], reverse=True) if x not in seen)
    seen, result = set(), []
    for root in reversed(order):
        if root in seen:
            continue
        component, stack = [], [root]
        while stack:
            node = stack.pop()
            if node in seen:
                continue
            seen.add(node)
            component.append(node)
            stack.extend(sorted(reverse[node] - seen, reverse=True))
        if len(component) > 1:
            result.append(dict(files=sorted(component), status="candidate", reason="static file dependency SCC; runtime behavior unproven"))
    return sorted(result, key=lambda row: row["files"])


def build_graph(snapshot, manifests=()):
    graph = Graph(snapshot)
    graph.finish()
    for value, label, sha256 in manifests:
        graph.manifest(value, label, sha256)
    return graph.export()


def overview(graph):
    summary = graph["summary"]
    lines = ["# Static architecture evidence", "", "This is an inventory and candidate graph, not a fully resolved call graph.", "",
             "- Snapshot: " + graph["provenance"]["mode"] + " / " + graph["provenance"]["commit"],
             "- Input fingerprint: " + graph["provenance"]["input_fingerprint"],
             f"- Inventory: {summary['inventory_files']} files; Python AST: {summary['parsed_python_files']} files.",
             f"- Edges: {summary['edges']}; statuses: " + stable(summary["edges_by_status"]),
             f"- SCC candidates: {len(graph['scc_candidates'])}; diagnostics: {len(graph['diagnostics'])}.", "",
             "## Boundary checks", "", "Review-required: " + str(sum(x["status"] == "review_required" for x in graph["boundary_findings"])), "",
             "No rules means no policy assertions were checked, not that boundaries passed.", "", "## Interpretation limits", ""]
    lines += ["- " + value for value in graph["limitations"]]
    nodes = {node["id"]: node for node in graph["nodes"]}

    def group(node):
        path = node.get("path")
        if path:
            return addon_context(path) or path.split("/")[0]
        return "protocol/" + node.get("protocol", "annotation") if node["kind"] == "protocol" else node["kind"]

    counts = Counter((group(nodes[e["source"]]), group(nodes[e["target"]]), e["status"]) for e in graph["edges"])
    counts = [(pair, count) for pair, count in counts.items() if pair[0] != pair[1]]
    selected = sorted(counts, key=lambda item: (-item[1], item[0]))[:120]
    groups = sorted({value for (source, target, _), _count in selected for value in (source, target)})
    ids = {name: "n" + str(i) for i, name in enumerate(groups)}
    mermaid = ["flowchart LR"]
    mermaid += [f'  {ids[name]}["{html.escape(name, quote=True)}"]' for name in groups]
    for (source, target, status), count in selected:
        arrow = "-->" if status == "confirmed" else "-.->"
        mermaid.append(f'  {ids[source]} {arrow}|"{status}: {count}"| {ids[target]}')
    lines += ["", "## Aggregated diagram", "", f"Diagram shows {len(selected)} of {len(counts)} cross-group edge buckets. Full evidence is in graph.json.", "", "```mermaid", *mermaid, "```", ""]
    return "\n".join(lines), "\n".join(mermaid) + "\n"


def write_outputs(graph, repo, destination, overwrite=False):
    destination, repo = Path(destination).resolve(), Path(repo).resolve()
    if destination == repo or repo in destination.parents:
        raise ValueError("output directory must be outside the repository")
    names = ("graph.json", "overview.md", "overview.mmd")
    if any((destination / name).is_symlink() for name in names):
        raise ValueError("refusing symlink output")
    if not overwrite and any((destination / name).exists() for name in names):
        raise ValueError("output exists; choose a fresh directory or explicit --overwrite")
    destination.mkdir(parents=True, exist_ok=True)
    markdown, mermaid = overview(graph)
    contents = (json.dumps(graph, ensure_ascii=True, indent=2, sort_keys=True) + "\n", markdown, mermaid)
    for name, content in zip(names, contents):
        with (destination / name).open("w" if overwrite else "x", encoding="utf-8", newline="\n") as stream:
            stream.write(content)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--revision", help="read immutable Git objects, without checkout")
    parser.add_argument("--output", required=True, type=Path, help="external artifact directory")
    parser.add_argument("--manifest", action="append", default=[], help="repository-relative snapshot JSON, or explicit external absolute JSON")
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument("--fail-on-boundary", action="store_true")
    args = parser.parse_args(argv)
    try:
        snapshot = read_snapshot(args.repo, args.revision)
        manifests = []
        for name in args.manifest:
            path = Path(name)
            if path.is_absolute():
                raw = path.read_bytes()
            else:
                normalized = PurePosixPath(name.replace("\\", "/"))
                if ".." in normalized.parts or str(normalized) not in snapshot.texts:
                    raise ValueError("manifest is not a loaded file in the selected snapshot")
                raw = snapshot.texts[str(normalized)].encode("utf-8")
            manifests.append((json.loads(raw), name, digest(raw)))
        graph = build_graph(snapshot, manifests)
        graph["provenance"]["tool_sha256"] = digest(Path(__file__).read_bytes())
        write_outputs(graph, args.repo, args.output, args.overwrite)
        print(stable(dict(output=str(args.output.resolve()), summary=graph["summary"],
                         boundary_review_required=sum(x["status"] == "review_required" for x in graph["boundary_findings"]))))
        return 2 if args.fail_on_boundary and any(x["status"] == "review_required" for x in graph["boundary_findings"]) else 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print("architecture_graph: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
