import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from snapshot_store import SnapshotStore, SnapshotConflict


def item(name='phone'):
    return {'schema': 1, 'id': name, 'model': 'model-a', 'joints': [{'angles': [1, 2, 3]}],
            'image': 'data:image/jpeg;base64,YQ==', 'camera': {'yaw': 2}, 'order': 0}


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = SnapshotStore(self.temp.name)

    def initialize(self):
        return self.store.write({'revision': 0, 'items': [item()]})

    def test_shared_data_survives_restart_and_deletion(self):
        self.initialize()
        other = SnapshotStore(self.temp.name)
        self.assertEqual(other.read()['items'], [item()])
        other.write({'revision': 1, 'items': []})
        self.assertEqual(self.store.read()['items'], [])
        self.assertEqual(other.read('2'), {'revision': 2, 'unchanged': True})

    def test_concurrent_edits_cannot_silently_overwrite(self):
        self.initialize()
        def change(name):
            try:
                self.store.write({'revision': 1, 'items': [item(name)]})
                return True
            except SnapshotConflict:
                return False
        with ThreadPoolExecutor(2) as pool:
            self.assertEqual(sorted(pool.map(change, ['a', 'b'])), [False, True])
        self.assertEqual(self.store.read()['revision'], 2)

    def test_invalid_updates_preserve_original(self):
        self.initialize()
        for items in [[item(), item()], [{**item(), 'image': '" onerror="alert(1)'}], [None]]:
            with self.assertRaises(ValueError):
                self.store.write({'revision': 1, 'items': items})
        self.assertEqual(self.store.read()['items'], [item()])


if __name__ == '__main__':
    unittest.main()
