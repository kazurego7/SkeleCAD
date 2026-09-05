"""Atomic snapshots survive Windows readers without hiding permanent I/O errors."""
import ctypes
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_store import write_json


class JsonPublicationTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.path = Path(self.root.name) / 'result.json'
        write_json(self.path, {'stage': 'old'})

    def test_transient_windows_denial_preserves_old_snapshot_until_commit(self):
        original = os.replace
        calls = []
        def replace(source, target):
            calls.append(1)
            self.assertEqual(json.loads(target.read_text()), {'stage': 'old'})
            if len(calls) < 3:
                error = PermissionError('busy'); error.winerror = 5
                raise error
            original(source, target)
        with patch('workflow_store.os.replace', side_effect=replace), patch('workflow_store.time.sleep'):
            write_json(self.path, {'stage': 'new'})
        self.assertEqual(json.loads(self.path.read_text()), {'stage': 'new'})
        self.assertEqual(len(calls), 3)
        self.assertFalse(list(self.path.parent.glob('*.tmp')))

    def test_persistent_denial_is_bounded_and_does_not_destroy_old_result(self):
        error = PermissionError('denied'); error.winerror = 5
        with patch('workflow_store.os.replace', side_effect=error) as replace, patch('workflow_store.time.sleep'):
            with self.assertRaises(PermissionError):write_json(self.path, {'stage': 'new'})
        self.assertEqual(replace.call_count, 21)
        self.assertEqual(json.loads(self.path.read_text()), {'stage': 'old'})
        self.assertFalse(list(self.path.parent.glob('*.tmp')))

    def test_unrelated_io_failure_is_not_retried(self):
        with patch('workflow_store.os.replace', side_effect=OSError('disk full')) as replace:
            with self.assertRaises(OSError):write_json(self.path, {'stage': 'new'})
        self.assertEqual(replace.call_count, 1)
        self.assertFalse(list(self.path.parent.glob('*.tmp')))

    @unittest.skipUnless(os.name == 'nt', 'Windows file sharing semantics')
    def test_real_windows_read_handle_without_delete_sharing(self):
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateFileW.argtypes = [wintypes.LPCWSTR,wintypes.DWORD,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD,wintypes.DWORD,wintypes.HANDLE]
        kernel.CreateFileW.restype = wintypes.HANDLE
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.CreateFileW(str(self.path),0x80000000,1|2,None,3,0,None)
        self.assertNotEqual(handle, ctypes.c_void_p(-1).value)
        # Hold a real reader across the first rename attempts, then release it.
        timer = threading.Timer(.08, lambda: kernel.CloseHandle(handle))
        timer.start()
        try:write_json(self.path, {'stage': 'new'})
        finally:timer.join()
        self.assertEqual(json.loads(self.path.read_text()), {'stage': 'new'})


if __name__ == '__main__':unittest.main()
