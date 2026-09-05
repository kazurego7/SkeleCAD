"""Speculative work cannot publish older edits or bypass print release."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_store import WorkflowStore, write_json
from workflow_background_worker import source_identity, digest


class BackgroundTests(unittest.TestCase):
    def test_failure_cleanup_preserves_cad_log_and_request(self):
        (self.source/'cad_joint.log').write_text('CAD details',encoding='utf-8')
        write_json(self.source/'request.json',{'phase':'joint'})
        self.record['stage']='failed'
        write_json(self.directory/'background.json',self.record)
        write_json(self.attempt/'result.json',{'identity':self.record['identity'],'stage':'failed'})
        with patch('workflow_background.process_identity',return_value=None):
            self.store.background.tick()
        saved=self.attempt/'diagnostics'/'machining'/self.revision
        self.assertEqual((saved/'cad_joint.log').read_text(),'CAD details')
        self.assertEqual(json.loads((saved/'request.json').read_text()),{'phase':'joint'})
        self.assertFalse((self.attempt/self.directory.name).exists())
        self.assertFalse((saved/'core_00.stl').exists())

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=WorkflowStore(self.temp.name,launch=False)
        self.directory=Path(self.temp.name)/('a'*32);self.directory.mkdir()
        self.state={'id':self.directory.name,'stage':'appearance_ready','partition_revision':'p1',
                    'manifest_sha256':'preview','preview_part_count':2,'selected_markers':[],
                    'selected_joints':['candidate_01']}
        write_json(self.directory/'state.json',self.state)
        write_json(self.directory/'manifest.json',{'joint_candidates':[{'name':'candidate_01','classification':'two_part_junction'}]})
        (self.directory/'appearance.stl').write_bytes(b'original')
        self.attempt=self.directory/'.background'/('c'*32)
        self.revision='b'*32
        self.source=self.attempt/self.directory.name/'machining'/self.revision
        self.source.mkdir(parents=True)
        (self.source/'core_00.stl').write_bytes(b'validated closed mesh')
        write_json(self.source/'manifest.json',{'stage':'mechanical_review','parts':[{
            'name':'core_00','filename':'core_00.stl','sha256':digest(self.source/'core_00.stl')}],'joints':[]})
        self.record={'identity':source_identity(self.directory),'source_revision':'p1','stage':'working',
                     'joints':['candidate_01'],'attempt':self.attempt.name}

    def tearDown(self):
        self.store.close();self.temp.cleanup()

    def publish(self, stage='mechanical_ready'):
        write_json(self.attempt/'result.json',{'identity':self.record['identity'],'stage':stage,
            'revision':self.revision,'manifest_sha256':digest(self.source/'manifest.json')})
        self.store.background._publish(self.directory,self.attempt,self.record)

    def test_partial_preview_is_immutable_current_and_never_printable(self):
        from workflow_motion_preview import emit
        snapshot=self.attempt/self.directory.name
        raw=snapshot/'raw';raw.mkdir()
        for name in ('core_00','core_01','core_02'):
            (raw/(name+'_raw.stl')).write_bytes(('raw '+name).encode())
            (raw/(name+'.stl')).write_bytes(('final '+name).encode())
        joints=[{'name':'one','parent':'core_00','part':'core_01','center':[0,0,0],'direction':[1,0,0]},
                {'name':'two','parent':'core_01','part':'core_02','center':[2,0,0],'direction':[1,0,0]}]
        preview=emit(snapshot,['core_00','core_01','core_02'],joints,{'core_00','core_01'},raw,['#fff'])
        write_json(self.attempt/'result.json',{'identity':self.record['identity'],'stage':'working','preview':preview})
        before=(self.directory/'state.json').read_bytes()
        self.store.background._publish_preview(self.directory,self.attempt,self.record)
        self.assertEqual(before,(self.directory/'state.json').read_bytes())
        published=self.store.public(self.directory.name)['background']['preview']
        self.assertEqual(published['ready_joint_count'],1)
        manifest_path=self.store.artifact(self.directory.name,'v_'+preview['revision']+'.json')
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        self.assertTrue(manifest['preview_only']);self.assertFalse(manifest['print_ready'])
        self.assertTrue(manifest['joints'][0]['motion_ready']);self.assertFalse(manifest['joints'][1]['motion_ready'])
        with self.assertRaises(KeyError):self.store.artifact(self.directory.name,'p_'+preview['revision']+'_01.3mf')
        self.state['partition_revision']='new';write_json(self.directory/'state.json',self.state)
        with self.assertRaises(KeyError):self.store.artifact(self.directory.name,'v_'+preview['revision']+'.json')

    def test_failure_is_public_only_for_current_partition(self):
        self.record['stage']='failed'
        write_json(self.directory/'background.json',self.record)
        location={'center':[1,2,3],'symmetry_pair_id':'pair'}
        write_json(self.attempt/'result.json',{'identity':self.record['identity'],
            'stage':'failed','error':'Axis unavailable','failed_marker_locations':[location]})
        public=self.store.background.public(self.directory,self.state)
        self.assertEqual(public['error'],'Axis unavailable')
        self.assertEqual(public['failed_marker_locations'],[location])
        self.assertNotIn('attempt',public)
        self.state['partition_revision']='new'
        self.assertIsNone(self.store.background.public(self.directory,self.state))

    def test_old_failure_recovers_both_symmetric_marker_locations(self):
        self.record['stage']='failed'
        write_json(self.directory/'background.json',self.record)
        self.state['selected_markers']=[{'center':[0,0,0]},
            {'center':[2,0,0],'symmetry_pair_id':'pair'},
            {'center':[-2,0,0],'symmetry_pair_id':'pair'}]
        write_json(self.attempt/'result.json',{'identity':self.record['identity'],
            'stage':'failed','error':'マーカー2番: axis unavailable'})
        result=self.store.background.public(self.directory,self.state)
        self.assertEqual(len(result['failed_marker_locations']),2)

    def test_publish_does_not_change_editing_state_but_can_be_adopted(self):
        before=(self.directory/'state.json').read_bytes()
        self.publish()
        self.assertEqual(before,(self.directory/'state.json').read_bytes())
        self.assertEqual(self.store.public(self.directory.name)['background']['stage'],'mechanical_ready')
        self.assertTrue(self.store.artifact(self.directory.name,f'r_{self.revision}.json').is_file())
        self.assertTrue(self.store.background.adopt(self.directory,self.state,['candidate_01']))
        current=self.store.read(self.directory.name)
        self.assertEqual(current['mechanical_revision'],self.revision)
        self.assertEqual(source_identity(self.directory),self.record['identity'])

    def test_edit_between_start_and_completion_never_publishes(self):
        self.state['selected_markers']=[{'center':[1,2,3]}]
        write_json(self.directory/'state.json',self.state)
        self.publish()
        self.assertEqual(self.record['stage'],'superseded')
        self.assertFalse((self.directory/'machining'/self.revision).exists())
        self.assertNotIn('mechanical_revision',self.store.read(self.directory.name))

    def test_edit_after_completion_invalidates_adoption(self):
        self.publish()
        self.state['selected_markers']=[{'center':[1,2,3]}]
        write_json(self.directory/'state.json',self.state)
        self.assertFalse(self.store.background.adopt(self.directory,self.state,['candidate_01']))

    def test_foreground_processing_hides_and_rejects_publication(self):
        self.state['stage']='queued';write_json(self.directory/'state.json',self.state)
        self.publish()
        self.assertNotIn('background',self.store.public(self.directory.name))
        self.assertFalse((self.directory/'machining'/self.revision).exists())

    def test_print_prefetch_does_not_grant_release(self):
        (self.source/'print').mkdir()
        write_json(self.source/'print/release.json',{'verification_run':True,'ready_to_print':False})
        self.publish('ready')
        self.assertTrue(self.store.background.adopt(self.directory,self.state,['candidate_01']))
        with self.assertRaises(KeyError):self.store.artifact(self.directory.name,f'p_{self.revision}_01.3mf')

    def test_live_worker_is_not_restarted_after_coordinator_restart(self):
        self.record.update(pid=123,process_identity='live')
        write_json(self.directory/'background.json',self.record)
        with patch('workflow_background.process_identity',return_value='live'), \
             patch('workflow_background.subprocess.Popen') as launch:
            self.store.background.tick()
            launch.assert_not_called()

    def test_changed_toolchain_or_code_invalidates_identity(self):
        with patch('workflow_background_worker.digest',side_effect=lambda path:'changed' if path.name=='toolchain.json' else digest(path)):
            self.assertNotEqual(source_identity(self.directory),self.record['identity'])

    def test_default_joint_selection_has_same_identity_after_adoption(self):
        del self.state['selected_joints'];write_json(self.directory/'state.json',self.state)
        self.assertEqual(source_identity(self.directory),self.record['identity'])

    def test_pending_foreground_adopts_inflight_machining(self):
        self.state.update(stage='queued',operation='machine')
        write_json(self.directory/'state.json',self.state)
        self.publish()
        self.assertEqual(self.store.read(self.directory.name)['stage'],'mechanical_review')
        self.assertEqual(self.store.read(self.directory.name)['mechanical_revision'],self.revision)

    def test_queued_print_can_receive_completed_speculative_slice(self):
        self.publish()
        self.store.background.adopt(self.directory,self.state,['candidate_01'])
        self.state.update(stage='queued',operation='print')
        write_json(self.directory/'state.json',self.state)
        (self.source/'print').mkdir()
        write_json(self.source/'print/release.json',{'verification_run':True,'ready_to_print':False})
        self.publish('ready')
        release=self.directory/'machining'/self.revision/'print/release.json'
        self.assertTrue(release.is_file())
        self.assertEqual(self.store.read(self.directory.name)['stage'],'queued')

    def test_foreground_waits_for_live_or_unpublished_identical_result(self):
        self.record.update(pid=123,process_identity='live')
        write_json(self.directory/'background.json',self.record)
        self.state.update(stage='queued',operation='machine')
        write_json(self.directory/'state.json',self.state)
        with patch('workflow_background.process_identity',return_value='live'):
            self.assertTrue(self.store.background.wait_for_foreground(self.directory,self.state))
        with patch('workflow_background.process_identity',return_value=None):
            self.assertFalse(self.store.background.wait_for_foreground(self.directory,self.state))
            write_json(self.attempt/'result.json',{'identity':self.record['identity'],'stage':'ready'})
            self.assertTrue(self.store.background.wait_for_foreground(self.directory,self.state))
        self.state['selected_markers']=[{'center':[2,3,4]}]
        write_json(self.directory/'state.json',self.state)
        with patch('workflow_background.process_identity',return_value='live'):
            self.assertFalse(self.store.background.wait_for_foreground(self.directory,self.state))

    def test_changed_appearance_cannot_adopt_old_result(self):
        self.publish();(self.directory/'appearance.stl').write_bytes(b'new geometry')
        self.assertFalse(self.store.background.adopt(self.directory,self.state,['candidate_01']))

    def test_slicing_failure_keeps_valid_machining_available(self):
        self.publish('print_failed')
        self.assertTrue(self.store.background.adopt(self.directory,self.state,['candidate_01']))

    def test_superseded_machining_stops_before_reading_or_changing_inputs(self):
        from machine_image_job import machine
        with self.assertRaises(InterruptedError):machine(Path('nonexistent-job'),cancelled=lambda:True)


if __name__=='__main__':unittest.main()
