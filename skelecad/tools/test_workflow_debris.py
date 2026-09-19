import sys
import unittest
from pathlib import Path
import json
import tempfile
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
from workflow_debris import remove_isolated_specks


class SpeckTests(unittest.TestCase):
    def test_remote_dense_dust_does_not_shrink_subject(self):
        from workflow_worker import normalize_mesh
        body = trimesh.creation.box([120, 20, 20])
        dust = trimesh.creation.icosphere(subdivisions=3, radius=.3)
        dust.apply_translation([1000, 0, 0])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trimesh.util.concatenate([body, dust]).export(root/'source.stl')
            report = normalize_mesh(root/'source.stl', root/'result.stl', 120,
                                    connectivity={'enabled': False})
            result = trimesh.load(root/'result.stl', force='mesh')
            self.assertEqual(report['isolated_speck_cleanup']['removed_components'], 1)
            self.assertAlmostEqual(max(result.extents), 120)
            self.assertAlmostEqual(result.volume, body.volume)

    def test_detached_head_is_included_in_physical_scale(self):
        from workflow_worker import normalize_mesh
        body = trimesh.creation.box([80, 20, 20])
        head = trimesh.creation.box([20, 20, 20])
        head.apply_translation([70, 0, 0])
        dust = trimesh.creation.icosphere(subdivisions=3, radius=.37)
        dust.apply_translation([1000, 0, 0])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trimesh.util.concatenate([body, head, dust]).export(root/'source.stl')
            report = normalize_mesh(root/'source.stl', root/'result.stl', 120,
                                    connectivity={'enabled': False})
            result = trimesh.load(root/'result.stl', force='mesh')
            self.assertEqual(report['isolated_speck_cleanup']['removed_components'], 1)
            self.assertAlmostEqual(max(result.extents), 120)
            self.assertAlmostEqual(result.volume, body.volume+head.volume)

    def test_density_anatomy_and_cavity(self):
        cfg = json.loads((Path(__file__).resolve().parents[1]/'config/parameters.json').read_text())['image_workflow']['debris_cleanup']
        body = trimesh.creation.box([10, 10, 10])
        cavity = trimesh.creation.icosphere(subdivisions=1, radius=.3)
        cavity.invert()
        near = trimesh.creation.icosphere(subdivisions=2, radius=.3)
        near.apply_translation([6, 0, 0])
        anatomy = trimesh.creation.box([3, 3, 3])
        anatomy.apply_translation([15, 0, 0])
        for density in (1, 3):
            dust = trimesh.creation.icosphere(subdivisions=density, radius=.3)
            dust.apply_translation([0, 10, 0])
            source = trimesh.util.concatenate([body, cavity, near, anatomy, dust])
            result, report = remove_isolated_specks(source, cfg)
            self.assertEqual(report['removed_components'], 1)
            self.assertEqual(report['removed_faces'], len(dust.faces))
            self.assertAlmostEqual(result.volume, body.volume+cavity.volume+near.volume+anatomy.volume)
            self.assertTrue(result.is_watertight)
            self.assertEqual(sum(p.volume < 0 for p in result.split()), 1)


if __name__ == '__main__':
    unittest.main()
