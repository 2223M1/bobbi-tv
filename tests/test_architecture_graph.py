"""Offline graph fixtures. Target modules are text, not imported test dependencies."""
import importlib.util
import json
from datetime import datetime
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import subprocess
import sys

import pytest


TOOL = Path(__file__).resolve().parents[1] / "tools" / "architecture_graph.py"
SPEC = importlib.util.spec_from_file_location("architecture_graph_under_test", TOOL)
architecture = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = architecture
SPEC.loader.exec_module(architecture)


def snapshot(files):
    return architecture.Snapshot(
        [dict(path=path, tracked=True, analysis="loaded") for path in sorted(files)], files,
        dict(mode="fixture", commit="fixture", input_fingerprint="fixture"))


def graph(files, manifests=()):
    return architecture.build_graph(snapshot(files), manifests)


def edges(result, kind):
    return [edge for edge in result["edges"] if edge["kind"] == kind]


def test_relative_import_alias_calls_have_lexical_caller_and_no_execution():
    result = graph({
        "addons/plugin.demo/lib/pkg/__init__.py": "",
        "addons/plugin.demo/lib/pkg/helpers.py": "def go(): pass\n",
        "addons/plugin.demo/lib/pkg/view.py": "from .helpers import go as launch\ndef render():\n    launch()\n",
        "addons/plugin.demo/lib/unsafe.py": "raise RuntimeError('must never execute')\n",
    })
    imported = edges(result, "python_import")[0]
    assert imported["status"] == "confirmed"
    assert "helpers.py#go@1" in imported["target"]
    call = edges(result, "python_call")[0]
    assert call["status"] == "candidate"
    assert call["caller"] == "render" and call["evidence"]["line"] == 3
    assert "view.py#render@2" in call["source"]
    assert call["target"] == imported["target"]
    assert not result["diagnostics"]


def test_same_named_modules_are_ambiguous_unless_addon_context_disambiguates():
    files = {
        "addons/plugin.a/lib/common.py": "def go(): pass\n",
        "addons/plugin.b/lib/common.py": "def go(): pass\n",
        "tools/runner.py": "import lib.common as c\nc.go()\n",
        "addons/plugin.a/main.py": "from lib import common\ncommon.go()\n",
    }
    result = graph(files)
    external_import = next(e for e in edges(result, "python_import") if e["evidence"]["path"] == "tools/runner.py")
    assert external_import["status"] == "unresolved"
    assert len(external_import["candidates"]) == 2
    local_import = next(e for e in edges(result, "python_import") if e["evidence"]["path"].endswith("main.py"))
    assert local_import["target"] == "file:addons/plugin.a/lib/common.py"
    assert local_import["status"] == "confirmed"
    assert any(row["module"] == "lib.common" for row in result["module_collisions"])


def test_dynamic_import_literals_computed_names_and_module_replacement_alias():
    result = graph({
        "addons/script.module.core/lib/core/model.py": "def value(): return 1\n",
        "addons/plugin.demo/lib/model.py": (
            "import sys as system\nfrom importlib import import_module as load\n"
            "system.modules[__name__] = load('core.' + 'model')\n"
            "def dynamic(name):\n    return load(name)\n"),
    })
    dynamic = edges(result, "python_dynamic_import")
    assert {row["status"] for row in dynamic} == {"confirmed", "unresolved"}
    alias = edges(result, "compatibility_alias")[0]
    assert alias["status"] == "confirmed"
    assert alias["duplicate_implementation"] is False
    assert alias["target"] == "file:addons/script.module.core/lib/core/model.py"


def test_relative_dynamic_import_requires_explicit_package_and_parameters_shadow_imports():
    result = graph({
        "pkg/__init__.py": "",
        "pkg/child.py": "def run(): pass\n",
        "main.py": (
            "import importlib as il\nfrom pkg.child import run\n"
            "il.import_module('.child', package='pkg')\n"
            "il.import_module('.child')\n"
            "def work(run):\n    run()\n"),
    })
    dynamic = edges(result, "python_dynamic_import")
    assert {row["status"] for row in dynamic} == {"confirmed", "unresolved"}
    call = next(row for row in edges(result, "python_call") if row["caller"] == "work")
    assert call["status"] == "unresolved"


