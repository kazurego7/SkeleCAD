"""Compare decoders using the same latent, without changing viewer jobs."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--hunyuan-root', type=Path, required=True)
    parser.add_argument('--seeds', type=int, nargs='+', default=[3407])
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    if (args.output_dir/'benchmark.json').exists():
        parser.error('Use a fresh output directory to preserve prior results')
    sys.path.insert(0, str(args.hunyuan_root/'hy3dshape'))
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'src'))
    import torch
    from PIL import Image
    from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
    from hunyuan_decoder import export_mesh
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        'tencent/Hunyuan3D-2.1', device='cuda', dtype=torch.float16)
    dense_decoder = pipeline.vae.volume_decoder
    report = dict(input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),
                  steps=50, guidance=5., resolution=384, num_chunks=8000,
                  cuda_device=torch.cuda.get_device_name(0), runs=[])
    for seed in args.seeds:
        torch.cuda.synchronize();start=time.perf_counter()
        latent = pipeline(image=Image.open(args.input).convert('RGBA'), num_inference_steps=50,
                          guidance_scale=5., generator=torch.Generator(device='cuda').manual_seed(seed),
                          output_type='latent')
        torch.cuda.synchronize();diffusion=time.perf_counter()-start
        torch.save(latent.cpu(), args.output_dir/f'{seed}-latent.pt')
        for decoder in ('vanilla', 'hierarchical_full', 'flashvdm'):
            pipeline.vae.volume_decoder = dense_decoder
            from hy3dshape.models.autoencoders.attention_processors import CrossAttentionProcessor
            pipeline.vae.geo_decoder.set_cross_attention_processor(CrossAttentionProcessor())
            torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize()
            start=time.perf_counter()
            with torch.inference_mode():
                mesh, actual, reason = export_mesh(pipeline, latent, decoder, 384, 8000)
            torch.cuda.synchronize();seconds=time.perf_counter()-start
            filename=f'{seed}-{decoder}.glb';mesh.export(args.output_dir/filename)
            row=dict(seed=seed, decoder=decoder, actual_decoder=actual, fallback_reason=reason,
                     diffusion_seconds=diffusion, surface_seconds=seconds, inference_seconds=seconds+diffusion,
                     peak_allocated_mib=torch.cuda.max_memory_allocated()/1024**2,
                     peak_reserved_mib=torch.cuda.max_memory_reserved()/1024**2,
                     watertight=bool(mesh.is_watertight), faces=len(mesh.faces), file=filename)
            report['runs'].append(row)
            (args.output_dir/'benchmark.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            print(json.dumps(row),flush=True)


if __name__ == '__main__':
    main()
