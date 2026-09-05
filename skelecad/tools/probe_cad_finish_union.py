import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import trex_v2_project as p
p.add_socket=lambda body,*args:body
body=p.torso_front()
outer,cut=p.socket_components((6,0,75),(1,0,0))
shell=outer.cut(cut)
print('INPUTS',[(s.isValid(),len(s.Solids),s.Volume,s.ShapeType) for s in (body,outer,cut,shell)],flush=True)
for label,s in [('body_cut',body.cut(cut)),('fused',body.fuse(outer)),('solid_cut',body.Solids[0].cut(cut.Solids[0]))]:
    print('STAGE',label,s.isValid(),len(s.Solids),s.Volume,flush=True)
body=body.Solids[0];outer=outer.Solids[0];cut=cut.Solids[0];shell=shell.Solids[0]
for tol in (0,1e-7,1e-6,1e-5):
    for order in ('cut-first','fuse-first'):
        try:
            result=body.cut(cut,tol).fuse(shell,tol) if order=='cut-first' else body.fuse(outer,tol).cut(cut,tol)
            print(tol,order,'before',result.isValid(),len(result.Solids),'after',result.removeSplitter().isValid(),result.Volume,flush=True)
        except Exception as e:print('ERROR',tol,order,str(e),flush=True)