def test_unknown_export_and_unknown_object_method_are_not_confirmed():
    result = graph({"pkg/__init__.py": "", "main.py": "from pkg import absent\nobj.absent()\n"})
    assert edges(result, "python_import")[0]["status"] == "unresolved"
    assert edges(result, "python_call")[0]["status"] == "unresolved"


def test_xml_kodi_route_reaches_python_dispatch_and_addon_entrypoint():
    result = graph({
        "addons/plugin.demo/addon.xml": '<addon id="plugin.demo"><extension point="xbmc.python.pluginsource" library="main.py"/></addon>',
        "addons/plugin.demo/main.py": "def dispatch(action):\n    if action == 'library':\n        pass\n",
        "addons/skin.demo/resources/home.xml": '<control><onclick>RunPlugin(plugin://plugin.demo/?action=library&amp;mode=works)</onclick></control>',
    })
    request = edges(result, "kodi_route")[0]
    handler = next(e for e in edges(result, "dispatch_branch") if e["source"] == request["target"])
    assert handler["caller"] == "dispatch"
    assert handler["status"] == "candidate" and request["status"] == "candidate"
    entry = edges(result, "addon_entrypoint")[0]
    assert entry["status"] == "confirmed" and entry["target"] == "file:addons/plugin.demo/main.py"


def test_js_http_action_and_cpp_registration_are_typed_not_runtime_proof():
    result = graph({
        "addons/plugin.demo/resources/manage.js": (
            "// fetch('/fake')\nfetch('/manage/api', {method:'POST', action:'catalog_query'});\n"
            "rpc('catalog_apply', {});\nfetch(path);\nconst hint=\"fetch('/fake')\";\n"),
        "addons/plugin.demo/server.py": "def post(path):\n    if path == '/manage/api': pass\n",
        "native/JSONServiceDescription.cpp": (
            '// { "Player.Fake", Fake::Method }\n'
            'JsonRpcMethodMap methods[] = {{ "Player.BobiState", CPlayerOperations::BobbiState }};\n'),
        "native/changes.patch": '+ { "Player.Patched", CPlayerOperations::Patched },\n- { "Player.Removed", CPlayerOperations::Removed },\n',
    })
    http = edges(result, "http_request")
    assert {e["status"] for e in http} == {"candidate", "unresolved"}
    assert not any("fake" in e["target"] for e in http)
    request = next(e for e in http if e["status"] == "candidate")
    assert any(e["source"] == request["target"] for e in edges(result, "dispatch_branch"))
    assert len(edges(result, "host_action_request")) == 2
    native = edges(result, "native_registration")
    assert len(native) == 2 and all(e["status"] == "candidate" for e in native)
    assert {e["patch_only"] for e in native} == {False, True}
    assert all("Removed" not in e["source"] and "Fake" not in e["source"] for e in native)


def test_scc_is_candidate_and_manifest_maps_state_storage_lifecycle_and_tests():
    files = {"core/a.py": "import platform.b\n", "platform/b.py": "import core.a\n", "tests/test_a.py": "def test_a(): pass\n"}
    manifest = dict(schema=1, nodes=[
        dict(id="state:catalog", kind="state"), dict(id="storage:catalog", kind="storage"),
        dict(id="lifecycle:host", kind="lifecycle")], edges=[
            dict(source="file:core/a.py", target=target, kind=kind, status="confirmed",
                 evidence=dict(path="core/a.py", line=1), note="Reviewed fixture declaration")
            for target, kind in (("state:catalog", "owns_state"), ("storage:catalog", "persists_to"), ("lifecycle:host", "owned_lifecycle"), ("file:tests/test_a.py", "covered_by"))
        ], boundaries=[dict(id="core-platform", source_prefixes=["core/"], target_prefixes=["platform/"],
                            kinds=["python_import"], note="Review dependency direction")])
    result = graph(files, [(manifest, "fixture.json", "sha")])
    assert result["scc_candidates"] == [dict(files=["core/a.py", "platform/b.py"], status="candidate", reason="static file dependency SCC; runtime behavior unproven")]
    assert len(result["boundary_findings"]) == 1
    assert result["boundary_findings"][0]["status"] == "review_required"
    assert all(e["origin"] == "manifest_assertion" for e in edges(result, "owns_state"))
    assert result["manifests"] == [dict(name="fixture.json", sha256="sha")]
    assert architecture.stable(result) == architecture.stable(graph(files, [(manifest, "fixture.json", "sha")]))


