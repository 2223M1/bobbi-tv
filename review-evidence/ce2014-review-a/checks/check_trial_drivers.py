"""Read-only PR3 review: real trial drivers with retained results and fake transport.

No Kodi or device connection is made. Run in a new output directory. The R06
checks protect the existing behavior; the new-driver check records the actual
command-versus-persisted exit-code discrepancy for reviewer interpretation.
"""
import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
from unittest import mock


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def exercise_standard(driver, original_result):
    with tempfile.TemporaryDirectory(prefix="bobbi-pr3-trial-") as directory:
        root = Path(directory)
        (root / "review-evidence").mkdir()
        transport = root / "transport" / "ui-redesign" / "tools"
        transport.mkdir(parents=True)
        (transport / "payload.json").write_text(json.dumps(original_result), encoding="utf-8")
        (transport / "device_transport.py").write_text(
            "import json\nfrom pathlib import Path\n"
            "class Client:\n    def close(self): pass\n"
            "class Wire:\n"
            "    def readonly(self, client, script, deadline_seconds):\n"
            "        return 0, json.loads(Path(__file__).with_name('payload.json').read_text()), False\n"
            "def connect(): return Client(), Wire()\n", encoding="utf-8")
        args = [str(driver.__file__), "--transport-source", str(root / "transport"),
                "--poll", "/storage/.kodi/temp/bobbi-standard-real-123"]
        with mock.patch.object(driver, "ROOT", root), mock.patch.object(sys, "argv", args):
            with contextlib.redirect_stdout(io.StringIO()):
                command_code = driver.main()
        files = list((root / "review-evidence").glob("*.json"))
        assert len(files) == 1
        saved = json.loads(files[0].read_text())
        return {"command_exit_code": command_code, "saved_exit_code": saved["exit_code"],
                "saved_trial_exit_code": saved.get("trial_exit_code"),
                "saved_transport_exit_code": saved.get("transport_exit_code"),
                "result_passed": saved["result"].get("passed"),
                "result_state": saved["result"].get("state")}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    driver = load(args.repo / "tools/ce_playback_trial.py", "pr3_playback_trial")
    cases = [
        ("observe explicit failure", "observe", {"operation": "observe", "passed": False}, False),
        ("observe success", "observe", {"operation": "observe", "passed": True}, True),
        ("stop explicit failure", "stop", {"operation": "stop", "stopped": False}, False),
        ("stop success", "stop", {"operation": "stop", "stopped": True}, True),
        ("cancel explicit failure", "cancel", {"operation": "cancel", "cancelled": False}, False),
        ("cancel success", "cancel", {"operation": "cancel", "cancelled": True}, True),
        ("select missing result", "select", {"operation": "select"}, False),
        ("observe missing result", "observe", {"operation": "observe"}, False),
        ("cards read", "cards", {"operation": "cards", "selected": False, "cards": []}, True),
        ("inspect read", "inspect", {"operation": "inspect", "sample": {}}, True),
        ("unsupported control", "manual_off", {"operation": "manual_off", "state": "not_tested", "passed": None}, False),
    ]
    tests = []
    for name, operation, payload, success in cases:
        code = driver.result_exit_code(payload, operation=operation)
        tests.append({"id": name, "actual_exit_code": code, "expected_success": success,
                      "passed": (code == 0) == success})
    standard = load(args.repo / "tools/ce_standard_real.py", "pr3_standard_trial")
    prior_failure = json.loads((args.evidence / "ce-standard-real-1792509112829842300.json").read_text())["result"]
    final_success = json.loads((args.evidence / "ce-standard-real-1792509830895851000.json").read_text())["result"]
    discrepancy = {
        "retained_standard_failure": exercise_standard(standard, prior_failure),
        "retained_standard_success": exercise_standard(standard, final_success),
        "explicit_pending_response": exercise_standard(standard, {"state": "running", "passed": None}),
    }
    result = {"reference_head": "c8de17ae9dabbe0f37753e1751b1d88107311316", "tests": tests,
              "passed": sum(row["passed"] for row in tests), "failed": sum(not row["passed"] for row in tests),
              "errors": 0, "new_driver_observations": discrepancy,
              "scope": "Actual Python driver modules; operation contract variants and original device receipts; temporary file/transport doubles, no device action"}
    (args.output / "RESULT.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
