"""Extract a neutral-background object's alpha mask for image-to-3D inference.

The original RGB pixels are preserved. This deterministic colour segmentation
is specific to the warm-bone reference on a neutral white/grey background.
"""
import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    original = args.output_dir / "source_original.png"
    output = args.output_dir / "inference_rgba.png"
    if original.exists() or output.exists():
        raise RuntimeError("Use a new input directory; original references are immutable")
    shutil.copy2(args.input, original)
    rgb = np.asarray(Image.open(original).convert("RGB"))
    warm = rgb[:, :, 0].astype(float) - rgb[:, :, 2].astype(float)
    mask = (warm >= 11).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, connectivity=8)
    keep = np.zeros(count, dtype=np.uint8)
    keep[1:] = (stats[1:, cv2.CC_STAT_AREA] >= 40).astype(np.uint8)
    mask = keep[labels] * 255
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    alpha = cv2.GaussianBlur(mask, (3, 3), 0.5)
    Image.fromarray(np.dstack((rgb, alpha))).save(output)
    composite = (rgb * (alpha[:, :, None] / 255) +
                 np.array([65, 70, 78]) * (1 - alpha[:, :, None] / 255)).astype(np.uint8)
    preview = Image.fromarray(composite)
    preview.thumbnail((960, 720))
    preview.save(args.output_dir / "input_mask_review.jpg", quality=78)
    report = {
        "source_original": str(args.input.resolve()),
        "archived_original": str(original.resolve()),
        "source_original_sha256": hashlib.sha256(original.read_bytes()).hexdigest(),
        "inference_input": str(output.resolve()),
        "inference_sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "original RGB, warm-colour alpha mask, no generated/repainted image pixels",
        "red_minus_blue_threshold": 11,
        "minimum_component_pixels": 40,
        "foreground_fraction": float((alpha > 127).mean()),
    }
    (args.output_dir / "provenance.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