def test_manifest_cannot_claim_absent_evidence_or_replace_extracted_nodes():
    files = {"main.py": "pass\n"}
    with pytest.raises(ValueError, match="redefine"):
        graph(files, [(dict(schema=1, nodes=[dict(id="file:main.py", kind="state")]), "bad", "sha")])
    with pytest.raises(ValueError, match="outside"):
        graph(files, [(dict(schema=1, edges=[dict(source="file:main.py", target="file:main.py",
              kind="owns", status="confirmed", evidence=dict(path="main.py", line=2), note="invalid")]), "bad", "sha")])


def command(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def test_git_revision_uses_blobs_and_worktree_includes_new_sources_without_running_them(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    command(repo, "init")
    (repo / "main.py").write_text("import old_dependency\n", encoding="utf-8")
    (repo / "asset.bin").write_bytes(b"\x00\x01")
    (repo / ".gitignore").write_text("ignored.py\n", encoding="utf-8")
    command(repo, "add", ".")
    command(repo, "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid", "commit", "-qm", "fixture")
    revision = command(repo, "rev-parse", "HEAD").decode().strip()
    (repo / "main.py").write_text("import new_dependency\n", encoding="utf-8")
    (repo / "new.py").write_text("raise RuntimeError('do not execute')\n", encoding="utf-8")
    (repo / "ignored.py").write_text("pass\n", encoding="utf-8")
    old = architecture.read_snapshot(repo, revision)
    working = architecture.read_snapshot(repo)
    assert old.texts["main.py"] == "import old_dependency\n"
    assert working.texts["main.py"].splitlines() == ["import new_dependency"]
    assert "new.py" in working.texts and "new.py" not in old.texts
    assert "ignored.py" not in working.texts
    assert any(row["path"] == "asset.bin" for row in old.inventory)
    assert len(old.inventory) == 3 and len(working.inventory) == 4
    output = tmp_path / "external"
    before = command(repo, "status", "--porcelain")
    assert architecture.main(["--repo", str(repo), "--revision", revision, "--output", str(output)]) == 0
    assert command(repo, "status", "--porcelain") == before
    artifact = json.loads((output / "graph.json").read_text(encoding="utf-8"))
    assert artifact["provenance"]["commit"] == revision
    assert (output / "overview.mmd").read_text(encoding="utf-8").startswith("flowchart LR\n")
    with pytest.raises(ValueError, match="outside"):
        architecture.write_outputs(artifact, repo, repo / "reports")
    with pytest.raises(ValueError, match="exists"):
        architecture.write_outputs(artifact, repo, output)


def test_parse_errors_are_reported_and_inventory_is_retained():
    result = graph({"broken.py": "def !!!\n", "broken.xml": "<unclosed>", "good.py": "pass\n"})
    assert result["summary"]["inventory_files"] == 3
    assert result["summary"]["parsed_python_files"] == 1
    assert {row["code"] for row in result["diagnostics"]} == {"python_parse_error", "xml_parse_error"}


def architecture_document(name):
    root = Path(__file__).resolve().parents[1]
    return json.loads((root / "docs" / "architecture" / name).read_text(encoding="utf-8"))


def repository_file(value):
    assert isinstance(value, str) and value
    assert not PurePosixPath(value).is_absolute() and not PureWindowsPath(value).is_absolute()
    assert ".." not in PurePosixPath(value).parts and "\\" not in value
    result = Path(__file__).resolve().parents[1] / value
    assert result.is_file(), value
    return result


def assert_reported_counts(value):
    assert set(value) == {"tests", "failures", "errors", "skipped"}
    assert all(type(count) is int and count >= 0 for count in value.values())
    assert value["tests"] > 0
    assert value["failures"] + value["errors"] + value["skipped"] <= value["tests"]


def test_ownership_manifest_has_live_source_anchors_and_explicit_static_test_mappings():
    manifest = architecture_document("ownership-manifest.json")
    assert manifest["schema"] == 1
    nodes = {node["id"]: node for node in manifest["nodes"]}
    assert len(nodes) == len(manifest["nodes"])
    assert all(node["kind"] in {"state", "storage", "lifecycle", "protocol", "responsibility"}
               for node in nodes.values())
    for edge in manifest["edges"]:
        for endpoint in (edge["source"], edge["target"]):
            if endpoint.startswith("file:"):
                repository_file(endpoint[len("file:"):])
            else:
                assert endpoint in nodes, endpoint
        evidence = edge["evidence"]
        lines = repository_file(evidence["path"]).read_text(encoding="utf-8-sig").splitlines()
        assert type(evidence["line"]) is int and 1 <= evidence["line"] <= len(lines)
        assert evidence["anchor"] and lines[evidence["line"] - 1].strip() == evidence["anchor"], evidence
        assert edge["status"] in {"confirmed", "candidate", "external", "unresolved"}
        assert edge["note"].strip()
        if edge["kind"] == "covered_by":
            assert edge["status"] == "candidate", "A static test mapping is not an execution result."


def test_local_receipt_metadata_preserves_mixed_outcomes_without_external_ci_dependency():
    evidence = architecture_document("interaction-coverage.json")["local_execution_evidence"]
    assert all(evidence[key].strip() for key in ("qualification", "source_binding", "device_qualification"))
    receipts = {receipt["id"]: receipt for receipt in evidence["receipts"]}
    assert len(receipts) == len(evidence["receipts"])
    for receipt in receipts.values():
        # External execution archives are not required to exist on another CI machine.
        assert receipt["path"].endswith(".xml")
        assert PurePosixPath(receipt["path"]).is_absolute() or PureWindowsPath(receipt["path"]).is_absolute()
        assert re.fullmatch(r"[0-9a-f]{64}", receipt["sha256"])
        assert datetime.fromisoformat(receipt["started_at"]).tzinfo is not None
        assert_reported_counts(receipt["reported"])
        failed = receipt["reported"]["failures"] or receipt["reported"]["errors"]
        assert receipt["outcome"] == ("mixed" if failed else "passed")
        assert receipt["device_contacted"] is False


def test_local_execution_references_are_reciprocal_and_counts_stay_inside_each_receipt():
    coverage = architecture_document("interaction-coverage.json")
    scenarios = {scenario["id"]: scenario for scenario in coverage["scenarios"]}
    evidence = coverage["local_execution_evidence"]
    receipts = {receipt["id"]: receipt for receipt in evidence["receipts"]}
    executions = {execution["id"]: execution for execution in evidence["executions"]}
    assert len(executions) == len(evidence["executions"])
    for execution in executions.values():
        assert execution["kind"] == "local_test_execution"
        assert execution["system_acceptance"] == "pending" and execution["device_contacted"] is False
        assert execution["scope"].strip()
        receipt = receipts[execution["receipt_ref"]]
        selected = execution["selected_test_classes"]
        assert selected and len({row["class_name"] for row in selected}) == len(selected)
        for row in selected:
            repository_file(row["pytest_file"])
            assert row["class_name"] == row["pytest_file"][:-3].replace("/", ".") or row["class_name"].startswith(
                row["pytest_file"][:-3].replace("/", ".") + ".")
            assert_reported_counts(row["reported"])
        for key, total in receipt["reported"].items():
            assert sum(row["reported"][key] for row in selected) <= total
        assert execution["scenario_ids"] and len(set(execution["scenario_ids"])) == len(execution["scenario_ids"])
        for scenario_id in execution["scenario_ids"]:
            assert execution["id"] in scenarios[scenario_id]["local_execution_refs"]
    assert set(receipts) == {execution["receipt_ref"] for execution in executions.values()}
    for scenario in scenarios.values():
        references = scenario.get("local_execution_refs", [])
        assert len(references) == len(set(references))
        for execution_id in references:
            assert scenario["id"] in executions[execution_id]["scenario_ids"]


def test_local_checkpoints_do_not_promote_the_original_system_or_device_scenarios():
    coverage = architecture_document("interaction-coverage.json")
    assert coverage["schema"] == 1
    assert [scenario["id"] for scenario in coverage["scenarios"]] == [
        "SYS-%03d" % number for number in range(1, 111)]
    for scenario in coverage["scenarios"]:
        assert scenario["status"] == "pending_system_acceptance"
        assert scenario["device"] == "not_run_current_revision"
        assert scenario["remaining"].strip()
        expected = ("local_execution_partial_system_acceptance_pending" if scenario.get("local_execution_refs")
                    else "candidate_mapping_only")
        assert scenario["evidence_kind"] == expected
