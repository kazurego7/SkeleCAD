"""One local OCR process per print run. It accepts read-only image requests only."""
import atexit
import json
from pathlib import Path
from queue import Queue, Empty
import subprocess
import threading


class OcrWorker:
    def __init__(self):
        self.replies = Queue()
        self.lock = threading.Lock()
        self.process = subprocess.Popen(
            ['powershell.exe', '-NoProfile', '-File', str(Path(__file__).with_name('read_connect_screen.ps1')), '-Worker'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        def read():
            for line in self.process.stdout:
                self.replies.put(line)
            self.replies.put(None)
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def request(self, image, output, scale, capture_only=False):
        with self.lock:
            if self.process.poll() is not None:
                raise RuntimeError('Windows OCR worker stopped.')
            self.process.stdin.write(json.dumps({'image': str(image) if image else None,
                                                 'output': str(output), 'scale': scale, 'capture_only': capture_only}) + '\n')
            self.process.stdin.flush()
            try:
                line = self.replies.get(timeout=40)
                if not line:
                    raise RuntimeError('Windows OCR worker closed without a result.')
                result = json.loads(line)
            except (Empty, ValueError, RuntimeError):
                self.close()  # Never accept a late response for a later request.
                raise RuntimeError('Windows OCR worker did not return a valid result.')
            if result.get('ok') is not True:
                raise RuntimeError(result.get('error', 'Windows OCR failed.'))
            return json.loads((output / 'ocr.json').read_text(encoding='utf-8-sig'))

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=1)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=2)
        self.reader.join(timeout=1)
        self.process.stdout.close()


_worker = None


def run_ocr(image, output, scale=2, capture_only=False):
    global _worker
    if _worker is None:
        _worker = OcrWorker()
        atexit.register(_worker.close)
    return _worker.request(image, output, scale, capture_only)
