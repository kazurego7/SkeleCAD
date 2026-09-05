"""Safety checks for arbitrary-model machining, not dinosaur-specific labels."""
import tempfile
import hashlib
import unittest
from unittest.mock import patch
from pathlib import Path
import numpy as np
import trimesh
from machine_image_job import tree_joints, choose_shell_relief, interior_anchor, export_print_mesh, solid, apply_partition_cuts, assign_marker_numbers, constrain_joint_directions, axis_anchor, ray_axis_anchors, _rotated_directions, fit_constrained_joint_axes, classify_hardware_interference, remove_boolean_micro_fragments, local_mesh_digest, apply_cached_joint, previous_machining_cache


class MachiningTests(unittest.TestCase):
    def test_cad_failure_keeps_detail_in_log_and_exception(self):
        from machine_image_job import cad
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as folder:
            output=Path(folder)
            with patch('machine_image_job.subprocess.run',return_value=SimpleNamespace(returncode=1,stdout=b'Traceback\nValueError: invalid socket\n')), patch('builtins.print') as report:
                with self.assertRaisesRegex(RuntimeError,'ValueError: invalid socket'):
                    cad(output,{'phase':'joint'})
            self.assertIn('invalid socket',(output/'cad_joint.log').read_text())
            report.assert_called_once()

    def test_batched_geometry_digest_preserves_original_bytes(self):
        rng=np.random.default_rng(3407)
        mesh=trimesh.Trimesh(vertices=rng.integers(-4,5,size=(300,3)).astype(float),
                             faces=np.arange(300).reshape(-1,3),process=False)
        triangles=mesh.triangles
        canonical=np.asarray([t[np.lexsort((t[:,2],t[:,1],t[:,0]))].reshape(-1)
                              for t in triangles],dtype='<f8')
        order=np.lexsort(tuple(canonical[:,i] for i in range(8,-1,-1)))
        expected=hashlib.sha256(canonical[order].tobytes()).hexdigest()
        self.assertEqual(local_mesh_digest(mesh,[0,0,0],10),expected)
        self.assertEqual(local_mesh_digest(mesh,[50,50,50],1),hashlib.sha256(b'').hexdigest())

    def test_bilateral_markers_share_one_visible_number(self):
        candidates=[{'name':'left','symmetry_pair_id':'pair_1'},{'name':'right','symmetry_pair_id':'pair_1'},{'name':'middle'}]
        assign_marker_numbers(candidates)
        self.assertEqual([candidate['marker_number'] for candidate in candidates],[1,1,2])

    def test_centre_plane_and_bilateral_joint_directions_are_constrained(self):
        joints=[
            {'name':'centre','placement_method':'midline_plane_snap_v1','direction':[.2,.8,.4]},
            {'name':'left','symmetry_pair_id':'pair_1','direction':[.8,.5,.1]},
            {'name':'right','symmetry_pair_id':'pair_1','direction':[-.7,.6,.2]},
        ]
        constrain_joint_directions(joints,'x')
        self.assertAlmostEqual(joints[0]['direction'][0],0.0)
        left=np.asarray(joints[1]['direction']);right=np.asarray(joints[2]['direction']);right[0]*=-1
        np.testing.assert_allclose(left,right,atol=1e-12)
        self.assertEqual(joints[0]['direction_rule'],'centre_plane_straight_v1')
        self.assertEqual(joints[1]['direction_rule'],'bilateral_mirror_v1')

    def test_axis_anchor_stays_on_constrained_axis_and_embeds(self):
        mesh=trimesh.creation.box([8,8,8]);cfg={'axis_anchor_sample_step_mm':.1,'anchor_embed_mm':1,'maximum_anchor_distance_mm':10}
        anchor=axis_anchor(mesh,np.array([6,0,0]),np.array([-1,0,0]),cfg)
        np.testing.assert_allclose(anchor,[3,0,0],atol=.11)
        self.assertTrue(mesh.contains(anchor.reshape(1,3))[0])

    def test_axis_ray_backend_error_is_explicit_and_never_falls_back(self):
        mesh=trimesh.creation.box([8,8,8]);cfg={'axis_anchor_sample_step_mm':.1,'anchor_embed_mm':1,'maximum_anchor_distance_mm':10}
        with patch.object(mesh.ray,'intersects_location',side_effect=RuntimeError('backend unavailable')):
            with self.assertRaisesRegex(RuntimeError,'光線交差計算に失敗.*backend unavailable'):
                axis_anchor(mesh,np.array([6,0,0]),np.array([-1,0,0]),cfg)

    def test_corrupt_completed_cache_is_reported_not_ignored(self):
        with tempfile.TemporaryDirectory() as directory:
            job=Path(directory);revision=job/'machining'/'old';revision.mkdir(parents=True)
            (revision/'status.json').write_text('{"stage":"mechanical_review"}',encoding='utf-8')
            (revision/'machining_cache.json').write_text('{broken',encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError,'加工キャッシュを読み取れません'):
                previous_machining_cache(job,job/'machining'/'new','source','settings')

    def test_local_geometry_identity_ignores_only_provably_remote_changes(self):
        local=trimesh.creation.box([4,4,4]);remote=trimesh.creation.box([2,2,2]);remote.apply_translation([30,0,0])
        baseline=local_mesh_digest(local,[0,0,0],5)
        self.assertEqual(local_mesh_digest(trimesh.util.concatenate([local,remote]),[0,0,0],5),baseline)
        changed=local.copy();changed.apply_translation([.1,0,0])
        self.assertNotEqual(local_mesh_digest(changed,[0,0,0],5),baseline)

    def test_bilateral_axis_fit_rotates_without_moving_centres(self):
        left_parent=trimesh.creation.box([2,3,3]);left_parent.apply_translation([-4,0,0])
        left_child=trimesh.creation.box([2,3,3]);left_child.apply_translation([-4,5,0])
        right_parent=left_parent.copy();right_parent.apply_scale([-1,1,1])
        right_child=left_child.copy();right_child.apply_scale([-1,1,1])
        joints=[
            {'name':'left','marker_number':1,'symmetry_pair_id':'p','parent':'lp','part':'lc','center':[-4,2.5,0],'direction':[1,1,0]},
            {'name':'right','marker_number':1,'symmetry_pair_id':'p','parent':'rp','part':'rc','center':[4,2.5,0],'direction':[-1,1,0]},
        ]
        constrain_joint_directions(joints,'x')
        cfg={'axis_anchor_sample_step_mm':.1,'anchor_embed_mm':.4,'maximum_anchor_distance_mm':5,
             'axis_search_step_deg':5,'axis_search_coarse_step_deg':15,'axis_search_max_angle_deg':75,'axis_search_azimuth_step_deg':30}
        base=np.asarray(joints[0]['direction']);choices=list(_rotated_directions(base,75,5,30));directions=np.asarray([choice[0] for choice in choices])
        mirrored=directions.copy();mirrored[:,0]*=-1
        results=[ray_axis_anchors(mesh,joint['center'],direction,cfg) for mesh,joint,direction in
                 ((left_parent,joints[0],-directions),(left_child,joints[0],directions),
                  (right_parent,joints[1],-mirrored),(right_child,joints[1],mirrored))]
        expected=next(index for index in range(len(choices)) if all(result[index] is not None for result in results))
        original=[joint['center'][:] for joint in joints]
        fit_constrained_joint_axes(joints,{'lp':left_parent,'lc':left_child,'rp':right_parent,'rc':right_child},cfg,'x')
        self.assertEqual([joint['center'] for joint in joints],original)
        left=np.asarray(joints[0]['direction']);right=np.asarray(joints[1]['direction']);right[0]*=-1
        np.testing.assert_allclose(left,right,atol=1e-12)
        self.assertGreater(joints[0]['direction_adjustment_deg'],0)
        np.testing.assert_allclose(joints[0]['direction'],choices[expected][0],atol=1e-12)

    def test_bilateral_axis_fit_handles_opposite_tree_orientation(self):
        left_parent=trimesh.creation.box([6,2,3]);left_parent.apply_translation([-4,0,0])
        left_child=trimesh.creation.box([6,2,3]);left_child.apply_translation([-4,5,0])
        right_parent=left_child.copy();right_parent.apply_scale([-1,1,1])
        right_child=left_parent.copy();right_child.apply_scale([-1,1,1])
        joints=[
            {'name':'left','marker_number':1,'symmetry_pair_id':'p','parent':'lp','part':'lc','center':[-4,2.5,0],'direction':[-.6,.8,0]},
            {'name':'right','marker_number':1,'symmetry_pair_id':'p','parent':'rp','part':'rc','center':[4,2.5,0],'direction':[-.6,-.8,0]},
        ]
        constrain_joint_directions(joints,'x')
        self.assertEqual(joints[0]['symmetry_direction_sign'],1.0)
        self.assertEqual(joints[1]['symmetry_direction_sign'],-1.0)
        left=np.asarray(joints[0]['direction']);right=np.asarray(joints[1]['direction']);right[0]*=-1
        np.testing.assert_allclose(left,-right,atol=1e-12)
        # Even if the initial orientation hint is stale or ambiguous, fitting
        # must test the other exact axis orientation before rejecting the pair.
        joints[1]['symmetry_direction_sign']=1.0
        cfg={'axis_anchor_sample_step_mm':.1,'anchor_embed_mm':.4,'maximum_anchor_distance_mm':5,
             'axis_search_step_deg':5,'axis_search_coarse_step_deg':15,'axis_search_max_angle_deg':75,'axis_search_azimuth_step_deg':30}
        fit_constrained_joint_axes(joints,{'lp':left_parent,'lc':left_child,'rp':right_parent,'rc':right_child},cfg,'x')
        self.assertEqual(joints[1]['symmetry_direction_sign'],-1.0)
        self.assertTrue(left_parent.contains([joints[0]['parent_anchor']])[0])
        self.assertTrue(left_child.contains([joints[0]['child_anchor']])[0])
        self.assertTrue(right_parent.contains([joints[1]['parent_anchor']])[0])
        self.assertTrue(right_child.contains([joints[1]['child_anchor']])[0])

    def test_priority_uses_actual_marker_edits_not_display_metadata(self):
        import json
        from machine_image_job import changed_joint_names
        with tempfile.TemporaryDirectory() as directory:
            job=Path(directory);revision='a'*32
            old=[{'name':'left','center':[1,2,3],'radius_mm':6,'symmetry_pair_id':'p'},
                 {'name':'right','center':[-1,2,3],'radius_mm':6,'symmetry_pair_id':'p'}]
            current=json.loads(json.dumps(old));current[0]['center']=[2,2,3];current[1]['status']='new label'
            previous=job/'partition'/revision;previous.mkdir(parents=True)
            (previous/'source_manifest.json').write_text(json.dumps({'joint_candidates':old}))
            (job/'manifest.json').write_text(json.dumps({'joint_candidates':current,'partition_review':{'revision':revision}}))
            self.assertEqual(changed_joint_names(job),['left'])
            (previous/'source_manifest.json').unlink()
            self.assertEqual(changed_joint_names(job),[])

    def test_failed_axis_search_does_not_repeat_identical_ray_queries(self):
        joints=[{'name':'left','marker_number':1,'symmetry_pair_id':'p','parent':'lp','part':'lc','center':[0,0,0],'direction':[0,1,0]},
                {'name':'right','marker_number':1,'symmetry_pair_id':'p','parent':'rp','part':'rc','center':[0,0,0],'direction':[0,1,0]}]
        cfg={'axis_search_step_deg':5,'axis_search_coarse_step_deg':15,'axis_search_max_angle_deg':30,'axis_search_azimuth_step_deg':30}
        queried={}
        def miss(mesh,center,directions,cfg):
            seen=queried.setdefault(mesh,set())
            for direction in directions:
                key=direction.tobytes()
                self.assertNotIn(key,seen,'coarse, detailed and opposite-orientation passes reuse exact queries')
                seen.add(key)
            return [None]*len(directions)
        with patch('machine_image_job.ray_axis_anchors',side_effect=miss):
            with self.assertRaisesRegex(ValueError,'マーカー1番'):
                fit_constrained_joint_axes(joints,{k:k for k in ('lp','lc','rp','rc')},cfg)

    def test_invalid_matching_joint_cache_stops_instead_of_recalculating(self):
        mesh=trimesh.creation.box([8,8,8]);joint={'center':[0,0,0],'parent':'a','part':'b'}
        broken={'direction':[1,0,0],'parent_anchor':[20,0,0],'child_anchor':[2,0,0],'direction_adjustment_deg':0}
        with self.assertRaisesRegex(ValueError,'outside current anatomy'):
            apply_cached_joint(joint,broken,{'a':mesh,'b':mesh})

    def test_external_hardware_overlap_is_allowed_but_socket_interior_is_protected(self):
        a=trimesh.creation.box([4,4,4]);b=trimesh.creation.box([4,4,4]);b.apply_translation([2,0,0])
        far_void=trimesh.creation.box([1,1,1]);far_void.apply_translation([20,0,0])
        joints=[{'name':'joint','socket_part':'a','ball_part':'b'}]
        tools={'joint':{'socket':solid(a),'ball':solid(b),'void':solid(far_void),'cavity':solid(far_void)}}
        collisions,allowed,intrusions=classify_hardware_interference({'a':solid(a),'b':solid(b)},joints,tools,.001)
        self.assertFalse(collisions);self.assertTrue(allowed);self.assertFalse(intrusions)
        invading=trimesh.creation.box([1,1,1]);invading.apply_translation([20,0,0])
        _,_,intrusions=classify_hardware_interference({'a':solid(a),'b':solid(b),'foreign':solid(invading)},joints,tools,.001)
        self.assertEqual(intrusions[0]['socket_joint'],'joint');self.assertEqual(intrusions[0]['part'],'foreign')

    def test_only_sub_tolerance_boolean_fragments_are_removed(self):
        main=solid(trimesh.creation.box([2,2,2]))
        tiny=trimesh.creation.box([.05,.05,.05]);tiny.apply_translation([5,0,0])
        cleaned,removed=remove_boolean_micro_fragments(main+solid(tiny),.001,'part')
        self.assertEqual(len(cleaned.decompose()),1);self.assertEqual(len(removed),1)
        detached=trimesh.creation.box([1,1,1]);detached.apply_translation([5,0,0])
        with self.assertRaisesRegex(ValueError,'not connected'):
            remove_boolean_micro_fragments(main+solid(detached),.001,'part')

    def test_tree_uses_declared_root_and_resolves_unordered_links(self):
        branches={'root_candidate':'body','cores':[{'name':x} for x in ('tip','body','arm')]}
        specs=[{'name':'elbow','center':[1,2,3],'radius_mm':4,'adjacent_cores':['tip','arm'],'classification':'two_part_junction'},
               {'name':'shoulder','center':[0,0,0],'radius_mm':5,'adjacent_cores':['arm','body'],'classification':'two_part_junction'}]
        result=tree_joints(branches,specs)
        self.assertEqual([(j['parent'],j['part']) for j in result],[('body','arm'),('arm','tip')])

    def test_partition_cut_diagnostic_identifies_visible_marker_number(self):
        source=solid(trimesh.creation.box([12,4,4]));good=trimesh.creation.box([.5,8,8]);good.apply_translation([-2,0,0])
        missed=trimesh.creation.box([.5,1,1]);missed.apply_translation([2,8,0])
        joints=[{'name':'good','marker_number':1},{'name':'missed','marker_number':2}]
        raw,steps=apply_partition_cuts(source,joints,{'good':good,'missed':missed})
        self.assertEqual(len(raw.decompose()),2)
        self.assertEqual([step['component_delta'] for step in steps],[1,0])
        self.assertEqual(steps[1]['marker_number'],2)

    def test_ambiguous_and_disconnected_graph_rejected(self):
        branches={'root_candidate':'a','cores':[{'name':x} for x in ('a','b','c','d')]}
        specs=[dict(name=f'j{i}',center=[0,0,0],radius_mm=3,adjacent_cores=list(pair),classification='two_part_junction')
               for i,pair in enumerate(('ab','bc','ca'))]
        with self.assertRaisesRegex(ValueError,'cyclic or disconnected'):tree_joints(branches,specs)
        specs[0]['classification']='ambiguous'
        with self.assertRaisesRegex(ValueError,'exactly two'):tree_joints(branches,specs)

    def test_shell_relief_chooses_only_the_side_that_keeps_minimum_wall(self):
        tail={'name':'tail'};hip={'name':'hip'}
        self.assertIs(choose_shell_relief((tail,hip),{'tail':0.0,'hip':2.32},2.0),hip)
        self.assertIsNone(choose_shell_relief((tail,hip),{'tail':0.0,'hip':1.99},2.0))

    def test_anchor_is_inside_not_on_surface_and_distance_is_bounded(self):
        mesh=trimesh.creation.box([8,8,8]);cfg={'anchor_embed_mm':1,'maximum_anchor_distance_mm':10}
        anchor=interior_anchor(mesh,np.array([6,0,0]),cfg)
        self.assertTrue(mesh.contains([anchor])[0]);self.assertAlmostEqual(anchor[0],3)
        with self.assertRaisesRegex(ValueError,'too long'):interior_anchor(mesh,np.array([60,0,0]),cfg)

    def test_real_export_topology(self):
        mesh=trimesh.creation.icosphere(subdivisions=3,radius=3)
        with tempfile.TemporaryDirectory() as directory:
            out=Path(directory)/'test.stl'
            actual,record=export_print_mesh(solid(mesh),out,
                {'stl_quantization_cleanup_mm':.00005,'stl_quantization_cleanup_max_mm':.0002},.001)
            self.assertTrue(actual.is_volume);self.assertEqual(record['components'],1)
            self.assertTrue(trimesh.load(out).is_watertight)

    def test_disconnected_print_part_rejected(self):
        a=trimesh.creation.box();b=a.copy();b.apply_translation([5,0,0])
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError,'トポロジーが不正'):
                export_print_mesh(solid(a)+solid(b),Path(directory)/'bad.stl',
                    {'stl_quantization_cleanup_mm':.00005,'stl_quantization_cleanup_max_mm':.0002},.001)

    def test_closed_quantisation_micro_fragment_is_removed_without_retry(self):
        main=trimesh.creation.box()
        fragment=trimesh.creation.icosphere(subdivisions=1,radius=.001)
        fragment.apply_translation([5,0,0])
        with tempfile.TemporaryDirectory() as directory:
            actual,record=export_print_mesh(solid(main)+solid(fragment),Path(directory)/'clean.stl',
                {'stl_quantization_cleanup_mm':.00005,'stl_quantization_cleanup_max_mm':.0002},.001)
            self.assertTrue(actual.is_volume);self.assertEqual(record['components'],1)
            self.assertEqual(len(record['removed_closed_micro_fragments_mm3']),1)
            self.assertLess(record['removed_closed_micro_fragments_mm3'][0],.001)


if __name__=='__main__':unittest.main()
