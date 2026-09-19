import json
import sys
import unittest
from pathlib import Path
import numpy as np
import trimesh
PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from workflow_connectivity import repair_connectivity
from workflow_symmetry import symmetrize_yz
from finish_cut_edges import solid


class ConnectivityTests(unittest.TestCase):
    def setUp(self):
        self.cfg = json.loads((PROJECT/'config/parameters.json').read_text())['image_workflow']['connectivity_repair']

    def test_closed_connection_preserves_source_and_is_idempotent(self):
        a=trimesh.creation.icosphere(subdivisions=2,radius=3)
        b=a.copy();b.apply_translation([7,0,0]);source=trimesh.util.concatenate([a,b])
        vertices=source.vertices.copy();result,report=repair_connectivity(source,self.cfg)
        self.assertTrue(result.is_volume);self.assertEqual(len(result.split()),1)
        self.assertLess(abs((solid(source)-solid(result)).volume()),.001)
        np.testing.assert_array_equal(source.vertices,vertices)
        second,again=repair_connectivity(result,self.cfg)
        self.assertEqual(again['bridges'],[])
        np.testing.assert_array_equal(result.vertices,second.vertices)

    def test_far_components_are_never_discarded(self):
        a=trimesh.creation.box();b=a.copy();b.apply_translation([10,0,0])
        source=trimesh.util.concatenate([a,b]);result,report=repair_connectivity(source,self.cfg)
        self.assertFalse(report['fully_connected']);self.assertEqual(report['output_components'],2)
        np.testing.assert_array_equal(source.vertices,result.vertices)

    def test_cavities_survive_symmetry_and_connection(self):
        a=trimesh.creation.icosphere(subdivisions=2,radius=3)
        cavity=trimesh.creation.icosphere(subdivisions=2,radius=1);cavity.invert()
        b=a.copy();b.apply_translation([0,7,0])
        source=symmetrize_yz(trimesh.util.concatenate([a,cavity,b]),'positive_x')
        self.assertEqual(sum(int(p.volume<0) for p in source.split()),1)
        result,report=repair_connectivity(source,self.cfg,mirror_yz=True)
        self.assertEqual(report['input_components'],2);self.assertEqual(report['output_components'],1)
        self.assertLess(report['filled_cavity_mm3'],.001)
        self.assertEqual(sum(int(p.volume<0) for p in result.split()),1)
        reflected=solid(result).transform([[-1.,0.,0.,0.],[0.,1.,0.,0.],[0.,0.,1.,0.]])
        self.assertLess(abs((solid(result)-reflected).volume()),.001)

    def test_open_surface_is_rejected(self):
        a=trimesh.creation.box();a.update_faces(np.arange(11))
        with self.assertRaises(ValueError):repair_connectivity(a,self.cfg)

    def test_disabled_does_not_change_mesh(self):
        a=trimesh.creation.box();result,report=repair_connectivity(a,{'enabled':False})
        np.testing.assert_array_equal(a.vertices,result.vertices)
        self.assertFalse(report['enabled'])


if __name__=='__main__':unittest.main()
