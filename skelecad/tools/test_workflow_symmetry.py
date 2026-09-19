import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import trimesh

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
sys.path.insert(0,str(PROJECT/'tools'))
from workflow_symmetry import symmetrize_yz
from workflow_store import now,write_json
from workflow_symmetry_worker import run as run_worker


class SymmetryTests(unittest.TestCase):
    def test_selected_half_is_mirrored_exactly_across_yz(self):
        body=trimesh.creation.icosphere(subdivisions=3,radius=8)
        right=trimesh.creation.icosphere(subdivisions=2,radius=3);right.apply_translation([7,2,1])
        left=trimesh.creation.icosphere(subdivisions=2,radius=2);left.apply_translation([-7,-2,-1])
        mesh=trimesh.boolean.union([body,right,left],engine='manifold')
        result=symmetrize_yz(mesh,'positive_x')
        self.assertTrue(result.is_volume)
        self.assertAlmostEqual(result.bounds[0,0],-result.bounds[1,0],places=4)
        positive=np.asarray(result.vertices[result.vertices[:,0]>1e-4]);negative=np.asarray(result.vertices[result.vertices[:,0]<-1e-4])
        reflected=positive.copy();reflected[:,0]*=-1
        from scipy.spatial import cKDTree
        self.assertLess(cKDTree(negative).query(reflected)[0].max(),2e-4)

    def test_rejects_open_surface_instead_of_falling_back(self):
        open_mesh=trimesh.creation.box([10,10,10]);open_mesh.update_faces(np.arange(len(open_mesh.faces)-1))
        with self.assertRaisesRegex(ValueError,'閉じた立体'):
            symmetrize_yz(open_mesh,'negative_x')

    def test_worker_keeps_original_and_publishes_only_valid_revision(self):
        body=trimesh.creation.icosphere(subdivisions=2,radius=8)
        bump=trimesh.creation.icosphere(subdivisions=1,radius=2);bump.apply_translation([7,0,0])
        mesh=trimesh.boolean.union([body,bump],engine='manifold')
        dust=trimesh.creation.icosphere(subdivisions=2,radius=.3)
        dust.apply_translation([15,0,0])
        mesh=trimesh.util.concatenate([mesh,dust])
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary);appearance=directory/'appearance.stl';mesh.export(appearance)
            shape_hash=hashlib.sha256(appearance.read_bytes()).hexdigest()
            manifest={'schema_version':1,'id':'a'*32,'name':'test','stage':'appearance_review','source_sha256':'source',
                      'target_length_mm':120,'preprocessing':{},'parts':[{'filename':'appearance.stl'}],
                      'joint_candidates':[],'branch_graph':{},'geometry':{'sha256':shape_hash},
                      'partition_controls':{},'print_ready':False}
            write_json(directory/'manifest.json',manifest);manifest_hash=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest()
            state={'id':'a'*32,'name':'test','stage':'queued','operation':'symmetry','source_sha256':'source',
                   'source_manifest_sha256':manifest_hash,'symmetry_source_side':'positive_x',
                   'created_at':now(),'updated_at':now()}
            write_json(directory/'state.json',state);run_worker(directory)
            published=json.loads((directory/'state.json').read_text(encoding='utf-8'))
            self.assertEqual(published['stage'],'appearance_ready');self.assertTrue(published['appearance_symmetry']['active'])
            self.assertEqual(hashlib.sha256((directory/'symmetry/original/appearance.stl').read_bytes()).hexdigest(),shape_hash)
            result=trimesh.load(appearance,force='mesh',process=True);self.assertTrue(result.is_volume)
            self.assertAlmostEqual(result.bounds[0,0],-result.bounds[1,0],places=4)
            revised=json.loads((directory/'manifest.json').read_text(encoding='utf-8'))
            self.assertEqual(revised['geometry']['isolated_speck_cleanup']['removed_components'],2)
            self.assertEqual(sum(part.volume>0 for part in result.split()),1)
            # Re-selecting a side must clean the historical original again.
            published.update(source_manifest_sha256=hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest(),
                             symmetry_source_side='positive_x')
            write_json(directory/'state.json',published);run_worker(directory)
            repeated=trimesh.load(appearance,force='mesh')
            self.assertEqual(sum(part.volume>0 for part in repeated.split()),1)


if __name__=='__main__':unittest.main()
