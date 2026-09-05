import argparse
import json
import subprocess

from cae_actual_bone import chunks, parse_gmsh_inp, parse_results


from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARAMS = json.loads((ROOT / "config" / "parameters.json").read_text(encoding="utf-8"))
OUT = ROOT / "build" / "cae_ball_stud"
REPORT = ROOT / "build" / "reports" / "cae_ball_stud_report.json"


def write_input(nodes, elements):
    xs = [coords[0] for coords in nodes.values()]
    min_x, max_x = min(xs), max(xs)
    fixed = [nid for nid, xyz in nodes.items() if xyz[0] >= max_x - 0.35]
    loaded = [nid for nid, xyz in nodes.items() if xyz[0] <= min_x + 0.55]
    if len(fixed) < 3 or len(loaded) < 3:
        raise RuntimeError("Could not identify ball cap and base faces")
    lines = [
        "*HEADING",
        f"SkeleCAD v{PARAMS['joint']['version']} ball-stud side-load analysis",
        "*NODE",
    ]
    lines.extend(
        f"{nid},{xyz[0]:.10g},{xyz[1]:.10g},{xyz[2]:.10g}"
        for nid, xyz in sorted(nodes.items())
    )
    lines.append("*ELEMENT,TYPE=C3D4,ELSET=EALL")
    lines.extend(
        f"{eid},{conn[0]},{conn[1]},{conn[2]},{conn[3]}"
        for eid, conn in elements
    )
    lines.append("*NSET,NSET=FIX")
    lines.extend(",".join(map(str, group)) for group in chunks(fixed))
    lines.append("*NSET,NSET=LOAD")
    lines.extend(",".join(map(str, group)) for group in chunks(loaded))
    material = PARAMS["material"]
    lines.extend([
        "*SOLID SECTION,ELSET=EALL,MATERIAL=PLA", "",
        "*MATERIAL,NAME=PLA", "*ELASTIC",
        f"{material['youngs_modulus_mpa']},{material['poisson_ratio']}",
        "*STEP", "*STATIC", "*BOUNDARY", "FIX,1,3,0", "*CLOAD",
    ])
    force_each = -PARAMS["cae"]["joint_side_load_n"] / len(loaded)
    lines.extend(f"{nid},3,{force_each:.12g}" for nid in loaded)
    lines.extend([
        "*NODE PRINT,NSET=LOAD", "U", "*EL PRINT,ELSET=EALL", "S",
        "*NODE FILE", "U", "*EL FILE", "S", "*END STEP",
    ])
    path = OUT / "ball_stud_actual.inp"
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path, fixed, loaded, max_x - min_x


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gmsh", required=True)
    parser.add_argument("--ccx", required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    mesh_path = OUT / "ball_stud_mesh.inp"
    gmsh_run = subprocess.run([
        args.gmsh, "build/parts/ball_stud_specimen_v2.step", "-3", "-order", "1",
        "-clmax", "1.0", "-format", "inp", "-o",
        "build/cae_ball_stud/ball_stud_mesh.inp", "-v", "2",
    ], cwd=ROOT, text=True, capture_output=True, timeout=120)
    if gmsh_run.returncode != 0 or not mesh_path.exists():
        raise RuntimeError(f"Gmsh failed: {gmsh_run.stdout[-1000:]} {gmsh_run.stderr[-1000:]}")
    nodes, elements = parse_gmsh_inp(mesh_path)
    inp, fixed, loaded, span = write_input(nodes, elements)
    ccx_run = subprocess.run(
        [args.ccx, inp.stem], cwd=OUT, text=True, capture_output=True, timeout=120
    )
    dat = OUT / f"{inp.stem}.dat"
    displacement, stress = parse_results(dat) if dat.exists() else (None, None)
    yield_mpa = PARAMS["material"]["reference_yield_mpa"]
    safety_factor = yield_mpa / stress if stress and stress > 0 else None
    report = {
        "solver": "Gmsh + CalculiX",
        "geometry": "ball_stud_specimen_v2",
        "nodes": len(nodes),
        "tetrahedral_elements": len(elements),
        "fixed_nodes": len(fixed),
        "loaded_ball_cap_nodes": len(loaded),
        "span_mm": span,
        "side_load_n": PARAMS["cae"]["joint_side_load_n"],
        "max_loaded_cap_displacement_mm": displacement,
        "max_von_mises_mpa": stress,
        "reference_yield_mpa": yield_mpa,
        "linear_static_reference_safety_factor": safety_factor,
        "passed": ccx_run.returncode == 0 and displacement is not None and stress is not None,
        "scope": (
            f"Actual v{PARAMS['joint']['version']} ball, neck, and base; "
            "linear-static PLA estimate without snap contact, fatigue, or layer anisotropy"
        ),
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    if not report["passed"]:
        return 4
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
