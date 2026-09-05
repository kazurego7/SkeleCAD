"""Print geometry and review gates; no slicer or printer launch in unit tests."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import trimesh
from unittest.mock import patch
import bambu_settings
from prepare_workflow_print import orient,pack
from audit_workflow_motion import moving_parts,pose_matrices
from workflow_store import WorkflowStore,write_json
from test_workflow import image_bytes


class WorkflowPrintTests(unittest.TestCase):
    def test_empty_project_does_not_read_historical_templates(self):
        from bambu_project_schema import empty_project
        from print_package_audit import NS
        with patch('pathlib.Path.open',side_effect=AssertionError('Unexpected template access')):
            root,obj,item,metadata,model,payload=empty_project()
        self.assertEqual(root.get('unit'),'millimeter')
        self.assertIsNotNone(obj.find(NS+'components/'+NS+'component'))
        self.assertIsNotNone(model.find('.//'+NS+'mesh'))
        self.assertEqual(set(payload),{'[Content_Types].xml','_rels/.rels'})

    def test_fast_xml_preserves_coordinate_precision_and_face_order(self):
        from prepare_workflow_print import mesh_xml,NS
        from xml.etree import ElementTree as ET
        from print_package_audit import arrays
        mesh=trimesh.creation.icosphere(subdivisions=1);mesh.vertices*=1.234567890123
        offset=np.array([.123456789123,-.234567891234,.345678912345])
        slow=ET.Element(NS+'mesh');vertices=ET.SubElement(slow,NS+'vertices');faces=ET.SubElement(slow,NS+'triangles')
        for xyz in mesh.vertices-offset:ET.SubElement(vertices,NS+'vertex',**{k:format(float(v),'.12g') for k,v in zip('xyz',xyz)})
        for face in mesh.faces:ET.SubElement(faces,NS+'triangle',**{k:str(v) for k,v in zip(('v1','v2','v3'),face)})
        before=arrays(ET.tostring(slow));after=arrays(mesh_xml(mesh,offset))
        self.assertTrue(np.array_equal(before[0],after[0]));self.assertTrue(np.array_equal(before[1],after[1]))

    def test_gui_preset_merge_preserves_custom_settings(self):
        settings=bambu_settings.native_settings()
        for index,kind,key in [(0,'process','process_preset'),(1,'filament','filament_preset'),(2,'machine','machine_preset')]:
            baseline=bambu_settings.preset(kind,bambu_settings.BAMBU[key])
            changed=set(filter(None,settings['different_settings_to_system'][index].split(';')))
            self.assertTrue(changed<=baseline.keys())
            restored={**baseline,**{k:settings[k] for k in changed}}
            for k,v in baseline.items():
                if k in settings and k not in ('different_settings_to_system','inherits_group'):
                    self.assertEqual(restored[k],settings[k],k)
        self.assertIn('enable_support',settings['different_settings_to_system'][0])
        self.assertIn('support_interface_speed',settings['different_settings_to_system'][0])

    def test_production_print_defaults_to_support_enabled(self):
        with patch.object(bambu_settings,'preset',return_value={}):
            settings=bambu_settings.native_settings()
        self.assertEqual(settings['enable_support'],'1')
        self.assertEqual(settings['support_type'],'tree(auto)')
        self.assertEqual(settings['support_interface_spacing'],'0.2')
        self.assertEqual(settings['support_interface_speed'],['35'])
        self.assertEqual(settings['support_top_z_distance'],'0.2')
        self.assertEqual(settings['support_interface_top_layers'],'3')

    def test_orientation_is_rigid_and_preserves_mating_scale(self):
        mesh=trimesh.creation.box([6,20,8]);R=orient(mesh)
        self.assertTrue(np.allclose(R@R.T,np.eye(3)));self.assertAlmostEqual(np.linalg.det(R),1)
        self.assertAlmostEqual(np.ptp(mesh.vertices@R,axis=0)[2],6)

    def test_large_sets_split_across_beds_without_scaling(self):
        objects=[{'name':str(i),'lo':np.zeros(3),'hi':np.array([120.,120.,12.])} for i in range(3)]
        cfg={'plate_margin_mm':12,'object_gap_mm':12,'plate_width_mm':180}
        plates=pack(objects,cfg);self.assertEqual(len(plates),3)
        for plate in plates:
            obj=plate[0];self.assertTrue(np.all(obj['lo']+obj['shift']>=0));self.assertTrue(np.all(obj['hi']+obj['shift']<180))
        with self.assertRaises(ValueError):pack([{'lo':np.zeros(3),'hi':np.array([200,10,10])}],cfg)

    def test_parent_movement_is_inherited_once(self):
        joints=[{'name':'hip','parent':'root','part':'leg','center':[0,0,0],'direction':[0,1,0]},
                {'name':'ankle','parent':'leg','part':'foot','center':[0,0,-10],'direction':[0,0,-1]}]
        self.assertEqual(moving_parts(joints,'leg'),{'leg','foot'})
        result=pose_matrices(joints,{'hip':[20,0,0],'ankle':[0,0,0]})
        self.assertTrue(np.allclose(result['leg'],result['foot']))
        with self.assertRaises(ValueError):pose_matrices(joints,{'hip':[float('nan'),0,0],'ankle':[0,0,0]})

    def test_print_requires_geometry_bound_clear_pose_and_explicit_confirmation(self):
        with tempfile.TemporaryDirectory() as directory:
            store=WorkflowStore(Path(directory),launch=False);job=store.create(image_bytes());folder=store.directory(job['id'])
            revision='a'*32;out=folder/'machining'/revision;out.mkdir(parents=True)
            write_json(out/'manifest.json',{'joints':[{'name':'j1','part':'arm','parent':'body','center':[0,0,0],'direction':[0,1,0]}]})
            digest=hashlib.sha256((out/'manifest.json').read_bytes()).hexdigest()
            state=store.read(job['id']);state.update(stage='mechanical_review',mechanical_revision=revision,manifest_sha256=digest)
            write_json(folder/'state.json',state)
            data={'accepted':True,'manifest_sha256':digest,'review':{'ready':True,'collision':'clear','pose':{'j1':[0,0,0]}}}
            for change in ({'accepted':False},{'manifest_sha256':'stale'},{'review':{'ready':False}},{'review':{'ready':True,'collision':'collision'}}):
                with self.assertRaises(ValueError):store.request_print(job['id'],{**data,**change})
            store.request_print(job['id'],data)
            self.assertEqual(store.read(job['id'])['operation'],'print')
            self.assertEqual(json.loads((out/'review_approval.json').read_text())['manifest_sha256'],digest)
            with self.assertRaises(ValueError):store.request_print(job['id'],data)


if __name__=='__main__':unittest.main()
