"""Audit the actual R2 STL and 3MF files, independent of FreeCAD's in-memory mesh."""
import hashlib,json,sys,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import trimesh
from print_package_audit import NS,arrays

ROOT=Path(__file__).resolve().parents[1]

def main(config_key='joint_holding_trial'):
    params=json.loads((ROOT/'config/parameters.json').read_text(encoding='utf-8'))
    c=params[config_key];out=ROOT/c['output_directory'];records=[]
    for v in c['variants']:
        for suffix in ('socket','ball_key'):
            name=v['label']+'_'+suffix;stl=out/'parts'/(name+'.stl');package=out/'parts'/(name+'.3mf')
            mesh=trimesh.load(stl,force='mesh',process=True)
            assert mesh.is_volume and len(mesh.split(only_watertight=False))==1,name
            with zipfile.ZipFile(package) as z:
                assert z.testzip() is None
                xml=z.read('3D/3dmodel.model');root=ET.fromstring(xml)
                assert root.get('unit')=='millimeter'
                vertices,faces=arrays(xml)
            other=trimesh.Trimesh(vertices,faces,process=True)
            assert other.is_volume and len(other.split(only_watertight=False))==1,name
            assert len(mesh.faces)==len(other.faces) and abs(mesh.volume-other.volume)<.001,name
            records.append({'name':name,'watertight':True,'components':1,'volume_mm3':float(mesh.volume),
                            'stl_sha256':hashlib.sha256(stl.read_bytes()).hexdigest(),
                            'three_mf_sha256':hashlib.sha256(package.read_bytes()).hexdigest()})
    report={'passed':True,'parts':records,'units':'millimeter'}
    (out/'topology_audit.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report),flush=True)
    return report

if __name__=='__main__':main(sys.argv[1] if len(sys.argv)>1 else 'joint_holding_trial')
