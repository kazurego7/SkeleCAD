import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import FreeCAD as App


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
CONFIG = json.loads((ROOT / "config" / "toolchain.json").read_text(encoding="utf-8"))
REPORT = ROOT / "build" / "reports" / "environment_report.json"


def workspace_path(relative):
    return WORKSPACE / Path(relative)


def command_version(executable, arguments):
    completed = subprocess.run(
        [str(executable), *arguments], capture_output=True, text=True, timeout=20
    )
    combined = (completed.stdout + "\n" + completed.stderr).strip()
    return completed.returncode, combined


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main():
    freecad = CONFIG["freecad"]
    gmsh = CONFIG["gmsh"]
    calculix = CONFIG["calculix"]
    orca = CONFIG["orcaslicer"]
    paths = {
        "freecad": workspace_path(freecad["executable"]),
        "python": workspace_path(freecad["python"]),
        "gmsh": workspace_path(gmsh["executable"]),
        "calculix": workspace_path(calculix["executable"]),
        "orcaslicer": workspace_path(orca["executable"]),
        "orcaslicer_archive": workspace_path(orca["archive"]),
    }
    for name in ('blender', 'workflow_python', 'inference_python'):
        paths[name] = workspace_path(CONFIG[name]['executable'])
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise RuntimeError("Toolchain files are missing: " + ", ".join(missing))

    gmsh_code, gmsh_text = command_version(paths["gmsh"], ["--version"])
    ccx_code, ccx_text = command_version(paths["calculix"], ["-v"])
    freecad_actual = ".".join(str(item) for item in App.Version()[:3])
    gmsh_match = re.search(r"\b\d+\.\d+(?:\.\d+)?\b", gmsh_text)
    ccx_match = re.search(r"\b\d+\.\d+(?:\.\d+)?\b", ccx_text)
    gmsh_actual = gmsh_match.group(0) if gmsh_match else None
    ccx_actual = ccx_match.group(0) if ccx_match else None
    archive_size = paths["orcaslicer_archive"].stat().st_size
    archive_hash = sha256(paths["orcaslicer_archive"])

    checks = {
        "freecad_version": freecad_actual == freecad["version"],
        "gmsh_version": gmsh_code == 0 and gmsh_actual == gmsh["version"],
        # CalculiX 2.22 returns a non-zero code for its version-only invocation
        # even though it prints a valid version. Solver job exit codes are still
        # enforced by the CAE stages.
        "calculix_version": ccx_actual == calculix["version"],
        "orcaslicer_executable": paths["orcaslicer"].is_file(),
        "orcaslicer_archive_size": archive_size == orca["archive_size_bytes"],
        "orcaslicer_archive_sha256": archive_hash.lower() == orca["archive_sha256"].lower(),
    }
    for name in ('gmsh', 'calculix', 'blender'):
        checks[name + '_sha256'] = sha256(paths[name]) == CONFIG[name]['executable_sha256']
    for name in ('workflow_python', 'inference_python'):
        code, version = command_version(paths[name], ['--version'])
        checks[name + '_version'] = code == 0 and version == 'Python ' + CONFIG[name]['version']
    blender_code, blender_version = command_version(paths['blender'], ['--version'])
    checks['blender_version'] = blender_code == 0 and blender_version.splitlines()[0] in (
        'Blender ' + CONFIG['blender']['version'], 'Blender ' + CONFIG['blender']['version'] + ' LTS')
    report = {
        "passed": all(checks.values()),
        "checks": checks,
        "versions": {
            "freecad": freecad_actual,
            "gmsh": gmsh_actual,
            "calculix": ccx_actual,
            "orcaslicer": orca["version"],
            "python": sys.version.split()[0],
            "workflow_python": CONFIG['workflow_python']['version'],
            "inference_python": CONFIG['inference_python']['version'],
            "blender": CONFIG['blender']['version'],
        },
        "version_command_exit_codes": {"gmsh": gmsh_code, "calculix": ccx_code},
        "paths": {name: str(path) for name, path in paths.items()},
        "orcaslicer_archive": {
            "size_bytes": archive_size,
            "sha256": archive_hash,
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report))
    if not report["passed"]:
        raise RuntimeError("Toolchain verification failed")


if __name__ == "__main__":
    main()
