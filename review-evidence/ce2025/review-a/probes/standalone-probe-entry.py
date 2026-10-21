#!/usr/bin/env python3
"""Probe the CE entry builder's hard dependency on a removed LICENSE member.

Usage: python standalone-probe-entry.py --repo /path/to/bobbi-tv

The supplied repository is read only. Required production source is copied into
a TemporaryDirectory, and all synthetic addon files, inventory, public trust and
signed bundles are created there. The temporary RSA private key stays in memory.
No production key, account, device, network or repository mutation is used.

Exit 1: missing-document dependency reproduced with a successful positive control.
Exit 0: the no-LICENSE build, signed entry audit and isolated bootstrap imports pass.
        This proves only the focused fixture; not a production delivery or device.
Exit 2: missing dependency, incompatible interface or another failure prevented
        this focused probe from determining the result.

This uses two synthetic components and the actual copied build(), sources(),
files(), SignedBundle and signature verifier without bypassing their checks.
It is not a production 22-component build or device certification.
"""
import argparse
import base64
import hashlib
import importlib
from io import BytesIO, StringIO
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import zipfile


class ProbeEnvironmentError(RuntimeError):
    pass


class ArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ProbeEnvironmentError(message)


def read_repo_file(repo, relative):
    path = repo / relative
    try:
        path.resolve().relative_to(repo)
    except ValueError as error:
        raise ProbeEnvironmentError('Source path escapes supplied repository: ' + relative) from error
    if not path.is_file():
        raise ProbeEnvironmentError('Required source file is missing: ' + relative)
    return path.read_bytes()


def copied_source(repo, scratch, relative, result):
    destination = scratch / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = read_repo_file(repo, relative)
    result['source_sha256'][relative] = hashlib.sha256(raw).hexdigest()
    destination.write_bytes(raw)


