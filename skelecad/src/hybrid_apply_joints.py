"""Apply FreeCAD-authored joint tools to the generated appearance partitions."""

from __future__ import annotations

import json
import io
from pathlib import Path

import numpy as np
import trimesh
from hybrid_context import HYBRID, H, PARAMS


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
RAW = HYBRID / "raw_split"
TOOLS = HYBRID / "joint_tools"
OUTPUT = HYBRID / "parts"
REPORT = BUILD / "reports" / "hybrid_parts.json"
BOOLEAN_CLEANUP = []


def clean_boolean_result(result, label):
    # Float32 Boolean intersections occasionally include exactly zero-area faces.
    # Removing only these preserves the surface and material volume; all remaining
    # topology is still required to pass strict closed-solid validation.
    keep = result.area_faces > 0.0
    removed = int((~keep).sum())
    if removed:
        result.update_faces(keep)
        result.remove_unreferenced_vertices()
        BOOLEAN_CLEANUP.append({"operation": label, "zero_area_faces_removed": removed})
    result.fix_normals(multibody=True)
    return result


def load(path):
    mesh = trimesh.load_mesh(path)
    mesh.fix_normals(multibody=True)
    if not mesh.is_volume:
        raise RuntimeError(f"Boolean input is not a closed positive volume: {path}")
    return mesh


def weld_quantized_micro_boundaries(mesh, tolerance, label):
    """Collapse only tiny connected open boundaries created by STL rounding.

    Never fill holes or simplify surrounding anatomy. Every affected boundary
    must fit inside the configured sub-micron span; final topology is rechecked.
    """
    counts=np.bincount(mesh.edges_unique_inverse)
    if np.any(counts>2):return mesh
    edges=mesh.edges_unique[counts==1]
    if not len(edges):return mesh
    groups=trimesh.graph.connected_components(edges,min_len=2)
    remap=np.arange(len(mesh.vertices));welds=[]
    for group in groups:
        points=mesh.vertices[group]
        span=float(np.linalg.norm(points.max(0)-points.min(0)))
        if span>tolerance:continue
        remap[group]=group[0]
        welds.append({'vertices':len(group),'span_mm':span})
    if welds:
        mesh=trimesh.Trimesh(mesh.vertices.copy(),remap[mesh.faces],process=False)
        mesh=clean_boolean_result(mesh,label+' micro-boundary weld')
        mesh.update_faces(mesh.unique_faces());mesh.remove_unreferenced_vertices()
        mesh.fix_normals(multibody=True)
        BOOLEAN_CLEANUP.append({'operation':label,'micro_boundary_welds':welds})
    return mesh


def union(base, addition, label):
    if H.get('palm_size',{}).get('enabled'):
        from finish_cut_edges import solid,from_solid
        result=from_solid(solid(base)+solid(addition))
    else:
        result = trimesh.boolean.union([base, addition], engine="manifold")
    result = clean_boolean_result(result, label)
    if not result.is_volume:
        raise RuntimeError(f"Union failed for {label}")
    return result


def difference(base, cutter, label):
    if H.get('palm_size',{}).get('enabled'):
        from finish_cut_edges import solid,from_solid
        result=from_solid(solid(base)-solid(cutter))
    else:
        result = trimesh.boolean.difference([base, cutter], engine="manifold")
    result = clean_boolean_result(result, label)
    if not result.is_volume:
        raise RuntimeError(f"Difference failed for {label}")
    return result


def remove_boolean_debris(mesh, minimum_volume_mm3=200.0):
    """Discard tiny closed chips produced when a clearance cut grazes ornament."""
    components = mesh.split(only_watertight=False)
    kept = [item for item in components if abs(item.volume) >= minimum_volume_mm3]
    if not kept:
        raise RuntimeError("Boolean cleanup discarded every component")
    result = trimesh.util.concatenate(kept)
    result.fix_normals(multibody=True)
    return result


