"""Compile generic production helpers; this is not Android device playback."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--source', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
args = parser.parse_args()
args.output.mkdir(parents=True, exist_ok=True)
run = Path(tempfile.mkdtemp(prefix='generic-', dir=args.output))
legacy = HERE.parent/'ce-original-audio-handoff-20261022/tests'
source = args.source/'xbmc'
report = {'scope': 'Generic Kodi production C++ helpers; host Linux ABI, not Android runtime', 'tests': []}
tests = [
    ('handoff_registry', [legacy/'handoff_registry_test.cpp', source/'utils/Variant.cpp', source/'cores/VideoSettings.cpp']),
    ('handoff_file', [HERE/'handoff_file_test.cpp']),
    ('scoped_control', [HERE/'scoped_control_test.cpp', source/'utils/Variant.cpp']),
    ('completion_observation', [HERE/'completion_observation_test.cpp', source/'utils/Variant.cpp'])]
for name, files in tests:
    command = ['g++', '-std=c++17', '-O1', '-pthread', '-DTARGET_POSIX', '-I'+str(source),
               '-I'+str(legacy/'includes'), *map(str, files), '-o', str(run/name)]
    compiled = subprocess.run(command, capture_output=True, text=True, timeout=90)
    result = subprocess.run([str(run/name)], capture_output=True, text=True, timeout=20) if not compiled.returncode else compiled
    report['tests'].append(dict(name=name, passed=result.returncode == 0, output=compiled.stdout+compiled.stderr+result.stdout+result.stderr))
spec = importlib.util.spec_from_file_location('audio_harness', legacy/'run_original_audio_test.py')
audio_harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audio_harness)
text = (source/'cores/VideoPlayer/VideoPlayer.cpp').read_text()
comparator = text[text.index('class PredicateAudioFilter'):text.index('class PredicateSubtitlePriority')]
# Generic Omega calls the no-argument overload; F9 calls the bool overload.
prefix = audio_harness.PREFIX.replace('GetAudioLanguage(bool)', 'GetAudioLanguage(bool=false)')
(run/'actual_audio_comparator.h').write_text(prefix+comparator)
compiled = subprocess.run(['g++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-Werror',
    '-I'+str(source), '-I'+str(run), str(legacy/'original_audio_test.cpp'), '-o', str(run/'audio')],
    capture_output=True, text=True, timeout=60)
audio = subprocess.run([str(run/'audio')], capture_output=True, text=True, timeout=15) if not compiled.returncode else compiled
report['tests'].append(dict(name='original_audio', passed=audio.returncode == 0,
    output=compiled.stdout+compiled.stderr+audio.stdout+audio.stderr))
visibility_spec = importlib.util.spec_from_file_location('directory_visibility', HERE/'run_directory_visibility_test.py')
visibility_harness = importlib.util.module_from_spec(visibility_spec)
visibility_spec.loader.exec_module(visibility_harness)
visibility_path, visibility_result = visibility_harness.run(args.source, run)
report['tests'].append(dict(name='directory_visibility', passed=visibility_result['passed'],
    result=str(visibility_path), sha256=hashlib.sha256(visibility_path.read_bytes()).hexdigest()))
scoped_spec = importlib.util.spec_from_file_location('scoped_actor', HERE/'run_scoped_actor_test.py')
scoped_harness = importlib.util.module_from_spec(scoped_spec)
scoped_spec.loader.exec_module(scoped_harness)
scoped_path, scoped_result = scoped_harness.run(args.source, run)
report['tests'].append(dict(name='scoped_actor', passed=scoped_result['passed'],
    result=str(scoped_path), sha256=hashlib.sha256(scoped_path.read_bytes()).hexdigest()))
inputs = (source/'cores/BobiHandoff.h', source/'dialogs/BobiHandoffFile.h',
          source/'cores/VideoPlayer/BobiOriginalAudio.h', source/'cores/VideoPlayer/VideoPlayer.cpp',
          source/'cores/VideoPlayer/BobiCompletion.h', source/'cores/VideoPlayer/BobiScopedControl.h',
          source/'utils/Variant.cpp', source/'utils/Variant.h')
report['sources'] = {str(file.relative_to(args.source)): hashlib.sha256(file.read_bytes()).hexdigest()
                     for file in inputs if file.is_file()}
report['missing_sources'] = [str(file.relative_to(args.source)) for file in inputs if not file.is_file()]
report['fixtures'] = {'completion_observation_test.cpp': hashlib.sha256(
    (HERE/'completion_observation_test.cpp').read_bytes()).hexdigest()}
(run/'result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
print(json.dumps(report, ensure_ascii=False))
raise SystemExit(0 if not report['missing_sources'] and all(test['passed'] for test in report['tests']) else 1)
