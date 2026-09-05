"""One low-priority speculative worker. Publish immutable revisions, never worker state.

Only this coordinator writes background.json. A worker writes into its private
snapshot. Input identity is checked again under the request lock at publication
and adoption, so a completed older edit cannot replace newer work.
"""
import json
import os
import shutil
import subprocess
import threading
import time
import uuid

from workflow_store import PROJECT, WORKSPACE, JOB_ID, ACTIVE, write_json, process_identity
from workflow_background_worker import source_identity, digest
from runtime_paths import python_path


def read_json(path, default=None):
    try:
        value=json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value,dict) else default
    except (OSError, ValueError):return default


def eligible(state):
    return (state.get('stage') in ('appearance_ready', 'mechanical_review')
            and bool(state.get('partition_revision'))
            and state.get('preview_part_count', 0) > 1)


def discard_private(path, root):
    if not path.exists():return
    if path.resolve()!=path or not path.is_relative_to(root.resolve()) or path==root.resolve():
        raise ValueError('Private work path escaped its job directory')
    shutil.rmtree(path)


def preserve_failure_diagnostics(snapshot, attempt):
    """Keep small diagnostic inputs/logs before removing private geometry."""
    if not snapshot.is_dir():return
    for source in snapshot.rglob('*'):
        if not source.is_file() or (source.suffix!='.log' and source.name not in
                ('request.json','status.json','source_manifest.json')):continue
        if not source.resolve().is_relative_to(snapshot.resolve()):continue
        target=attempt/'diagnostics'/source.relative_to(snapshot)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(source,target)