def remove_local_numerical_fragments(mesh, name):
    from validate_anatomy_preservation import protected_mask
    kept=[]
    for component in mesh.split(only_watertight=False):
        if (abs(component.volume) <= H['boolean_fragment_max_volume_mm3']
                and not protected_mask(component.vertices).any()):
            BOOLEAN_CLEANUP.append({'part':name,'local_numerical_fragment_mm3':float(component.volume)})
        else:
            kept.append(component)
    return trimesh.util.concatenate(kept)


def apply_socket(part, connection, machine=True):
    target_clear = load(TOOLS / f"{connection}_target_clear.stl")
    outer = load(TOOLS / f"{connection}_socket_outer.stl")
    cutter = load(TOOLS / f"{connection}_socket_cut.stl")
    if machine and connection not in H.get('preserve_anatomy_connections',[])+H.get('preserve_target_anatomy_connections',[]):
        part = difference(part, target_clear, f"{connection} target motion clearance")
    anatomy_path=TOOLS / f"{connection}_socket_anatomy_cut.stl"
    if anatomy_path.exists():
        # Machine the source exactly as before; change only the added cup.
        if machine:part=difference(part,load(anatomy_path),f"{connection} preserved anatomy cavity")
        shell=difference(outer,cutter,f"{connection} shallow socket shell")
        return union(part,shell,f"{connection} shallow socket addition")
    part = union(part, outer, f"{connection} socket outer")
    return difference(part, cutter, f"{connection} socket cavity")


def apply_ball(part, connection, machine=True):
    clearance = load(TOOLS / f"{connection}_source_clear.stl")
    ball = load(TOOLS / f"{connection}_ball_add.stl")
    if machine and connection not in H.get('preserve_anatomy_connections',[]):
        part = difference(part, clearance, f"{connection} source clearance")
    return union(part, ball, f"{connection} ball stud")


OWNERS={'neck':('head','torso'),'shoulder_left':('arm_left','torso'),
        'shoulder_right':('arm_right','torso'),'hip_left':('leg_left','torso'),
        'hip_right':('leg_right','torso'),'tail_root':('tail','torso'),
        'ankle_left':('foot_left','leg_left'),'ankle_right':('foot_right','leg_right')}


def machining_tools():
    result={name:[] for name in set(sum((list(v) for v in OWNERS.values()),[]))}
    for connection,(male,female) in OWNERS.items():
        result[female].append(connection+'_socket_anatomy_cut')
        if connection not in H['preserve_anatomy_connections']:
            result[male].append(connection+'_source_clear')
            if connection not in H.get('preserve_target_anatomy_connections',[]):
                result[female].append(connection+'_target_clear')
    for spec in H.get('local_reliefs',[]):result[spec['part']].append(spec['name'])
    return result


def boundary_tools(name, tool_names):
    from hybrid_local_partition import local_cutters,ring_seam
    tools=[m.copy() for _,m in local_cutters()]+[ring_seam(1),ring_seam(-1)]
    for tool in tools:tool.apply_translation(H.get('part_translation_mm',{}).get(name,[0,0,0]))
    return tools+[load(TOOLS/f'{tool}.stl') for tool in tool_names]


