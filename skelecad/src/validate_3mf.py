import json
import zipfile
from pathlib import Path
from hybrid_context import HYBRID
from xml.etree import ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "build" / "reports" / "three_mf_report.json"


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def analyse(path):
    with zipfile.ZipFile(path) as archive:
        corrupt = archive.testzip()
        normalized = {name.replace("\\", "/"): name for name in archive.namelist()}
        required = {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"}
        missing = sorted(required - set(normalized))
        if missing:
            return {"file": str(path.relative_to(ROOT)), "passed": False,
                    "missing": missing, "corrupt_entry": corrupt}
        xml = archive.read(normalized["3D/3dmodel.model"])
    root = ET.fromstring(xml)
    counts = {"object": 0, "vertex": 0, "triangle": 0, "item": 0}
    for element in root.iter():
        name = local_name(element.tag)
        if name in counts:
            counts[name] += 1
    result = {
        "file": str(path.relative_to(ROOT)),
        "unit": root.attrib.get("unit"),
        "objects": counts["object"],
        "vertices": counts["vertex"],
        "triangles": counts["triangle"],
        "build_items": counts["item"],
        "corrupt_entry": corrupt,
    }
    result["passed"] = (
        corrupt is None and result["unit"] == "millimeter" and
        result["objects"] > 0 and result["vertices"] > 0 and
        result["triangles"] > 0 and result["build_items"] > 0
    )
    return result


def main():
    paths = sorted((ROOT / "build" / "parts").glob("*.3mf"))
    paths += sorted((ROOT / "build" / "print").glob("*.3mf"))
    paths += sorted((HYBRID / "parts").glob("*.3mf"))
    paths += sorted((HYBRID / "print").glob("*.3mf"))
    results = [analyse(path) for path in paths]
    if not results:
        raise RuntimeError("No 3MF files found")
    REPORT.write_text(json.dumps({"files": results}, indent=2), encoding="utf-8")
    print(json.dumps({"files": results}))
    if not all(item["passed"] for item in results):
        raise SystemExit(5)


if __name__ == "__main__":
    main()
