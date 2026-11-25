import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

SPEC = importlib.util.spec_from_file_location('stage_components', Path(__file__).resolve().parents[1] / 'stage-components.py')
STAGE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STAGE)


class StageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.host = self.root / 'host'
        (self.host / 'system').mkdir(parents=True)
        (self.host / 'system/addon-manifest.xml').write_text('<addons><addon>xbmc.python</addon>'
            '<addon optional="true">service.xbmc.versioncheck</addon></addons>')
        self.rows = []
        for addon in ('plugin.video.bobbi', 'skin.bobbi.cinema', 'resource.uisounds.bobbi-modern'):
            archive = self.root / (addon + '.zip')
            with zipfile.ZipFile(archive, 'w') as zipped:
                zipped.writestr(addon + '/addon.xml', f'<addon id="{addon}" version="1.0"/>')
                zipped.writestr(addon + '/code.py', 'print("fixture")\n')
            self.rows.append({'id': addon, 'version': '1.0', 'file': archive.name,
                              'bytes': archive.stat().st_size,
                              'sha256': hashlib.sha256(archive.read_bytes()).hexdigest()})
        self.manifest = self.root / 'manifest.json'
        self.write_manifest()

    def tearDown(self):
        self.temp.cleanup()

    def write_manifest(self):
        self.manifest.write_text(json.dumps({'version': 'fixture', 'components': self.rows}))

    def test_full_stage(self):
        result = STAGE.stage(self.manifest, self.host)
        self.assertFalse(result['profile_copied'])
        self.assertEqual(len(result['components']), 3)
        self.assertIn('optional="true"', (self.host / 'system/addon-manifest.xml').read_text())
        self.assertTrue((self.host / 'addons/plugin.video.bobbi/code.py').is_file())
        self.assertNotIn('service.xbmc.versioncheck', (self.host / 'system/addon-manifest.xml').read_text())
        self.assertEqual(result['disabled_upstream_services_for_new_profiles'], ['service.xbmc.versioncheck'])

    def test_hash_rejected_before_any_component_write(self):
        self.rows[-1]['sha256'] = '0' * 64
        self.write_manifest()
        with self.assertRaises(ValueError):
            STAGE.stage(self.manifest, self.host)
        self.assertFalse((self.host / 'addons').exists())

    def test_non_installable_source_check_cannot_be_packaged_as_android(self):
        self.manifest.write_text(json.dumps({'channel': 'source-check', 'components': self.rows}))
        with self.assertRaisesRegex(ValueError, 'not an installable'):
            STAGE.stage(self.manifest, self.host)
        self.assertFalse((self.host / 'addons').exists())

    def test_existing_profile_rejected(self):
        (self.host / 'portable_data').mkdir()
        with self.assertRaises(ValueError):
            STAGE.stage(self.manifest, self.host)

    def test_duplicate_id_rejected(self):
        self.rows.append(self.rows[0])
        self.write_manifest()
        with self.assertRaises(ValueError):
            STAGE.stage(self.manifest, self.host)

    def test_traversal_package_rejected(self):
        self.rows[0]['file'] = '../outside.zip'
        self.write_manifest()
        with self.assertRaises(ValueError):
            STAGE.stage(self.manifest, self.host)

    def test_stale_tree_not_overwritten(self):
        (self.host / 'addons/resource.uisounds.bobbi-modern').mkdir(parents=True)
        with self.assertRaises(ValueError):
            STAGE.stage(self.manifest, self.host)
        self.assertFalse((self.host / 'addons/plugin.video.bobbi').exists())

    def test_windows_drive_package_path_rejected(self):
        self.rows[0]['file'] = 'C:/outside.zip'
        self.write_manifest()
        with self.assertRaises(ValueError):
            STAGE.stage(self.manifest, self.host)
        self.assertFalse((self.host / 'addons').exists())

    def test_case_alias_member_rejected_before_write(self):
        row = self.rows[-1]
        archive = self.root / row['file']
        with zipfile.ZipFile(archive, 'a') as zipped:
            zipped.writestr(row['id'] + '/CODE.py', 'ambiguous')
        row['bytes'] = archive.stat().st_size
        row['sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.write_manifest()
        with self.assertRaises(ValueError):
            STAGE.stage(self.manifest, self.host)
        self.assertFalse((self.host / 'addons').exists())

    def test_windows_ads_member_rejected_before_write(self):
        row = self.rows[-1]
        archive = self.root / row['file']
        with zipfile.ZipFile(archive, 'a') as zipped:
            zipped.writestr(row['id'] + '/code.py:alternate', 'stream')
        row['bytes'] = archive.stat().st_size
        row['sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
        self.write_manifest()
        with self.assertRaises(ValueError):
            STAGE.stage(self.manifest, self.host)
        self.assertFalse((self.host / 'addons').exists())


    def test_archive_mutated_between_validation_and_extraction_never_extracts_unverified_bytes(self):
        first_archive = self.root / self.rows[0]['file']
        second_archive = self.root / self.rows[1]['file']
        original_zip = STAGE.zipfile.ZipFile
        open_calls = []

        def intercept_after_first_validated(path, *args, **kwargs):
            open_calls.append(Path(path))
            if Path(path) == second_archive:
                # Mutate first_archive AFTER its validation finished, BEFORE extraction starts
                with original_zip(first_archive, 'w') as tampered:
                    tampered.writestr(self.rows[0]['id'] + '/addon.xml', f'<addon id="{self.rows[0]["id"]}" version="1.0"/>')
                    tampered.writestr(self.rows[0]['id'] + '/code.py', 'UNVERIFIED_TAMPERED\n')
            return original_zip(path, *args, **kwargs)

        STAGE.zipfile.ZipFile = intercept_after_first_validated
        try:
            STAGE.stage(self.manifest, self.host)
        finally:
            STAGE.zipfile.ZipFile = original_zip
        self.assertEqual(open_calls.count(first_archive), 1)
        self.assertEqual((self.host / 'addons/plugin.video.bobbi/code.py').read_text(), 'print("fixture")\n')

    def test_archive_mutated_between_stat_hash_and_zip_open_is_rejected(self):
        first_archive = self.root / self.rows[0]['file']
        original_zip = STAGE.zipfile.ZipFile

        def intercept_during_open(path, *args, **kwargs):
            zf = original_zip(path, *args, **kwargs)
            if Path(path) == first_archive:
                with original_zip(first_archive, 'w') as tampered:
                    tampered.writestr(self.rows[0]['id'] + '/addon.xml', f'<addon id="{self.rows[0]["id"]}" version="1.0"/>')
                    tampered.writestr(self.rows[0]['id'] + '/code.py', 'UNVERIFIED_TAMPERED\n')
            return zf

        STAGE.zipfile.ZipFile = intercept_during_open
        try:
            with self.assertRaisesRegex(ValueError, 'changed during validation'):
                STAGE.stage(self.manifest, self.host)
        finally:
            STAGE.zipfile.ZipFile = original_zip
        self.assertFalse((self.host / 'addons').exists())


if __name__ == '__main__':
    unittest.main()
