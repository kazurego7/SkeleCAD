import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflow_store import WorkflowStore, write_json
from workflow_symmetry_states import save


class SymmetryStateTests(unittest.TestCase):
    def test_three_choices_restore_latest_partition_and_print_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=WorkflowStore(Path(temporary),launch=False)
            directory=store.root/('a'*32);directory.mkdir()
            def publish(side, marker):
                (directory/'appearance.stl').write_bytes(side.encode())
                write_json(directory/'manifest.json',{'joint_candidates':[marker]})
                state={'id':directory.name,'stage':'print_ready','operation':'print',
                       'manifest_sha256':'mechanical-'+side,'mechanical_revision':side,
                       'prints':{'path':side},'selected_markers':[marker],
                       'partition_revision':side,'selected_joints':[marker['name']]}
                if side!='original':state['appearance_symmetry']={'active':True,'source_side':side}
                write_json(directory/'state.json',state)
                return state
            try:
                for side in ('original','negative_x','positive_x'):
                    state=publish(side,{'name':side,'center':[1,2,3],'radius_mm':6})
                    save(directory,state)
                with patch.object(store,'public',side_effect=store.read):
                    left=store.request_symmetry(directory.name,state['manifest_sha256'],'negative_x')
                    self.assertEqual(left['selected_markers'][0]['name'],'negative_x')
                    self.assertEqual(left['prints']['path'],'negative_x')
                    self.assertEqual(left['stage'],'print_ready')
                    left['selected_markers'][0]['radius_mm']=9
                    write_json(directory/'state.json',left)
                    original=store.restore_symmetry(directory.name)
                    self.assertEqual(original['mechanical_revision'],'original')
                    self.assertEqual((directory/'appearance.stl').read_bytes(),b'original')
                    right=store.request_symmetry(directory.name,original['manifest_sha256'],'positive_x')
                    self.assertEqual(right['selected_markers'][0]['radius_mm'],6)
                    left=store.request_symmetry(directory.name,right['manifest_sha256'],'negative_x')
                    self.assertEqual(left['selected_markers'][0]['radius_mm'],9)
                    self.assertEqual(left['selected_joints'],['negative_x'])
            finally:store.close()

    def test_new_choice_is_queued_and_saves_full_current_state(self):
        with tempfile.TemporaryDirectory() as temporary:
            store=WorkflowStore(Path(temporary),launch=False)
            directory=store.root/('a'*32);directory.mkdir()
            (directory/'appearance.stl').write_bytes(b'original')
            write_json(directory/'manifest.json',{'joint_candidates':[]})
            state={'id':directory.name,'stage':'mechanical_review','manifest_sha256':'mechanical',
                   'mechanical_revision':'original','selected_markers':[{'name':'keep'}]}
            write_json(directory/'state.json',state)
            try:
                with patch.object(store,'public',side_effect=store.read):
                    queued=store.request_symmetry(directory.name,'mechanical','negative_x')
                    self.assertEqual(queued['stage'],'queued')
                    self.assertEqual(queued['source_manifest_sha256'],hashlib.sha256((directory/'manifest.json').read_bytes()).hexdigest())
                pointer=json.loads((directory/'symmetry/states/original/current.json').read_text())
                saved=json.loads((directory/'symmetry/states/original'/pointer['revision']/'state.json').read_text())
                self.assertEqual(saved,state)
            finally:store.close()

if __name__=='__main__':unittest.main()
