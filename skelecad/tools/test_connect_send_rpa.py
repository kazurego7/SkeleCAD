"""Print state machine regression tests; no desktop or printer input."""
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from connect_print import compatible_copy, OPTIONS, validate_profile
from connect_send_rpa import plan_send, send_once, classify_outcome


def profile():
    return {'model': 'A1 mini', 'use_ams': False, 'material': 'PLA', 'spool': 'external',
            'printer_label': '3DP-030-654', 'options': OPTIONS.copy()}


class SendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.file = self.root / 'SkeleCAD-12345678.gcode.3mf'
        self.file.write_bytes(b'validated calibration package')
        self.digest = hashlib.sha256(self.file.read_bytes()).hexdigest()
        self.expected = self.root / 'profile.json'
        self.expected.write_text(json.dumps(profile()))
        self.observation = {'source_kind': 'live_window_capture', 'observed_at': datetime.now(timezone.utc).isoformat(),
                            'stage_candidate': 'send_dialog', 'printer_label_candidates': ['3DP-030-654'],
                            'filament_text_visible': 'PLA', 'spool_selection': 'external',
                            'option_visual_candidates': OPTIONS.copy(), 'blocking_message_candidates': [],
                            'green_button_candidates': [{'text': 'Send', 'bounds': [700, 500, 760, 530]}],
                            'window_reference': {'handle': 1, 'width': 800, 'height': 600},
                            'decision_scope': {'kind': 'active_dialog', 'title': 'Send to print', 'bounds': [0, 50, 790, 570]}}
        self.before = self.root / 'before'; self.before.mkdir()
        (self.before / 'analysis.json').write_text(json.dumps(self.observation))
        self.preparation = {'status': 'stopped_before_Send', 'clicked': 'Print', 'file': str(self.file.resolve()),
                            'sha256': self.digest, 'send_observation_directory': str(self.before)}
        self.result = {'status': 'stopped_before_Send'}

    def tearDown(self):
        self.temp.cleanup()

    def started(self):
        return {**self.observation, 'stage_candidate': 'unknown',
                'visible_text_lines': ['3DP-030-654', 'Preparing', self.file.stem]}

    def send(self):
        return send_once(self.file, self.digest, self.expected, self.root, self.preparation, self.result)

    def test_send_once_and_matching_job_observation(self):
        with patch('connect_send_rpa.observe', side_effect=[self.observation, self.started()]), \
                patch('connect_send_rpa.time.sleep'), patch('connect_send_rpa._click_verified_button') as click:
            self.send()
            self.assertEqual(self.result['status'], 'started')
            self.assertTrue(self.result['send_clicked'])
            click.assert_called_once()
            self.assertTrue(click.call_args.kwargs['verify_dialog'])
            self.assertEqual((self.root / 'dispatch.decision').read_text(), 'send')

    def test_lost_click_result_stays_unknown_and_cannot_resend(self):
        with patch('connect_send_rpa.observe', return_value=self.observation), \
                patch('connect_send_rpa._click_verified_button', side_effect=TimeoutError) as click:
            with self.assertRaises(TimeoutError): self.send()
            with self.assertRaises(FileExistsError): self.send()
            click.assert_called_once()
            self.assertEqual(self.result['status'], 'unknown')

    def test_cancel_wins_without_input(self):
        (self.root / 'dispatch.decision').write_text('cancel')
        with patch('connect_send_rpa._click_verified_button') as click:
            with self.assertRaisesRegex(RuntimeError, 'キャンセル'): self.send()
            click.assert_not_called()

    def test_cancel_during_recheck_wins(self):
        def observe(*_):
            (self.root / 'dispatch.decision').write_text('cancel')
            return self.observation
        with patch('connect_send_rpa.observe', side_effect=observe), patch('connect_send_rpa._click_verified_button') as click:
            with self.assertRaisesRegex(RuntimeError, 'キャンセル'): self.send()
            click.assert_not_called()

    def test_wrong_file_or_unverified_preparation_cannot_send(self):
        for change in ({'file': 'other.gcode.3mf'}, {'sha256': 'changed'}, {'clicked': None}, {'status': 'failed'}):
            original = self.preparation.copy(); self.preparation.update(change)
            with self.assertRaises(RuntimeError): self.send()
            self.preparation = original

    def test_changed_file_or_screen_cannot_send(self):
        for mutate in ('file', 'window'):
            with self.subTest(mutate=mutate):
                fresh = copy.deepcopy(self.observation)
                if mutate == 'file': self.file.write_bytes(b'changed')
                else: fresh['window_reference']['handle'] = 2
                with patch('connect_send_rpa.observe', return_value=fresh), patch('connect_send_rpa._click_verified_button') as click:
                    with self.assertRaises(RuntimeError): self.send()
                    click.assert_not_called()
                self.file.write_bytes(b'validated calibration package')

    def test_mismatching_settings_disabled_send_saved_or_stale_observation_rejected(self):
        for change in ({'printer_label_candidates': ['3DP-999-999']}, {'spool_selection': 'unknown'},
                       {'filament_text_visible': 'PETG'}, {'option_visual_candidates': {}},
                       {'green_button_candidates': []}, {'source_kind': 'provided_image'},
                       {'observed_at': '2000-01-01T00:00:00+00:00'}, {'blocking_message_candidates': ['incompatible']}):
            with self.subTest(change=change), self.assertRaises(RuntimeError):
                plan_send({**self.observation, **change}, profile())

    def test_closed_dialog_old_job_other_printer_do_not_prove_start(self):
        for change in ({'visible_text_lines': ['success']}, {'printer_label_candidates': ['3DP-999-999']},
                       {'visible_text_lines': ['3DP-030-654', 'Preparing', 'SkeleCAD-OLD']},
                       {'source_kind': 'provided_image'}, {'stage_candidate': 'send_dialog'}):
            self.assertEqual(classify_outcome({**self.started(), **change}, self.file.name, '3DP-030-654'), 'unknown')

    def test_matching_failure_and_no_automatic_retry_when_result_is_unknown(self):
        failed = {**self.started(), 'visible_text_lines': ['3DP-030-654', 'Failed', self.file.stem]}
        self.assertEqual(classify_outcome(failed, self.file.name, '3DP-030-654'), 'failed')
        with patch('connect_send_rpa.observe', return_value=self.observation), patch('connect_send_rpa.time.sleep'), \
                patch('connect_send_rpa._click_verified_button') as click:
            self.send()
            self.assertEqual(self.result['status'], 'unknown')
            click.assert_called_once()


