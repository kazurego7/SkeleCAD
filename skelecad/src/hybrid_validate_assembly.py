"""Validate collisions in the assembled hybrid appearance/joint mesh set."""

from __future__ import annotations

import itertools
import json
from pathlib import Path

import trimesh
from hybrid_context import HYBRID


ROOT = Path(__file__).resolve().parents[1]
PARTS = HYBRID / "parts"
REPORT = ROOT / "build" / "reports" / "hybrid_assembly_collision.json"
NAMES = (
    "head",
    "torso",
    "arm_left",
    "arm_right",
    "leg_left",
    "leg_right",
    "foot_left",
    "foot_right",
    "tail",
)
MATING = {
    frozenset(('head','torso')):'neck',
    frozenset(('arm_left','torso')):'shoulder_left',
    frozenset(('arm_right','torso')):'shoulder_right',
    frozenset(('leg_left','torso')):'hip_left',
    frozenset(('leg_right','torso')):'hip_right',
    frozenset(('foot_left','leg_left')):'ankle_left',
    frozenset(('foot_right','leg_right')):'ankle_right',
    frozenset(('tail','torso')):'tail_root',
}


def bounds_overlap(a, b):
    return bool(((a.bounds[0] <= b.bounds[1]) & (b.bounds[0] <= a.bounds[1])).all())


def main():
    meshes = {}
    for name in NAMES:
        mesh = trimesh.load_mesh(PARTS / f"{name}.stl")
        mesh.fix_normals(multibody=True)
        meshes[name] = mesh

    pairs = []
    for left_name, right_name in itertools.combinations(NAMES, 2):
        left = meshes[left_name]
        right = meshes[right_name]
        volume = 0.0
        if bounds_overlap(left, right):
            overlap = trimesh.boolean.intersection([left, right], engine="manifold")
            volume = abs(float(overlap.volume)) if len(overlap.faces) else 0.0
        joint=MATING.get(frozenset((left_name,right_name)))
        intentional=0.0
        if joint:
            shell=trimesh.load_mesh(HYBRID/'joint_tools'/f'{joint}_socket_shell.stl')
            ball=trimesh.load_mesh(HYBRID/'joint_tools'/f'{joint}_ball_add.stl')
            if bounds_overlap(shell,ball):
                expected=trimesh.boolean.intersection([shell,ball],engine='manifold')
                intentional=abs(float(expected.volume)) if len(expected.faces) else 0.0
        excess=max(0.0,volume-intentional)
        pairs.append(
            {
                "parts": [left_name, right_name],
                "overlap_volume_mm3": volume,
                "intentional_joint_preload_mm3": intentional,
                "excess_overlap_mm3": excess,
                "clear": excess <= 0.30,
            }
        )
    result = {
        "maximum_allowed_excess_overlap_mm3": 0.30,
        "parts": list(NAMES),
        "pairs_checked": len(pairs),
        "collision_count": sum(not item["clear"] for item in pairs),
        "collisions": [item for item in pairs if not item["clear"]],
        "passed": all(item["clear"] for item in pairs),
    }
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise RuntimeError("Hybrid assembly collision validation failed")


if __name__ == "__main__":
    main()
