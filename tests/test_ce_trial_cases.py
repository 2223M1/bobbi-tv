"""Exercise the real CLI parser and generated remote selection guard offline."""
import ast
import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('trial_manifest_cli', ROOT / 'tools/ce_playback_trial.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def test_cli_and_generated_remote_have_one_work_and_operation_declaration():
    manifest = cli.trial_cases()
    assert manifest['schema'] == 1 and len(manifest['works']) == 47
    parser = cli.build_parser()
    for work, expected in manifest['works'].items():
        args = parser.parse_args([work, 'start', '--transport-source', str(ROOT)])
        generated = cli.remote_code(dict(NAME=args.work, OP=args.operation))
        compile(generated, 'actual-generated-trial', 'exec')
        tree = ast.parse(generated)
        # Only execute the actual injected literals and remote scope guard;
        # importing the remote script would create files and contact a device.
        injection = []
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                break
            injection.append(node)
        guard = next(node for node in tree.body if isinstance(node, ast.Assert)
                     and isinstance(node.msg, ast.Constant) and node.msg.value == 'TRIAL_SCOPE')
        namespace = {}
        exec(compile(ast.Module(body=injection + [guard], type_ignores=[]), 'actual-remote-guard', 'exec'), namespace)
        assert namespace['TESTS'][args.work] == expected
        assert set(namespace['TESTS']) == set(manifest['works'])
        assert set(namespace['OPERATIONS']) == set(manifest['operations']) - set(manifest['local_operations'])
    for operation in manifest['operations']:
        assert parser.parse_args(['galactic_heroes', operation, '--transport-source', str(ROOT)]).operation == operation
    with pytest.raises(ValueError, match='LOCAL_OPERATION'):
        cli.remote_code(dict(NAME='galactic_heroes', OP='collect'))
    with pytest.raises(ValueError, match='TRIAL_SCOPE'):
        cli.remote_code(dict(NAME='unknown', OP='start'))
    help_result = subprocess.run([sys.executable, str(ROOT / 'tools/ce_playback_trial.py'), '--help'],
                                text=True, capture_output=True, timeout=15)
    assert help_result.returncode == 0 and all(name in help_result.stdout for name in manifest['works'])


def test_removed_importer_and_remote_cannot_reset_static_cases():
    assert not (ROOT / 'tools/import_playback_trial.py').exists()
    remote = ast.parse((ROOT / 'tools/ce_trial_remote.py').read_text(encoding='utf-8'))
    assert not any(isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
        and target.id == 'TESTS' for target in node.targets) for node in remote.body)
    for name, row in cli.trial_cases()['works'].items():
        assert row['kind'] in ('movie', 'tv') and type(row['tmdb_id']) is int and row['tmdb_id'] > 0
        assert isinstance(row['title'], str) and row['title']
        if row['kind'] == 'tv':
            assert row['season'] >= 0 and row['episode'] > 0
