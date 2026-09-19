"""Bounded same-image tuning; reuse loaded weights and latents across resolutions."""
import argparse
import hashlib
import json
import sys
import time
from pathlib import Path


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--hunyuan-root',type=Path,required=True)
    parser.add_argument('--seed',type=int,default=3407)
    parser.add_argument('--cpu-threads',type=int,default=4)
    args=parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=False)
    start=time.perf_counter()
    sys.path.insert(0,str(args.hunyuan_root/'hy3dshape'))
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
    import torch
    torch.set_num_threads(args.cpu_threads)
    from PIL import Image
    from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline
    from hunyuan_decoder import FullAttentionHierarchicalDecoder
    pipeline=Hunyuan3DDiTFlowMatchingPipeline.from_pretrained('tencent/Hunyuan3D-2.1',device='cuda',dtype=torch.float16)
    image=Image.open(args.input).convert('RGBA')
    load_seconds=time.perf_counter()-start
    image_hash=hashlib.sha256(args.input.read_bytes()).hexdigest()
    results=[]
    for steps,resolutions in ((20,(512,640)),(30,(640,))):
        torch.cuda.synchronize();diffusion_start=time.perf_counter()
        latents=pipeline(image=image,num_inference_steps=steps,guidance_scale=5.,
                         generator=torch.Generator(device='cuda').manual_seed(args.seed),output_type='latent')
        torch.cuda.synchronize();diffusion_seconds=time.perf_counter()-diffusion_start
        for resolution in resolutions:
            output=args.output/f'r{resolution}_s{steps}';output.mkdir()
            report={'model':'tencent/Hunyuan3D-2.1','input_sha256':image_hash,'seed':args.seed,
                    'steps':steps,'guidance':5.,'octree_resolution':resolution,'num_chunks':8000,
                    'cpu_threads':args.cpu_threads,'actual_decoder':'hierarchical_full',
                    'shared_batch_load_seconds':load_seconds,'diffusion_seconds':diffusion_seconds,
                    'timing_scope':'same loaded model; latent reused for equal step count'}
            try:
                torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats()
                pipeline.vae.volume_decoder=FullAttentionHierarchicalDecoder()
                decode_start=time.perf_counter()
                with torch.inference_mode():
                    mesh=pipeline._export(latents,output_type='trimesh',octree_resolution=resolution,num_chunks=8000)[0]
                torch.cuda.synchronize()
                report['decode_seconds']=time.perf_counter()-decode_start
                report['inference_seconds']=diffusion_seconds+report['decode_seconds']
                report['peak_allocated_mib']=torch.cuda.max_memory_allocated()/1024**2
                report['peak_reserved_mib']=torch.cuda.max_memory_reserved()/1024**2
                mesh.export(output/'inference.glb')
                report.update(faces=len(mesh.faces),output_sha256=hashlib.sha256((output/'inference.glb').read_bytes()).hexdigest(),success=True)
                del mesh
            except Exception as exc:
                report.update(success=False,error=f'{type(exc).__name__}: {exc}')
            (output/'inference.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
            results.append(report)
            (args.output/'summary.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
            print(json.dumps(report),flush=True)
        del latents


if __name__=='__main__':main()
