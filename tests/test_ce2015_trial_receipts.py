import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location('standard_trial_driver',
    Path(__file__).resolve().parents[1]/'tools/ce_standard_real.py')
driver = importlib.util.module_from_spec(spec); spec.loader.exec_module(driver)


@pytest.mark.parametrize('value,transport,diagnostic,trial,final,pending', [
    ({'state': 'complete', 'passed': True}, 0, False, 0, 0, False),
    ({'state': 'complete', 'passed': False}, 0, False, 1, 1, False),
    ({'state': 'running', 'passed': None}, 0, False, None, 0, True),
    ({'state': 'running', 'passed': False}, 0, False, 1, 1, False),
    ({'state': 'complete', 'passed': True}, 1, False, 0, 1, False),
    ({'state': 'complete', 'passed': True}, 0, True, 0, 1, False),
    ({}, 0, False, 1, 1, False),
])
def test_business_failure_and_pending_are_not_transport_success(value, transport, diagnostic, trial, final, pending):
    assert driver.receipt_status(value, transport, diagnostic) == dict(
        transport_exit_code=transport, trial_exit_code=trial, exit_code=final,
        pending=pending, diagnostic_present=diagnostic)
