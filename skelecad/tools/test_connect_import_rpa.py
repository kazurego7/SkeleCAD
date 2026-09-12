"""URL preparation and state-machine tests; all GUI calls are mocked."""
import copy
from datetime import datetime, timezone
import hashlib
import json
import itertools
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlparse, parse_qs
import zipfile

from connect_import_rpa import create_staged_job, import_uri, plan_import, execute_import
from connect_prepare_rpa import _click_preparation_button


class ImportPreparation(unittest.TestCase):
    def setUp(self):
        self.now = datetime.now(timezone.utc)
        self.filename = 'SkeleCAD-1234ABCD.gcode.3mf'
        self.observation = {
            'source_kind': 'live_window_capture', 'observed_at': self.now.isoformat(),
            'stage_candidate': 'import_confirmation', 'blocking_message_candidates': [],
            'import_filename_candidates': [self.filename],
            'green_button_candidates': [{'text': 'Import Gcode 3MF', 'bounds': [200, 300, 360, 332]}],
            'window_reference': {'width': 800, 'height': 600},
        }

    def test_import_is_allowlisted(self):
        self.assertEqual(plan_import(self.observation, self.filename)['action'], 'confirm_import')

    def test_wrong_or_duplicate_file_never_confirms(self):
        for names in ([], ['SkeleCAD-OTHER.gcode.3mf'], [self.filename, self.filename]):
            with self.subTest(names=names):
                self.observation['import_filename_candidates'] = names
                self.assertEqual(plan_import(self.observation, self.filename)['action'], 'stop')

    def test_send_screen_and_send_button_never_confirms(self):
        self.observation['stage_candidate'] = 'send_dialog'
        self.assertEqual(plan_import(self.observation, self.filename)['action'], 'stop')
        self.observation['stage_candidate'] = 'import_confirmation'
        self.observation['green_button_candidates'].append({'text': 'Send'})
        self.assertEqual(plan_import(self.observation, self.filename)['action'], 'stop')

    def test_input_helper_rejects_Send_before_importing_driver(self):
        with self.assertRaisesRegex(RuntimeError, 'Send is never supported'):
            _click_preparation_button({'stage_candidate': 'send_dialog'}, {'action': 'send', 'button': 'Send'})

    def test_package_is_copied_byte_for_byte_with_distinct_names(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'original.gcode.3mf'
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('Metadata/plate_1.gcode', '; calibration test')
            original = source.read_bytes()
            first, digest = create_staged_job(source, root / 'one')
            second, _ = create_staged_job(source, root / 'two')
            self.assertNotEqual(first.name, second.name)
            self.assertEqual(first.read_bytes(), original)
            self.assertEqual(second.read_bytes(), original)
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(digest, hashlib.sha256(original).hexdigest())

    def test_unsliced_package_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / 'bad.gcode.3mf'
            with zipfile.ZipFile(source, 'w') as archive:
                archive.writestr('3D/model.model', 'model')
            with self.assertRaisesRegex(ValueError, 'no sliced plate'):
                create_staged_job(source, Path(temp) / 'out')

    def test_url_roundtrip_handles_spaces_unicode_ampersands(self):
        path = Path('C:/test dir/模型&a/SkeleCAD-1234ABCD.gcode.3mf')
        parsed = urlparse(import_uri(path))
        self.assertEqual((parsed.scheme, parsed.netloc), ('bambu-connect', 'import-file'))
        params = parse_qs(parsed.query)
        self.assertEqual(params['path'], [str(path)])
        self.assertEqual(params['name'], [path.name])
        self.assertEqual(params['version'], ['1.0.0'])

    def run_flow(self, screen_factory, expected_error=None):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            staged = output / self.filename
            staged.write_bytes(b'test job')
            digest = hashlib.sha256(staged.read_bytes()).hexdigest()
            result = {'can_send': False}
            def prepare_mock(args):
                args.output.mkdir()
                (args.output / 'result.json').write_text(json.dumps({'status': 'stopped_before_Send', 'can_send': False}))
            with patch('connect_import_rpa.validate_handler'), \
                 patch('connect_import_rpa.os.startfile', create=True) as start, \
                 patch('connect_import_rpa.time.sleep'), \
                 patch('connect_import_rpa.observe', side_effect=screen_factory()), \
                 patch('connect_import_rpa.click_import_once') as click, \
                 patch('connect_import_rpa.prepare', side_effect=prepare_mock) as preparation:
                if expected_error:
                    with self.assertRaisesRegex(RuntimeError, expected_error):
                        execute_import(staged, digest, output / 'expected.json', output, result)
                else:
                    execute_import(staged, digest, output / 'expected.json', output, result)
                    self.assertEqual(result['status'], 'stopped_before_Send')
                self.assertFalse(result['can_send'])
                return start.call_count, click.call_count, preparation.call_count

    def preview(self):
        preview = copy.deepcopy(self.observation)
        preview.update({'stage_candidate': 'loaded_preview', 'filename_line_candidates': [self.filename],
                        'green_button_candidates': [{'text': 'Print', 'bounds': [600, 100, 680, 132]}]})
        return preview

    def test_import_once_then_prepare_once(self):
        self.assertEqual(self.run_flow(lambda: [self.observation, self.observation, self.preview()]), (1, 1, 1))

    def test_auto_import_version_can_skip_confirmation(self):
        self.assertEqual(self.run_flow(lambda: [self.preview()]), (1, 0, 1))

    def test_existing_send_dialog_aborts_without_clicks(self):
        screen = copy.deepcopy(self.observation)
        screen['stage_candidate'] = 'send_dialog'
        self.assertEqual(self.run_flow(lambda: [screen], 'existing Send dialog'), (1, 0, 0))

    def test_confirmation_that_does_not_close_is_not_clicked_twice(self):
        self.assertEqual(self.run_flow(lambda: itertools.repeat(self.observation), 'did not reach'), (1, 1, 0))

    def test_foreign_import_file_stops(self):
        self.observation['import_filename_candidates'] = ['SkeleCAD-OTHER.gcode.3mf']
        self.assertEqual(self.run_flow(lambda: [self.observation], 'could not be verified'), (1, 0, 0))


if __name__ == '__main__':
    unittest.main()
