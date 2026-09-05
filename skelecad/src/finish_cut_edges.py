"""Finite-band mesh finishing of machined anatomy, BEFORE precision hardware.

Only sharp edges on an actual machining/partition tool are eligible. Conforming
edge refinement avoids T junctions. Fairing has compact support and a displacement
limit, and intersection with the input prohibits growing into articulation gaps.
The resulting removal tool is audited against the original seam, not accepted
merely because it was produced by this function.
"""
import numpy as np
import trimesh
import manifold3d
from scipy.spatial import cKDTree
from scipy import sparse


def solid(mesh):
    # Nanobind requires writable C arrays; Trimesh may expose read-only caches.
    vertices=np.array(mesh.vertices,dtype=np.float64,order='C',copy=True).reshape((-1,3))
    faces=np.array(mesh.faces,dtype=np.uint64,order='C',copy=True).reshape((-1,3))
    result=manifold3d.Manifold(manifold3d.Mesh64(vertices,faces))
    if result.is_empty():raise RuntimeError('Empty finishing Boolean input')
    return result


def from_solid(value, clean_faces=True):
    if not clean_faces:
        # Internal audit solids retain the Boolean kernel's closed topology,
        # including negligible facets which must not be deleted into open holes.
        m=value.to_mesh64()
        return trimesh.Trimesh(m.vert_properties[:,:3],m.tri_verts,process=False)
    # Remove sub-micron Boolean slivers before the float32 STL export.
    m=value.simplify(0.00001).to_mesh64()
    return clean(trimesh.Trimesh(m.vert_properties[:,:3],m.tri_verts,process=False))


def clean(mesh):
    mesh.update_faces(mesh.area_faces>0.0)
    mesh.update_faces(mesh.unique_faces())
    mesh.remove_unreferenced_vertices()
    if len(mesh.faces):mesh.fix_normals(multibody=True)
    return mesh


def cut_seams(mesh, cutters, cfg):
    ids=np.flatnonzero((mesh.face_adjacency_angles>np.radians(cfg['sharp_angle_deg']))
                       & mesh.face_adjacency_convex)
    edges=mesh.face_adjacency_edges[ids]
    middle=mesh.vertices[edges].mean(axis=1)
    eligible=np.zeros(len(edges),dtype=bool)
    tol=cfg['tool_surface_tolerance_mm']
    for cutter in cutters:
        candidates=np.flatnonzero(((middle>=cutter.bounds[0]-tol)&(middle<=cutter.bounds[1]+tol)).all(axis=1)&~eligible)
        for start in range(0,len(candidates),128):
            batch=candidates[start:start+128]
            _,distance,_=trimesh.proximity.closest_point(cutter,middle[batch])
            eligible[batch]=distance<=tol
    return mesh.vertices[edges[eligible]]


def seam_samples(segments, spacing):
    return np.vstack([a+(b-a)*np.linspace(0,1,max(2,int(np.ceil(np.linalg.norm(b-a)/spacing))+1))[:,None]
                      for a,b in segments])


def refine_band(mesh, tree, band, length):
    vertices=np.array(mesh.vertices); faces=np.array(mesh.faces)
    for iteration in range(12):
        current=trimesh.Trimesh(vertices,faces,process=False)
        edges=current.edges_unique
        ends=vertices[edges]; sizes=np.linalg.norm(ends[:,1]-ends[:,0],axis=1)
        distances=tree.query(ends.mean(axis=1))[0]
        split=(sizes>length)&(distances<band+sizes/2)
        if not split.any():return current
        mids=np.full(len(edges),-1,dtype=np.int64)
        mids[split]=np.arange(split.sum())+len(vertices)
        vertices=np.vstack((vertices,ends[split].mean(axis=1)))
        per_face=mids[current.edges_unique_inverse.reshape((-1,3))]
        new=[]
        for (a,b,c),(ab,bc,ca) in zip(faces,per_face):
            # Explicit integer count (NumPy boolean addition is logical OR).
            count=sum(int(x>=0) for x in (ab,bc,ca))
            if count==0:new.append((a,b,c))
            elif count==3:new.extend(((a,ab,ca),(ab,b,bc),(ca,bc,c),(ab,bc,ca)))
            elif count==1:
                if ab>=0:new.extend(((a,ab,c),(ab,b,c)))
                elif bc>=0:new.extend(((b,bc,a),(bc,c,a)))
                else:new.extend(((c,ca,b),(ca,a,b)))
            else:
                if ca<0:new.extend(((b,bc,ab),(a,ab,c),(ab,bc,c)))
                elif ab<0:new.extend(((c,ca,bc),(b,bc,a),(bc,ca,a)))
                else:new.extend(((a,ab,ca),(c,ca,b),(ca,ab,b)))
        faces=np.asarray(new,dtype=np.int64)
    raise RuntimeError('Cut-edge refinement did not converge')


