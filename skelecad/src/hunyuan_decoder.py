"""Full-attention hierarchical surface evaluation for the pinned Hunyuan 2.1.

Retains the requested grid resolution and evaluates selected coordinates in FP32
before converting queries to the model dtype. No adaptive KV selection is used.
"""
import numpy as np
import torch
import torch.nn.functional as functional
from tqdm import tqdm


def expand(mask, count=1):
    for _ in range(count):
        mask = functional.max_pool3d(mask.float()[None, None], 3, stride=1, padding=1)[0, 0] > 0
    return mask


class FullAttentionHierarchicalDecoder:
    @torch.inference_mode()
    def __call__(self, latents, geo_decoder, bounds=1.01, num_chunks=8000,
                 mc_level=0., octree_resolution=384, min_resolution=63,
                 enable_pbar=True, **kwargs):
        from hy3dshape.models.autoencoders.attention_processors import CrossAttentionProcessor
        from hy3dshape.models.autoencoders.volume_decoders import (
            generate_dense_grid_points, extract_near_surface_volume_fn,
        )
        if latents.shape[0] != 1:
            raise ValueError("Hierarchical decoding currently supports one image at a time")
        if num_chunks < 1 or octree_resolution < 1:
            raise ValueError("Positive chunk size and resolution are required")
        geo_decoder.set_cross_attention_processor(CrossAttentionProcessor())
        levels = [int(octree_resolution)]
        while levels[-1] // 2 >= min_resolution:
            levels.append(levels[-1] // 2)
        levels.reverse()
        if isinstance(bounds, (float, int)):
            bounds = [-bounds] * 3 + [bounds] * 3
        lower = np.asarray(bounds[:3], dtype=np.float64)
        extent = np.asarray(bounds[3:], dtype=np.float64) - lower

        def evaluate(points, resolution):
            pieces = []
            for start in tqdm(range(0, len(points), num_chunks),
                              desc=f"Hierarchical Surface [r{resolution}]", disable=not enable_pbar):
                query = points[start:start + num_chunks].to(dtype=latents.dtype)[None]
                pieces.append(geo_decoder(queries=query, latents=latents).reshape(-1))
            if not pieces:
                raise ValueError("No surface queries; use the dense decoder")
            return torch.cat(pieces)

        points, shape, _ = generate_dense_grid_points(lower, lower + extent, levels[0], indexing='ij')
        points = torch.as_tensor(points, device=latents.device, dtype=latents.dtype).reshape(-1, 3)
        grid = evaluate(points, levels[0]).reshape(tuple(shape))
        for level in levels[1:]:
            near = extract_near_surface_volume_fn(grid, mc_level).bool() | (grid.abs() < .95)
            intermediate = level != levels[-1]
            if intermediate:
                near = expand(near)
            indices = torch.where(near)
            mask = torch.zeros((level + 1,) * 3, device=latents.device, dtype=torch.bool)
            mask[tuple(axis * 2 for axis in indices)] = True
            mask = expand(mask, 1 if intermediate else 2)
            selected = torch.where(mask)
            # Integer grid indices must never determine the coordinate dtype:
            # using integer dtype here truncates extent / level to zero.
            points = torch.stack(selected, dim=1).float()
            points = points * torch.as_tensor(extent / level, device=latents.device, dtype=torch.float32)
            points += torch.as_tensor(lower, device=latents.device, dtype=torch.float32)
            values = evaluate(points, level)
            grid = torch.full(mask.shape, float('nan'), device=latents.device, dtype=latents.dtype)
            grid[selected] = values
        return grid[None]


def export_mesh(pipeline, latents, decoder, resolution, num_chunks):
    """Fall back to dense evaluation of the same latent if acceleration fails."""
    original = pipeline.vae.volume_decoder
    if decoder == 'hierarchical_full':
        pipeline.vae.volume_decoder = FullAttentionHierarchicalDecoder()
    elif decoder == 'flashvdm':
        pipeline.enable_flashvdm(replace_vae=False)
    options = dict(output_type='trimesh', octree_resolution=resolution, num_chunks=num_chunks)
    reason = None
    try:
        mesh = pipeline._export(latents, **options)[0]
        if decoder == 'hierarchical_full':
            # Match the worker's degenerate-face cleanup before judging closure.
            probe = mesh.copy()
            probe.merge_vertices()
            probe.update_faces(probe.nondegenerate_faces(height=1e-10))
            probe.update_faces(probe.unique_faces())
            probe.remove_unreferenced_vertices()
            if (not len(probe.faces) or not np.isfinite(probe.vertices).all()
                    or not probe.is_watertight or not probe.is_winding_consistent):
                raise ValueError('Accelerated mesh failed finite/closed/oriented surface checks')
        return mesh, decoder, None
    except Exception as exc:
        if decoder != 'hierarchical_full':
            raise
        reason = f'{type(exc).__name__}: {exc}'
    pipeline.vae.volume_decoder = original
    torch.cuda.empty_cache()
    print(f'Falling back to dense surface evaluation: {reason}', flush=True)
    return pipeline._export(latents, **options)[0], 'vanilla', reason
