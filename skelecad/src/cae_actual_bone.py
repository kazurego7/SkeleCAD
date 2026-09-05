import argparse
import json
import math
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARAMS = json.loads((ROOT / "config" / "parameters.json").read_text(encoding="utf-8"))
OUT = ROOT / "build" / "cae_actual"
REPORT = ROOT / "build" / "reports" / "cae_actual_bone_report.json"


def chunks(values, size=16):
    return [values[index:index + size] for index in range(0, len(values), size)]


def parse_gmsh_inp(path):
    nodes = {}
    elements = []
    section = None
    element_type = None
    for raw in path.read_text(encoding="latin-1").splitlines():
        line = raw.strip()
        upper = line.upper()
        if upper == "*NODE":
            section, element_type = "node", None
            continue
        if upper.startswith("*ELEMENT"):
            section = "element"
            element_type = "C3D4" if "TYPE=C3D4" in upper else "other"
            continue
        if line.startswith("*"):
            section, element_type = None, None
            continue
        if not line or not line[0].isdigit():
            continue
        fields = [field.strip() for field in line.split(",")]
        if section == "node":
            nodes[int(fields[0])] = tuple(float(value) for value in fields[1:4])
        elif section == "element" and element_type == "C3D4":
            elements.append((int(fields[0]), tuple(int(value) for value in fields[1:5])))
    return nodes, elements


def write_calculix_input(nodes, elements):
    xs = [coords[0] for coords in nodes.values()]
    min_x, max_x = min(xs), max(xs)
    tolerance = 1e-5
    fixed = [nid for nid, xyz in nodes.items() if abs(xyz[0] - min_x) < tolerance]
    loaded = [nid for nid, xyz in nodes.items() if abs(xyz[0] - max_x) < tolerance]
    if len(fixed) < 3 or len(loaded) < 3:
        raise RuntimeError("Could not identify the two planar socket rims")
    lines = ["*HEADING", "SkeleCAD actual bone_long tetrahedral static analysis", "*NODE"]
    lines.extend(f"{nid},{xyz[0]:.10g},{xyz[1]:.10g},{xyz[2]:.10g}"
                 for nid, xyz in sorted(nodes.items()))
    lines.append("*ELEMENT,TYPE=C3D4,ELSET=EALL")
    lines.extend(f"{eid},{conn[0]},{conn[1]},{conn[2]},{conn[3]}"
                 for eid, conn in elements)
    lines.append("*NSET,NSET=FIX")
    lines.extend(",".join(map(str, part)) for part in chunks(fixed))
    lines.append("*NSET,NSET=LOAD")
    lines.extend(",".join(map(str, part)) for part in chunks(loaded))
    material = PARAMS["material"]
    lines.extend((
        "*SOLID SECTION,ELSET=EALL,MATERIAL=PLA", "",
        "*MATERIAL,NAME=PLA", "*ELASTIC",
        f"{material['youngs_modulus_mpa']},{material['poisson_ratio']}",
        "*STEP", "*STATIC", "*BOUNDARY", "FIX,1,3,0", "*CLOAD"
    ))
    force_each = -PARAMS["cae"]["end_load_n"] / len(loaded)
    lines.extend(f"{nid},3,{force_each:.12g}" for nid in loaded)
    lines.extend((
        "*NODE PRINT,NSET=LOAD", "U",
        "*EL PRINT,ELSET=EALL", "S",
        "*NODE FILE", "U", "*EL FILE", "S", "*END STEP"
    ))
    path = OUT / "bone_long_actual.inp"
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path, fixed, loaded, min_x, max_x


def parse_results(dat_path):
    displacement_mode = False
    stress_mode = False
    displacements = []
    von_mises = []
    for line in dat_path.read_text(encoding="latin-1", errors="ignore").splitlines():
        lower = line.lower()
        if "displacements" in lower:
            displacement_mode, stress_mode = True, False
            continue
        if "stresses" in lower:
            displacement_mode, stress_mode = False, True
            continue
        fields = line.split()
        if displacement_mode and len(fields) >= 4 and fields[0].isdigit():
            try:
                u = [float(value.replace("D", "E")) for value in fields[1:4]]
                displacements.append(math.sqrt(sum(value * value for value in u)))
            except ValueError:
                pass
        elif stress_mode and len(fields) >= 8 and fields[0].isdigit():
            try:
                # CalculiX EL PRINT: element, integration point, Sxx,Syy,Szz,Sxy,Sxz,Syz.
                s = [float(value.replace("D", "E")) for value in fields[-6:]]
                sx, sy, sz, sxy, sxz, syz = s
                vm = math.sqrt(0.5*((sx-sy)**2 + (sy-sz)**2 + (sz-sx)**2) +
                               3*(sxy*sxy + sxz*sxz + syz*syz))
                von_mises.append(vm)
            except ValueError:
                pass
    return (max(displacements) if displacements else None,
            max(von_mises) if von_mises else None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gmsh", required=True)
    parser.add_argument("--ccx", required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    mesh_path = OUT / "bone_long_mesh.inp"
    # Relative paths are intentional: Gmsh's Windows CLI can misdecode Unicode absolute paths.
    gmsh_run = subprocess.run([
        args.gmsh, "build/parts/bone_long.step", "-3", "-order", "1",
        "-clmax", "2.2", "-format", "inp", "-o",
        "build/cae_actual/bone_long_mesh.inp", "-v", "2"
    ], cwd=ROOT, text=True, capture_output=True, timeout=120)
    if gmsh_run.returncode != 0 or not mesh_path.exists():
        raise RuntimeError(f"Gmsh failed: {gmsh_run.stdout[-1200:]} {gmsh_run.stderr[-1200:]}")
    nodes, elements = parse_gmsh_inp(mesh_path)
    if not nodes or not elements:
        raise RuntimeError("Gmsh output contained no tetrahedral volume mesh")
    inp, fixed, loaded, min_x, max_x = write_calculix_input(nodes, elements)
    ccx_run = subprocess.run([args.ccx, inp.stem], cwd=OUT, text=True,
                             capture_output=True, timeout=120)
    dat = OUT / f"{inp.stem}.dat"
    displacement, max_stress = parse_results(dat) if dat.exists() else (None, None)
    cae = PARAMS["cae"]
    mat = PARAMS["material"]
    diameter = PARAMS["bones"]["shaft_diameter_mm"]
    inertia = math.pi * diameter**4 / 64
    span = max_x - min_x
    analytical_u = cae["end_load_n"] * span**3 / (3 * mat["youngs_modulus_mpa"] * inertia)
    analytical_stress = 32 * cae["end_load_n"] * span / (math.pi * diameter**3)
    report = {
        "solver": "Gmsh + CalculiX",
        "gmsh_exit_code": gmsh_run.returncode,
        "calculix_exit_code": ccx_run.returncode,
        "nodes": len(nodes),
        "tetrahedral_elements": len(elements),
        "fixed_rim_nodes": len(fixed),
        "loaded_rim_nodes": len(loaded),
        "span_mm": span,
        "end_load_n": cae["end_load_n"],
        "max_loaded_rim_displacement_mm": displacement,
        "max_von_mises_mpa": max_stress,
        "circular_beam_reference_displacement_mm": analytical_u,
        "circular_beam_reference_stress_mpa": analytical_stress,
        "reference_yield_mpa": mat["reference_yield_mpa"],
        "passed": ccx_run.returncode == 0 and displacement is not None,
        "scope": "Actual bone_long solid with sockets; linear-static PLA estimate, no contact or impact"
    }
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    if not report["passed"]:
        raise SystemExit(4)


if __name__ == "__main__":
    main()
