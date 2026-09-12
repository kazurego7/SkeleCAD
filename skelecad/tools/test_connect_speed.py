"""Optimized image components and fresh-capture reuse, without GUI input."""
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch, Mock
from queue import Empty

from PIL import Image, ImageDraw
import analyze_connect_screen as vision
from connect_ocr_worker import OcrWorker


class ComponentTests(unittest.TestCase):
    def test_span_scan_matches_independent_pixel_flood(self):
        randomizer = random.Random(47)
        for probability in (.05, .3, .7, 1):
            for _ in range(12):
                width, height = 27, 19
                mask = bytearray(255 if randomizer.random() < probability else 0 for _ in range(width * height))
                remaining = {i for i, value in enumerate(mask) if value}
                while remaining:
                    first = min(remaining)
                    pending, component = [first], set()
                    while pending:
                        point = pending.pop()
                        if point not in remaining:
                            continue
                        remaining.remove(point); component.add(point)
                        x, y = point % width, point // width
                        pending.extend(ny * width + nx for nx, ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1))
                                       if 0 <= nx < width and 0 <= ny < height)
                    box, count = vision.take_component(mask, width, first)
                    self.assertEqual(count, len(component))
                    self.assertEqual(box, (min(p % width for p in component), min(p // width for p in component),
                                           max(p % width for p in component)+1, max(p // width for p in component)+1))
                    self.assertFalse(any(mask[p] for p in component))

    def test_color_thresholds_and_separate_buttons(self):
        image = Image.new('RGB', (200, 150))
        draw = ImageDraw.Draw(image)
        draw.rectangle((10, 20, 60, 50), fill=(20, 160, 60))
        draw.rectangle((80, 70, 180, 105), fill=(0, 175, 80))
        draw.rectangle((0, 120, 180, 145), fill=(65, 110, 85))  # exactly at the excluded limits
        self.assertEqual(vision.button_regions(image), [(10,20,61,51),(80,70,181,106)])


class FreshReuseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.image = self.root / 'frame.png'
        Image.new('RGB', (200, 100), '#777777').save(self.image)
        self.report = {'image': str(self.image), 'window_title': 'Connect',
                       'window_reference': {'handle': 2, 'process_id': 3, 'width': 200, 'height': 100},
                       'captured_at': datetime.now(timezone.utc).isoformat(), 'lines': []}
        self.calls = []
        def ocr(image, output, scale=2, capture_only=False):
            self.calls.append(capture_only)
            return copy.deepcopy(self.report)
        self.patch = patch.object(vision, 'run_ocr', side_effect=ocr)
        self.patch.start()
        vision._scene_cache = None

    def tearDown(self):
        self.patch.stop(); vision._scene_cache = None; self.temp.cleanup()

    def inspect(self, name):
        return vision.inspect_screen(self.root / name)

    def test_unchanged_pixels_require_a_new_capture_but_skip_repeated_ocr(self):
        first = self.inspect('one')
        self.report['captured_at'] = datetime.now(timezone.utc).isoformat()
        second = self.inspect('two')
        self.assertEqual(self.calls, [True, False, True])
        self.assertFalse(first['recognition_reused_for_identical_pixels'])
        self.assertTrue(second['recognition_reused_for_identical_pixels'])
        self.assertEqual(second['observed_at'], self.report['captured_at'])
        self.assertFalse(second['can_send'])

    def test_a_single_changed_pixel_forces_new_recognition(self):
        self.inspect('one')
        with Image.open(self.image) as image:
            image.putpixel((10,10), (119,119,120)); image.save(self.image)
        self.assertFalse(self.inspect('two')['recognition_reused_for_identical_pixels'])
        self.assertEqual(self.calls, [True, False, True, False])

    def test_window_identity_and_saved_capture_never_reuse_live_evidence(self):
        self.inspect('one')
        self.report['window_reference']['handle'] = 4
        self.assertFalse(self.inspect('two')['recognition_reused_for_identical_pixels'])
        self.report['window_reference'] = None; self.report['window_title'] = None
        saved = self.inspect('three')
        self.assertFalse(saved['recognition_reused_for_identical_pixels'])
        self.assertEqual(saved['source_kind'], 'provided_image')

    def test_failed_capture_does_not_return_cached_result(self):
        self.inspect('one')
        vision.run_ocr.side_effect = RuntimeError('window unavailable')
        with self.assertRaisesRegex(RuntimeError, 'unavailable'):
            self.inspect('two')
        self.assertFalse((self.root / 'two/analysis.json').exists())


class WorkerProtocolTests(unittest.TestCase):
    def worker(self, reply):
        worker = OcrWorker.__new__(OcrWorker)
        worker.lock = threading.Lock()
        worker.process = SimpleNamespace(poll=lambda: None, stdin=Mock())
        worker.replies = Mock(); worker.replies.get.return_value = reply
        worker.close = Mock()
        return worker

    def test_timeout_or_malformed_reply_closes_worker_so_late_results_cannot_be_used(self):
        for reply in ('not json', None):
            worker = self.worker(reply)
            with self.assertRaises(RuntimeError):
                worker.request(None, Path('unused'), 2)
            worker.close.assert_called_once()
        worker = self.worker('')
        worker.replies.get.side_effect = Empty
        with self.assertRaises(RuntimeError): worker.request(None, Path('unused'), 2)
        worker.close.assert_called_once()

    def test_error_reply_never_reads_a_previous_output_file(self):
        worker = self.worker(json.dumps({'ok': False, 'error': 'capture failed'}))
        with patch.object(Path, 'read_text') as read:
            with self.assertRaisesRegex(RuntimeError, 'capture failed'):
                worker.request(None, Path('unused'), 2)
            read.assert_not_called()


if __name__ == '__main__': unittest.main()
