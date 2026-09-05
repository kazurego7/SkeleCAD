"""Run with the inference Python; synthetic fields need no model weights or GPU."""
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
if not (ROOT / '.tools/Hunyuan3D-2.1/hy3dshape').is_dir():
    raise unittest.SkipTest('Requires the local Hunyuan source checkout')
sys.path.insert(0, str(ROOT / 'skelecad/src'))
sys.path.insert(0, str(ROOT / '.tools/Hunyuan3D-2.1/hy3dshape'))
try:
    import torch
except ImportError as exc:
    raise unittest.SkipTest('Requires the inference environment') from exc
import numpy as np
import trimesh
from hunyuan_decoder import FullAttentionHierarchicalDecoder, export_mesh


class Sphere:
    def set_cross_attention_processor(self, processor):
        self.processor = processor

    def __call__(self, queries, latents):
        return ((queries.square().sum(dim=-1, keepdim=True) - .45**2) * 10)


class DecoderTests(unittest.TestCase):
    def test_refined_coordinates_and_surface_coverage(self):
        decoder = FullAttentionHierarchicalDecoder()
        grid = decoder(torch.zeros((1, 1, 1)), Sphere(), octree_resolution=32,
                       min_resolution=8, num_chunks=1000, enable_pbar=False)[0]
        xyz = torch.stack(torch.meshgrid(*[torch.linspace(-1.01, 1.01, 33)] * 3, indexing='ij'), dim=-1)
        expected = (xyz.square().sum(-1) - .45**2) * 10
        finite = torch.isfinite(grid)
        self.assertLess(float((grid[finite] - expected[finite]).abs().max()), 1e-5)
        # Every edge crossed by the reference sphere must have both endpoints evaluated.
        for axis in range(3):
            a = [slice(None)] * 3;b = a.copy()
            a[axis] = slice(None, -1);b[axis] = slice(1, None)
            crossing = expected[tuple(a)] * expected[tuple(b)] < 0
            self.assertTrue(torch.all((finite[tuple(a)] & finite[tuple(b)])[crossing]))
        self.assertLess(int(finite.sum()), grid.numel())

    def test_failed_acceleration_reuses_same_latent_for_dense_fallback(self):
        dense = object();latent = object();calls = []
        broken = trimesh.creation.box();broken.update_faces(np.arange(len(broken.faces) - 1))
        closed = trimesh.creation.box()
        pipeline = SimpleNamespace(vae=SimpleNamespace(volume_decoder=dense))
        def export(value, **kwargs):
            calls.append((value, pipeline.vae.volume_decoder))
            return [broken if len(calls) == 1 else closed]
        pipeline._export = export
        result, actual, reason = export_mesh(pipeline, latent, 'hierarchical_full', 384, 8000)
        self.assertIs(result, closed)
        self.assertEqual(actual, 'vanilla')
        self.assertIn('surface checks', reason)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(value is latent for value, _ in calls))
        self.assertIs(calls[1][1], dense)


if __name__ == '__main__':
    unittest.main()
