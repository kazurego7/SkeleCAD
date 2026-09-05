import json
import hashlib
import sys
import unittest
import tempfile
from pathlib import Path
import numpy as np
import trimesh

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from workflow_geometry import sphere_candidates,infer_branches,partition_preview,choose_root_candidate
from workflow_partition_worker import run as run_partition
from workflow_store import now,write_json
SETTINGS=json.loads((PROJECT/'config/parameters.json').read_text(encoding='utf-8'))['image_workflow']['joint_detection']


class CandidateTests(unittest.TestCase):
    def test_multi_limb_hub_is_root_even_when_a_wing_has_more_area(self):
        cores=[{'name':'wing_left','area_mm2':1000},{'name':'wing_right','area_mm2':1000},{'name':'body','area_mm2':450},
               {'name':'head','area_mm2':300},{'name':'tail','area_mm2':300}]
        links=[{'candidate':'left','cores':['body','wing_left']},{'candidate':'right','cores':['body','wing_right']},
               {'candidate':'neck','cores':['body','head']},{'candidate':'tail_root','cores':['body','tail']}]
        self.assertEqual(choose_root_candidate(cores,links),'body')

    def test_detects_translated_sphere_without_species_coordinates(self):
        sphere=trimesh.creation.icosphere(subdivisions=3,radius=6)
        sphere.apply_translation([20,-13,9])
        result=sphere_candidates(sphere,SETTINGS)
        self.assertEqual(len(result),1)
        self.assertLess(np.linalg.norm(np.array(result[0]['center'])-[20,-13,9]),.15)
        self.assertAlmostEqual(result[0]['radius_mm'],6,delta=.15)
        self.assertEqual(result[0]['status'],'proposal_requires_review')

    def test_cylinder_and_box_are_not_ball_joints(self):
        box=trimesh.creation.box([12,15,20])
        cylinder=trimesh.creation.cylinder(radius=6,height=30,sections=64)
        self.assertEqual(sphere_candidates(box,SETTINGS),[])
        self.assertEqual(sphere_candidates(cylinder,SETTINGS),[])

    def test_two_sided_junction_yields_lossless_preview_not_printable_parts(self):
        sphere=trimesh.creation.icosphere(subdivisions=3,radius=6)
        rod=trimesh.creation.cylinder(radius=2,height=34,sections=32)
        rod.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[0,1,0]))
        left=trimesh.creation.box([10,10,10]);left.apply_translation([-17,0,0])
        right=left.copy();right.apply_translation([34,0,0])
        mesh=trimesh.boolean.union([sphere,rod,left,right],engine='manifold')
        decoration=trimesh.creation.icosphere(subdivisions=1,radius=.2);decoration.apply_translation([-8,8,0])
        mesh=trimesh.util.concatenate([mesh,decoration])
        candidates=[{'name':'junction','center':[0,0,0],'radius_mm':6}]
        branches=infer_branches(mesh,candidates,SETTINGS)
        self.assertEqual(candidates[0]['classification'],'two_part_junction')
        with tempfile.TemporaryDirectory() as temporary:
            result=partition_preview(mesh,candidates,branches,SETTINGS,Path(temporary))
            self.assertEqual(len(result['parts']),2)
            self.assertEqual(result['assigned_faces'],len(mesh.faces))
            self.assertGreater(result['nearest_assigned_disconnected_faces'],0)
            assignment=np.load(Path(temporary)/'preview_assignment.npz')['face_part']
            self.assertTrue(np.all(assignment>=0));self.assertEqual(len(assignment),len(mesh.faces))
            self.assertFalse(result['print_ready'])
            self.assertTrue(all(not p['manufacturing_ready'] for p in result['parts']))

    def test_marker_constrained_worker_publishes_revision_and_preserves_every_face(self):
        sphere=trimesh.creation.icosphere(subdivisions=3,radius=6)
        rod=trimesh.creation.cylinder(radius=2,height=34,sections=32)
        rod.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[0,1,0]))
        left=trimesh.creation.box([10,10,10]);left.apply_translation([-17,0,0])
        right=left.copy();right.apply_translation([34,0,0])
        mesh=trimesh.boolean.union([sphere,rod,left,right],engine='manifold')
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);source=directory/'appearance.stl';mesh.export(source)
            manifest={'schema_version':1,'geometry':{'sha256':hashlib.sha256(source.read_bytes()).hexdigest()},
                      'parts':[{'filename':'appearance.stl'}],'part_segmentation':{'provider':'geometry_fallback'}}
            write_json(directory/'manifest.json',manifest);digest=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()
            state={'id':'a'*32,'stage':'queued','created_at':now(),'updated_at':now(),'source_manifest_sha256':digest,
                   'selected_markers':[{'name':'user_ab12','center':[0,0,0],'radius_mm':6,'status':'user_selected'},
                                       {'name':'user_cd34','center':[100,100,100],'radius_mm':3,'status':'user_selected'}]}
            write_json(directory/'state.json',state);run_partition(directory)
            result=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
            final=json.loads((directory/'state.json').read_text(encoding='utf-8'))
            self.assertEqual(final['stage'],'appearance_ready');self.assertEqual(final['preview_part_count'],2)
            self.assertEqual(result['partition_review']['constraint'],'only marker regions may create part boundaries')
            self.assertEqual(result['partition_review']['rejected_markers'],['user_cd34'])
            self.assertEqual([m['status'] for m in result['joint_candidates']],['user_selected','rejected_not_boundary'])
            self.assertEqual(sum(p['faces'] for p in result['parts']),len(trimesh.load(source,force='mesh').faces))
            self.assertTrue(all((directory/p['filename']).is_file() for p in result['parts']))


if __name__=='__main__':unittest.main()
