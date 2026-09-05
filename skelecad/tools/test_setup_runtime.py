"""Setup guards and local application paths without downloading packages."""
import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runtime_paths
import setup_runtime


class RuntimeSetupTests(unittest.TestCase):
    def test_local_override_keeps_version_and_presets(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            (project / 'config').mkdir()
            (project / 'config/toolchain.json').write_text(json.dumps({
                'freecad': {'version': '1.1.3', 'python': 'old/python.exe'},
                'bambu_studio': {'machine_preset': 'A1 mini'}}))
            (project / 'config/toolchain.local.json').write_text(json.dumps({
                'freecad': {'python': 'custom/python.exe'}}))
            with patch.object(runtime_paths, 'PROJECT', project):
                config = runtime_paths.tool_config()
                self.assertEqual(config['freecad']['version'], '1.1.3')
                self.assertEqual(config['bambu_studio']['machine_preset'], 'A1 mini')
                self.assertEqual(runtime_paths.tool_path('freecad', 'python'),
                                 project.parent / 'custom/python.exe')

    def test_portable_freecad_is_verified_before_install_and_reused(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory)
            config={'freecad':{'version':'1.1.3','python':'.tools/freecad-1.1.3/bin/python.exe'}}
            def download(url,path,digest):
                path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(b'test');return path
            def extract(command):
                staging=Path(next(str(arg)[2:] for arg in command if str(arg).startswith('-o')))
                binary=staging/'FreeCAD-portable/bin/python.exe'
                binary.parent.mkdir(parents=True);binary.touch()
            with patch.object(setup_runtime,'WORKSPACE',workspace), \
                 patch.object(setup_runtime,'download_verified',side_effect=download) as fetch, \
                 patch.object(setup_runtime,'run',side_effect=extract), \
                 patch.object(setup_runtime,'check_freecad') as check:
                python=setup_runtime.ensure_freecad(config)
                self.assertTrue(python.is_file());self.assertEqual(fetch.call_count,2)
                self.assertEqual(check.call_count,2)
                self.assertEqual(setup_runtime.ensure_freecad(config),python)
                self.assertEqual(fetch.call_count,2)

    def test_bad_download_never_replaces_cache(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'archive';path.write_bytes(b'existing')
            with patch.object(setup_runtime.urllib.request,'urlopen',return_value=io.BytesIO(b'corrupt')):
                with self.assertRaisesRegex(RuntimeError,'checksum mismatch'):
                    setup_runtime.download_verified('https://example.test/archive',path,'0'*64)
            self.assertEqual(path.read_bytes(),b'existing')

    def test_failed_validation_never_installs_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            workspace=Path(directory);(workspace/'.tools').mkdir()
            config={'freecad':{'version':'1.1.3','python':'.tools/freecad-1.1.3/bin/python.exe'}}
            def extract(command):
                staging=Path(next(str(arg)[2:] for arg in command if str(arg).startswith('-o')))
                binary=staging/'FreeCAD-portable/bin/python.exe'
                binary.parent.mkdir(parents=True);binary.touch()
            with patch.object(setup_runtime,'WORKSPACE',workspace), \
                 patch.object(setup_runtime,'download_verified',return_value=Path('asset')), \
                 patch.object(setup_runtime,'run',side_effect=extract), \
                 patch.object(setup_runtime,'check_freecad',side_effect=RuntimeError('Invalid runtime')):
                with self.assertRaisesRegex(RuntimeError,'Invalid runtime'):setup_runtime.ensure_freecad(config)
            self.assertFalse((workspace/'.tools/freecad-1.1.3').exists())

    def test_missing_bambu_stops_before_environment_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'bambu_studio': {'executable': str(Path(directory) / 'missing.exe')}}
            with patch.object(setup_runtime, 'tool_config', return_value=config), \
                 patch.object(setup_runtime, 'ensure_freecad'), \
                 patch.object(setup_runtime, 'run') as run:
                with self.assertRaisesRegex(RuntimeError, 'Install Bambu Studio'):
                    setup_runtime.setup('uv')
                run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
