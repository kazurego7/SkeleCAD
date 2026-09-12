"""Fail-closed diagnostic checks; no Windows UI or printer access."""
import copy
from datetime import datetime, timedelta, timezone
import unittest
from PIL import Image, ImageDraw

from analyze_connect_screen import evaluate_visible_fields, resolve_button_text, scope_active_dialog


class DialogScopeChecks(unittest.TestCase):
    def setUp(self):
        self.image = Image.new('RGB', (600, 400), '#777777')
        ImageDraw.Draw(self.image).rectangle((100, 100, 500, 300), fill='white')
        def line(text, x, y):
            return {'text': text, 'words': [{'text': text, 'x': x, 'y': y, 'width': 60, 'height': 14}]}
        self.report = {'lines': [line('Import file', 120, 120), line('You will import the file', 120, 160),
                                 line('Failed', 10, 30), line('Import error', 120, 190)]}

    def test_background_error_excluded_but_dialog_error_retained(self):
        report, _, scope = scope_active_dialog(self.report, self.image, [])
        labels = [line['text'] for line in report['lines']]
        self.assertNotIn('Failed', labels)
        self.assertIn('Import error', labels)
        self.assertEqual(scope['excluded_background_messages'], ['Failed'])

    def test_background_buttons_excluded(self):
        buttons = [{'text': 'Print', 'bounds': [10, 30, 70, 60]},
                   {'text': 'Import Gcode 3MF', 'bounds': [300, 240, 470, 270]}]
        _, included, _ = scope_active_dialog(self.report, self.image, buttons)
        self.assertEqual(included, [buttons[1]])

    def test_unidentifiable_dialog_stops(self):
        with self.assertRaisesRegex(RuntimeError, 'Cannot uniquely locate'):
            scope_active_dialog(self.report, Image.new('RGB', (600, 400), '#777777'), [])

    def test_nonmodal_screen_keeps_errors(self):
        self.report['lines'] = [self.report['lines'][2]]
        report, _, scope = scope_active_dialog(self.report, self.image, [])
        self.assertEqual(report['lines'][0]['text'], 'Failed')
        self.assertEqual(scope['kind'], 'full_window')


class ButtonTextChecks(unittest.TestCase):
    def report(self, label='Import Gcode 3MF', x=110):
        return {'lines': [{'text': label, 'words': [{'text': label, 'x': x, 'y': 210, 'width': 130, 'height': 14}]}]}

    def test_full_image_corrects_crop_only_with_exact_same_region(self):
        result = resolve_button_text(self.report(), [100, 200, 250, 232], 'Import Gcode SMF')
        self.assertEqual(result['text'], 'Import Gcode 3MF')

    def test_text_elsewhere_cannot_supply_button_label(self):
        result = resolve_button_text(self.report(x=400), [100, 200, 250, 232], 'Import Gcode SMF')
        self.assertEqual(result['text'], 'Import Gcode SMF')

    def test_no_global_S_to_3_substitution(self):
        result = resolve_button_text({'lines': []}, [100, 200, 250, 232], 'Import Gcode SMF')
        self.assertNotEqual(result['text'], 'Import Gcode 3MF')

    def test_conflicting_known_labels_are_rejected(self):
        result = resolve_button_text(self.report('Send'), [100, 200, 250, 232], 'Print')
        self.assertEqual(result['text'], '')

    def test_cropped_Send_still_works_when_full_image_misses_it(self):
        result = resolve_button_text({'lines': []}, [100, 200, 250, 232], 'Send')
        self.assertEqual(result['text'], 'Send')


class VisibleFieldChecks(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 12, tzinfo=timezone.utc)
        self.expected = {'printer_label': 'test-printer', 'material': 'PLA', 'spool': 'external',
                         'options': {'Timelapse': 'Off', 'Bed leveling': 'On', 'Flow dynamic calibration': 'On'}}
        self.summary = {
            'stage_candidate': 'send_dialog', 'printer_label_candidates': ['test-printer'],
            'filament_text_visible': 'PLA', 'spool_selection': 'external',
            'option_visual_candidates': copy.deepcopy(self.expected['options']),
            'blocking_message_candidates': [], 'green_button_candidates': [{'text': 'Send'}],
            'source_kind': 'live_window_capture', 'observed_at': self.now.isoformat(),
        }

    def check(self):
        result = evaluate_visible_fields(self.summary, self.expected, now=self.now)
        self.assertFalse(result['can_send'])
        return result

    def test_matching_screen_still_cannot_authorize_print(self):
        result = self.check()
        self.assertTrue(result['live_observation_matches'])
        self.assertIn('job_identity', result['unverified'])

    def test_saved_image_never_counts_as_live(self):
        self.summary['source_kind'] = 'provided_image'
        result = self.check()
        self.assertTrue(result['visible_fields_match'])
        self.assertFalse(result['live_observation_matches'])

    def test_expired_future_and_invalid_times_stop(self):
        for stamp in ((self.now - timedelta(seconds=46)).isoformat(),
                      (self.now + timedelta(seconds=1)).isoformat(), 'invalid', '2026-09-12'):
            with self.subTest(stamp=stamp):
                self.summary['observed_at'] = stamp
                self.assertFalse(self.check()['live_observation_matches'])

    def test_wrong_or_multiple_printers_stop(self):
        for labels in ([], ['other-printer'], ['test-printer', 'other-printer']):
            with self.subTest(labels=labels):
                self.summary['printer_label_candidates'] = labels
                self.assertFalse(self.check()['visible_fields_match'])

    def test_missing_or_duplicate_send_stops(self):
        for buttons in ([], [{'text': 'Send'}, {'text': 'Send'}], [{'text': 'Sending'}]):
            with self.subTest(buttons=buttons):
                self.summary['green_button_candidates'] = buttons
                self.assertFalse(self.check()['visible_fields_match'])

    def test_unknown_spool_and_material_mismatch_stop(self):
        self.summary['spool_selection'] = 'unknown'
        self.assertFalse(self.check()['visible_fields_match'])
        self.summary['spool_selection'] = 'external'
        self.summary['filament_text_visible'] = 'PETG'
        self.assertFalse(self.check()['visible_fields_match'])

    def test_wrong_or_unreadable_options_stop(self):
        for label in self.expected['options']:
            with self.subTest(label=label):
                self.summary['option_visual_candidates'] = copy.deepcopy(self.expected['options'])
                self.summary['option_visual_candidates'][label] = 'unknown'
                self.assertFalse(self.check()['visible_fields_match'])

    def test_error_stops_even_with_green_send(self):
        self.summary['blocking_message_candidates'] = ['Printer incompatible']
        self.assertFalse(self.check()['visible_fields_match'])

    def test_other_screen_stops(self):
        self.summary['stage_candidate'] = 'import_page'
        self.assertFalse(self.check()['visible_fields_match'])

    def test_incomplete_profile_is_rejected(self):
        self.expected['options'].pop('Timelapse')
        with self.assertRaises(ValueError):
            self.check()


if __name__ == '__main__':
    unittest.main()
