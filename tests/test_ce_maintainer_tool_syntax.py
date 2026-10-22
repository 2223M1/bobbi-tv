"""Compile the maintained diagnostic tools and their literal remote scripts."""
import ast
from pathlib import Path
import pytest

TOOLS = ('ce_attended_player_action.py', 'ce_bt_test_preflight.py',
         'ce_entry_device.py', 'ce_handoff_observe.py', 'ce_native_generation_probe.py',
         'ce_native_update.py', 'ce_playback_log_probe.py', 'ce_preparation_status.py',
         'ce_preparation_diagnose.py', 'ce_preparation_readonly.py', 'ce_startup_logging.py',
         'ce_transport_readiness_probe.py', 'ce_115_direct_start.py', 'ce_115_direct_kodi.py',
         'ce_115_direct_remote.py', 'ce_115_direct_trial.py')


@pytest.mark.parametrize('name', TOOLS)
def test_maintained_local_and_remote_scripts_compile_without_execution(name):
    path = Path(__file__).parents[1] / 'tools' / name
    source = path.read_text(encoding='utf-8')
    compile(source, str(path), 'exec')
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
            continue
        is_remote = any(isinstance(target, ast.Name) and target.id == 'REMOTE'
                        or isinstance(target, ast.Attribute) and target.attr == 'REMOTE'
                        for target in node.targets)
        if is_remote and isinstance(node.value.value, str):
            compile(node.value.value, name + ':REMOTE', 'exec')