def finish(mesh, cutters, cfg, label, fragment_tolerance=None):
    segments=cut_seams(mesh,cutters,cfg)
    record={'part':label,'seam_edges':len(segments),'passed':True}
    if not len(segments):return mesh,None,record,segments
    samples=seam_samples(segments,cfg['sample_step_mm']);tree=cKDTree(samples)
    band=cfg['blend_band_mm'];limit=cfg['max_displacement_mm']
    refined=refine_band(mesh,tree,band,cfg['edge_length_mm'])
    if not refined.is_volume:raise RuntimeError(f'{label}: non-conforming refinement')
    original=refined.vertices.copy();vertices=original.copy()
    distance=tree.query(original)[0]
    weights=np.maximum(1-(distance/band)**2,0)**2
    edges=refined.edges_unique
    rows=np.r_[edges[:,0],edges[:,1]];cols=np.r_[edges[:,1],edges[:,0]]
    graph=sparse.csr_matrix((np.ones(len(rows)),(rows,cols)),shape=(len(vertices),len(vertices)))
    valence=np.asarray(graph.sum(axis=1)).ravel()
    for _ in range(cfg['iterations']):
        delta=(graph@vertices)/valence[:,None]-vertices
        candidate=vertices+cfg['relaxation']*weights[:,None]*delta
        shift=candidate-original;norm=np.linalg.norm(shift,axis=1)
        vertices=original+shift*np.minimum(1,limit/np.maximum(norm,1e-15))[:,None]
    refined.vertices=vertices
    if not refined.is_volume:raise RuntimeError(f'{label}: finishing invalidated mesh')
    # Boolean re-triangulation can create microscopic coplanar slivers outside
    # the fairing band. Clip to an independently constructed, finite seam tube,
    # then reconstruct from the untouched input. No remote surface is replaced.
    tube_points=seam_samples(segments,cfg['edge_length_mm'])
    tube_points=np.unique(np.round(tube_points,6),axis=0)
    ball=manifold3d.Manifold.sphere(cfg['audit_band_mm']-cfg['sample_step_mm'],12)
    tube=manifold3d.Manifold.batch_boolean([ball.translate(q.tolist()) for q in tube_points],manifold3d.OpType.Add)
    # Subtract the complement of the smoothed anatomy INSIDE this tube. This
    # avoids using near-zero raw-minus-smoothed slivers as Boolean inputs.
    removal_solid=tube-solid(refined)
    removal=from_solid(removal_solid,clean_faces=False)
    result=from_solid(solid(mesh)-removal_solid)
    if fragment_tolerance is None:
        from hybrid_context import H
        fragment_tolerance=H['boolean_fragment_max_volume_mm3']
    fragments=[]
    components=result.split(only_watertight=False)
    if len(components)>1:
        main=max(components,key=lambda m:abs(m.volume))
        for component in components:
            if component is main:continue
            if not component.is_volume or abs(component.volume)>fragment_tolerance:
                raise RuntimeError(f'{label}: finishing detached anatomy: volume={component.volume}, closed={component.is_volume}, faces={len(component.faces)}')
            certify_band(component,segments,cfg)
            fragments.append(float(component.volume))
            removal_solid=removal_solid+solid(component)
        result=main;removal=from_solid(removal_solid,clean_faces=False)
    if not result.is_volume or len(result.split())!=1:
        raise RuntimeError(f'{label}: bounded finishing invalid; volume={result.is_volume}; components={[(len(m.faces),m.volume) for m in result.split(only_watertight=False)]}')
    # Test complete boundary triangles, not only their vertices. Every triangle
    # is certified inside a sphere at its centroid with radius its furthest
    # vertex; the nearest seam sample then bounds its entire distance to seam.
    allowed=cfg['audit_band_mm']
    if not removal.is_volume:raise RuntimeError(f'{label}: invalid internal removal solid')
    certified=certify_band(removal,segments,cfg)
    max_shift=float(np.linalg.norm(vertices-original,axis=1).max())
    record.update({'input_volume_mm3':float(mesh.volume),'removed_volume_mm3':float(mesh.volume-result.volume),
                   'local_numerical_fragments_mm3':fragments,
                   'max_vertex_shift_mm':max_shift,'certified_removal_band_mm':certified,
                   'audit_band_mm':allowed,'refined_faces':len(refined.faces),
                   'passed':bool(certified<=allowed and max_shift<=limit+1e-8)})
    if not record['passed']:raise RuntimeError(f'Finishing escaped its finite seam allowance: {record}')
    return result,removal,record,segments


def certify_band(removal, segments, cfg):
    """Conservative whole-triangle proof; subdivide loose bounds, not geometry."""
    tree=cKDTree(seam_samples(segments,cfg['sample_step_mm']))
    triangles=removal.triangles.copy(); certified=0.0
    for depth in range(12):
        centers=triangles.mean(axis=1)
        radii=np.linalg.norm(triangles-centers[:,None,:],axis=2).max(axis=1)
        bound=tree.query(centers)[0]+radii
        good=bound<=cfg['audit_band_mm']
        if good.any():certified=max(certified,float(bound[good].max()))
        triangles=triangles[~good]
        if not len(triangles):return certified
        actual=tree.query(triangles.reshape(-1,3))[0].max()
        if actual>cfg['audit_band_mm']+1e-4:
            raise RuntimeError(f'Finish removal vertex outside seam band: {actual}')
        a,b,c=triangles[:,0],triangles[:,1],triangles[:,2]
        ab=(a+b)/2;bc=(b+c)/2;ca=(c+a)/2
        triangles=np.concatenate([np.stack(t,axis=1) for t in ((a,ab,ca),(ab,b,bc),(ca,bc,c),(ab,bc,ca))])
    raise RuntimeError('Unable to certify complete finishing removal inside seam band')
