"""Preparation planner tests: no desktop input or printer connection."""
from datetime import datetime, timedelta, timezone
import contextlib
import copy
import io
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from connect_prepare_rpa import plan_preparation, run


class PreparationPlanner(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 9, 12, tzinfo=timezone.utc)
        self.file = 'calibration.gcode.3mf'
        self.observation = {
            'source_kind': 'live_window_capture', 'observed_at': self.now.isoformat(),
            'stage_candidate': 'loaded_preview', 'blocking_message_candidates': [],
            'filename_line_candidates': [self.file + ' v'],
            'green_button_candidates': [{'text': 'Print', 'bounds': [600, 160, 680, 192]}],
            'window_reference': {'width': 786, 'height': 593},
        }

    def plan(self):
        result = plan_preparation(self.observation, self.file, now=self.now)
        self.assertFalse(result['can_send'])
        return result

    def test_preview_allows_only_opening_dialog(self):
        self.assertEqual(self.plan()['action'], 'open_print_dialog')
        self.assertEqual(self.plan()['button'], 'Print')

    def test_send_dialog_is_terminal_even_when_print_visible_behind_it(self):
        self.observation['stage_candidate'] = 'send_dialog'
        self.observation['green_button_candidates'].append({'text': 'Send', 'bounds': [600, 480, 680, 512]})
        self.assertEqual(self.plan()['reason'], 'send_dialog_reached')

    def test_filename_substring_and_duplicates_rejected(self):
        for names in (['other-' + self.file], [self.file + '.bak'], [self.file, self.file], []):
            with self.subTest(names=names):
                self.observation['filename_line_candidates'] = names
                self.assertEqual(self.plan()['action'], 'stop')

    def test_unknown_screen_and_error_stop(self):
        self.observation['blocking_message_candidates'] = ['Error']
        self.assertEqual(self.plan()['action'], 'stop')
        self.observation['blocking_message_candidates'] = []
        self.observation['stage_candidate'] = 'unknown'
        self.assertEqual(self.plan()['action'], 'stop')

    def test_duplicate_buttons_stop(self):
        self.observation['green_button_candidates'] *= 2
        self.assertEqual(self.plan()['action'], 'stop')

    def test_send_misclassified_as_preview_stops(self):
        self.observation['green_button_candidates'].append({'text': 'Send', 'bounds': [600, 480, 680, 512]})
        self.assertEqual(self.plan()['action'], 'stop')

    def test_old_or_saved_image_stops(self):
        self.observation['observed_at'] = (self.now - timedelta(seconds=21)).isoformat()
        self.assertEqual(self.plan()['action'], 'stop')
        self.observation['observed_at'] = self.now.isoformat()
        self.observation['source_kind'] = 'provided_image'
        self.assertEqual(self.plan()['action'], 'stop')

    def test_invalid_coordinates_stop(self):
        for bounds in ([-5, 1, 40, 32], [600, 160, 999, 192], [5, 5, 5, 32]):
            with self.subTest(bounds=bounds):
                self.observation['green_button_candidates'][0]['bounds'] = bounds
                self.assertEqual(self.plan()['action'], 'stop')

    def run_mocked(self, execute, observations):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            job = root / self.file
            job.write_bytes(b'local test artifact')
            profile = root / 'expected.json'
            profile.write_text('{}')
            args = SimpleNamespace(output=root / 'result', file=job, expected=profile, execute_open_dialog=execute)
            with patch('connect_prepare_rpa.observe', side_effect=observations), \
                 patch('connect_prepare_rpa.click_print_once') as click, \
                 patch('connect_prepare_rpa.time.sleep'), contextlib.redirect_stdout(io.StringIO()):
                run(args)
                return click.call_count

    def test_dry_run_never_calls_input(self):
        self.observation['observed_at'] = datetime.now(timezone.utc).isoformat()
        self.assertEqual(self.run_mocked(False, [self.observation]), 0)

    def test_execute_on_send_dialog_never_calls_input(self):
        self.observation['observed_at'] = datetime.now(timezone.utc).isoformat()
        self.observation['stage_candidate'] = 'send_dialog'
        self.assertEqual(self.run_mocked(True, [self.observation]), 0)

    def test_execute_clicks_only_once_then_stops_at_send(self):
        self.observation['observed_at'] = datetime.now(timezone.utc).isoformat()
        after = copy.deepcopy(self.observation)
        after['stage_candidate'] = 'send_dialog'
        after['preflight'] = {'live_observation_matches': True}
        self.assertEqual(self.run_mocked(True, [self.observation, self.observation, after]), 1)

    def test_fast_observation_waits_for_send_to_become_ready_without_another_click(self):
        self.observation['observed_at'] = datetime.now(timezone.utc).isoformat()
        loading = {**self.observation, 'stage_candidate': 'send_dialog', 'preflight': {'live_observation_matches': False}}
        ready = {**loading, 'preflight': {'live_observation_matches': True}}
        self.assertEqual(self.run_mocked(True, [self.observation, self.observation, loading, loading, ready]), 1)

    def test_changed_screen_does_not_click(self):
        self.observation['observed_at'] = datetime.now(timezone.utc).isoformat()
        changed = copy.deepcopy(self.observation)
        changed['green_button_candidates'][0]['bounds'][0] += 10
        with self.assertRaisesRegex(RuntimeError, 'Screen changed'):
            self.run_mocked(True, [self.observation, changed])


if __name__ == '__main__':
    unittest.main()
