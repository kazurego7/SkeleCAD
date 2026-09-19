"""Foreground preparation regression tests. No desktop input."""
import unittest
from unittest.mock import Mock, patch
from connect_prepare_rpa import ensure_preparation_foreground

class ForegroundTests(unittest.TestCase):
    def test_already_foreground(self):
        window, user32 = Mock(), Mock()
        user32.GetForegroundWindow.return_value = 12
        ensure_preparation_foreground(window, user32, 12, 'import_confirmation')
        window.set_focus.assert_not_called()

    def test_preparation_activates_once(self):
        for stage in ('import_confirmation', 'loaded_preview'):
            window, user32 = Mock(), Mock()
            user32.GetForegroundWindow.side_effect = [99, 12]
            ensure_preparation_foreground(window, user32, 12, stage)
            window.set_focus.assert_called_once()

    @patch('connect_prepare_rpa.time.sleep')
    def test_failed_activation_stops(self, sleep):
        window, user32 = Mock(), Mock()
        user32.GetForegroundWindow.return_value = 99
        with self.assertRaises(RuntimeError):
            ensure_preparation_foreground(window, user32, 12, 'import_confirmation')
        window.set_focus.assert_called_once()

    def test_send_is_not_automatically_activated(self):
        window, user32 = Mock(), Mock()
        user32.GetForegroundWindow.return_value = 99
        with self.assertRaises(RuntimeError):
            ensure_preparation_foreground(window, user32, 12, 'send_dialog')
        window.set_focus.assert_not_called()

if __name__ == '__main__':
    unittest.main()
