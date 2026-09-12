"""Separate remote slicing and one-shot dispatch; local print/open is unchanged."""
import hashlib
import json
import shutil
import subprocess
import threading
import uuid
from pathlib import Path

from workflow_store import JOB_ID, now, write_json
from bambu_lan import Printer, upload, require_idle
from connect_print import configuration, identity, compatible_copy, PROJECT


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RemotePrint:
    def __init__(self, store):
        self.store = store
        self.root = store.root / '.remote-print'
        self.root.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.sending = False
        for saved in self.root.glob('*/state.json'):
            record = json.loads(saved.read_text(encoding='utf-8'))
            if record.get('stage') in ('preparing', 'sending'):
                uncertain = record['stage'] == 'sending'
                record.update(stage='unknown' if uncertain else 'failed', message='処理が中断されました。プリンター本体を確認してください。' if uncertain else '準備が中断されました。もう一度準備してください。')
                write_json(saved, record)

    def path(self, ticket):
        if not isinstance(ticket, str) or not JOB_ID.fullmatch(ticket):
            raise ValueError('印刷の確認情報が不正です。')
        return self.root / ticket

    def read(self, ticket, job_id):
        data = json.loads((self.path(ticket) / 'state.json').read_text(encoding='utf-8'))
        if data['job_id'] != job_id:
            raise ValueError('別モデルの印刷情報です。')
        return data

    def public(self, data):
        return {k: data[k] for k in ('ticket', 'job_id', 'stage', 'message', 'plates', 'printer', 'filament') if k in data}

    def update(self, folder, **fields):
        with self.lock:
            data = json.loads((folder / 'state.json').read_text(encoding='utf-8'))
            data.update(updated_at=now(), **fields)
            write_json(folder / 'state.json', data)
            return data

    def check_current(self, data):
        state = self.store.read(data['job_id'])
        if state.get('manifest_sha256') != data['manifest_sha256'] or state.get('mechanical_revision') != data['revision']:
            raise ValueError('モデルが更新されました。印刷データを準備し直してください。')
        if state['stage'] not in ('mechanical_review', 'print_ready', 'print_failed'):
            raise ValueError('モデルを処理中です。完了後にやり直してください。')
        folder = self.store.directory(data['job_id']) / 'machining' / data['revision']
        if digest(folder / 'manifest.json') != data['manifest_sha256']:
            raise ValueError('モデルが更新されました。')
        manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
        for part in manifest['parts']:
            if Path(part['filename']).name != part['filename'] or digest(folder / part['filename']) != part['sha256']:
                raise ValueError('部品データが変更されています。')
        return folder, manifest

    def prepare(self, job_id, data):
        cfg = configuration()
        from print_cache import cache_context
        print_context = cache_context([])
        review = data.get('review', {})
        if not isinstance(review, dict) or review.get('ready') is not True or review.get('collision') != 'clear' or not isinstance(review.get('pose'), dict):
            raise ValueError('可動域で衝突確認が完了してから、プリント開始を押してください。')
        with self.store.lock, self.lock:
            state = self.store.read(job_id)
            revision = state.get('mechanical_revision', '')
            if not JOB_ID.fullmatch(revision):
                raise ValueError('加工済みモデルが必要です。')
            ticket = uuid.uuid4().hex
            record = {'ticket': ticket, 'job_id': job_id, 'revision': revision,
                'manifest_sha256': data.get('manifest_sha256'), 'pose': review['pose'],
                'print_context': print_context,
                'printer_identity': identity(cfg), 'printer': cfg.get('name', 'A1 mini'),
                'filament': 'Bambu PLA Matte / ' + ('AMS Lite スロット' + str(cfg['ams_slot'] + 1) if cfg['use_ams'] else '外部スプール'),
                'stage': 'preparing', 'message': '印刷データを準備しています…', 'created_at': now()}
            self.check_current(record)
            # Repeated preparation clicks reuse the pending result; no slicing storm.
            for saved in self.root.glob('*/state.json'):
                prior = json.loads(saved.read_text(encoding='utf-8'))
                if prior.get('stage') in ('preparing', 'ready') and all(prior.get(k) == record[k] for k in
                        ('job_id', 'revision', 'manifest_sha256', 'pose', 'printer_identity', 'print_context')):
                    return self.public(prior)
                if prior.get('stage') == 'preparing':
                    raise ValueError('別の印刷データを準備中です。完了後にやり直してください。')
            folder = self.path(ticket)
            folder.mkdir()
            write_json(folder / 'state.json', record)
            threading.Thread(target=self._prepare, args=(folder, record), daemon=True).start()
            return self.public(record)

    def _prepare(self, folder, record):
        try:
            from audit_workflow_motion import verify_review_pose
            from prepare_workflow_project import run as prepare_project
            from print_package_audit import sliced_audit
            from runtime_paths import tool_config
            from print_cache import cache_context
            context = cache_context([])
            with self.store.lock:
                original, manifest = self.check_current(record)
                snapshot = folder / 'model'
                snapshot.mkdir()
                for name in ['manifest.json', *[p['filename'] for p in manifest['parts']]]:
                    shutil.copy2(original / name, snapshot / name)
                # Pose verification also needs the joint socket/ball clearance solids.
                # They are generated alongside the parts, not embedded in the manifest.
                shutil.copytree(original / 'tools', snapshot / 'tools')
                write_json(snapshot / 'review_approval.json', {'accepted': True,
                    'manifest_sha256': record['manifest_sha256'], 'pose': record['pose']})
            verify_review_pose(snapshot, record['pose'])
            project = prepare_project(snapshot)
            executable = tool_config()['bambu_studio']['executable']
            plates = []
            for plate in project['plates']:
                if self.read(record['ticket'], record['job_id'])['stage'] == 'cancelled':
                    return
                number = plate['plate']
                output = snapshot / 'print' / f'plate_{number:02d}'
                filename = f'SkeleCAD_plate_{number:02d}.gcode.3mf'
                self.update(folder, message=f'プレート{number}の印刷経路を計算しています…')
                with (output / 'slice.log').open('wb') as log:
                    result = subprocess.run([executable, '--slice', '1', '--arrange', '0', '--orient', '0',
                        '--outputdir', str(output), '--export-3mf', filename, str(output / plate['filename'])],
                        stdout=log, stderr=subprocess.STDOUT, timeout=1200,
                        creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if result.returncode:
                    raise ValueError('スライスに失敗しました。印刷データを確認してください。')
                target = output / filename
                audit = sliced_audit(target)
                if len(audit['plates']) != 1 or audit['plates'][0]['plate'] != 1:
                    raise ValueError('印刷プレートを確認できません。')
                detail = audit['plates'][0]
                cfg = configuration()
                warnings = detail['warnings']
                if cfg.get('transport') == 'bambu_connect':
                    warnings = [w for w in warnings if w.get('msg') != 'not_support_traditional_timelapse']
                    # Check that the generated profile really matches Connect before approval.
                    compatible_copy(target, output / 'connect-profile-check.gcode.3mf')
                if warnings or not detail['preview_bbox_within_bed']:
                    raise ValueError('スライス結果に警告があります。ローカルで確認してください。')
                plates.append({'plate': number, 'sha256': digest(target), 'seconds': detail['seconds'], 'grams': detail['grams']})
            with self.store.lock:
                self.check_current(record)
            if not plates:
                raise ValueError('印刷するプレートがありません。')
            if cache_context([]) != context:
                raise ValueError('印刷設定が変わりました。準備し直してください。')
            with self.lock:
                if self.read(record['ticket'], record['job_id'])['stage'] != 'cancelled':
                    self.update(folder, stage='ready', message='印刷内容を確認してください。', plates=plates, print_context=context)
        except Exception as exc:
            with self.lock:
                if self.read(record['ticket'], record['job_id'])['stage'] != 'cancelled':
                    self.update(folder, stage='failed', message=str(exc) if isinstance(exc, ValueError) else '印刷データの準備に失敗しました。接続先PCを確認してください。')

    def status(self, job_id, ticket):
        with self.lock:
            return self.public(self.read(ticket, job_id))

    def start(self, job_id, data):
        with self.store.lock, self.lock:
            record = self.read(data.get('ticket'), job_id)
            if data.get('accepted') is not True or data.get('bed_clear') is not True:
                raise ValueError('印刷内容とプレートが空であることを確認してください。')
            if record['stage'] in ('sending', 'started', 'unknown'):
                return self.public(record)  # Same ticket is never sent twice.
            if record['stage'] != 'ready' or self.sending:
                raise ValueError('印刷を送信できる状態ではありません。')
            self.check_current(record)
            from print_cache import cache_context
            if record.get('print_context') != cache_context([]):
                raise ValueError('印刷設定が変わりました。準備し直してください。')
            cfg = configuration()
            if identity(cfg) != record['printer_identity']:
                raise ValueError('印刷先の設定が変わりました。準備し直してください。')
            plate = next((p for p in record['plates'] if type(data.get('plate')) is int and p['plate'] == data['plate']), None)
            if plate is None:
                raise ValueError('印刷するプレートを選んでください。')
            folder = self.path(record['ticket'])
            path = folder / 'model/print' / f'plate_{plate["plate"]:02d}' / f'SkeleCAD_plate_{plate["plate"]:02d}.gcode.3mf'
            if digest(path) != plate['sha256']:
                raise ValueError('印刷データが変更されています。')
            # Persist before any network write, including a crash or lost HTTP reply.
            record = self.update(folder, stage='sending', message='プリンターへ送信しています…', selected_plate=plate['plate'])
            self.sending = True
            threading.Thread(target=self._start, args=(folder, record, cfg, path), daemon=True).start()
            return self.public(record)

    def _start(self, folder, record, cfg, path):
        command_possible = False
        try:
            if cfg.get('transport') == 'bambu_connect':
                self._start_connect(folder, record, cfg, path)
                return
            with Printer(cfg) as printer:
                require_idle(printer.report)
            name = 'skelecad_' + record['ticket'] + '.gcode.3mf'
            upload(cfg, path, name)
            with self.store.lock, Printer(cfg) as printer:
                self.check_current(record)
                require_idle(printer.report)
                command_possible = True
                printer.start(name)
            self.update(folder, stage='started', message='プリンターが印刷を開始しました。')
        except Exception:
            self.update(folder, stage='unknown' if command_possible else 'failed',
                message='開始結果を確認できません。再送せず、プリンター本体を確認してください。' if command_possible else 'プリンターへ送信できませんでした。接続・待機状態・SDカードを確認してください。')
        finally:
            with self.lock:
                self.sending = False

    def _start_connect(self, folder, record, cfg, path):
        output = folder / 'connect'
        output.mkdir(exist_ok=True)
        expected = folder / 'connect-profile.json'
        write_json(expected, cfg)
        self.update(folder, message='PCで印刷を準備しています。Connectの操作が終わるまでPCの操作をお待ちください。')
        args = [str(PROJECT / '.runtime/connect-rpa-venv/Scripts/python.exe'), '-X', 'utf8',
                str(PROJECT / 'tools/connect_send_rpa.py'), '--file', str(path),
                '--expected', str(expected), '--output', str(output), '--execute-print']
        try:
            with (folder / 'connect.log').open('wb') as log:
                subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, timeout=360,
                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            result = json.loads((output / 'result.json').read_text(encoding='utf-8'))
            stage = result.get('status')
            if stage not in ('started', 'failed', 'cancelled', 'unknown'):
                stage = 'unknown'
            self.update(folder, stage=stage, message=result.get('message', '開始結果をBambu Handyで確認してください。'))
        except Exception:
            decision = output / 'dispatch.decision'
            possible = decision.exists() and decision.read_text(encoding='utf-8') != 'cancel'
            self.update(folder, stage='unknown' if possible else 'failed',
                        message='開始結果が不明です。Bambu Handyまたはプリンター本体を確認してください。' if possible else 'Connectでの準備が停止しました。PCの画面を確認してください。')

    def cancel(self, job_id, data):
        with self.lock:
            record = self.read(data.get('ticket'), job_id)
            folder = self.path(record['ticket'])
            if record['stage'] in ('preparing', 'ready'):
                return self.public(self.update(folder, stage='cancelled', message='印刷の準備をキャンセルしました。'))
            if record['stage'] == 'sending':
                if configuration().get('transport') != 'bambu_connect':
                    raise ValueError('送信処理中です。停止はBambu Handyまたは本体から操作してください。')
                output = folder / 'connect'
                output.mkdir(exist_ok=True)
                try:
                    with (output / 'dispatch.decision').open('x', encoding='utf-8') as decision:
                        decision.write('cancel')
                except FileExistsError:
                    if (output / 'dispatch.decision').read_text(encoding='utf-8') != 'cancel':
                        raise ValueError('Sendの処理に入りました。停止はBambu Handyまたは本体から操作してください。')
                return self.public(self.update(folder, message='送信をキャンセルしています…'))
            if record['stage'] in ('started', 'unknown'):
                raise ValueError('停止はBambu Handyまたはプリンター本体から操作してください。')
            return self.public(record)
