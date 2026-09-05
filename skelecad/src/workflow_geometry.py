"""Geometry-derived joint proposals, without species names or pre-annotated centres.

Proposals are not approved cuts or dimensioned printable joints. Fit curved surface
patches to spheres, then score global support and merge redundant detections.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import trimesh
from scipy.spatial import cKDTree
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components, dijkstra


def sphere_candidates(mesh, parameters):
    rng=np.random.default_rng(parameters['seed'])
    count=parameters['surface_samples']
    face_ids=rng.choice(len(mesh.faces),size=count,replace=True,p=mesh.area_faces/mesh.area)
    uv=rng.random((count,2));uv[uv.sum(axis=1)>1]=1-uv[uv.sum(axis=1)>1]
    triangles=mesh.triangles[face_ids]
    points=triangles[:,0]+uv[:,:1]*(triangles[:,1]-triangles[:,0])+uv[:,1:]*(triangles[:,2]-triangles[:,0])
    # Interpolating normals reduces tessellation-dependent curvature noise.
    vertex_normals=mesh.vertex_normals[mesh.faces[face_ids]]
    normals=vertex_normals[:,0]*(1-uv.sum(axis=1))[:,None]+vertex_normals[:,1]*uv[:,:1]+vertex_normals[:,2]*uv[:,1:]
    normals/=np.maximum(np.linalg.norm(normals,axis=1,keepdims=True),1e-12)
    tree=cKDTree(points);proposals=[]
    seed_ids=rng.choice(count,min(count,parameters['seed_samples']),replace=False)
    for patch_radius in parameters['patch_radii_mm']:
        for index in seed_ids:
            neighbours=tree.query_ball_point(points[index],patch_radius)
            if len(neighbours)<16:continue
            p=points[neighbours];n=normals[neighbours]
            pm=p.mean(axis=0);nm=n.mean(axis=0)
            dp=p-pm;dn=n-nm
            denominator=(dn*dn).sum()
            if denominator/len(n)<.08:continue
            radius=float((dp*dn).sum()/denominator)
            if not parameters['minimum_radius_mm']<radius<parameters['maximum_radius_mm']:continue
            center=pm-radius*nm
            residual=np.linalg.norm(p-center-radius*n,axis=1)
            if np.quantile(residual,.85)>radius*parameters['patch_error_ratio']:continue
            # A sphere needs normal variation in two tangent directions. A bevel
            # cylinder varies in only one, and must not become an articulated joint.
            values=np.linalg.eigvalsh(dn.T@dn/len(n))
            if values[1]<.025 or values[1]/max(values[2],1e-12)<.2:continue
            proposals.append((center,radius,float(np.mean(residual))))
    if not proposals:return []
    centers=np.array([p[0] for p in proposals]);center_tree=cKDTree(centers)
    ranking=sorted(range(len(proposals)),key=lambda i:len(center_tree.query_ball_point(centers[i],parameters['cluster_distance_mm'])),reverse=True)
    chosen=[]
    for index in ranking:
        center,radius,fit_error=proposals[index]
        if any(np.linalg.norm(center-c['center'])<max(radius,c['radius_mm'])*.8 for c in chosen):continue
        neighbour_ids=center_tree.query_ball_point(center,parameters['cluster_distance_mm'])
        if len(neighbour_ids)<parameters['minimum_patch_votes']:continue
        center=np.median(centers[neighbour_ids],axis=0)
        radius=float(np.median([proposals[i][1] for i in neighbour_ids]))
        nearby=tree.query_ball_point(center,radius*1.2)
        p=points[nearby];n=normals[nearby];delta=p-center
        distances=np.linalg.norm(delta,axis=1)
        supported=(np.abs(distances-radius)<radius*parameters['surface_error_ratio'])&((delta*n).sum(axis=1)/np.maximum(distances,1e-12)>.9)
        support=int(supported.sum())
        area_estimate=support/count*mesh.area
        coverage=float(area_estimate/(4*np.pi*radius**2))
        if coverage<parameters['minimum_coverage']:continue
        directions=delta[supported]/distances[supported,None]
        normal_cov=np.linalg.eigvalsh(np.cov(directions.T))
        if normal_cov[0]<.035:continue
        chosen.append({'name':f'candidate_{len(chosen)+1:02d}','center':center.tolist(),'radius_mm':radius,
                       'surface_coverage_estimate':min(coverage,1.),'support_samples':support,'patch_votes':len(neighbour_ids),
                       'fit_error_mm':fit_error,'status':'proposal_requires_review'})
    return chosen


def infer_branches(mesh,candidates,parameters):
    """Distinguish a terminal round hand/bevel from a junction of two parts.

    Only label faces for inference. No cuts, discarded faces or exported geometry.
    """
    centers=mesh.triangles_center
    excluded=np.zeros(len(mesh.faces),dtype=bool)
    regions=[]
    for candidate in candidates:
        region=np.linalg.norm(centers-np.asarray(candidate['center']),axis=1)<candidate['radius_mm']*parameters['branch_envelope_ratio']
        regions.append(region);excluded|=region
    kept=np.flatnonzero(~excluded)
    mapping=np.full(len(mesh.faces),-1,dtype=np.int32);mapping[kept]=np.arange(len(kept))
    adjacency=mesh.face_adjacency
    edges=mapping[adjacency[np.all(~excluded[adjacency],axis=1)]]
    graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(kept),len(kept)))
    count,labels=connected_components(graph,directed=False)
    areas=np.bincount(labels,weights=mesh.area_faces[kept],minlength=count)
    valid=np.flatnonzero(areas>=parameters['minimum_core_area_mm2'])
    order=sorted(valid,key=lambda i:areas[i],reverse=True)
    core_ids={label:f'core_{i:02d}' for i,label in enumerate(order)}
    face_labels=np.full(len(mesh.faces),-1,dtype=np.int32);face_labels[kept]=labels
    cores=[]
    for label in order:
        ids=kept[labels==label]
        centre=np.average(centers[ids],axis=0,weights=mesh.area_faces[ids])
        seed=centers[ids[np.argmin(np.linalg.norm(centers[ids]-centre,axis=1))]]
        cores.append({'name':core_ids[label],'area_mm2':float(areas[label]),'centroid':centre.tolist(),'surface_seed':seed.tolist()})
    for candidate,region in zip(candidates,regions):
        crossings=adjacency[np.any(region[adjacency],axis=1)&~np.all(region[adjacency],axis=1)]
        adjoining=np.unique(face_labels[crossings])
        names=[core_ids[int(label)] for label in adjoining if label in core_ids]
        candidate['adjacent_cores']=names
        candidate['classification']='two_part_junction' if len(names)==2 else ('terminal_or_decoration' if len(names)==1 else 'ambiguous')
    links=[{'candidate':c['name'],'cores':c['adjacent_cores']} for c in candidates if c['classification']=='two_part_junction']
    return {'cores':cores,'links':links,'root_candidate':choose_root_candidate(cores,links),
            'geometry_modified':False,'requires_review':True}


def choose_root_candidate(cores,links):
    """Prefer a multi-limb hub over one large peripheral surface.

    Surface area alone selects a wing or tail when it is larger than the torso,
    which reverses one side of bilateral parent/child relationships. A node
    with at least three connections is an unambiguous articulation hub; simple
    chains retain the established largest-core behaviour.
    """
    if not cores:return None
    degree={core['name']:0 for core in cores}
    for link in links:
        for name in link['cores']:
            if name in degree:degree[name]+=1
    maximum=max(degree.values(),default=0)
    if maximum<3:return cores[0]['name']
    areas={core['name']:float(core['area_mm2']) for core in cores}
    return max(degree,key=lambda name:(degree[name],areas[name]))


def partition_preview(mesh,candidates,branches,parameters,output_directory,filename_prefix='preview'):
    """Color a complete surface by geodesic distance from the inferred part cores.

    These OPEN surface groups are not printable parts. Preserve each input face
    exactly once and keep the unpartitioned closed mesh for later exact machining.
    """
    accepted=[c for c in candidates if c['classification']=='two_part_junction']
    if not accepted:return None
    centers=mesh.triangles_center
    excluded=np.zeros(len(mesh.faces),dtype=bool)
    for c in accepted:
        excluded|=np.linalg.norm(centers-np.array(c['center']),axis=1)<c['radius_mm']*parameters['branch_envelope_ratio']
    adjacency=mesh.face_adjacency;kept=np.flatnonzero(~excluded)
    mapping=np.full(len(mesh.faces),-1,dtype=np.int32);mapping[kept]=np.arange(len(kept))
    edges=mapping[adjacency[np.all(~excluded[adjacency],axis=1)]]
    graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(kept),len(kept)))
    _,labels=connected_components(graph,directed=False)
    areas=np.bincount(labels,weights=mesh.area_faces[kept]);valid=np.flatnonzero(areas>=parameters['minimum_core_area_mm2'])
    if len(valid)<2:return None
    # Repeatable part numbering, root is the largest core; no dinosaur name table.
    order=sorted(valid,key=lambda i:areas[i],reverse=True);part_index={label:i for i,label in enumerate(order)}
    initial=np.full(len(mesh.faces),-1,dtype=np.int32)
    for label,index in part_index.items():initial[kept[labels==label]]=index
    seeds=np.flatnonzero(initial>=0)
    weights=np.linalg.norm(centers[adjacency[:,0]]-centers[adjacency[:,1]],axis=1)
    graph=coo_matrix((np.maximum(weights,1e-9),(adjacency[:,0],adjacency[:,1])),shape=(len(mesh.faces),len(mesh.faces))).tocsr()
    _,_,sources=dijkstra(graph,directed=False,indices=seeds,min_only=True,return_predecessors=True)
    # Small disconnected decorations may be below minimum_core_area_mm2 and have
    # no geodesic route to a retained core. Preserve them exactly once by joining
    # them to the spatially nearest seeded surface instead of dropping the faces
    # or aborting the complete preview.
    unreachable=np.flatnonzero(sources<0)
    if len(unreachable):
        _,nearest=cKDTree(centers[seeds]).query(centers[unreachable],k=1)
        sources[unreachable]=seeds[np.asarray(nearest,dtype=np.int64)]
    assignment=initial[sources];parts=[];palette=['#b7c1ce','#f1b85b','#f27578','#aa88ec','#51bbd0','#7894ee','#91c85b','#e2a1d3','#d18a50','#58cbb2','#c1a0ef','#bdd071']
    for index in range(len(order)):
        faces=np.flatnonzero(assignment==index)
        part=trimesh.Trimesh(vertices=mesh.vertices.copy(),faces=mesh.faces[faces].copy(),process=False)
        part.remove_unreferenced_vertices();filename=f'{filename_prefix}_part_{index:02d}.stl';part.export(output_directory/filename)
        parts.append({'name':f'part_{index:02d}','label':f'パーツ {index+1}','color':palette[index%len(palette)],
                      'filename':filename,'sha256':hashlib.sha256((output_directory/filename).read_bytes()).hexdigest(),
                      'faces':len(faces),'watertight':bool(part.is_watertight),'manufacturing_ready':False})
    np.savez_compressed(output_directory/'preview_assignment.npz',face_part=assignment)
    return {'parts':parts,'original_faces':len(mesh.faces),'assigned_faces':int(sum(p['faces'] for p in parts)),
            'all_source_faces_preserved_once':bool(np.all(assignment>=0)),'stage':'partition_preview',
            'nearest_assigned_disconnected_faces':int(len(unreachable)),
            'print_ready':False,'note':'Surface labels only; open part boundaries need CAD machining before articulation/printing.'}


def analyse(input_path, output_path, parameters):
    mesh=trimesh.load(input_path,force='mesh',process=True)
    candidates=sphere_candidates(mesh,parameters)
    branches=infer_branches(mesh,candidates,parameters)
    preview=partition_preview(mesh,candidates,branches,parameters,output_path.parent)
    report={'schema_version':1,'source_sha256':hashlib.sha256(input_path.read_bytes()).hexdigest(),
            'method':'surface-normal sphere fitting, no anatomical labels or fixed centres',
            'parameters':parameters,'candidates':candidates,'branch_graph':branches,'partition_preview':preview,'cutting_performed':False,
            'limitations':['Sphere-like geometry is not necessarily an intended joint.',
                           'Occluded, deformed or very small joints may be missed.']}
    output_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--input',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();config=json.loads((Path(__file__).resolve().parents[1]/'config/parameters.json').read_text(encoding='utf-8'))
    print(json.dumps(analyse(args.input,args.output,config['image_workflow']['joint_detection']),indent=2))