class BackgroundWork:
    def __init__(self, store):
        self.store = store
        self.observed = {}
        self.process = None
        self.stopping = threading.Event()
        self.thread = None

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True, name='workflow-prefetch')
        self.thread.start()

    def close(self):
        self.stopping.set()
        # Release the store ownership lock only after publication has finished.
        if self.thread:self.thread.join()

    def public(self, directory, state):
        record = read_json(directory/'background.json', {})
        # Requests invalidate visibility immediately, even before the worker notices.
        if not eligible(state) or record.get('source_revision') != state.get('partition_revision'):
            return None
        public = {k:record[k] for k in ('stage', 'revision', 'manifest_sha256', 'preview') if k in record}
        if record.get('stage') in ('failed','print_failed'):
            attempt = record.get('attempt','')
            result = read_json(directory/'.background'/attempt/'result.json', {}) if JOB_ID.fullmatch(attempt) else {}
            if result.get('identity') == record.get('identity'):
                public['error'] = result.get('error') or '先行処理を完了できませんでした。'
                locations = result.get('failed_marker_locations', [])
                # Old attempts retained the error but not the structured locations.
                # Their partition revision is checked above, so numbering is stable.
                if not locations and record['stage']=='failed':
                    import re
                    match = re.search(r'マーカー([0-9]+)番', public['error'])
                    if match:
                        number=0;pairs={};locations=[]
                        for marker in state.get('selected_markers',[]):
                            pair=marker.get('symmetry_pair_id')
                            if pair and pair in pairs:current=pairs[pair]
                            else:
                                number+=1;current=number
                                if pair:pairs[pair]=current
                            if current==int(match.group(1)):
                                locations.append({k:marker[k] for k in ('center','symmetry_pair_id') if k in marker})
                if locations:public['failed_marker_locations']=locations
            else:public['error']='先行処理を完了できませんでした。'
        return public or None

    def wait_for_foreground(self, directory, state):
        """Do not launch a second CAD/slicer for work already in flight."""
        operation=state.get('operation')
        if operation not in ('machine','print'):return False
        record=read_json(directory/'background.json',{})
        if record.get('stage') not in ('working','mechanical_ready'):return False
        if operation=='print' and record.get('revision')!=state.get('mechanical_revision'):return False
        if record.get('identity')!=source_identity(directory):return False
        identity=process_identity(record.get('pid',0))
        if identity and identity==record.get('process_identity'):return True
        attempt=record.get('attempt','')
        if not JOB_ID.fullmatch(attempt):return False
        result=read_json(directory/'.background'/attempt/'result.json',{})
        # The process can exit before the coordinator copies its completed files.
        return result.get('identity')==record.get('identity') and result.get('stage') in ('mechanical_ready','ready')

    def adopt(self, directory, state, joints):
        record = read_json(directory/'background.json', {})
        if (record.get('stage') not in ('mechanical_ready', 'ready', 'print_failed')
                or record.get('identity') != source_identity(directory)
                or sorted(record.get('joints', [])) != sorted(joints)):
            return False
        revision = record.get('revision', '')
        if not JOB_ID.fullmatch(revision):return False
        folder = directory/'machining'/revision
        manifest = read_json(folder/'manifest.json', {})
        if (manifest.get('stage') != 'mechanical_review'
                or digest(folder/'manifest.json') != record['manifest_sha256']):return False
        for part in manifest['parts']:
            target = folder/part['filename']
            if target.resolve().parent != folder.resolve() or digest(target) != part['sha256']:
                return False
        state.update(stage='mechanical_review', operation='machine', selected_joints=joints,
                     mechanical_revision=revision, manifest_sha256=record['manifest_sha256'],
                     manifest=f'../api/jobs/{directory.name}/files/r_{revision}.json',
                     message='先行処理済みのジョイントを表示しています。ドラッグで可動を確認できます。')
        for key in ('error', 'prints', 'pid', 'process_identity'):state.pop(key, None)
        write_json(directory/'state.json', state)
        return True

    def _publish_preview(self, directory, attempt, record):
        result=read_json(attempt/'result.json',{})
        preview=result.get('preview') or {}
        revision=preview.get('revision','')
        if (result.get('identity')!=record.get('identity') or not JOB_ID.fullmatch(revision)
                or record.get('preview')==preview):return
        source=attempt/directory.name/'motion_previews'/revision
        manifest=read_json(source/'manifest.json',{})
        if (digest(source/'manifest.json')!=preview.get('manifest_sha256') or
                manifest.get('preview_only') is not True or manifest.get('print_ready') is not False
                or manifest.get('stage')!='motion_preview'):raise ValueError('Invalid motion preview')
        for part in manifest.get('parts',[]):
            import re
            if not re.fullmatch(r'core_[0-9]{2}\.stl',part.get('filename','')):raise ValueError('Invalid preview part')
            target=source/part['filename']
            if target.resolve().parent!=source.resolve() or digest(target)!=part.get('sha256'):raise ValueError('Preview geometry changed')
        destination=directory/'motion_previews'/revision
        staged=directory/'motion_previews'/('.pending_'+uuid.uuid4().hex)
        shutil.copytree(source,staged)
        try:
            with self.store.lock:
                state=self.store.read(directory.name)
                if not eligible(state) or source_identity(directory)!=record['identity']:return
                if not destination.exists():staged.rename(destination)
                history=record.get('preview_history',[])
                if record.get('preview'):history=[record['preview'],*history][:2]
                record.update(preview=preview,preview_history=history)
                write_json(directory/'background.json',record)
        finally:discard_private(staged,directory)

    def _publish(self, directory, attempt, record):
        if record.get('stage') in ('failed','superseded'):return
        result = read_json(attempt/'result.json', {})
        if result.get('identity') != record['identity']:return
        stage = result.get('stage')
        if stage not in ('mechanical_ready', 'ready', 'print_failed', 'failed', 'superseded'):return
        if record.get('stage') == stage:return
        revision = result.get('revision', '')
        if stage in ('mechanical_ready', 'ready', 'print_failed'):
            if not JOB_ID.fullmatch(revision):raise ValueError('Invalid speculative revision')
            source = attempt/directory.name/'machining'/revision
            if digest(source/'manifest.json') != result.get('manifest_sha256'):raise ValueError('Speculative manifest changed')
            # Copy outside the request lock, then atomically rename after rechecking.
            destination = directory/'machining'/revision
            staged = directory/'machining'/('.pending_'+uuid.uuid4().hex)
            if not destination.exists():
                shutil.copytree(source, staged, ignore=shutil.ignore_patterns('print'))
            else:staged = None
            print_staged = None
            if stage == 'ready' and not (destination/'print').exists():
                print_staged = directory/'machining'/('.print_'+uuid.uuid4().hex)
                shutil.copytree(source/'print', print_staged)
            with self.store.lock:
                state = self.store.read(directory.name)
                waiting=(state.get('stage')=='queued' and
                         (state.get('operation')=='machine' or
                          (state.get('operation')=='print' and state.get('mechanical_revision')==revision)))
                if not (eligible(state) or waiting) or source_identity(directory) != record['identity']:
                    # Private, unpublished copies remain private; no stale state write.
                    record.update(stage='superseded')
                else:
                    if staged is not None:staged.rename(destination)
                    if print_staged is not None and not (destination/'print').exists():
                        print_staged.rename(destination/'print')
                    record.update(stage=stage, revision=revision, manifest_sha256=result['manifest_sha256'])
                write_json(directory/'background.json', record)
                if waiting and state.get('operation')=='machine' and record.get('stage')!='superseded':
                    self.adopt(directory,state,record['joints'])
            for private in (staged,print_staged):
                if private is not None:discard_private(private,directory)
        else:
            record.update(stage=stage)
            write_json(directory/'background.json', record)

    def tick(self):
        # Durable process identity also protects server restarts from duplicate work.
        live = False
        directories = [p for p in self.store.root.iterdir() if JOB_ID.fullmatch(p.name) and p.is_dir() and p.resolve()==p]
        for directory in directories:
            record = read_json(directory/'background.json', {})
            attempt_id = record.get('attempt', '')
            if not JOB_ID.fullmatch(attempt_id):continue
            attempt = directory/'.background'/attempt_id
            identity = process_identity(record.get('pid', 0))
            running = bool(identity and identity == record.get('process_identity'))
            live |= running
            try:
                self._publish_preview(directory,attempt,record)
                self._publish(directory, attempt, record)
            except (OSError,ValueError,KeyError,TypeError):
                # A broken speculative result must not block the foreground queue.
                import traceback
                traceback.print_exc();record.update(stage='failed')
                write_json(directory/'background.json',record)
            if record.get('stage') in ('working', 'mechanical_ready') and not running:
                result = read_json(attempt/'result.json', {})
                if result.get('stage') not in ('ready', 'print_failed', 'failed', 'superseded'):
                    record.update(stage='failed')
                    write_json(directory/'background.json', record)
            if not running and record.get('stage') in ('ready','print_failed','failed','superseded'):
                if record.get('stage') in ('failed','print_failed'):
                    preserve_failure_diagnostics(attempt/directory.name,attempt)
                discard_private(attempt/directory.name,directory)
        if self.process and self.process.poll() is not None:self.process = None
        if live or self.process:return
        states = [(p, read_json(p/'state.json', {})) for p in directories]
        if any(s.get('stage') in ACTIVE | {'queued', 'paused'} for _, s in states):return
        # Recent edits first. Debounce identity, not just a timestamp from the worker.
        for directory, state in sorted(states, key=lambda row:row[1].get('updated_at', ''), reverse=True):
            if not eligible(state):continue
            identity = source_identity(directory)
            previous = self.observed.get(directory.name)
            if not previous or previous[0] != identity:
                self.observed[directory.name] = (identity, time.monotonic());continue
            if time.monotonic()-previous[1] < 3:continue
            record = read_json(directory/'background.json', {})
            if record.get('identity') == identity:continue
            manifest = read_json(directory/'manifest.json', {})
            joints = state.get('selected_joints')
            if joints is None:
                joints = [c['name'] for c in manifest.get('joint_candidates', []) if c.get('classification') == 'two_part_junction']
            if not joints:continue
            attempt_id = uuid.uuid4().hex
            attempt = directory/'.background'/attempt_id
            snapshot = attempt/directory.name
            snapshot.mkdir(parents=True)
            for name in ('manifest.json', 'state.json', 'appearance.stl'):shutil.copy2(directory/name, snapshot/name)
            # Existing validated machining can go straight to speculative slicing.
            revision = state.get('mechanical_revision')
            if revision and JOB_ID.fullmatch(revision):
                shutil.copytree(directory/'machining'/revision, snapshot/'machining'/revision,
                                ignore=shutil.ignore_patterns('print'))
            elif (directory/'machining').is_dir():
                # Reuse verified per-part/per-joint caches across edits. This is
                # only an input cache; it never grants a current motion/print release.
                for previous in sorted((p for p in (directory/'machining').iterdir() if p.is_dir() and JOB_ID.fullmatch(p.name)),key=lambda p:p.stat().st_mtime,reverse=True):
                    status=read_json(previous/'status.json',{})
                    if status.get('stage')!='mechanical_review' or not (previous/'machining_cache.json').is_file():continue
                    if digest(previous/'manifest.json')!=status.get('manifest_sha256'):continue
                    shutil.copytree(previous,snapshot/'machining'/previous.name,ignore=shutil.ignore_patterns('print'))
                    break
            with self.store.lock:
                latest = self.store.read(directory.name)
                if not eligible(latest) or source_identity(directory) != identity:
                    discard_private(snapshot,directory);continue
                write_json(attempt/'request.json', {'original':str(directory), 'identity':identity,
                                                  'mechanical_revision':revision})
                environment = os.environ.copy()
                environment.update(OMP_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1', MKL_NUM_THREADS='1',
                                   NUMEXPR_NUM_THREADS='1')
                with (attempt/'worker.log').open('ab') as log:
                    self.process = subprocess.Popen([str(python_path(WORKSPACE)), str(PROJECT/'tools/workflow_background_worker.py'),
                                                     '--snapshot', str(snapshot)], cwd=PROJECT, env=environment,
                                                    stdout=log, stderr=subprocess.STDOUT,
                                                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0)
                                                        | getattr(subprocess, 'BELOW_NORMAL_PRIORITY_CLASS', 0))
                write_json(directory/'background.json', {'identity':identity, 'source_revision':state['partition_revision'],
                    'stage':'working', 'joints':joints, 'attempt':attempt_id, 'pid':self.process.pid,
                    'process_identity':process_identity(self.process.pid)})
            return

    def run(self):
        while not self.stopping.wait(.75):
            try:self.tick()
            except Exception:
                import traceback
                traceback.print_exc()
