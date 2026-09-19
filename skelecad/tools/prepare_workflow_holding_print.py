"""Fit coupons use the same native print profile as image models."""
import prepare_retention_print as shared
import json, shutil, zipfile
from xml.etree import ElementTree as ET
import numpy as np
import trimesh
from print_package_audit import NS,PNS,arrays

def main(config_key='joint_workflow_holding_trial'):
    config=shared.PARAMS[config_key]
    revision=config['revision'];first=config['variants'][0]['label'];last=config['variants'][-1]['label']
    shared.BASE=shared.ROOT/config['output_directory']
    shared.main([v['label']+suffix for v in config['variants'] for suffix in ('_socket','_ball_key')],
                title=f'Holding {revision} - C4_28 - {first} to {last}',native_profile=True,paired_layout=True)
    output=shared.BASE/'print'
    path=output/'input.3mf'
    meshes=[]
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        settings=json.loads(archive.read('Metadata/project_settings.config'))
        assert settings==shared.native_settings()
        root=ET.fromstring(archive.read('3D/3dmodel.model'))
        resources={obj.get('id'):obj for obj in root.find(NS+'resources')}
        for item in root.find(NS+'build'):
            component=resources[item.get('objectid')].find(NS+'components/'+NS+'component')
            vertices,faces=arrays(archive.read(component.get(PNS+'path').lstrip('/')))
            transform=np.array([float(x) for x in item.get('transform').split()])
            rotation=transform[:9].reshape(3,3)
            assert np.allclose(rotation@rotation.T,np.eye(3))
            mesh=trimesh.Trimesh(vertices@rotation+transform[9:],faces,process=True)
            assert mesh.is_volume and len(mesh.split())==1
            meshes.append(mesh)
    assert len(meshes)==2*len(config['variants'])
    for i,mesh in enumerate(meshes):
        for other in meshes[i+1:]:
            assert np.any(mesh.bounds[1] <= other.bounds[0]) or np.any(other.bounds[1] <= mesh.bounds[0])
    trimesh.util.concatenate(meshes).export(output/'plate_preview.stl')
    if config.get('number_label'):
        samples=[]
        for index,mesh in enumerate(meshes[-2:]):
            sample=mesh.copy()
            sample.vertices-=sample.bounds.mean(axis=0)
            sample.vertices*=np.array([1,-1,-1])
            sample.vertices[:,0]+=index*config['preview_spacing_mm']
            samples.append(sample)
        trimesh.util.concatenate(samples).export(output/'number_preview.stl')

    shutil.copy2(path,output/f'SkeleCAD_Holding_{revision}_{first}-{last}.3mf')
    (output/'profile_audit.json').write_text(json.dumps({'passed':True,'native_profile':True,'objects':len(meshes),'plate_collisions':0}),encoding='utf-8')

if __name__=='__main__':
    import sys
    main(sys.argv[1] if len(sys.argv)>1 else 'joint_workflow_holding_trial')
