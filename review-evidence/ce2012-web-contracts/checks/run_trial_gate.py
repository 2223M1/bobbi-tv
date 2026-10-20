"""Candidate gate for CE trial exit semantics, using complete original receipt shapes.

The original real-device receipts are successful controls. Failed inputs are
explicitly constructed copies, not claims that the historical attempts failed.
No target code is edited; no Kodi/network/device operation is invoked.
"""
import argparse
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--out', type=Path, default=ROOT / 'TRIAL-GATE-RESULT.json')
    args = parser.parse_args()
    target = args.repo.resolve() / 'tools/ce_playback_trial.py'
    spec = importlib.util.spec_from_file_location('ce_trial_candidate_gate', target)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    observe = json.loads((ROOT / 'fixtures/observe-envelope.json').read_text())['result']
    stop = json.loads((ROOT / 'fixtures/stop-envelope.json').read_text())['result']
    results = []

    class TrialGate(unittest.TestCase):
        def check(self, name, payload, require_nonzero):
            actual = module.result_exit_code(payload, 0, False)
            results.append(dict(name=name, actual_exit_code=actual,
                expected='nonzero' if require_nonzero else 'zero',
                passed=(actual != 0) if require_nonzero else (actual == 0)))
            if require_nonzero:
                self.assertNotEqual(actual, 0, name + ': explicit failed receipt must fail the command')
            else:
                self.assertEqual(actual, 0, name + ': successful control must succeed')

        def test_observe_failed_caching_sample(self):
            payload = deepcopy(observe)
            # ce_trial_remote.py:658-660 yields False when any captured sample
            # is caching, even with zero remote exit/no Python exception.
            payload['samples'][1]['caching'] = True
            payload['passed'] = False
            self.check('observe_failed_caching_sample', payload, True)

        def test_stop_wait_timed_out(self):
            payload = deepcopy(stop)
            # ce_trial_remote.py:640-642 emits this shape after the 12s wait
            # when Player.GetActivePlayers is still nonempty.
            payload['stopped'] = False
            payload['seconds'] = 12.05
            self.check('stop_wait_timed_out', payload, True)

        def test_original_successful_observation(self):
            self.assertIs(observe['passed'], True)
            self.check('original_successful_observation', deepcopy(observe), False)

        def test_original_successful_stop(self):
            self.assertIs(stop['stopped'], True)
            self.check('original_successful_stop', deepcopy(stop), False)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(TrialGate)
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    report = dict(target=str(target), reference_head='28819d202b6d4b4ff00367e46c37d8542a1b35af',
        scope='candidate result_exit_code only; complete original successful receipts plus explicit constructed failure variants',
        tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        passed=result.testsRun-len(result.failures)-len(result.errors), results=results, unittest=stream.getvalue())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'unittest'}, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
