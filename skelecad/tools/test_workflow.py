"""Real HTTP/image/mesh tests; never invoke inference or launch an external GUI."""
import hashlib
import http.client
import io
import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

import numpy as np
from PIL import Image, ImageDraw

from viewer_server import ViewerHandler
from workflow_store import WorkflowStore, process_identity, write_json
from workflow_worker import normalize_mesh, prepare_image


def image_bytes(color='royalblue'):
    image = Image.new('RGB', (256, 256), 'white')
    draw = ImageDraw.Draw(image)
    draw.ellipse((40, 40, 215, 215), fill=color)
    stream = io.BytesIO(); image.save(stream, format='PNG')
    return stream.getvalue()


class QuietHandler(ViewerHandler):
    def log_message(self, *args):
        pass


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = WorkflowStore(Path(self.temp.name), launch=False)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), QuietHandler)
        self.server.workflows = self.store
        self.server.workflow_token = 'test-token'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join()
        self.store.close(); self.temp.cleanup()

    def request(self, path, method='GET', body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        result = response.status, response.read()
        connection.close()
        return result

    def post(self, body, **headers):
        return self.request('/api/jobs', 'POST', body, {'Content-Type':'image/png',
                            'X-SkeleCAD-Token':'test-token', **headers})

    def test_upload_isolated_persistent_and_hash_linked(self):
        source = image_bytes()
        status, body = self.post(source, **{'X-Image-Name':'../../blue.png'})
        self.assertEqual(status, 201)
        job = json.loads(body)
        self.assertEqual(job['name'], 'blue.png')
        self.assertEqual(job['source_sha256'], hashlib.sha256(source).hexdigest())
        self.assertEqual((self.store.directory(job['id']) / 'source_original.bin').read_bytes(), source)
        self.assertEqual(WorkflowStore(self.temp.name, launch=False).public(job['id']), job)
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/files/source.png')[0], 200)
        self.assertNotIn('settings', job)
        self.assertNotIn('pid', job)

    def test_queued_generation_can_pause_resume_and_stop_with_complete_deletion(self):
        job=self.store.create(image_bytes())
        headers={'Content-Type':'application/json','X-SkeleCAD-Token':'test-token'}
        status,body=self.request('/api/jobs/'+job['id']+'/pause','POST',b'{}',headers)
        paused=json.loads(body);self.assertEqual(status,202);self.assertEqual(paused['stage'],'paused');self.assertIn('progress',paused)
        status,body=self.request('/api/jobs/'+job['id']+'/resume','POST',b'{}',headers)
        self.assertEqual(status,202);self.assertEqual(json.loads(body)['stage'],'queued')
        directory=self.store.directory(job['id'])
        status,body=self.request('/api/jobs/'+job['id']+'/cancel','POST',b'{}',headers)
        stopped=json.loads(body);self.assertEqual(status,202);self.assertTrue(stopped['deleted']);self.assertFalse(directory.exists())
        self.assertEqual(self.request('/api/jobs/'+job['id'])[0],404)

    def test_finished_model_moves_to_trash_restores_and_can_be_deleted_permanently(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id'])
        state=self.store.read(job['id']);state.update(stage='appearance_ready',message='外観の生成完了');write_json(directory/'state.json',state)
        headers={'Content-Type':'application/json','X-SkeleCAD-Token':'test-token'}
        status,body=self.request('/api/jobs/'+job['id']+'/trash','POST',b'{}',headers)
        trashed=json.loads(body);self.assertEqual(status,202);self.assertEqual(trashed['id'],job['id']);self.assertIn('trashed_at',trashed)
        self.assertFalse(directory.exists());self.assertTrue((Path(self.temp.name)/'.trash'/job['id']).is_dir())
        self.assertEqual(self.request('/api/jobs/'+job['id'])[0],404)
        status,body=self.request('/api/trash');self.assertEqual(status,200);self.assertEqual(json.loads(body)['jobs'][0]['id'],job['id'])
        self.assertEqual(self.request('/api/trash/'+job['id']+'/files/source.png')[0],200)
        status,body=self.request('/api/trash/'+job['id']+'/restore','POST',b'{}',headers)
        restored=json.loads(body);self.assertEqual(status,202);self.assertEqual(restored['stage'],'appearance_ready');self.assertNotIn('trashed_at',restored)
        self.assertTrue(directory.is_dir());self.assertFalse((Path(self.temp.name)/'.trash'/job['id']).exists())
        self.assertEqual(self.request('/api/jobs/'+job['id'])[0],200)
        self.assertEqual(self.request('/api/jobs/'+job['id']+'/trash','POST',b'{}',headers)[0],202)
        status,body=self.request('/api/trash/empty','POST',b'{}',headers);result=json.loads(body)
        self.assertEqual(status,202);self.assertEqual(result,{'deleted':[job['id']],'count':1})
        self.assertFalse((Path(self.temp.name)/'.trash'/job['id']).exists());self.assertEqual(json.loads(self.request('/api/trash')[1])['jobs'],[])

    def test_processing_model_cannot_move_to_trash(self):
        job=self.store.create(image_bytes());headers={'Content-Type':'application/json','X-SkeleCAD-Token':'test-token'}
        status,body=self.request('/api/jobs/'+job['id']+'/trash','POST',b'{}',headers)
        self.assertEqual(status,400);self.assertIn('処理中',json.loads(body)['error']);self.assertTrue(self.store.directory(job['id']).is_dir())

    def test_running_generation_process_tree_is_suspended_and_resumed(self):
        job=self.store.create(image_bytes());state=self.store.read(job['id'])
        state.update(stage='generating',pid=123,process_identity='owned');write_json(self.store.directory(job['id'])/'state.json',state)
        events=[]
        class Process:
            def __init__(self,name):self.name=name
            def suspend(self):events.append(('suspend',self.name))
            def resume(self):events.append(('resume',self.name))
        root,child=Process('root'),Process('child')
        with patch.object(self.store,'_worker_tree',return_value=(root,[child])):
            self.assertEqual(self.store.pause_generation(job['id'])['stage'],'paused')
            self.assertEqual(self.store.resume_generation(job['id'])['stage'],'generating')
        self.assertEqual(events,[('suspend','child'),('suspend','root'),('resume','child'),('resume','root')])

    def test_running_generation_stop_terminates_tree_before_deleting_job(self):
        job=self.store.create(image_bytes());state=self.store.read(job['id'])
        state.update(stage='generating',pid=123,process_identity='owned');write_json(self.store.directory(job['id'])/'state.json',state)
        events=[]
        class Process:
            def __init__(self,name):self.name=name
            def terminate(self):events.append(('terminate',self.name))
            def kill(self):events.append(('kill',self.name))
        root,child=Process('root'),Process('child')
        with patch.object(self.store,'_worker_tree',return_value=(root,[child])),patch('psutil.wait_procs',return_value=([],[])):
            stopped=self.store.cancel_generation(job['id'])
        self.assertTrue(stopped['deleted']);self.assertEqual(events,[('terminate','child'),('terminate','root')]);self.assertFalse((Path(self.temp.name)/job['id']).exists())

    def test_csrf_dns_rebinding_and_non_image_rejected(self):
        for headers in ({'X-SkeleCAD-Token':'wrong'}, {'Origin':'https://evil.example'},
                        {'Host':'evil.example'}, {'Sec-Fetch-Site':'cross-site'}):
            self.assertEqual(self.post(image_bytes(), **headers)[0], 403)
        self.assertEqual(self.post(b'<svg>not a raster image</svg>')[0], 400)
        self.assertEqual(self.request('/api/session', headers={'Host':'evil.example'})[0], 403)
        self.assertEqual(self.store.list(), [])

    def test_original_logs_and_traversal_not_served(self):
        job=self.store.create(image_bytes())
        for name in ('source_original.bin','state.json','worker.log','../state.json','%2e%2e/state.json'):
            self.assertEqual(self.request('/api/jobs/'+job['id']+'/files/'+name)[0],404)

    def test_only_manifest_owned_preview_files_are_served(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id'])
        write_json(directory/'manifest.json',{'parts':[{'filename':'preview_part_00.stl'}]})
        (directory/'preview_part_00.stl').write_bytes(b'owned preview')
        (directory/'preview_part_01.stl').write_bytes(b'unreferenced stale preview')
        base='/api/jobs/'+job['id']+'/files/'
        self.assertEqual(self.request(base+'preview_part_00.stl')[0],200)
        self.assertEqual(self.request(base+'preview_part_01.stl')[0],404)

    def test_queue_limit_does_not_overwrite(self):
        ids=[self.store.create(image_bytes())['id'] for _ in range(3)]
        self.assertEqual(len(set(ids)),3)
        self.assertEqual(self.post(image_bytes())[0],400)
        self.assertEqual(len(self.store.list()),3)

    def test_mask_is_not_yellow_specific(self):
        for color in ('royalblue','red','black'):
            source=Path(self.temp.name)/'mask-source.png';source.write_bytes(image_bytes(color))
            dest=Path(self.temp.name)/'mask.png'
            report=prepare_image(source,dest)
            result=np.asarray(Image.open(dest))
            self.assertEqual(report['method'],'border_seeded_grabcut')
            self.assertEqual(result[128,128,3],255)
            self.assertEqual(result[0,0,3],0)

    def test_alpha_preserved_and_empty_alpha_rejected(self):
        source=Path(self.temp.name)/'alpha.png';dest=Path(self.temp.name)/'result.png'
        image=Image.new('RGBA',(128,128),(0,0,255,0));ImageDraw.Draw(image).ellipse((20,20,100,100),fill=(0,0,255,200))
        image.save(source)
        self.assertEqual(prepare_image(source,dest)['method'],'supplied_alpha')
        np.testing.assert_array_equal(np.asarray(Image.open(source)),np.asarray(Image.open(dest)))
        Image.new('RGBA',(128,128),(0,0,0,0)).save(source)
        with self.assertRaises(ValueError):prepare_image(source,dest)

    def test_normalization_preserves_major_components_and_removes_tiny_debris(self):
        import trimesh
        a=trimesh.creation.icosphere(subdivisions=2)
        b=a.copy();b.apply_translation([3,0,0]);mesh=trimesh.util.concatenate([a,b])
        debris=trimesh.creation.icosphere(subdivisions=1,radius=.01);debris.apply_translation([0,5,0]);mesh=trimesh.util.concatenate([mesh,debris])
        source=Path(self.temp.name)/'in.glb';output=Path(self.temp.name)/'out.stl'
        mesh.export(source);report=normalize_mesh(source,output,120)
        self.assertAlmostEqual(max(report['extents_mm']),120)
        result=trimesh.load(output,force='mesh')
        self.assertEqual(len(result.split()),2)
        self.assertTrue(result.is_watertight)
        self.assertEqual(report['debris_cleanup']['removed_components'],1)
        self.assertGreater(report['debris_cleanup']['removed_faces'],0)

    def test_dead_worker_not_restarted_but_live_worker_preserved(self):
        import os
        job=self.store.create(image_bytes());directory=self.store.directory(job['id'])
        state=self.store.read(job['id']);state.update(stage='generating',pid=os.getpid(),process_identity=process_identity(os.getpid()))
        write_json(directory/'state.json',state);self.store._tick()
        self.assertEqual(self.store.read(job['id'])['stage'],'generating')
        state['process_identity']='not-the-same-process';write_json(directory/'state.json',state)
        self.store._tick()
        self.assertEqual(self.store.read(job['id'])['stage'],'interrupted')

    def test_machining_requires_current_manifest_and_explicit_same_origin_request(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id'])
        write_json(directory/'manifest.json',{'joint_candidates':[{'name':'candidate_01','classification':'two_part_junction'}]})
        digest=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()
        state=self.store.read(job['id']);state.update(stage='appearance_ready',manifest_sha256=digest)
        write_json(directory/'state.json',state)
        path='/api/jobs/'+job['id']+'/machine'
        headers={'Content-Type':'application/json','X-SkeleCAD-Token':'test-token'}
        self.assertEqual(self.request(path,'POST',json.dumps({'manifest_sha256':digest}),{'Content-Type':'application/json'})[0],403)
        self.assertEqual(self.request(path,'POST',json.dumps({'manifest_sha256':'stale'}),headers)[0],400)
        self.assertEqual(self.request(path,'POST',json.dumps({'manifest_sha256':digest,'joints':['unknown']}),headers)[0],400)
        self.assertEqual(self.request(path,'POST',json.dumps({'manifest_sha256':digest}),headers)[0],202)
        state=self.store.read(job['id']);self.assertEqual(state['operation'],'machine');self.assertEqual(state['stage'],'queued')
        self.assertEqual(state['selected_joints'],['candidate_01'])
        self.assertEqual(self.request(path,'POST',json.dumps({'manifest_sha256':digest}),headers)[0],400)

    def test_machining_keeps_visible_marker_order(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id'])
        candidates=[{'name':'user_z','classification':'two_part_junction','center':[0,0,0]},
                    {'name':'user_a','classification':'two_part_junction','center':[20,0,0]}]
        write_json(directory/'manifest.json',{'joint_candidates':candidates});digest=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()
        state=self.store.read(job['id']);state.update(stage='appearance_ready',manifest_sha256=digest);write_json(directory/'state.json',state)
        path='/api/jobs/'+job['id']+'/machine';headers={'Content-Type':'application/json','X-SkeleCAD-Token':'test-token'}
        self.assertEqual(self.request(path,'POST',json.dumps({'manifest_sha256':digest}),headers)[0],202)
        self.assertEqual(self.store.read(job['id'])['selected_joints'],['user_z','user_a'])

    def test_failed_marker_locations_are_public_but_order_numbers_and_internal_names_are_private(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id']);state=self.store.read(job['id'])
        location={'center':[1.0,2.0,3.0],'symmetry_pair_id':'pair_public'}
        state.update(stage='machining_failed',failed_marker_numbers=[4],failed_marker_names=['user_private'],failed_marker_locations=[location])
        write_json(directory/'state.json',state);published=self.store.public(job['id'])
        self.assertEqual(published['failed_marker_locations'],[location]);self.assertNotIn('failed_marker_numbers',published);self.assertNotIn('failed_marker_names',published)

    def test_machining_rejects_joint_centres_inside_socket_envelope(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id'])
        candidates=[{'name':'candidate_01','classification':'two_part_junction','center':[0,0,0]},
                    {'name':'candidate_02','classification':'two_part_junction','center':[6,0,0]}]
        write_json(directory/'manifest.json',{'joint_candidates':candidates});digest=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()
        state=self.store.read(job['id']);state.update(stage='appearance_ready',manifest_sha256=digest);write_json(directory/'state.json',state)
        path='/api/jobs/'+job['id']+'/machine';headers={'Content-Type':'application/json','X-SkeleCAD-Token':'test-token'}
        status,body=self.request(path,'POST',json.dumps({'manifest_sha256':digest}),headers)
        text=body.decode('utf-8');self.assertEqual(status,400);self.assertIn('6.0 mm',text);self.assertIn('10.2 mm',text)
        self.assertEqual(self.store.read(job['id'])['stage'],'appearance_ready','invalid spacing never starts the CAD worker')

    def test_partition_review_accepts_only_bounded_explicit_markers(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id'])
        write_json(directory/'manifest.json',{'joint_candidates':[]});digest=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()
        state=self.store.read(job['id']);state.update(stage='appearance_ready',manifest_sha256=digest)
        write_json(directory/'state.json',state);path='/api/jobs/'+job['id']+'/partition';headers={'Content-Type':'application/json','X-SkeleCAD-Token':'test-token'}
        marker={'name':'user_ab12','center':[1,2,3],'radius_mm':6,'placement_method':'ray_solid_midpoint_v2'}
        self.assertEqual(self.request(path,'POST',json.dumps({'manifest_sha256':'stale','markers':[marker]}),headers)[0],400)
        self.assertEqual(self.request(path,'POST',json.dumps({'manifest_sha256':digest,'markers':[]}),headers)[0],400)
        status,body=self.request(path,'POST',json.dumps({'manifest_sha256':digest,'markers':[marker]}),headers)
        self.assertEqual(status,202);queued=json.loads(body);self.assertEqual(queued['stage'],'queued')
        state=self.store.read(job['id']);self.assertEqual(state['operation'],'partition');self.assertEqual(state['selected_markers'][0]['center'],[1.0,2.0,3.0])
        self.assertEqual(state['selected_markers'][0]['placement_method'],'ray_solid_midpoint_v2')

    def test_partition_review_persists_complete_symmetry_pairs(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id'])
        write_json(directory/'manifest.json',{'joint_candidates':[]});digest=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()
        state=self.store.read(job['id']);state.update(stage='appearance_ready',manifest_sha256=digest);write_json(directory/'state.json',state)
        path='/api/jobs/'+job['id']+'/partition';headers={'Content-Type':'application/json','X-SkeleCAD-Token':'test-token'}
        markers=[{'name':'user_ab12','center':[1,2,3],'radius_mm':6,'placement_method':'ray_solid_midpoint_v2','symmetry_pair_id':'pair_ab12'},
                 {'name':'user_cd34','center':[-1.4,2.3,2.8],'radius_mm':7,'placement_method':'symmetry_mirror_x_v1','symmetry_pair_id':'pair_ab12'}]
        status,_=self.request(path,'POST',json.dumps({'manifest_sha256':digest,'markers':markers}),headers);self.assertEqual(status,202)
        saved=self.store.read(job['id'])['selected_markers'];self.assertEqual([m['symmetry_pair_id'] for m in saved],['pair_ab12','pair_ab12'])
        self.assertEqual(saved[1]['center'],[-1.0,2.0,3.0]);self.assertEqual(saved[1]['radius_mm'],6.0)

        second=self.store.create(image_bytes());directory=self.store.directory(second['id'])
        write_json(directory/'manifest.json',{'joint_candidates':[]});digest=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()
        state=self.store.read(second['id']);state.update(stage='appearance_ready',manifest_sha256=digest);write_json(directory/'state.json',state)
        markers.pop();path='/api/jobs/'+second['id']+'/partition'
        self.assertEqual(self.request(path,'POST',json.dumps({'manifest_sha256':digest,'markers':markers}),headers)[0],400)

    def test_yz_symmetry_request_is_bound_to_manifest_and_original_can_be_restored(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id'])
        original_manifest={'geometry':{'sha256':'shape-original'},'parts':[{'filename':'appearance.stl'}]}
        write_json(directory/'manifest.json',original_manifest);(directory/'appearance.stl').write_bytes(b'original-shape')
        digest=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()
        state=self.store.read(job['id']);state.update(stage='appearance_ready',manifest_sha256=digest,preview_part_count=2,partition_revision='a'*32)
        write_json(directory/'state.json',state)
        path='/api/jobs/'+job['id']+'/symmetry';headers={'Content-Type':'application/json','X-SkeleCAD-Token':'test-token'}
        self.assertEqual(self.request(path,'POST',json.dumps({'manifest_sha256':'stale','source_side':'negative_x'}),headers)[0],400)
        status,body=self.request(path,'POST',json.dumps({'manifest_sha256':digest,'source_side':'negative_x'}),headers)
        self.assertEqual(status,202);queued=json.loads(body);self.assertEqual(queued['stage'],'queued')
        saved=self.store.read(job['id']);self.assertEqual(saved['operation'],'symmetry');self.assertEqual(saved['symmetry_source_side'],'negative_x')

        original=directory/'symmetry'/'original';original.mkdir(parents=True)
        (original/'appearance.stl').write_bytes(b'original-shape');write_json(original/'manifest.json',original_manifest)
        write_json(original/'record.json',{'appearance_sha256':hashlib.sha256(b'original-shape').hexdigest(),
                   'manifest_sha256':hashlib.sha256((original/'manifest.json').read_bytes()).hexdigest(),
                   'preview_part_count':2,'partition_revision':'a'*32})
        (directory/'appearance.stl').write_bytes(b'symmetric-shape');write_json(directory/'manifest.json',{'geometry':{'sha256':'symmetric'}})
        state=self.store.read(job['id']);state.update(stage='appearance_ready',appearance_symmetry={'active':True,'plane':'YZ','source_side':'negative_x'},manifest_sha256='symmetric')
        write_json(directory/'state.json',state)
        status,body=self.request('/api/jobs/'+job['id']+'/restore-symmetry','POST','{}',headers)
        restored=json.loads(body);self.assertEqual(status,202);self.assertEqual(restored['stage'],'appearance_ready')
        self.assertNotIn('appearance_symmetry',restored);self.assertEqual((directory/'appearance.stl').read_bytes(),b'original-shape')
        self.assertEqual(self.store.read(job['id'])['partition_revision'],'a'*32)

    def test_unexpected_partition_exit_retries_once_then_reports_specific_failure(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id']);state=self.store.read(job['id'])
        state.update(operation='partition',stage='partitioning',worker_attempt=1);write_json(directory/'state.json',state)
        self.store._recover_worker_exit(job['id'],state,-9);retried=self.store.read(job['id'])
        self.assertEqual(retried['stage'],'queued');self.assertIn('一度だけ自動再試行',retried['message']);self.assertEqual(retried['error'],'終了コード -9')
        retried.update(stage='partitioning',worker_attempt=2);write_json(directory/'state.json',retried)
        self.store._recover_worker_exit(job['id'],retried,-9);failed=self.store.read(job['id'])
        self.assertEqual(failed['stage'],'partition_failed');self.assertIn('色分け処理',failed['message'])

    def test_completed_old_worker_never_overwrites_newer_queued_marker_operation(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id']);state=self.store.read(job['id'])
        state.update(operation='partition',stage='queued',worker_attempt=1);write_json(directory/'state.json',state)
        class Done:
            def poll(self):return 0
        class Running:
            def poll(self):return None
        self.store.children[job['id']]=Done()
        # The mocked process must not depend on a workstation's installed tools.
        from runtime_paths import python_path
        python_stub=python_path(directory)
        python_stub.parent.mkdir(parents=True);python_stub.touch()
        with patch('workflow_store.WORKSPACE',directory),patch('workflow_store.subprocess.Popen',return_value=Running()):self.store._tick()
        current=self.store.read(job['id']);self.assertEqual(current['stage'],'starting');self.assertNotIn('error',current)

    def test_machined_job_can_restore_immutable_partition_preview(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id'])
        manifest={'stage':'partition_preview','parts':[{'name':'part_00'},{'name':'part_01'}],
                  'partition_review':{'revision':'c'*32},'joint_candidates':[]}
        write_json(directory/'manifest.json',manifest);digest=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()
        state=self.store.read(job['id']);state.update(stage='mechanical_review',manifest='../api/jobs/'+job['id']+'/files/r_'+'b'*32+'.json',
            manifest_sha256='machined',partition_revision='c'*32,mechanical_revision='b'*32,prints=[{'plate':1}],error='old')
        write_json(directory/'state.json',state);path='/api/jobs/'+job['id']+'/repartition'
        headers={'Content-Type':'application/json','X-SkeleCAD-Token':'test-token'}
        self.assertEqual(self.request(path,'POST','{}',{'Content-Type':'application/json'})[0],403)
        status,body=self.request(path,'POST','{}',headers);self.assertEqual(status,202)
        restored=json.loads(body);self.assertEqual(restored['stage'],'appearance_ready');self.assertEqual(restored['manifest_sha256'],digest)
        self.assertEqual(restored['preview_part_count'],2);self.assertNotIn('mechanical_revision',restored);self.assertNotIn('error',restored)
        saved=self.store.read(job['id']);self.assertNotIn('prints',saved);self.assertEqual(saved['manifest'],'../api/jobs/'+job['id']+'/files/manifest.json')
        self.assertEqual(self.request(path,'POST','{}',headers)[0],400)

    def test_generation_progress_uses_bounded_worker_log_data(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id']);state=self.store.read(job['id'])
        state['settings']['progress_estimates_seconds'] = dict(preparing=35, diffusion=95, volume_decoding=125, analysing=10)
        state.update(stage='generating',pid=None);write_json(directory/'state.json',state)
        (directory/'inference.log').write_text('Diffusion Sampling::  50%|#####| 25/50 [00:47<00:47]\n',encoding='utf-8')
        progress=self.store.public(job['id'])['progress']
        self.assertEqual(progress['label'],'形を組み立て中');self.assertGreater(progress['percent'],10);self.assertLess(progress['percent'],50)
        (directory/'inference.log').write_text('Volume Decoding:  50%|#####| 3567/7134 [01:00<01:00]\n',encoding='utf-8')
        progress=self.store.public(job['id'])['progress']
        self.assertEqual(progress['label'],'立体の表面を作成中');self.assertGreater(progress['percent'],60);self.assertLess(progress['percent'],90)
        self.assertNotIn('inference.log',json.dumps(progress))

    def test_flash_decoding_progress_with_shorter_estimate(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id']);state=self.store.read(job['id'])
        state['settings']['progress_estimates_seconds'] = dict(preparing=45, diffusion=95, volume_decoding=7, analysing=10)
        state.update(stage='generating',pid=None);write_json(directory/'state.json',state)
        (directory/'inference.log').write_text('FlashVDM Volume Decoding: 100%|#####| 64/64 [00:01<00:00]\n',encoding='utf-8')
        progress=self.store.public(job['id'])['progress']
        self.assertEqual(progress['label'],'立体の表面を作成中')
        self.assertLess(progress['percent'],100)
        self.assertEqual(progress['remaining_seconds'],10)

    def test_hierarchical_progress_and_dense_fallback_estimate(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id']);state=self.store.read(job['id'])
        state['settings']['progress_estimates_seconds'] = dict(preparing=45, diffusion=95, volume_decoding=7, analysing=10)
        state.update(stage='generating',pid=None);write_json(directory/'state.json',state)
        log=directory/'inference.log'
        log.write_text('Hierarchical Surface [r96]: 50% 50/100\n',encoding='utf-8')
        progress=self.store.public(job['id'])['progress']
        self.assertEqual(progress['label'],'立体の表面を作成中')
        self.assertEqual(progress['remaining_seconds'],17)
        log.write_text('Hierarchical Surface [r96]: 50% 50/100\nFalling back to dense surface evaluation: invalid surface\nVolume Decoding: 50% 3567/7134\n',encoding='utf-8')
        progress=self.store.public(job['id'])['progress']
        self.assertGreater(progress['remaining_seconds'],60)
        self.assertLess(progress['percent'],100)

    def test_mechanical_artifact_is_bound_to_job_and_published_revision(self):
        job=self.store.create(image_bytes());directory=self.store.directory(job['id'])
        revision='a'*32;folder=directory/'machining'/revision;folder.mkdir(parents=True)
        write_json(folder/'manifest.json',{'parts':[{'name':'core_00'}]});(folder/'core_00.stl').write_bytes(b'model')
        artifact='r_'+revision+'_core_00.stl'
        with self.assertRaises(KeyError):self.store.artifact(job['id'],artifact)
        state=self.store.read(job['id']);state['mechanical_revision']=revision;write_json(directory/'state.json',state)
        self.assertEqual(self.store.artifact(job['id'],artifact).read_bytes(),b'model')
        for name in ('r_'+revision+'_core_01.stl','r_'+revision+'.stl','r_'+revision+'_core_00.json','r_'+'b'*32+'.json'):
            with self.assertRaises(KeyError):self.store.artifact(job['id'],name)


if __name__=='__main__':unittest.main()
