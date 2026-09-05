"""Per-image local jobs. Inputs, manifests and exports never share production paths."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import subprocess
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from workflow_joint_rules import minimum_joint_spacing,spacing_conflicts
from runtime_paths import python_path

PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parent
JOB_ID = re.compile(r'^[0-9a-f]{32}$')
ACTIVE = {'starting', 'preparing', 'generating', 'analysing', 'symmetrizing', 'partitioning', 'machining', 'printing'}
GENERATION_STAGES = {'queued', 'starting', 'preparing', 'generating', 'analysing'}
PUBLIC = ('id', 'name', 'stage', 'message', 'created_at', 'updated_at',
          'source_sha256', 'target_length_mm', 'manifest', 'manifest_sha256', 'preview_part_count', 'error', 'partition_revision', 'mechanical_revision', 'prints',
          'failed_marker_locations', 'appearance_symmetry', 'trashed_at')


def now():
    return datetime.now(timezone.utc).isoformat()


def write_json(path, value):
    """Readers see an old or new complete snapshot, never a partial JSON file."""
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        for attempt in range(21):
            try:
                os.replace(temporary, path)
                return
            except OSError as error:
                # Windows readers (or scanners) can briefly deny rename/delete sharing.
                # Keep the old complete snapshot and retry only that atomic replacement.
                if getattr(error, 'winerror', None) not in (5, 32, 33) or attempt == 20:
                    raise
                time.sleep(min(.01 * 2 ** attempt, .1))
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass  # Do not hide the original write error if a scanner also holds the temp file.


def find_bambu_studio():
    candidates=[]
    for root in (os.environ.get('ProgramFiles'),os.environ.get('LOCALAPPDATA')):
        if root:
            base=Path(root)
            candidates.extend((base/'Bambu Studio'/'bambu-studio.exe',base/'Programs'/'Bambu Studio'/'bambu-studio.exe'))
    for candidate in candidates:
        if candidate.is_file():return candidate
    raise ValueError('Bambu Studioが見つかりません。先にBambu Studioをインストールしてください。')


def process_identity(pid):
    """Creation time prevents a recycled Windows PID from appearing to be our worker."""
    if os.name == 'nt':
        import ctypes
        from ctypes import wintypes
        api = ctypes.WinDLL('kernel32', use_last_error=True)
        api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        api.OpenProcess.restype = wintypes.HANDLE
        api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        api.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = api.OpenProcess(0x1000, False, int(pid))
        if not handle:
            return None
        try:
            values = [wintypes.FILETIME() for _ in range(4)]
            if not api.GetProcessTimes(handle, *(ctypes.byref(v) for v in values)):
                return None
            created = values[0]
            # GetProcessTimes succeeds for an exited, unreaped handle too.
            if values[1].dwLowDateTime or values[1].dwHighDateTime:
                return None
            return str((created.dwHighDateTime << 32) | created.dwLowDateTime)
        finally:
            api.CloseHandle(handle)
    try:
        return Path(f'/proc/{pid}/stat').read_text().split()[21]
    except (OSError, IndexError):
        return None


class WorkflowStore:
    def __init__(self, root=None, launch=True):
        self.root = Path(root or PROJECT / 'build/workflows').resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.trash_root = (self.root / '.trash').resolve()
        self.trash_root.mkdir(parents=True, exist_ok=True)
        self.owner = None
        if launch:
            self.owner = (self.root / '.server.lock').open('a+b')
            try:
                if os.name == 'nt':
                    import msvcrt
                    self.owner.seek(0)
                    if not self.owner.read(1):
                        self.owner.write(b'0'); self.owner.flush()
                    self.owner.seek(0)
                    msvcrt.locking(self.owner.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(self.owner.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                self.owner.close()
                raise RuntimeError('Another image workflow server already owns this job directory')
        self.lock = threading.RLock()
        self.children = {}
        self.launch = launch
        self.stopping = threading.Event()
        from workflow_background import BackgroundWork
        self.background = BackgroundWork(self)
        if launch:
            self._recover_legacy_partition_failures()
            self.thread = threading.Thread(target=self._pump, daemon=True)
            self.thread.start()
            self.background.start()

    def _recover_legacy_partition_failures(self):
        legacy_message='生成処理が終了しましたが、結果を確認できません。'
        for directory in self.root.iterdir():
            if not JOB_ID.fullmatch(directory.name):continue
            try:state=json.loads((directory/'state.json').read_text(encoding='utf-8'))
            except (OSError,ValueError,TypeError):continue
            if (state.get('stage')=='failed' and state.get('operation')=='partition' and state.get('message')==legacy_message
                    and isinstance(state.get('selected_markers'),list) and state.get('source_manifest_sha256')):
                state.update(stage='queued',message='旧バージョンで中断した色分けを、同じマーカーで自動復旧します。',worker_attempt=0,updated_at=now())
                for key in ('pid','process_identity','error'):state.pop(key,None)
                write_json(directory/'state.json',state)

    def directory(self, job_id):
        if not JOB_ID.fullmatch(job_id):
            raise KeyError('Invalid job id')
        path = self.root / job_id
        if path.resolve() != path or not path.is_dir():
            raise KeyError('Unknown job')
        return path

    def read(self, job_id):
        return json.loads((self.directory(job_id) / 'state.json').read_text(encoding='utf-8'))

    def public(self, job_id):
        state = self.read(job_id)
        return self._public_state(state)

    def _public_state(self,state):
        result={k: state[k] for k in PUBLIC if k in state}
        background=self.background.public(self.root/state['id'],state)
        if background:result['background']=background
        from workflow_motion_preview import previous
        prior=previous(self.root/state['id'],state)
        if prior:result['previous_motion']=prior
        progress=self._generation_progress(state)
        if progress:result['progress']=progress
        return result

    def _generation_progress(self,state):
        """Expose only bounded aggregate inference progress, never worker logs."""
        if state.get('operation') in ('symmetry','partition','machine','print') or state.get('stage') not in GENERATION_STAGES | {'paused'}:
            return None
        estimates=state.get('settings',{}).get('progress_estimates_seconds',{})
        preparing=float(estimates.get('preparing',35));diffusion=float(estimates.get('diffusion',95))
        decoding=float(estimates.get('volume_decoding',125));analysing=float(estimates.get('analysing',10));total=max(1,preparing+diffusion+decoding+analysing)
        clock=time.time()
        if state.get('stage')=='paused':
            try:clock=datetime.fromisoformat(state['paused_at']).timestamp()
            except (KeyError,TypeError,ValueError):pass
        try:elapsed=max(0,clock-datetime.fromisoformat(state['created_at']).timestamp()-float(state.get('paused_total_seconds',0)))
        except (KeyError,TypeError,ValueError):elapsed=0
        stage=state.get('paused_from_stage') if state.get('stage')=='paused' else state['stage'];completed=0.;remaining=max(0,total-elapsed);label='生成待ち'
        if stage in ('starting','preparing'):
            completed=min(preparing,elapsed);label='画像を3D生成用に準備中'
        elif stage=='generating':
            label='形を組み立て中';log=self.directory(state['id'])/'inference.log';content=''
            try:
                with log.open('rb') as stream:
                    stream.seek(max(0,log.stat().st_size-262144));content=stream.read().decode('utf-8','ignore')
            except OSError:pass
            if 'Falling back to dense surface evaluation:' in content:
                decoding=max(decoding,125);total=max(1,preparing+diffusion+decoding+analysing)
            volume=re.findall(r'Volume Decoding:[^\r\n]*?(\d+)/(\d+)',content)
            diffusion_steps=re.findall(r'Diffusion Sampling::[^\r\n]*?(\d+)/(\d+)',content)
            if volume and int(volume[-1][1])>0:
                fraction=min(1,int(volume[-1][0])/int(volume[-1][1]));completed=preparing+diffusion+decoding*fraction
                remaining=decoding*(1-fraction)+analysing;label='立体の表面を作成中'
            elif 'Hierarchical Surface [r' in content:
                completed=preparing+diffusion;remaining=decoding+analysing;label='立体の表面を作成中'
            elif diffusion_steps and int(diffusion_steps[-1][1])>0:
                fraction=min(1,int(diffusion_steps[-1][0])/int(diffusion_steps[-1][1]));completed=preparing+diffusion*fraction
                remaining=diffusion*(1-fraction)+decoding+analysing
            else:completed=min(preparing,elapsed)
        elif stage=='analysing':
            label='形状とサイズを最終確認中';completed=total-analysing
            try:phase_elapsed=max(0,time.time()-(self.directory(state['id'])/'inference.glb').stat().st_mtime)
            except OSError:phase_elapsed=0
            completed+=min(analysing,phase_elapsed);remaining=max(0,analysing-phase_elapsed)
        return {'value':round(min(.99,max(0,completed/total)),4),'percent':int(min(99,max(0,round(completed/total*100)))),
                'label':label,'elapsed_seconds':int(elapsed),'remaining_seconds':int(max(0,round(remaining))),
                'estimate_basis':'ジョブに保存したRTX 3060の方式別時間目安と現在の生成ログ'}

    def list(self):
        result = []
        for directory in self.root.iterdir():
            if JOB_ID.fullmatch(directory.name):
                try:
                    result.append(self.public(directory.name))
                except (KeyError, OSError, ValueError):
                    continue
        return sorted(result, key=lambda item: item['created_at'], reverse=True)

    def trash_directory(self,job_id):
        if not JOB_ID.fullmatch(job_id):raise KeyError('Invalid job id')
        path=self.trash_root/job_id
        if path.resolve()!=path or not path.is_dir():raise KeyError('Unknown trashed job')
        return path

    def list_trash(self):
        result=[]
        for directory in self.trash_root.iterdir():
            if not JOB_ID.fullmatch(directory.name):continue
            try:result.append(self._public_state(json.loads((directory/'state.json').read_text(encoding='utf-8'))))
            except (KeyError,OSError,ValueError,TypeError):continue
        return sorted(result,key=lambda item:item.get('trashed_at',item.get('updated_at','')),reverse=True)

    def trash_job(self,job_id):
        with self.lock:
            state=self.read(job_id)
            if state.get('stage') in ACTIVE|GENERATION_STAGES|{'paused','queued'}:
                raise ValueError('処理中の3Dモデルはゴミ箱へ移動できません。処理を停止してから操作してください。')
            source=self.directory(job_id);target=self.trash_root/job_id
            if target.exists():raise ValueError('同じ3Dモデルがすでにゴミ箱にあります。')
            state['trashed_at']=now();write_json(source/'state.json',state)
            os.replace(source,target)
            return self._public_state(state)

    def restore_job(self,job_id):
        with self.lock:
            source=self.trash_directory(job_id);target=self.root/job_id
            if target.exists():raise ValueError('同じ3Dモデルが一覧に存在するため復元できません。')
            state=json.loads((source/'state.json').read_text(encoding='utf-8'));state.pop('trashed_at',None);state['updated_at']=now()
            write_json(source/'state.json',state);os.replace(source,target)
            return self.public(job_id)

    def empty_trash(self):
        with self.lock:
            deleted=[]
            import shutil
            for directory in list(self.trash_root.iterdir()):
                if not JOB_ID.fullmatch(directory.name) or directory.parent!=self.trash_root:continue
                shutil.rmtree(directory);deleted.append(directory.name)
            return {'deleted':deleted,'count':len(deleted)}

    def trash_artifact(self,job_id,name):
        directory=self.trash_directory(job_id)
        if name not in ('source.png','input.png'):raise KeyError('Unknown artifact')
        target=directory/name
        if target.resolve()!=target or not target.is_file():raise KeyError('Unknown artifact')
        return target

    def create(self, data, name='画像'):
        from PIL import Image, ImageOps, UnidentifiedImageError
        settings = json.loads((PROJECT / 'config/parameters.json').read_text(encoding='utf-8'))['image_workflow']
        if not data or len(data) > settings['max_upload_bytes']:
            raise ValueError('画像は20 MB以内にしてください。')
        try:
            with Image.open(io.BytesIO(data)) as source:
                if source.format not in ('PNG', 'JPEG', 'WEBP') or getattr(source, 'n_frames', 1) != 1:
                    raise ValueError('静止画のPNG・JPEG・WebPを選んでください。')
                if source.width * source.height > settings['max_image_pixels'] or min(source.size) < 64:
                    raise ValueError('画像の画素数が範囲外です（最小64 px、最大2400万画素）。')
                rgba = ImageOps.exif_transpose(source).convert('RGBA')
                rgba.thumbnail((settings['input_max_pixels'], settings['input_max_pixels']))
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError('画像ファイルを読み取れませんでした。') from exc
        with self.lock:
            if len([x for x in self.list() if x['stage'] in ACTIVE | {'queued'}]) >= 3:
                raise ValueError('生成待ちは3件までです。完了してから追加してください。')
            job_id = uuid.uuid4().hex
            directory = self.root / job_id
            directory.mkdir()
            (directory / 'source_original.bin').write_bytes(data)
            rgba.save(directory / 'source.png')
            state = {'id': job_id, 'name': Path(name.replace('\\', '/')).name[:100] or '画像',
                     'stage': 'queued', 'message': '生成待ち', 'created_at': now(), 'updated_at': now(),
                     'source_sha256': hashlib.sha256(data).hexdigest(),
                     'target_length_mm': settings['target_length_mm'], 'settings': settings}
            write_json(directory / 'state.json', state)
            return self.public(job_id)

    def artifact(self, job_id, name):
        directory = self.directory(job_id)
        print_artifact=re.fullmatch(r'p_([0-9a-f]{32})_([0-9]{2})\.3mf',name)
        if print_artifact:
            revision,plate=print_artifact.groups();state=self.read(job_id)
            if state['stage']!='print_ready' or state.get('mechanical_revision')!=revision:raise KeyError('Print not ready')
            folder=directory/'machining'/revision
            try:
                release=json.loads((folder/'print/release.json').read_text(encoding='utf-8'))
                digest=hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest()
                prepared_project=(release.get('artifact_kind')=='bambu_project' and release.get('ready_to_open') is True
                                  and release.get('project_verified') is True and release.get('slicing_verified') is False
                                  and release.get('ready_to_print') is False)
                sliced_release=release.get('ready_to_print') is True and release.get('slicing_verified') is True
                if (not (prepared_project or sliced_release)
                        or release.get('verification_run') is not False
                        or release.get('manifest_sha256')!=digest or state.get('manifest_sha256')!=digest):
                    raise KeyError('Stale print')
                approval_path=folder/'review_approval.json'
                approval=json.loads(approval_path.read_text(encoding='utf-8'))
                if (approval.get('accepted') is not True or approval.get('manifest_sha256')!=digest
                        or hashlib.sha256(approval_path.read_bytes()).hexdigest()!=release.get('review_approval_sha256')):
                    raise KeyError('Review changed')
                manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
                if not manifest['parts']:raise KeyError('Missing print parts')
                for part in manifest['parts']:
                    source=folder/part['filename']
                    if (source.parent!=folder or source.resolve()!=source
                            or hashlib.sha256(source.read_bytes()).hexdigest()!=part['sha256']):
                        raise KeyError('Geometry changed after printing')
                records=[p for p in release['plates'] if p['plate']==int(plate)]
                published=[p for p in state.get('prints',[]) if p['plate']==int(plate)]
                if len(records)!=1 or len(published)!=1:raise KeyError('Unknown plate')
                record=records[0]
                filename=f'SkeleCAD_A1mini_plate_{plate}.3mf'
                if (record['filename']!=filename or published[0]['filename']!=filename
                        or record['sha256']!=published[0]['sha256']):raise KeyError('Print record changed')
                target=folder/'print'/f'plate_{plate}'/filename
                if target.resolve()!=target or hashlib.sha256(target.read_bytes()).hexdigest()!=record['sha256']:
                    raise KeyError('Print changed')
                return target
            except (OSError,ValueError,TypeError,AttributeError) as exc:
                raise KeyError('Print artifacts are incomplete or changed') from exc
        preview_artifact=re.fullmatch(r'v_([0-9a-f]{32})(?:_(core_[0-9]{2}))?\.(json|stl)',name)
        if preview_artifact:
            revision,part,extension=preview_artifact.groups()
            state=self.read(job_id)
            public=self.background.public(directory,state) or {}
            record=json.loads((directory/'background.json').read_text(encoding='utf-8'))
            references=[public.get('preview'),*(record.get('preview_history',[]) if public.get('preview') else [])]
            reference=next((r for r in references if r and r.get('revision')==revision),None)
            if not reference:raise KeyError('Unknown motion preview')
            folder=directory/'motion_previews'/revision
            manifest_path=folder/'manifest.json'
            if hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=reference.get('manifest_sha256'):raise KeyError('Preview changed')
            manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
            if manifest.get('preview_only') is not True:raise KeyError('Not a motion preview')
            if part:
                if extension!='stl':raise KeyError('Unknown preview format')
                item=next((p for p in manifest['parts'] if p['name']==part),None)
                if not item:raise KeyError('Unknown preview part')
                target=folder/(part+'.stl')
                if hashlib.sha256(target.read_bytes()).hexdigest()!=item['sha256']:raise KeyError('Preview part changed')
            else:
                if extension!='json':raise KeyError('Unknown preview format')
                target=manifest_path
            if target.resolve()!=target or not target.is_file():raise KeyError('Unknown preview artifact')
            return target
        revision_artifact=re.fullmatch(r'r_([0-9a-f]{32})(?:_(core_[0-9]{2}))?\.(json|stl)',name)
        if revision_artifact:
            revision,part,extension=revision_artifact.groups()
            state=self.read(job_id)
            background=self.background.public(directory,state) or {}
            from workflow_motion_preview import previous
            prior=previous(directory,state) or {}
            if state.get('mechanical_revision')!=revision and background.get('revision')!=revision and prior.get('revision')!=revision:raise KeyError('Unknown revision')
            folder=directory/'machining'/revision
            manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
            if part:
                if extension!='stl' or part not in [p['name'] for p in manifest['parts']]:raise KeyError('Unknown part')
                target=folder/(part+'.stl')
            else:
                if extension!='json':raise KeyError('Unknown artifact')
                target=folder/'manifest.json'
            if target.resolve()!=target or not target.is_file():raise KeyError('Unknown artifact')
            return target
        # No original metadata, logs, arbitrary filenames, relative traversal or reparse points.
        if name not in ('source.png', 'input.png', 'appearance.stl', 'manifest.json'):
            if not (re.fullmatch(r'preview_part_[0-9]{2}\.stl',name)
                    or re.fullmatch(r'preview_[0-9a-f]{32}_part_[0-9]{2}\.stl',name)):
                raise KeyError('Unknown artifact')
            manifest=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
            if name not in [part.get('filename') for part in manifest['parts']]:
                raise KeyError('Unknown artifact')
        target = directory / name
        if target.resolve() != target or not target.is_file():
            raise KeyError('Unknown artifact')
        return target

    def request_partition(self,job_id,manifest_sha256,markers):
        with self.lock:
            state=self.read(job_id)
            if state['stage'] not in ('appearance_ready','partition_failed'):
                raise ValueError('外観生成後に分割位置を指定してください。')
            manifest_path=self.directory(job_id)/'manifest.json'
            if state.get('manifest_sha256')!=manifest_sha256 or hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=manifest_sha256:
                raise ValueError('表示モデルが更新されています。再表示してから指定してください。')
            review=json.loads((PROJECT/'config/parameters.json').read_text(encoding='utf-8'))['image_workflow']['partition_review']
            maximum=int(review['maximum_markers']);minimum_radius=float(review['minimum_marker_radius_mm']);maximum_radius=float(review['maximum_marker_radius_mm'])
            if not isinstance(markers,list) or not 1<=len(markers)<=maximum:raise ValueError(f'分割マーカーは1〜{maximum}個にしてください。')
            names=set();clean=[]
            for marker in markers:
                if not isinstance(marker,dict):raise ValueError('分割マーカーが不正です。')
                name=marker.get('name');center=marker.get('center');radius=marker.get('radius_mm')
                if not isinstance(name,str) or not re.fullmatch(r'(?:candidate|user)_[0-9a-z]{2,32}',name) or name in names:raise ValueError('分割マーカー名が不正です。')
                if not isinstance(center,list) or len(center)!=3 or not all(isinstance(v,(int,float)) and abs(v)<=10000 for v in center):raise ValueError('分割マーカー位置が不正です。')
                if not isinstance(radius,(int,float)) or not minimum_radius<=radius<=maximum_radius:raise ValueError(f'分割マーカー範囲は{minimum_radius:g}〜{maximum_radius:g} mmにしてください。')
                placement=marker.get('placement_method')
                if placement not in (None,'ray_solid_midpoint','ray_solid_midpoint_v2','midline_plane_snap_v1','symmetry_mirror_x_v1'):raise ValueError('分割マーカーの配置方法が不正です。')
                pair_id=marker.get('symmetry_pair_id')
                if pair_id is not None and (not isinstance(pair_id,str) or not re.fullmatch(r'pair_[0-9a-z]{2,40}',pair_id)):raise ValueError('左右対称マーカーの対応情報が不正です。')
                record={'name':name,'center':[float(v) for v in center],'radius_mm':float(radius),'source':'user' if name.startswith('user_') else 'automatic','status':'user_selected'}
                if placement:record['placement_method']=placement
                if pair_id:record['symmetry_pair_id']=pair_id
                names.add(name);clean.append(record)
            pair_counts={pair_id:sum(marker.get('symmetry_pair_id')==pair_id for marker in clean) for pair_id in {marker.get('symmetry_pair_id') for marker in clean} if pair_id}
            if any(count!=2 for count in pair_counts.values()):raise ValueError('左右対称マーカーは2個1組で指定してください。')
            axis_name=review.get('symmetry_mirroring',{}).get('axis','x');axis_index={'x':0,'y':1,'z':2}.get(axis_name)
            if axis_index is None:raise ValueError('左右対称面の設定が不正です。')
            for pair_id in pair_counts:
                pair=[marker for marker in clean if marker.get('symmetry_pair_id')==pair_id]
                mirrored=[marker for marker in pair if marker.get('placement_method')=='symmetry_mirror_x_v1']
                if len(mirrored)!=1:continue
                counterpart=mirrored[0];primary=next(marker for marker in pair if marker is not counterpart)
                counterpart['center']=primary['center'][:];counterpart['center'][axis_index]*=-1
                counterpart['radius_mm']=primary['radius_mm']
            state.update(operation='partition',selected_markers=clean,source_manifest_sha256=manifest_sha256,
                         stage='queued',message='指定位置から色分けを自動更新待ち',worker_attempt=0,updated_at=now())
            for key in ('error','failed_marker_numbers','failed_marker_names','failed_marker_locations'):state.pop(key,None)
            write_json(self.directory(job_id)/'state.json',state);return self.public(job_id)

    def request_symmetry(self,job_id,manifest_sha256,source_side):
        with self.lock:
            state=self.read(job_id)
            if state['stage'] not in ('appearance_ready','partition_failed','symmetry_failed') or state.get('mechanical_revision'):
                raise ValueError('分割・ジョイント加工の前に左右対称化してください。')
            if source_side not in ('negative_x','positive_x'):
                raise ValueError('基準にする側を選んでください。')
            directory=self.directory(job_id);manifest_path=directory/'manifest.json'
            if (state.get('manifest_sha256')!=manifest_sha256 or
                    hashlib.sha256(manifest_path.read_bytes()).hexdigest()!=manifest_sha256):
                raise ValueError('表示モデルが更新されています。再表示してから左右対称化してください。')
            state.update(operation='symmetry',symmetry_source_side=source_side,
                         source_manifest_sha256=manifest_sha256,stage='queued',
                         message='左右対称化待ち',worker_attempt=0,updated_at=now())
            state.pop('error',None)
            write_json(directory/'state.json',state)
            return self.public(job_id)

    def restore_symmetry(self,job_id):
        with self.lock:
            state=self.read(job_id)
            symmetry=state.get('appearance_symmetry') or {}
            if state['stage'] not in ('appearance_ready','partition_failed','symmetry_failed') or not symmetry.get('active'):
                raise ValueError('元に戻せる左右対称化がありません。')
            directory=self.directory(job_id);original=directory/'symmetry'/'original'
            try:
                record=json.loads((original/'record.json').read_text(encoding='utf-8'))
                source_appearance=original/'appearance.stl';source_manifest=original/'manifest.json'
                if (hashlib.sha256(source_appearance.read_bytes()).hexdigest()!=record['appearance_sha256'] or
                        hashlib.sha256(source_manifest.read_bytes()).hexdigest()!=record['manifest_sha256']):
                    raise ValueError
            except (OSError,KeyError,TypeError,ValueError,json.JSONDecodeError) as exc:
                raise ValueError('保存した元形状を照合できないため、変更しませんでした。') from exc
            import shutil
            def replace_from(source,target):
                temporary=target.with_name(target.name+'.'+uuid.uuid4().hex+'.tmp')
                shutil.copy2(source,temporary);os.replace(temporary,target)
            replace_from(source_appearance,directory/'appearance.stl')
            replace_from(source_manifest,directory/'manifest.json')
            base=f'../api/jobs/{job_id}/files/'
            state.update(operation='partition',stage='appearance_ready',message='左右対称化前の形状に戻しました。',
                         manifest=base+'manifest.json',manifest_sha256=record['manifest_sha256'],
                         preview_part_count=record.get('preview_part_count') or 1,updated_at=now())
            for key in ('appearance_symmetry','symmetry_source_side','source_manifest_sha256','partition_revision',
                        'selected_markers','selected_joints','mechanical_revision','prints','error',
                        'failed_marker_numbers','failed_marker_names','failed_marker_locations','pid','process_identity'):
                state.pop(key,None)
            for key in ('partition_revision','selected_markers','selected_joints'):
                if record.get(key) is not None:state[key]=record[key]
            write_json(directory/'state.json',state)
            return self.public(job_id)

    def request_machining(self,job_id,manifest_sha256,joints=None):
        with self.lock:
            state=self.read(job_id)
            if state['stage'] not in ('appearance_ready','machining_failed'):
                raise ValueError('分割候補の生成完了後に加工してください。')
            if state.get('manifest_sha256')!=manifest_sha256:
                raise ValueError('表示モデルが更新されています。再表示してから加工してください。')
            if hashlib.sha256((self.directory(job_id)/'manifest.json').read_bytes()).hexdigest()!=manifest_sha256:
                raise ValueError('元の分割候補が変更されています。再生成が必要です。')
            manifest=json.loads((self.directory(job_id)/'manifest.json').read_text(encoding='utf-8'))
            candidates=[c for c in manifest['joint_candidates'] if c['classification']=='two_part_junction']
            allowed={c['name'] for c in candidates}
            if joints is None:joints=[c['name'] for c in candidates]
            if not isinstance(joints,list) or not joints or not all(isinstance(n,str) for n in joints):raise ValueError('関節候補を選んでください。')
            if len(set(joints))!=len(joints) or set(joints)-allowed:raise ValueError('関節候補が不正です。')
            parameters=json.loads((PROJECT/'config/parameters.json').read_text(encoding='utf-8'))
            conflicts=spacing_conflicts(manifest['joint_candidates'],set(joints),minimum_joint_spacing(parameters))
            if conflicts:
                first=conflicts[0];numbers={candidate['name']:number for number,candidate in enumerate(manifest['joint_candidates'],1)}
                raise ValueError(f'マーカー{numbers[first["a"]]}番と{numbers[first["b"]]}番が近すぎます（{first["distance_mm"]:.1f} mm、必要 {first["minimum_mm"]:.1f} mm）。片方を削除するか、離れた位置へ置き直してください。')
            try:
                if self.background.adopt(self.directory(job_id),state,joints):return self.public(job_id)
            except (OSError,ValueError,KeyError,TypeError):
                # Corrupt/missing speculative data falls back to a fresh job.
                pass
            state.update(operation='machine',selected_joints=joints,stage='queued',message='ジョイント加工待ち',worker_attempt=0,updated_at=now())
            for key in ('error','failed_marker_numbers','failed_marker_names','failed_marker_locations'):state.pop(key,None)
            write_json(self.directory(job_id)/'state.json',state)
            return self.public(job_id)

    def return_to_partition(self,job_id):
        with self.lock:
            state=self.read(job_id)
            if state['stage'] not in ('mechanical_review','machining_failed','print_failed','print_ready'):
                raise ValueError('ジョイント加工後に分割へ戻ってください。')
            directory=self.directory(job_id);manifest_path=directory/'manifest.json'
            manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
            if manifest.get('stage')!='partition_preview' or not manifest.get('partition_review') or len(manifest.get('parts',[]))<2:
                raise ValueError('戻せる分割プレビューがありません。')
            digest=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
            base=f'../api/jobs/{job_id}/files/manifest.json'
            state.update(operation='partition',stage='appearance_ready',message='ジョイント加工前の分割候補に戻しました。マーカー操作に合わせて色分けを自動更新します。',
                         manifest=base,manifest_sha256=digest,preview_part_count=len(manifest['parts']),updated_at=now())
            for key in ('mechanical_revision','prints','error','failed_marker_numbers','failed_marker_names','failed_marker_locations','pid','process_identity'):
                state.pop(key,None)
            write_json(directory/'state.json',state)
            return self.public(job_id)

    def request_print(self,job_id,data):
        with self.lock:
            state=self.read(job_id)
            if state['stage'] not in ('mechanical_review','print_failed'):raise ValueError('加工後の可動確認が必要です。')
            if data.get('accepted') is not True:raise ValueError('可動確認と試作条件の確認が必要です。')
            digest=data.get('manifest_sha256')
            if digest!=state.get('manifest_sha256'):raise ValueError('表示モデルが更新されています。再確認してください。')
            revision=state.get('mechanical_revision','')
            if not JOB_ID.fullmatch(revision):raise ValueError('加工結果が見つかりません。')
            folder=self.directory(job_id)/'machining'/revision
            if hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest()!=digest:raise ValueError('加工結果が変更されています。')
            review=data.get('review',{})
            if not isinstance(review,dict) or review.get('ready') is not True or review.get('collision')!='clear':raise ValueError('衝突判定が完了した、食い込みのない姿勢で確認してください。')
            manifest=json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
            # Lightweight request validation; the print worker independently tests
            # all actual meshes at the reviewed pose before any slicing.
            from audit_workflow_motion import pose_matrices
            if not isinstance(review.get('pose'),dict):raise ValueError('確認姿勢が不正です。')
            pose_matrices(manifest['joints'],review['pose'])
            write_json(folder/'review_approval.json',{'accepted':True,'manifest_sha256':digest,
                       'pose':review['pose'],'confirmed_at':now(),'physical_fit_verified':False})
            state.update(operation='print',stage='queued',message='Bambu用の印刷準備待ち',worker_attempt=0,updated_at=now())
            state.pop('error',None);state.pop('prints',None)
            write_json(self.directory(job_id)/'state.json',state)
            return self.public(job_id)

    def open_print_in_bambu(self,job_id,data):
        with self.lock:
            state=self.read(job_id)
            if state['stage']!='print_ready' or data.get('manifest_sha256')!=state.get('manifest_sha256'):
                raise ValueError('最新の印刷ファイルが準備できていません。')
            revision=state.get('mechanical_revision','')
            if not JOB_ID.fullmatch(revision):raise ValueError('印刷ファイルが見つかりません。')
            plates=state.get('prints',[])
            if not plates:raise ValueError('印刷ファイルが見つかりません。')
            targets=[]
            for plate in plates:
                number=int(plate['plate'])
                targets.append(self.artifact(job_id,f'p_{revision}_{number:02d}.3mf'))
            executable=find_bambu_studio()
            subprocess.Popen([str(executable),*[str(target) for target in targets]],close_fds=True,
                             creationflags=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0))
            return {'opened':True,'plate_count':len(targets)}

    def _worker_tree(self,state):
        """Return only a still-live worker whose creation identity we recorded."""
        pid=state.get('pid');identity=state.get('process_identity')
        if not isinstance(pid,int) or not identity or process_identity(pid)!=identity:
            raise ValueError('生成プロセスを確認できません。状態を再読み込みしてください。')
        import psutil
        try:
            root=psutil.Process(pid);children=root.children(recursive=True)
        except psutil.Error as exc:
            raise ValueError('生成プロセスを確認できません。状態を再読み込みしてください。') from exc
        return root,children

    def pause_generation(self,job_id):
        with self.lock:
            state=self.read(job_id)
            if state.get('operation') in ('symmetry','partition','machine','print') or state.get('stage') not in GENERATION_STAGES:
                raise ValueError('画像から3D形状を生成中のときだけ一時停止できます。')
            previous=state['stage']
            if previous!='queued':
                root,children=self._worker_tree(state);suspended=[]
                try:
                    for process in [*reversed(children),root]:process.suspend();suspended.append(process)
                except Exception as exc:
                    for process in reversed(suspended):
                        try:process.resume()
                        except Exception:pass
                    raise ValueError('生成処理を一時停止できませんでした。') from exc
                state=self.read(job_id)
                if state.get('stage') not in GENERATION_STAGES:
                    for process in reversed(suspended):
                        try:process.resume()
                        except Exception:pass
                    return self.public(job_id)
                previous=state['stage']
            state.update(stage='paused',paused_from_stage=previous,paused_at=now(),message='画像からの3D生成を一時停止しています。GPUメモリは保持されています。',updated_at=now())
            write_json(self.directory(job_id)/'state.json',state);return self.public(job_id)

    def resume_generation(self,job_id):
        with self.lock:
            state=self.read(job_id)
            if state.get('stage')!='paused':raise ValueError('一時停止中の生成処理がありません。')
            previous=state.get('paused_from_stage')
            if previous not in GENERATION_STAGES:raise ValueError('再開する生成段階を確認できません。')
            if previous!='queued':
                root,children=self._worker_tree(state)
                try:
                    for process in [*children,root]:process.resume()
                except Exception as exc:raise ValueError('生成処理を再開できませんでした。') from exc
            try:paused_seconds=max(0,time.time()-datetime.fromisoformat(state['paused_at']).timestamp())
            except (KeyError,TypeError,ValueError):paused_seconds=0
            state.update(stage=previous,message='画像からの3D生成を再開しました。',paused_total_seconds=float(state.get('paused_total_seconds',0))+paused_seconds,updated_at=now())
            for key in ('paused_from_stage','paused_at'):state.pop(key,None)
            write_json(self.directory(job_id)/'state.json',state);return self.public(job_id)

    def cancel_generation(self,job_id):
        with self.lock:
            state=self.read(job_id)
            if state.get('operation') in ('symmetry','partition','machine','print') or state.get('stage') not in GENERATION_STAGES | {'paused'}:
                raise ValueError('停止できる画像生成処理がありません。')
            if state['stage'] not in ('queued',) and not (state['stage']=='paused' and state.get('paused_from_stage')=='queued'):
                root,children=self._worker_tree(state)
                import psutil
                processes=[*reversed(children),root]
                for process in processes:
                    try:process.terminate()
                    except psutil.NoSuchProcess:pass
                _,alive=psutil.wait_procs(processes,timeout=2)
                for process in alive:
                    try:process.kill()
                    except psutil.NoSuchProcess:pass
            result={'id':job_id,'name':state.get('name','画像'),'stage':'cancelled','deleted':True,
                    'message':'画像からの3D生成を停止し、元画像と途中データを削除しました。'}
            self.children.pop(job_id,None)
            import shutil
            directory=self.directory(job_id)
            if directory.parent!=self.root or not JOB_ID.fullmatch(directory.name):raise ValueError('削除対象の生成データを確認できません。')
            shutil.rmtree(directory)
            return result

    def _recover_worker_exit(self,job_id,state,returncode=None):
        operation=state.get('operation');attempt=int(state.get('worker_attempt',0) or 0)
        detail='終了コード '+str(returncode) if returncode is not None else 'プロセス終了を検出'
        if operation=='partition' and attempt<2:
            state.update(stage='queued',message='色分け処理が中断したため、同じマーカーで一度だけ自動再試行します。',error=detail,updated_at=now())
        else:
            failed_stage={'symmetry':'symmetry_failed','partition':'partition_failed','machine':'machining_failed','print':'print_failed'}.get(operation,'failed')
            label={'symmetry':'左右対称化','partition':'色分け','machine':'ジョイント加工','print':'印刷準備'}.get(operation,'生成処理')
            state.update(stage=failed_stage,message=label+'処理が予期せず終了しました。直前の結果は保持しています。',error=detail,updated_at=now())
        for key in ('pid','process_identity'):state.pop(key,None)
        write_json(self.directory(job_id)/'state.json',state)

    def _tick(self):
        with self.lock:
            for job_id, process in list(self.children.items()):
                returncode=process.poll()
                if returncode is not None:
                    state = self.read(job_id)
                    # A queued state may belong to a newer marker operation that
                    # arrived before this older child was reaped. Never let the
                    # older exit overwrite or retry the newer request.
                    if state['stage'] in ACTIVE:
                        self._recover_worker_exit(job_id,state,returncode)
                    del self.children[job_id]
            busy = bool(self.children)
            for item in reversed(self.list()):
                state = self.read(item['id'])
                if state['stage'] in ACTIVE:
                    identity = process_identity(state.get('pid', 0))
                    if identity and identity == state.get('process_identity'):
                        busy = True
                    elif state['id'] not in self.children:
                        if state.get('operation') in ('symmetry','partition','machine','print'):self._recover_worker_exit(state['id'],state)
                        else:
                            state.update(stage='interrupted', message='生成処理が停止しました。元画像は保存されています。', updated_at=now())
                            write_json(self.directory(state['id']) / 'state.json', state)
            if busy:
                return
            for item in reversed(self.list()):
                if item['stage'] != 'queued':
                    continue
                directory = self.directory(item['id'])
                if self.background.wait_for_foreground(directory,self.read(item['id'])):
                    continue
                python = python_path(WORKSPACE)
                if not python.is_file():
                    state = self.read(item['id'])
                    state.update(stage='failed', message='ローカル3D生成環境が見つかりません。', updated_at=now())
                    write_json(directory / 'state.json', state)
                    return
                state = self.read(item['id'])
                state.update(stage='starting', message='生成処理を起動しています',worker_attempt=int(state.get('worker_attempt',0) or 0)+1,updated_at=now())
                write_json(directory / 'state.json', state)
                with (directory / 'worker.log').open('ab') as log:
                    worker={'symmetry':'workflow_symmetry_worker.py','partition':'workflow_partition_worker.py','machine':'workflow_machine_worker.py','print':'workflow_print_worker.py'}.get(state.get('operation'),'workflow_worker.py')
                    process = subprocess.Popen([str(python), str(PROJECT / 'tools'/worker),
                                                '--job-directory', str(directory)],
                                               cwd=PROJECT, stdout=log, stderr=subprocess.STDOUT,
                                               creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                self.children[item['id']] = process
                return

    def _pump(self):
        while not self.stopping.wait(.5):
            try:
                self._tick()
            except Exception:
                # A request remains readable even if a scheduler operation fails.
                import traceback
                traceback.print_exc()

    def close(self):
        # Running jobs own their state and continue without the browser/server.
        self.stopping.set()
        self.background.close()
        if self.launch:
            self.thread.join(timeout=2)
        if self.owner:
            self.owner.close()
