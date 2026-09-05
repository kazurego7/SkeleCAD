"""Create a traceable scaled anatomy input; never scale dimensioned joints."""
import hashlib
import json
import trimesh
from hybrid_context import ROOT, H, HYBRID, INPUT

def prepare():
    cfg=H['palm_size']
    source=ROOT/cfg['source_mesh']
    mesh=trimesh.load_mesh(source)
    factor=(cfg['target_assembly_length_mm']-cfg['head_extra_forward_mm']-cfg['tail_extra_rearward_mm'])/cfg['reference_assembly_length_mm']
    mesh.apply_scale(factor)
    if not mesh.is_volume: raise RuntimeError('Invalid scaled anatomy')
    HYBRID.mkdir(parents=True,exist_ok=True)
    mesh.export(INPUT)
    report={'original_source':str(source.relative_to(ROOT)),
            'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'anatomy_scale':factor,'source_extents_mm':mesh.extents.tolist(),
            'joint_dimensions_scaled':False,'effective_hybrid_parameters':H}
    (HYBRID/'sizing.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='effective_hybrid_parameters'}))

if __name__=='__main__': prepare()
