"""Conservative, resolution-independent removal of isolated positive specks."""
import numpy as np
import trimesh


def remove_isolated_specks(mesh, settings):
    shells = list(mesh.split(only_watertight=False))
    largest = max(shells, key=lambda part: part.area)
    candidates = [part for part in shells if part is not largest
                  and part.is_watertight and part.is_winding_consistent
                  and 0 < part.volume <= settings['maximum_speck_volume_mm3']
                  and max(part.extents) <= settings['maximum_speck_extent_mm']]
    reference = [part for part in shells if all(part is not c for c in candidates)
                 and part.volume > 0]
    removed = []
    if reference:
        surface = trimesh.util.concatenate(reference)
        for part in candidates:
            # Exact point-to-triangle distances, independent of reference tessellation.
            _, distances, _ = trimesh.proximity.closest_point(surface, part.vertices)
            gap = float(np.min(distances))
            if gap > settings['minimum_speck_separation_mm']:
                removed.append((part, gap))
    kept = [part for part in shells if all(part is not c for c, _ in removed)]
    result = trimesh.util.concatenate(kept) if removed else mesh.copy()
    return result, {'method': 'isolated_physical_specks_v1',
                    'removed_components': len(removed),
                    'removed_faces': sum(len(part.faces) for part, _ in removed),
                    'removed_volume_mm3': float(sum(part.volume for part, _ in removed)),
                    'components': [{'faces': len(part.faces), 'volume_mm3': float(part.volume),
                                    'extents_mm': part.extents.tolist(), 'gap_mm': gap}
                                   for part, gap in removed], 'settings': dict(settings)}
