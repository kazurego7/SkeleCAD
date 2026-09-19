import unittest
from datetime import datetime, timezone
from connect_dialog_cleanup import plan_cleanup

class CleanupTests(unittest.TestCase):
    def screen(self, stage='send_dialog'):
        return dict(stage_candidate=stage, source_kind='live_window_capture',
                    observed_at=datetime.now(timezone.utc).isoformat(),
                    decision_scope=dict(kind='active_dialog', title='Send to print' if stage=='send_dialog' else 'Import file', bounds=[10,10,400,400]),
                    green_button_candidates=[dict(text='Send' if stage=='send_dialog' else 'Import Gcode 3MF')],
                    cancel_button_candidates=[dict(bounds=[200,300,250,320])])
    def test_idle_dialog_cancel(self):
        for stage in ('send_dialog','import_confirmation'):
            self.assertEqual(plan_cleanup(self.screen(stage))['button'], 'Cancel')
    def test_busy_dialog_not_cancelled(self):
        screen=self.screen();screen['green_button_candidates']=[]
        self.assertEqual(plan_cleanup(screen), 'busy')
    def test_loading_spinner_is_busy_even_with_send_label(self):
        screen=self.screen();screen['send_button_loading']=True
        self.assertEqual(plan_cleanup(screen), 'busy')

    def test_normal_screen_untouched(self):
        self.assertIsNone(plan_cleanup(dict(stage_candidate='loaded_preview')))
    def test_ambiguous_cancel_and_outside_dialog_rejected(self):
        screen=self.screen();screen['cancel_button_candidates'] *= 2
        with self.assertRaises(RuntimeError): plan_cleanup(screen)
        screen=self.screen();screen['cancel_button_candidates'][0]['bounds']=[1,1,5,5]
        with self.assertRaises(RuntimeError): plan_cleanup(screen)
    def test_saved_capture_rejected(self):
        screen=self.screen();screen['source_kind']='provided_image'
        with self.assertRaises(RuntimeError): plan_cleanup(screen)

if __name__=='__main__': unittest.main()
