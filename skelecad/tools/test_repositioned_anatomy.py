"""Regression checks for local cuts, anatomy preservation and rigid placement."""
from pathlib import Path
import sys
import unittest
import numpy as np
import trimesh

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from hybrid_context import H
from validate_repositioned_anatomy import outside_disc, partition_protected, volume


class RepositionedAnatomyTests(unittest.TestCase):
    def test_cut_permission_is_a_disc_not_a_sphere(self):
        points=np.array([[0,0,0],[0,2,0],[8,0,0],[5,0,0]],dtype=float)
        self.assertEqual(outside_disc(points,[0,0,0],[0,1,0],7,1.2).tolist(),[False,True,True,False])

    def test_original_partition_centres_are_not_joint_centres(self):
        self.assertNotEqual(H['partition_centers_mm']['hip_left'],H['hip_center_left_mm'])
        self.assertEqual(partition_protected(np.array([H['partition_centers_mm']['hip_left']])).tolist(),[False])

    def test_feet_and_ankles_follow_legs(self):
        for side in ['left','right']:
            move=np.array(H['part_translation_mm']['leg_'+side])
            np.testing.assert_array_equal(move,H['part_translation_mm']['foot_'+side])
            np.testing.assert_array_equal(np.array(H['partition_centers_mm']['ankle_'+side])+move,H['ankle_center_'+side+'_mm'])

    def test_old_subtractive_clearance_is_detectable(self):
        original=trimesh.creation.box(extents=[10,10,10])
        erased=trimesh.boolean.difference([original,trimesh.creation.icosphere(radius=2)],engine='manifold')
        missing=trimesh.boolean.difference([original,erased],engine='manifold')
        self.assertGreater(volume(missing),30)
        for name in ['shoulder_left','shoulder_right','hip_left','hip_right']:
            self.assertIn(name,H['preserve_anatomy_connections'])

    def test_all_limb_changes_are_mirrored(self):
        mirror=np.array([1,-1,1])
        for part in ['arm','leg','foot']:
            np.testing.assert_array_equal(np.array(H['part_translation_mm'][part+'_left'])*mirror,H['part_translation_mm'][part+'_right'])
        for joint in ['shoulder','hip','ankle']:
            np.testing.assert_array_equal(np.array(H[joint+'_center_left_mm'])*mirror,H[joint+'_center_right_mm'])
        specs={s['name']:s for s in H['connections']}
        for joint in ['shoulder','hip','ankle']:
            for key in ['source_support','target_support','mouth_direction']:
                np.testing.assert_array_equal(np.array(specs[joint+'_left'][key])*mirror,specs[joint+'_right'][key])

    def test_compact_roots_and_local_tail_permission(self):
        specs={s['name']:s for s in H['connections']}
        for side in ['left','right']:
            self.assertEqual(specs['shoulder_'+side]['source_support_mode'],'embedded_stem')
        self.assertGreater(H['compact_socket_min_contact_mm3'],0)
        self.assertEqual([s['part'] for s in H['local_reliefs']],['tail'])
        spec=H['local_reliefs'][0]
        self.assertEqual(spec['box_min_mm'][1],-spec['box_max_mm'][1])
        self.assertEqual(spec['shape'],'sloped_relief')
        self.assertGreaterEqual(spec['edge_radius_mm'],1)


if __name__=='__main__':unittest.main()
