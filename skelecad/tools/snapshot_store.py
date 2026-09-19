"""Shared snapshot collection with optimistic concurrency and atomic writes."""
import json
import os
import re
import threading
from pathlib import Path


class SnapshotConflict(ValueError):
    pass


class SnapshotStore:
    def __init__(self, root):
        self.root = Path(root) / '.snapshots'
        self.lock = threading.Lock()

    def _read(self):
        path = self.root / 'current.json'
        if not path.exists():
            return {'revision': 0, 'items': []}
        return json.loads(path.read_text(encoding='utf-8'))

    def read(self, since=None):
        with self.lock:
            value = self._read()
            if since == str(value['revision']):
                return {'revision': value['revision'], 'unchanged': True}
            return value

    def write(self, data):
        if not isinstance(data, dict) or type(data.get('revision')) is not int:
            raise ValueError('スナップショットの保存形式が不正です。')
        items = data.get('items')
        if not isinstance(items, list) or len(items) > 3000:
            raise ValueError('スナップショットの件数が不正です。')
        ids = set()
        counts = {}
        for item in items:
            if (not isinstance(item, dict) or item.get('schema') != 1
                    or not isinstance(item.get('id'), str) or not item['id']
                    or not isinstance(item.get('model'), str) or not item['model']
                    or not isinstance(item.get('joints'), list)):
                raise ValueError('スナップショットの内容が不正です。')
            key = (item['model'], item['id'])
            if key in ids:
                raise ValueError('スナップショットが重複しています。')
            ids.add(key)
            counts[item['model']] = counts.get(item['model'], 0) + 1
            if counts[item['model']] > 30:
                raise ValueError('モデルごとの上限は30件です。')
            image = item.get('image')
            if image and (not isinstance(image, str) or not re.fullmatch(r'data:image/(?:jpeg|png|webp);base64,[A-Za-z0-9+/=\r\n]+', image)):
                raise ValueError('プレビュー画像の形式が不正です。')
        with self.lock:
            current = self._read()
            if data['revision'] != current['revision']:
                raise SnapshotConflict('別の端末で更新されています。最新の一覧を確認して操作し直してください。')
            value = {'revision': current['revision'] + 1, 'items': items}
            encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
            self.root.mkdir(parents=True, exist_ok=True)
            pending = self.root / 'current.tmp'
            with pending.open('w', encoding='utf-8') as stream:
                stream.write(encoded)
                stream.flush()
                os.fsync(stream.fileno())
            pending.replace(self.root / 'current.json')
            return value
