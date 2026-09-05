"""Run with FreeCAD's Python: exact C4 slit reflection, including oblique axes."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import FreeCAD as App
from freecad_workflow_tools import socket_rotation,workflow_socket_shell,authority,V


class SocketSymmetryTests(unittest.TestCase):
    def test_exact_shell_reflections(self):
        label=authority.PARAMS['image_workflow']['manufacturing']['joint_variant']
        variant=next(v for v in authority.PARAMS['joint_retention_trial']['deep_c4']['variants'] if v['label']==label)
        base,_=workflow_socket_shell(variant)
        mirror=App.Matrix();mirror.A11=-1
        for axis in (V(.4,.7,.3),V(0,.7,.3),V(1,0,0),V(-1,0,0)):
            with self.subTest(axis=tuple(axis)):
                left=base.copy();left.Placement=App.Placement(V(),socket_rotation(axis))
                right=base.copy();right.Placement=App.Placement(V(),socket_rotation(V(-axis.x,axis.y,axis.z)))
                reflected=left.transformGeometry(mirror)
                self.assertTrue(right.isValid())
                self.assertLess(reflected.cut(right).Volume+right.cut(reflected).Volume,1e-6)


if __name__=='__main__':unittest.main()
