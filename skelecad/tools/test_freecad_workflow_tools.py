"""FreeCAD regressions for arbitrary image-workflow joint tools."""
import unittest
import tempfile
from pathlib import Path

import FreeCAD as App
import Mesh
import Part
import MeshPart

import freecad_project as authority
from freecad_workflow_tools import safe_refine, workflow_socket_shell, resolve_workflow_variant
from joint_retention_trial import deep_c4
from trex_v2_project import capsule


class WorkflowToolCadTests(unittest.TestCase):
    def test_selected_fit_matches_coupon_and_rejects_unselected_interference(self):
        import copy
        params=authority.PARAMS
        cfg=copy.deepcopy(params['image_workflow']['manufacturing'])
        variant=resolve_workflow_variant(cfg,params)
        self.assertEqual(variant['cavity_clearance_mm'],-.25)
        shell,_=workflow_socket_shell(variant)
        self.assertFalse(shell.isInside(App.Vector(-1,-1,-1).normalize()*2.865,1e-7,True))
        self.assertTrue(shell.isInside(App.Vector(-1,-1,-1).normalize()*2.885,1e-7,True))
        self.assertTrue(shell.isValid())
        self.assertGreater(shell.common(Part.makeSphere(3)).Volume,0)
        cfg['cavity_clearance_mm']=-.275
        with self.assertRaises(ValueError):resolve_workflow_variant(cfg,params)
        cfg.pop('fit_selection')
        with self.assertRaises(ValueError):resolve_workflow_variant(cfg,params)

    def test_workflow_socket_omits_flat_calibration_mount_and_labels(self):
        trial=authority.PARAMS['joint_retention_trial']
        workflow=authority.PARAMS['image_workflow']['manufacturing']
        variant=next(v for v in trial['deep_c4']['variants'] if v['label']==workflow['joint_variant'])
        rounded,void=workflow_socket_shell(variant)
        coupon=deep_c4(variant)
        ro=(trial['ball_diameter_mm']+trial['deep_c4']['cavity_clearance_mm'])/2+trial['deep_c4']['wall_mm']
        self.assertTrue(rounded.isValid());self.assertEqual(len(rounded.Solids),1)
        self.assertTrue(void.isValid());self.assertAlmostEqual(rounded.BoundBox.XMin,-ro,places=5)
        self.assertLess(coupon.BoundBox.XMin,rounded.BoundBox.XMin-1.5)
        self.assertLess(rounded.Volume,coupon.Volume)

    def test_invalid_oblique_refinement_keeps_valid_boolean(self):
        trial=authority.PARAMS['joint_retention_trial']
        workflow=authority.PARAMS['image_workflow']['manufacturing']
        variant=next(v for v in trial['deep_c4']['variants'] if v['label']==workflow['joint_variant'])
        center=App.Vector(5.306122149374014,-6.055768824487643,-12.414850165471702)
        axis=App.Vector(0.430688137284223,-0.756124804214165,-0.492730158255751);axis.normalize()
        parent=App.Vector(-0.144038624252951,-11.6995728311579,-11.3809671764804)
        shell,void=deep_c4(variant,return_void=True)
        placement=App.Placement(center,App.Rotation(App.Vector(1,0,0),axis))
        shell.Placement=placement;shell=shell.copy();void.Placement=placement;void=void.copy()
        ri=(trial['ball_diameter_mm']+trial['deep_c4']['cavity_clearance_mm'])/2
        ro=ri+trial['deep_c4']['wall_mm']
        back=center-axis*(ro-workflow['socket_bridge_overlap_mm'])
        bridge=capsule(tuple(back),tuple(parent),workflow['socket_bridge_radius_mm'])
        unsafe=shell.fuse(bridge).cut(void)
        self.assertTrue(unsafe.isValid())
        self.assertFalse(unsafe.removeSplitter().isValid(),'fixture must continue to exercise the OpenCascade edge case')
        raw=shell.fuse(bridge.cut(void));result,fallback=safe_refine(raw)
        self.assertFalse(fallback);self.assertTrue(result.isValid());self.assertEqual(len(result.Solids),1)
        self.assertAlmostEqual(result.Volume,unsafe.Volume,places=4)
        trial=authority.PARAMS['joint_retention_trial']
        mesh=MeshPart.meshFromShape(Shape=result,LinearDeflection=trial['mesh_linear_deflection_mm'],
                                    AngularDeflection=trial['mesh_angular_deflection_rad'],Relative=False)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'socket.stl';mesh.write(str(path))
            self.assertTrue(Mesh.Mesh(str(path)).isSolid())


if __name__=='__main__':unittest.main()
