"""Generate a local image-to-3D appearance mesh with Hunyuan3D 2.1.

This produces appearance geometry only. Mechanical joints remain authored and
dimensioned in FreeCAD.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--hunyuan-root", required=True, type=Path)
    parser.add_argument("--model", default="tencent/Hunyuan3D-2.1")
    parser.add_argument("--seed", default=3407, type=int)
    parser.add_argument("--steps", default=50, type=int)
    parser.add_argument("--guidance", default=5.0, type=float)
    parser.add_argument("--resolution", default=384, type=int)
    parser.add_argument("--num-chunks", default=8000, type=int)
    parser.add_argument("--decoder", choices=("vanilla", "flashvdm", "hierarchical_full"), default="vanilla")
    parser.add_argument("--source-original", type=Path)
    args = parser.parse_args()
    if args.num_chunks <= 0:
        parser.error("--num-chunks must be positive")
    return args


def main() -> None:
    args = parse_args()
    package_root = args.hunyuan_root / "hy3dshape"
    if not package_root.is_dir():
        raise SystemExit(f"Hunyuan shape package not found: {package_root}")
    if not args.input.is_file():
        raise SystemExit(f"Input image not found: {args.input}")
    if args.output.exists():
        raise SystemExit(f"Refusing to replace an existing generation: {args.output}")
    started_at = datetime.now(timezone.utc).isoformat()
    started = time.perf_counter()
    input_sha256 = hashlib.sha256(args.input.read_bytes()).hexdigest()
    original = args.source_original or args.input
    original_sha256 = hashlib.sha256(original.read_bytes()).hexdigest()
    print(f"NEW INFERENCE started={started_at} source_sha256={original_sha256}", flush=True)

    sys.path.insert(0, str(package_root))

    import torch
    from PIL import Image
    from hy3dshape.pipelines import Hunyuan3DDiTFlowMatchingPipeline

    if not torch.cuda.is_available():
        raise SystemExit("CUDA GPU is required for this local generation run")

    image = Image.open(args.input).convert("RGBA")
    pipeline = Hunyuan3DDiTFlowMatchingPipeline.from_pretrained(
        args.model,
        device="cuda",
        dtype=torch.float16,
    )
    generator = torch.Generator(device="cuda").manual_seed(args.seed)
    torch.cuda.synchronize()
    loaded = time.perf_counter()
    torch.cuda.reset_peak_memory_stats()
    latents = pipeline(
        image=image,
        num_inference_steps=args.steps,
        guidance_scale=args.guidance,
        generator=generator,
        octree_resolution=args.resolution,
        num_chunks=args.num_chunks,
        output_type="latent",
    )
    from hunyuan_decoder import export_mesh
    with torch.inference_mode():
        mesh, actual_decoder, fallback_reason = export_mesh(
            pipeline, latents, args.decoder, args.resolution, args.num_chunks,
        )
    torch.cuda.synchronize()
    generated = time.perf_counter()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(args.output)
    report = {
        "generator": "Tencent Hunyuan3D 2.1 shape model",
        "started_at_utc": started_at,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_original": str(original.resolve()),
        "source_original_sha256": original_sha256,
        "input_sha256": input_sha256,
        "output_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "model": args.model,
        "input": str(args.input.resolve()),
        "output": str(args.output.resolve()),
        "seed": args.seed,
        "steps": args.steps,
        "guidance": args.guidance,
        "octree_resolution": args.resolution,
        "num_chunks": args.num_chunks,
        "decoder": args.decoder,
        "actual_decoder": actual_decoder,
        "decoder_fallback_reason": fallback_reason,
        "load_seconds": loaded - started,
        "inference_seconds": generated - loaded,
        "total_seconds": time.perf_counter() - started,
        "peak_allocated_mib": torch.cuda.max_memory_allocated() / 1024**2,
        "peak_reserved_mib": torch.cuda.max_memory_reserved() / 1024**2,
        "vertices": int(len(mesh.vertices)),
        "faces": int(len(mesh.faces)),
        "watertight": bool(mesh.is_watertight),
        "cuda_device": torch.cuda.get_device_name(0),
    }
    args.output.with_suffix(".json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
