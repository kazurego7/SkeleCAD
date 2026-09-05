"""Validate provenance/topology and package the new appearance, not its mechanics."""
import hashlib
import json
from pathlib import Path

import FreeCAD as App
import Mesh

from validate_stl import analyse

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    params = json.loads((ROOT / "config/parameters.json").read_text(encoding="utf-8"))
    candidate = params.get("appearance_candidate")
    if not candidate:
        print("No separate appearance candidate configured")
        return
    mesh_path = ROOT / candidate["mesh"]
    generation_path = ROOT / candidate["generation_report"]
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    original_path = ROOT / candidate["source_image"]
    source_matches = sha256(original_path) == candidate["source_sha256"] == generation["source_original_sha256"]
    raw_matches = sha256(Path(generation["output"])) == generation["output_sha256"]
    topology = analyse(mesh_path)
    passed = source_matches and raw_matches and topology["passed"]
    report = {
        "status": "appearance_review_only",
        "passed": passed,
        "source_hash_matches": source_matches,
        "raw_generation_hash_matches": raw_matches,
        "started_at_utc": generation["started_at_utc"],
        "finished_at_utc": generation["finished_at_utc"],
        "source_image": candidate["source_image"],
        "source_sha256": candidate["source_sha256"],
        "mesh": candidate["mesh"],
        "mesh_sha256": sha256(mesh_path),
        "topology": topology,
        "joints_integrated": False,
        "cad_solid_validation": "not applicable: appearance is a mesh feature, not a parametric solid",
        "assembly_collision_validation": "not performed: not partitioned into articulated parts",
        "calculix_validation": "not performed on this new appearance; old specimen results do not apply",
        "print_ready": False,
    }
    report_path = ROOT / "build/reports/appearance_candidate.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if not passed:
        raise RuntimeError("New appearance provenance or topology validation failed")
    doc = App.newDocument("NewImageTo3DReference")
    feature = doc.addObject("Mesh::Feature", "NewAppearance")
    feature.Label = "NEW image-to-3D 2026-08-30 / mechanical joints not yet integrated"
    feature.Mesh = Mesh.Mesh(str(mesh_path))
    feature.addProperty("App::PropertyString", "SourceSHA256")
    feature.SourceSHA256 = candidate["source_sha256"]
    feature.addProperty("App::PropertyString", "ReviewStatus")
    feature.ReviewStatus = "Appearance only; not a validated printable articulated assembly"
    doc.recompute()
    doc.saveAs(str(mesh_path.parent / "New_ImageTo3D_Reference.FCStd"))
    App.closeDocument(doc.Name)
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
