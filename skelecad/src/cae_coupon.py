import argparse
import json
import math
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARAMS = json.loads((ROOT / "config" / "parameters.json").read_text(encoding="utf-8"))
OUT = ROOT / "build" / "cae"
REPORT = ROOT / "build" / "reports" / "cae_report.json"


def node_id(i, j, k, ny, nz):
    return i * (ny + 1) * (nz + 1) + j * (nz + 1) + k + 1


def write_input():
    cae = PARAMS["cae"]
    mat = PARAMS["material"]
    length, width, height = cae["coupon_length_mm"], cae["coupon_width_mm"], cae["coupon_height_mm"]
    nx, ny, nz = cae["mesh_divisions"]
    lines = ["*HEADING", "SkeleCAD PLA equivalent bone cantilever", "*NODE"]
    fixed_nodes, load_nodes = [], []
    for i in range(nx + 1):
        x = length * i / nx
        for j in range(ny + 1):
            y = -width / 2 + width * j / ny
            for k in range(nz + 1):
                z = -height / 2 + height * k / nz
                nid = node_id(i, j, k, ny, nz)
                lines.append(f"{nid},{x:.8f},{y:.8f},{z:.8f}")
                if i == 0:
                    fixed_nodes.append(nid)
                if i == nx:
                    load_nodes.append(nid)
    lines.append("*ELEMENT,TYPE=C3D8,ELSET=EALL")
    eid = 1
    for i in range(nx):
        for j in range(ny):
            for k in range(nz):
                n000 = node_id(i, j, k, ny, nz)
                n100 = node_id(i + 1, j, k, ny, nz)
                n110 = node_id(i + 1, j + 1, k, ny, nz)
                n010 = node_id(i, j + 1, k, ny, nz)
                n001 = node_id(i, j, k + 1, ny, nz)
                n101 = node_id(i + 1, j, k + 1, ny, nz)
                n111 = node_id(i + 1, j + 1, k + 1, ny, nz)
                n011 = node_id(i, j + 1, k + 1, ny, nz)
                lines.append(f"{eid},{n000},{n100},{n110},{n010},{n001},{n101},{n111},{n011}")
                eid += 1
    lines.append("*NSET,NSET=FIX")
    lines.extend(",".join(map(str, fixed_nodes[i:i+16]))
                 for i in range(0, len(fixed_nodes), 16))
    lines.append("*NSET,NSET=LOAD")
    lines.extend(",".join(map(str, load_nodes[i:i+16]))
                 for i in range(0, len(load_nodes), 16))
    lines.extend(("*SOLID SECTION,ELSET=EALL,MATERIAL=PLA", "",
                  "*MATERIAL,NAME=PLA",
                  "*ELASTIC", f"{mat['youngs_modulus_mpa']},{mat['poisson_ratio']}",
                  "*STEP", "*STATIC", "*BOUNDARY", "FIX,1,3,0"))
    force_each = -cae["end_load_n"] / len(load_nodes)
    lines.append("*CLOAD")
    lines.extend(f"{nid},3,{force_each:.10f}" for nid in load_nodes)
    lines.extend(("*NODE PRINT,NSET=LOAD", "U", "*NODE FILE", "U",
                  "*EL FILE", "S", "*END STEP"))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "bone_coupon.inp"
    path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return path, len(load_nodes), eid - 1


def parse_displacements(dat_path):
    if not dat_path.exists():
        return None
    in_displacements = False
    magnitudes = []
    for line in dat_path.read_text(encoding="latin-1", errors="ignore").splitlines():
        lower = line.lower()
        if "displacements" in lower:
            in_displacements = True
            continue
        if in_displacements:
            fields = line.split()
            if len(fields) >= 4 and fields[0].isdigit():
                try:
                    values = [float(value.replace("D", "E")) for value in fields[1:4]]
                    magnitudes.append(math.sqrt(sum(value * value for value in values)))
                except ValueError:
                    pass
            elif magnitudes and not line.strip():
                break
    return max(magnitudes) if magnitudes else None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ccx", required=True)
    args = parser.parse_args()
    inp, load_count, element_count = write_input()
    job = inp.stem
    completed = subprocess.run([args.ccx, job], cwd=OUT, text=True,
                               capture_output=True, timeout=120)
    displacement = parse_displacements(OUT / f"{job}.dat")
    cae = PARAMS["cae"]
    mat = PARAMS["material"]
    inertia = cae["coupon_width_mm"] * cae["coupon_height_mm"] ** 3 / 12
    analytical = cae["end_load_n"] * cae["coupon_length_mm"] ** 3 / (
        3 * mat["youngs_modulus_mpa"] * inertia
    )
    report = {
        "solver": "CalculiX",
        "solver_exit_code": completed.returncode,
        "elements": element_count,
        "loaded_nodes": load_count,
        "max_loaded_end_displacement_mm": displacement,
        "beam_theory_reference_mm": analytical,
        "stdout_tail": completed.stdout[-1200:],
        "stderr_tail": completed.stderr[-1200:],
        "passed": completed.returncode == 0 and displacement is not None,
        "scope": "Equivalent rectangular long-bone shaft; not socket-contact or impact analysis"
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    if not report["passed"]:
        raise SystemExit(3)


if __name__ == "__main__":
    main()
