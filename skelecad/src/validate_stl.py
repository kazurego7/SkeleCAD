import json
import math
import struct
import sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from hybrid_context import HYBRID


ROOT = Path(__file__).resolve().parents[1]
PARTS = ROOT / "build" / "parts"
REPORT = ROOT / "build" / "reports" / "mesh_report.json"


def load_triangles(path):
    data = path.read_bytes()
    triangles = []
    if len(data) >= 84:
        count = struct.unpack_from("<I", data, 80)[0]
        if 84 + count * 50 == len(data):
            for index in range(count):
                values = struct.unpack_from("<12fH", data, 84 + index * 50)
                triangles.append((values[3:6], values[6:9], values[9:12]))
            return triangles
    vertices = []
    for line in data.decode("utf-8", errors="ignore").splitlines():
        fields = line.strip().split()
        if len(fields) == 4 and fields[0].lower() == "vertex":
            vertices.append(tuple(float(value) for value in fields[1:]))
            if len(vertices) == 3:
                triangles.append(tuple(vertices))
                vertices = []
    return triangles


def key(point):
    # Image-to-3D meshes legitimately contain dense sub-micron tessellation.
    # Preserve STL float32 vertex identity instead of merging nearby vertices.
    return tuple(float(value) for value in point)


def analyse(path):
    triangles = load_triangles(path)
    if not triangles:
        raise RuntimeError(f"No triangles in {path.name}")
    edge_counts = Counter()
    edge_to_triangles = defaultdict(list)
    degenerate = 0
    signed_volume = 0.0
    all_points = []
    for index, tri in enumerate(triangles):
        a, b, c = tri
        all_points.extend(tri)
        ab = tuple(b[i] - a[i] for i in range(3))
        ac = tuple(c[i] - a[i] for i in range(3))
        cross = (ab[1]*ac[2]-ab[2]*ac[1], ab[2]*ac[0]-ab[0]*ac[2], ab[0]*ac[1]-ab[1]*ac[0])
        if sum(value * value for value in cross) == 0.0:
            degenerate += 1
        signed_volume += (a[0]*(b[1]*c[2]-b[2]*c[1]) +
                          a[1]*(b[2]*c[0]-b[0]*c[2]) +
                          a[2]*(b[0]*c[1]-b[1]*c[0])) / 6.0
        for p, q in ((a, b), (b, c), (c, a)):
            edge = tuple(sorted((key(p), key(q))))
            edge_counts[edge] += 1
            edge_to_triangles[edge].append(index)
    adjacency = defaultdict(set)
    for owners in edge_to_triangles.values():
        for owner in owners:
            adjacency[owner].update(other for other in owners if other != owner)
    seen = set()
    components = 0
    for start in range(len(triangles)):
        if start in seen:
            continue
        components += 1
        queue = deque([start])
        seen.add(start)
        while queue:
            item = queue.popleft()
            for neighbor in adjacency[item]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
    bad_edges = sum(count != 2 for count in edge_counts.values())
    mins = [min(point[i] for point in all_points) for i in range(3)]
    maxs = [max(point[i] for point in all_points) for i in range(3)]
    result = {
        "file": path.name,
        "triangles": len(triangles),
        "closed_two_manifold": bad_edges == 0,
        "nonmanifold_or_boundary_edges": bad_edges,
        "degenerate_triangles": degenerate,
        "connected_components": components,
        "signed_volume_mm3": signed_volume,
        "absolute_volume_mm3": abs(signed_volume),
        "bounds_mm": [maxs[i] - mins[i] for i in range(3)],
    }
    result["passed"] = (
        result["closed_two_manifold"] and degenerate == 0 and
        components == 1 and signed_volume > 0.01
    )
    return result


def main():
    paths = sorted(PARTS.glob("*.stl"))
    paths += sorted((HYBRID / "parts").glob("*.stl"))
    results = [analyse(path) for path in paths]
    if not results:
        raise RuntimeError("No generated STL files found")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps({"parts": results}, indent=2), encoding="utf-8")
    print(json.dumps({"parts": results}))
    if not all(item["passed"] for item in results):
        sys.exit(2)


if __name__ == "__main__":
    main()