def finish_anatomy(parts):
    from finish_cut_edges import finish
    tool_map=machining_tools();records=[]
    review=HYBRID/'edge_finish';review.mkdir(exist_ok=True)
    for name,part in parts.items():
        for tool in tool_map[name]:part=difference(part,load(TOOLS/f'{tool}.stl'),f'{name} {tool}')
        part.export(review/f'{name}_before.stl')
        result,cutter,record,seams=finish(part,boundary_tools(name,tool_map[name]),H['cut_edge_finish'],name)
        np.save(review/f'{name}_seams.npy',seams)
        if cutter is not None:
            # Internal allowance tools have thin faces not representable in
            # float32 STL. Preserve double precision for the Boolean audit.
            np.savez_compressed(TOOLS/f'{name}_edge_finish.npz',vertices=cutter.vertices,faces=cutter.faces)
            record['cutter']=f'{name}_edge_finish'
        result.export(review/f'{name}_after.stl')
        records.append(record);parts[name]=result
        print('EDGE_FINISH',json.dumps(record),flush=True)
    (review/'report.json').write_text(json.dumps({'parameters':H['cut_edge_finish'],'parts':records,'passed':all(r['passed'] for r in records)},indent=2),encoding='utf-8')
    for connection,(male,female) in OWNERS.items():
        parts[female]=apply_socket(parts[female],connection,machine=False)
        parts[male]=apply_ball(parts[male],connection,machine=False)
    return records


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    for stale in OUTPUT.glob("*.stl"):
        stale.unlink()
    parts = {
        name: load(RAW / f"{name}.stl")
        for name in (
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
    }

    local_reliefs=[]
    if not H.get('cut_edge_finish'):
        raise ValueError('Current cut_edge_finish configuration is required')
    edge_finish=finish_anatomy(parts)

    report_parts = []
    for name, mesh in parts.items():
        if H.get("partition_method") != "local_joint_discs":
            mesh = remove_boolean_debris(mesh, 600.0 if name == "head" else 200.0)
        else:
            mesh = remove_local_numerical_fragments(mesh, name)
        if H.get('palm_size',{}).get('enabled'):
            # Certify the actual float32 printing representation, not just the
            # higher-precision Boolean result. Drop only faces collapsed to zero
            # area or exact duplicates by STL quantization; never remove solids.
            original=mesh
            def quantize(candidate):
                result=trimesh.load_mesh(io.BytesIO(candidate.export(file_type='stl')),file_type='stl')
                result=clean_boolean_result(result,name+' STL quantization')
                result.update_faces(result.unique_faces())
                result.remove_unreferenced_vertices()
                return result
            mesh=quantize(original)
            if not mesh.is_volume or len(mesh.split(only_watertight=False))!=1:
                from finish_cut_edges import solid
                tolerance=PARAMS['printing']['stl_quantization_cleanup_mm']
                while tolerance<=PARAMS['printing']['stl_quantization_cleanup_max_mm']:
                    simplified=solid(original).simplify(tolerance).to_mesh64()
                    mesh=quantize(trimesh.Trimesh(simplified.vert_properties[:,:3],simplified.tri_verts,process=False))
                    mesh=weld_quantized_micro_boundaries(mesh,tolerance,name)
                    if mesh.is_volume and len(mesh.split(only_watertight=False))==1:
                        break
                    tolerance*=2
                delta=abs(float(mesh.volume-original.volume))
                BOOLEAN_CLEANUP.append({'part':name,'stl_simplification_mm':tolerance,'volume_delta_mm3':delta})
                if delta>H['boolean_fragment_max_volume_mm3']:
                    raise RuntimeError(f'{name}: STL simplification changed excessive volume: {delta}')
            if not mesh.is_volume or len(mesh.split(only_watertight=False))!=1:
                np.savez_compressed(HYBRID/f'{name}_precision_failure.npz',vertices=original.vertices,faces=original.faces)
                raise RuntimeError(f'{name}: STL precision topology failure')
        parts[name] = mesh
        mesh.fix_normals(multibody=True)
        path = OUTPUT / f"{name}.stl"
        mesh.export(path)
        components = mesh.split(only_watertight=False)
        item = {
            "name": name,
            "file": str(path.relative_to(ROOT)),
            "vertices": int(len(mesh.vertices)),
            "faces": int(len(mesh.faces)),
            "watertight": bool(mesh.is_watertight),
            "winding_consistent": bool(mesh.is_winding_consistent),
            "positive_volume": bool(mesh.volume > 0),
            "connected_components": int(len(components)),
            "volume_mm3": float(mesh.volume),
            "bounds_mm": np.round(mesh.extents, 3).tolist(),
        }
        report_parts.append(item)

    result = {
        "parts": report_parts,
        "boolean_cleanup": BOOLEAN_CLEANUP,
        "local_reliefs": local_reliefs,
        "edge_finish":edge_finish,
        "passed": all(
            item["watertight"]
            and item["winding_consistent"]
            and item["positive_volume"]
            and item["connected_components"] == 1
            for item in report_parts
        ),
    }
    REPORT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if not result["passed"]:
        raise RuntimeError("Hybrid jointed part topology validation failed")


if __name__ == "__main__":
    main()
