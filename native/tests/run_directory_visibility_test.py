"""Compile verbatim production provider/static-item/container methods.

Only surrounding Kodi services are stubbed, not the changed branch or path
reidentification. Both the original and the incomplete Update-only fix must
fail the same C++ test at their respective visibility boundaries.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

METHODS = {
    'xbmc/guilib/listproviders/DirectoryProvider.cpp': (
        'bool CDirectoryProvider::Update(bool forceRefresh)',
        'void CDirectoryProvider::Fetch(', 'bool CDirectoryProvider::IsUpdating() const',
        'void CDirectoryProvider::OnJobComplete('),
    'xbmc/guilib/GUIStaticItem.cpp': (
        'CGUIStaticItem::CGUIStaticItem(const CFileItem &item)',
        'bool CGUIStaticItem::UpdateVisibility(', 'bool CGUIStaticItem::IsVisible() const',
        'void CGUIStaticItem::SetVisibleCondition('),
    'xbmc/guilib/GUIBaseContainer.cpp': (
        'void CGUIBaseContainer::UpdateListProvider(', 'void CGUIBaseContainer::Reset()',
        'bool CGUIBaseContainer::CanFocus() const'),
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def method(text, signature):
    assert text.count(signature) == 1, 'PRODUCTION_METHOD_DRIFT:' + signature
    start = text.index(signature)
    brace = text.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def run(source, output):
    source, output = Path(source), Path(output)
    output.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix='directory-visibility-', dir=output))
    bodies = []
    for path, signatures in METHODS.items():
        text = (source/path).read_text()
        bodies.extend(method(text, signature) for signature in signatures)
    candidate = '\n\n'.join(bodies) + '\n'
    publish = '    i->UpdateVisibility(m_parentID);\n'
    guarded = ('  if (!changed)\n  {\n    for (auto& i : m_items)\n'
               '      changed |= i->UpdateVisibility(m_parentID);\n  }')
    unguarded = ('  for (auto& i : m_items)\n'
                 '    changed |= i->UpdateVisibility(m_parentID);')
    assert candidate.count(publish) == 1 and candidate.count(guarded) == 1, 'VISIBILITY_FIX_NOT_APPLIED'
    baseline = candidate.replace(publish, '')
    update_only = baseline.replace(guarded, unguarded)
    report = dict(scope='verbatim production methods with surrounding Kodi stubs; not GUI device certification',
                  source_sha256={path: sha(source/path) for path in METHODS}, tests=[])
    fixture = Path(__file__).with_name('directory_visibility_test.cpp')
    report['fixture_sha256'] = sha(fixture)
    variants = (
        ('candidate', candidate, None),
        ('pre_fix_negative_control', baseline, 'FAIL DONE same-tick visibility/focusability'),
        ('update_only_negative_control', update_only, 'FAIL interleaved completion visibility before publication'),
    )
    for label, text, failure in variants:
        folder = work/label
        folder.mkdir()
        (folder/'actual_directory_visibility.inc').write_text(text)
        binary = folder/'directory-visibility-test'
        command = ['g++', '-std=c++17', '-O1', '-Wall', '-Wextra', '-Werror',
                   '-Wno-unused-parameter', '-I'+str(folder), str(fixture), '-o', str(binary)]
        compiled = subprocess.run(command, capture_output=True, text=True, timeout=90)
        assert compiled.returncode == 0, compiled.stdout + compiled.stderr
        trial = subprocess.run([str(binary)], capture_output=True, text=True, timeout=15)
        passed = trial.returncode == 0 if failure is None else (
            trial.returncode == 1 and failure in trial.stderr)
        report['tests'].append(dict(name=label, passed=passed, exit_code=trial.returncode,
            output=trial.stdout+trial.stderr, extracted_sha256=sha(folder/'actual_directory_visibility.inc'),
            binary_sha256=sha(binary), command=command))
    report['passed'] = all(row['passed'] for row in report['tests'])
    path = work/'result.json'
    path.write_text(json.dumps(report, indent=2))
    assert report['passed'], 'PRODUCTION_VISIBILITY_TEST_FAILED'
    return path, report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    path, report = run(args.source, args.output)
    print(json.dumps(dict(result=str(path), passed=report['passed'])))
