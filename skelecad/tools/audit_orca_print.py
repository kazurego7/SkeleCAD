"""Audit the saved Orca projects and local sliced exports, without changing them.

Run with the mesh environment (numpy required). This is not machine certification.
"""
import hashlib
import json
import math
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build/print_ready"
NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
PNS = "{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}"
NAMES = {"head", "torso", "arm_left", "arm_right", "leg_left", "leg_right",
         "foot_left", "foot_right", "tail"}


def metadata(element):
    return {m.get("key"): m.get("value") for m in element.findall("metadata")}


def arrays(xml):
    root = ET.fromstring(xml)
    vertices = np.array([[float(e.get(k)) for k in "xyz"]
                         for e in root.findall(".//" + NS + "vertex")])
    faces = np.array([[int(e.get(k)) for k in ("v1", "v2", "v3")]
                     for e in root.findall(".//" + NS + "triangle")])
    return vertices, faces


def project_audit(path, fit=False, hybrid_directory="build/hybrid_20260830"):
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        root = ET.fromstring(z.read("3D/3dmodel.model"))
        assert root.get("unit") == "millimeter"
        settings = json.loads(z.read("Metadata/project_settings.config"))
        meta = ET.fromstring(z.read("Metadata/model_settings.config"))
        objects = {o.get("id"): o for o in meta.findall("object")}
        records = []
        for obj in root.find(NS + "resources").findall(NS + "object"):
            md = objects[obj.get("id")]
            name = metadata(md)["name"]
            component = obj.find(NS + "components/" + NS + "component")
            av, af = arrays(z.read(component.get(PNS + "path").lstrip("/")))
            source = ROOT / ("build/print/starter_fit_kit.3mf" if fit else
                             f"{hybrid_directory}/parts/{name}.3mf")
            with zipfile.ZipFile(source) as original:
                bv, bf = arrays(original.read("3D/3dmodel.model"))
            part_meta = metadata(md.find("part"))
            offset = [float(part_meta["source_offset_" + k]) for k in "xyz"]
            assert av.shape == bv.shape and np.array_equal(af, bf), name
            delta = float(np.max(np.abs(av + offset - bv)))
            assert delta < 0.00002, (name, delta)
            records.append({"name": name, "vertices": len(av), "triangles": len(af),
                            "max_coordinate_rounding_mm": delta,
                            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest()})
        for item in root.find(NS + "build"):
            rotation = np.array([float(v) for v in item.get("transform").split()][:9]).reshape(3, 3)
            assert np.allclose(rotation @ rotation.T, np.eye(3), atol=1e-7)
            assert abs(np.linalg.det(rotation) - 1) < 1e-7
        if not fit:
            assert {r["name"] for r in records} == NAMES
        keys = ["printer_model", "printer_settings_id", "filament_settings_id", "curr_bed_type",
                "layer_height", "initial_layer_print_height", "wall_loops", "enable_support",
                "support_type", "brim_type", "brim_width", "hot_plate_temp",
                "hot_plate_temp_initial_layer", "nozzle_temperature", "sparse_infill_density"]
        return {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "geometry_preserved_with_export_rounding": True, "scale_unchanged": True,
                "plates": len(meta.findall("plate")), "parts": records,
                "settings": {k: settings.get(k) for k in keys}}