def execute(repo, result):
    try:
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.asymmetric import padding, rsa
    except ImportError as error:
        raise ProbeEnvironmentError('The probe requires the cryptography package.') from error

    package_relative = 'addons/script.module.bobbi.platform/lib/bobbi_platform'
    original_sys_path = list(sys.path)
    original_dont_write = sys.dont_write_bytecode
    # Import only the copies. Bytecode generation is unnecessary for this probe.
    sys.dont_write_bytecode = True
    try:
        with TemporaryDirectory(prefix='ce-entry-probe-') as directory:
            scratch = Path(directory)
            for relative in (
                'tools/build_ce_entry.py',
                'tools/build_release.py',
                'tools/delivery_policy.py',
                'tools/audit_ce_entry.py',
                package_relative + '/__init__.py',
                package_relative + '/offline_updates.py',
                package_relative + '/updates.py',
                package_relative + '/signatures.py',
            ):
                copied_source(repo, scratch, relative, result)
            sys.path.insert(0, str(scratch / 'tools'))
            builder = importlib.import_module('build_ce_entry')
            release = importlib.import_module('build_release')
            auditor = importlib.import_module('audit_ce_entry')
            for module in (builder, release, auditor):
                try:
                    Path(module.__file__).resolve().relative_to(scratch)
                except ValueError as error:
                    raise ProbeEnvironmentError('An existing imported module prevented isolated loading.') from error
            if not isinstance(builder.BOOTSTRAP, (tuple, list)):
                raise ProbeEnvironmentError('Unsupported BOOTSTRAP interface.')
            for name in builder.BOOTSTRAP:
                if not isinstance(name, str) or Path(name).name != name or '\\' in name:
                    raise ProbeEnvironmentError('Unsupported bootstrap source name.')
                copied_source(repo, scratch, package_relative + '/' + name, result)

            ids = ['script.bobbi.start', 'script.module.bobbi.platform']
            private = rsa.generate_private_key(public_exponent=65537, key_size=3072)
            public = private.public_key().public_numbers()
            trust = dict(schema=1,
                key=dict(algorithm='RSA3072-SHA256', n=format(public.n, 'x'), e=public.e),
                components=ids)
            # All writes below are under scratch, never under the --repo path.
            (scratch / package_relative / 'release_trust.json').write_text(
                json.dumps(trust), encoding='utf-8')
            for name in ids:
                addon = scratch / 'addons' / name
                addon.mkdir(parents=True, exist_ok=True)
                (addon / 'addon.xml').write_text(
                    '<addon id="' + name + '" version="0.1.0"><requires><import addon="xbmc.python"/><import addon="script.module.pycryptodome"/></requires><extension point="xbmc.python.script" library="default.py"/></addon>', encoding='utf-8')
                (addon / 'default.py').write_text('# Synthetic fixture entry; not executed.\n', encoding='utf-8')
            (scratch / 'release').mkdir()
            (scratch / 'release/source-inventory.json').write_text(
                json.dumps(dict(schema=1, components={
                    name: release.files(scratch / 'addons' / name) for name in ids})),
                encoding='utf-8')

            def make_bundle(with_license):
                rows, blobs = [], []
                for name in ids:
                    stream = BytesIO()
                    with zipfile.ZipFile(stream, 'w') as archive:
                        for relative in release.files(scratch / 'addons' / name):
                            archive.writestr(name + '/' + relative,
                                (scratch / 'addons' / name / relative).read_bytes())
                        if name == ids[1] and with_license:
                            archive.writestr(name + '/LICENSE', b'synthetic positive-control document')
                    raw = stream.getvalue()
                    filename = name + '/' + name + '-0.1.0.zip'
                    rows.append(dict(id=name, version='0.1.0', file=filename,
                        size=len(raw), sha256=hashlib.sha256(raw).hexdigest()))
                    blobs.append((filename, raw))
                manifest = dict(schema=2, channel='private-candidate', profile='coreelec',
                    sequence=1, components=rows)
                raw = json.dumps(manifest, sort_keys=True, separators=(',', ':')).encode()
                signature = base64.b64encode(private.sign(raw, padding.PKCS1v15(), hashes.SHA256()))
                path = scratch / ('with-license.zip' if with_license else 'without-license.zip')
                with zipfile.ZipFile(path, 'w') as archive:
                    for name, data in [('release.json', raw), ('release.sig', signature)] + blobs:
                        archive.writestr(zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0)), data)
                # Keep production verification intact and require it to succeed.
                with builder.SignedBundle(path, builder.load_trust(), 'coreelec') as checked:
                    checked.check_all()
                return path

            for with_license in (False, True):
                bundle = make_bundle(with_license)
                case = dict(with_license=with_license, signature_and_component_integrity='passed')
                target = scratch / ('entry-with-license.zip' if with_license else 'entry-without-license.zip')
                try:
                    built = builder.build(bundle, target)
                    if not target.is_file() or not isinstance(built, dict):
                        raise ProbeEnvironmentError('Unsupported build return/output interface.')
                    case.update(build='passed', sequence=built.get('sequence'), entry_audit=auditor.audit(target))
                except Exception as error:
                    case.update(build='failed', exception=type(error).__name__, message=str(error))
                result['cases'].append(case)

            negative, positive = result['cases']
            if negative['build'] == 'passed':
                result.update(status='focused_entry_checks_passed', exit_code=0)
            elif (negative.get('exception') == 'KeyError'
                    and 'script.module.bobbi.platform/LICENSE' in negative.get('message', '')
                    and positive['build'] == 'passed'):
                result.update(status='missing_license_dependency_reproduced', exit_code=1)
            else:
                result.update(status='incompatible_or_other_failure', exit_code=2)
    finally:
        sys.path[:] = original_sys_path
        sys.dont_write_bytecode = original_dont_write
        # The script is intended as a standalone process; remove its temporary
        # module bindings as well so a programmatic invocation cannot reuse them.
        for name in list(sys.modules):
            if name in ('build_ce_entry', 'build_release', 'audit_ce_entry', 'delivery_policy', 'bobbi_platform') or name.startswith('bobbi_platform.'):
                del sys.modules[name]


def main():
    result = dict(schema=1, probe='entry_builder_document_dependency',
        scope='isolated two-component synthetic fixture; no production signing or device validation',
        repository_mutated=False, production_checks_bypassed=False,
        temporary_private_key='memory_only', fixture_sequence=1,
        fixture_sequence_is_product_identity=False, source_sha256={}, cases=[])
    try:
        parser = ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
        parser.add_argument('--repo', type=Path, required=True, help='Read-only source repository root')
        args = parser.parse_args()
        repo = args.repo.expanduser().resolve()
        if not repo.is_dir():
            raise ProbeEnvironmentError('--repo is not a directory.')
        result['source_root'] = str(repo)
        # Keep standard output a single JSON object even if a reviewed tool logs.
        with redirect_stdout(StringIO()):
            execute(repo, result)
    except Exception as error:
        result.update(status='environment_or_interface_error', exit_code=2,
            exception=type(error).__name__, message=str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result['exit_code']


if __name__ == '__main__':
    sys.exit(main())