class PackageTests(unittest.TestCase):
    def package(self, path, change=None, model=''):
        settings = {'printer_model': 'Bambu Lab A1 mini', 'printer_settings_id': 'Bambu Lab A1 mini 0.4 nozzle',
                    'nozzle_diameter': ['0.4'], 'filament_type': ['PLA'], 'curr_bed_type': 'Textured PEI Plate'}
        settings.update(change or {})
        with zipfile.ZipFile(path, 'w') as z:
            z.writestr('Metadata/project_settings.config', json.dumps(settings))
            z.writestr('Metadata/slice_info.config', '<config><plate>' + ''.join(
                f'<metadata key="{k}" value="{v}"/>' for k, v in {'index': '1', 'outside': 'false', 'nozzle_diameters': '0.4', 'printer_model_id': model}.items()) + '</plate></config>')
            z.writestr('Metadata/plate_1.gcode', b'gcode')
            z.writestr('Metadata/plate_1.gcode.md5', hashlib.md5(b'gcode').hexdigest())
            z.writestr('3D/model.model', b'unchanged geometry')

    def test_only_two_metadata_files_change_and_source_is_untouched(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp) / 'source.3mf', Path(temp) / 'target.3mf'
            self.package(source); original = source.read_bytes()
            compatible_copy(source, target)
            self.assertEqual(source.read_bytes(), original)
            with zipfile.ZipFile(source) as a, zipfile.ZipFile(target) as b:
                changed = [name for name in a.namelist() if a.read(name) != b.read(name)]
                self.assertEqual(set(changed), {'Metadata/project_settings.config', 'Metadata/slice_info.config'})
            with self.assertRaises(FileExistsError): compatible_copy(source, target)
            with self.assertRaises(ValueError): compatible_copy(source, source)

    def test_wrong_machine_material_nozzle_and_nonempty_model_cannot_be_relabelled(self):
        with tempfile.TemporaryDirectory() as temp:
            source, target = Path(temp) / 'source.3mf', Path(temp) / 'target.3mf'
            for change in ({'printer_model': 'Bambu Lab X1 Carbon'}, {'filament_type': ['ABS']}, {'nozzle_diameter': ['0.6']},
                           {'print_compatible_printers': ['X1']}):
                self.package(source, change)
                with self.assertRaises(ValueError): compatible_copy(source, target)
            self.package(source, model='X1')
            with self.assertRaises(ValueError): compatible_copy(source, target)

    def test_unknown_profile_not_used(self):
        for change in ({'use_ams': True}, {'material': 'PETG'}, {'model': 'X1'}, {'options': {}}):
            with self.assertRaises(ValueError): validate_profile({**profile(), **change})


if __name__ == '__main__':
    unittest.main()