def extrusion_bounds(gcode):
    """Model/support/brim centerline bounds, including XY arc extrema.

    Excludes machine start/end macros and their intentionally off-bed purge moves.
    Valid only for this Orca export's absolute XYZ / relative E / XY arc mode.
    """
    body = gcode.split("; CHANGE_LAYER", 1)[1].split("; filament end gcode", 1)[0]
    xyz = np.zeros(3)
    low, high = np.full(3, np.inf), np.full(3, -np.inf)
    segments = 0
    for line in body.splitlines():
        command = line.split(";", 1)[0].strip()
        if not re.match(r"G[0123] ", command):
            continue
        fields = {k: float(v) for k, v in re.findall(r"([XYZIJE])(-?(?:\d+(?:\.\d*)?|\.\d+))", command)}
        end = np.array([fields.get(k, xyz[i]) for i, k in enumerate("XYZ")])
        if fields.get("E", 0) > 0 and ("X" in fields or "Y" in fields):
            points = [xyz.copy(), end.copy()]
            if command.startswith(("G2 ", "G3 ")) and ("I" in fields or "J" in fields):
                center = xyz[:2] + [fields.get("I", 0), fields.get("J", 0)]
                radius = np.linalg.norm(xyz[:2] - center)
                a = math.atan2(*(xyz[:2] - center)[::-1])
                b = math.atan2(*(end[:2] - center)[::-1])
                direction = 1 if command.startswith("G3 ") else -1
                sweep = ((b - a) * direction) % (2 * math.pi)
                for angle in (0, math.pi / 2, math.pi, math.pi * 1.5):
                    if ((angle - a) * direction) % (2 * math.pi) <= sweep + 1e-8:
                        points.append(np.array([*(center + radius * np.array([math.cos(angle), math.sin(angle)])), end[2]]))
            low = np.minimum(low, np.min(points, axis=0))
            high = np.maximum(high, np.max(points, axis=0))
            segments += 1
        xyz = end
    assert segments > 100
    assert np.all(low >= 0) and np.all(high <= 180), (low, high)
    return {"min_mm": low.tolist(), "max_mm": high.tolist(), "extrusion_segments": segments,
            "centerlines_within_180mm_cube": True}


def sliced_audit(path):
    records = []
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        info = ET.fromstring(z.read("Metadata/slice_info.config"))
        for plate in info.findall("plate"):
            md = metadata(plate)
            name = f"Metadata/plate_{md['index']}.gcode"
            data = z.read(name)
            assert hashlib.md5(data).hexdigest().lower() == z.read(name + ".md5").decode().strip().lower()
            assert md["outside"] == "false"
            assert all(o.get("skipped") == "false" for o in plate.findall("object"))
            code = data.decode()
            bounds = extrusion_bounds(code)
            bbox = json.loads(z.read(f"Metadata/plate_{md['index']}.json"))["bbox_all"]
            records.append({"plate": int(md["index"]), "seconds": int(md["prediction"]),
                            "grams": float(md["weight"]), "layers": int(re.search(r"; total layer number: (\d+)", code)[1]),
                            "objects": [o.get("name") for o in plate.findall("object")],
                            "outside": False, "gcode_md5_valid": True, "toolpath_bounds": bounds,
                            "preview_bbox": bbox, "preview_bbox_within_bed": min(bbox) >= 0 and max(bbox) <= 180,
                            "warnings": [w.attrib for w in plate.findall("warning")]})
    return {"file": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "plates": records}


if __name__ == "__main__":
    report = {
        "status": "sliced_under_provisional_settings_not_released_for_printing",
        "physical_fit_tested": False,
        "machine_material_plate_confirmed_by_user": False,
        "body": project_audit(OUT / "SkeleCAD_1.2.4_A1mini_PLA_draft.3mf"),
        "fit_kit": project_audit(OUT / "SkeleCAD_1.2.4_fit_kit_A1mini_PLA_draft.3mf", fit=True),
        "sliced_body": sliced_audit(OUT / "SkeleCAD_1.2.4_A1mini_PLA_UNCONFIRMED_all_plates.gcode.3mf"),
        "sliced_fit_kit": sliced_audit(OUT / "SkeleCAD_1.2.4_fit_kit_A1mini_PLA_UNCONFIRMED.gcode.3mf"),
        "limitations": [
            "Machine, exact filament and plate must be confirmed before using G-code.",
            "Bed temperature and timelapse warnings preserved; not a warning-free release.",
            "Orca plate 2 preview JSON has negative X bounds; actual G-code extrusion coordinates are checked independently.",
            "Toolpath centerline bounds do not certify machine macros, adhesion or support removal.",
            "Print and physically inspect fit kit first; final joint orientations also require testing.",
            "No geometry/material-model change; existing CAD/CalculiX reports were not regenerated for slicing.",
        ],
    }
    output = OUT / "print_audit.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"report": str(output), "geometry_checks_passed": True,
                      "toolpath_bounds_passed": True, "status": report["status"]}))
