"""Failed retries and changed human-reviewed inputs must never release old output."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from workflow_store import WorkflowStore,write_json
from test_workflow import image_bytes
import slice_workflow_print as slicer


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PrintReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.store=WorkflowStore(Path(self.temp.name),launch=False)
        self.job=self.store.create(image_bytes())['id']
        self.jobdir=self.store.directory(self.job)
        self.revision='b'*32
        self.folder=self.jobdir/'machining'/self.revision
        self.plate=self.folder/'print/plate_01'
        self.plate.mkdir(parents=True)
        self.part=self.folder/'core_00.stl';self.part.write_bytes(b'reviewed model')
        self.manifest=self.folder/'manifest.json'
        write_json(self.manifest,{'stage':'mechanical_review','joints':[],
                   'parts':[{'name':'core_00','filename':self.part.name,'sha256':digest(self.part)}]})
        self.approval=self.folder/'review_approval.json'
        write_json(self.approval,{'accepted':True,'manifest_sha256':digest(self.manifest),'pose':{}})
        self.filename='SkeleCAD_A1mini_plate_01.3mf'
        self.target=self.plate/self.filename;self.target.write_bytes(b'previous checked output')
        (self.plate/'input.3mf').write_bytes(b'new input')
        write_json(self.plate/'result.json',{'return_code':0})
        self.record={'plate':1,'filename':self.filename,'sha256':digest(self.target)}
        self.release=self.folder/'print/release.json'
        write_json(self.release,{'ready_to_print':True,'slicing_verified':True,'verification_run':False,
                   'manifest_sha256':digest(self.manifest),'review_approval_sha256':digest(self.approval),
                   'plates':[self.record]})
        state=self.store.read(self.job)
        state.update(stage='print_ready',manifest_sha256=digest(self.manifest),
                     mechanical_revision=self.revision,prints=[self.record])
        write_json(self.jobdir/'state.json',state)
        self.name=f'p_{self.revision}_01.3mf'

    def tearDown(self):
        self.store.close();self.temp.cleanup()

    def test_valid_release_download_survives_store_restart(self):
        self.assertEqual(self.store.artifact(self.job,self.name),self.target)
        self.assertEqual(WorkflowStore(self.temp.name,launch=False).artifact(self.job,self.name),self.target)

    def test_unsliced_project_is_downloadable_but_not_print_certified(self):
        release=json.loads(self.release.read_text())
        release.update(artifact_kind='bambu_project',project_verified=True,ready_to_open=True,
                       ready_to_print=False,slicing_verified=False)
        write_json(self.release,release)
        self.assertEqual(self.store.artifact(self.job,self.name),self.target)
        release['verification_run']=True;write_json(self.release,release)
        with self.assertRaises(KeyError):self.store.artifact(self.job,self.name)

    def test_project_generation_reuses_audited_bytes_without_slicer(self):
        import prepare_workflow_project as project
        report={'plate':1,'parts':[{'name':'core_00'}]}
        def package(folder):
            import zipfile
            with zipfile.ZipFile(self.plate/'input.3mf','w') as z:z.writestr('model','shape')
            write_json(folder/'print/preparation.json',{'plates':[report]})
            return [report]
        with patch.object(project,'package',side_effect=package) as build,patch.object(project,'cache_context',return_value='context'),patch('subprocess.run',side_effect=AssertionError('Slicer must not launch')):
            first=project.run(self.folder,verification_run=True)
            self.assertFalse(first['ready_to_print']);self.assertFalse(first['ready_to_open'])
            second=project.run(self.folder)
            self.assertTrue(second['ready_to_open']);self.assertFalse(second['slicing_verified'])
            self.assertTrue(second['project_reused']);self.assertEqual(build.call_count,1)
            (self.plate/self.record['filename']).write_bytes(b'corrupt')
            third=project.run(self.folder)
            self.assertFalse(third['project_reused']);self.assertEqual(build.call_count,2)

    def speculative_proof(self):
        preparation=self.folder/'print/preparation.json'
        write_json(preparation,{'plates':[{'plate':1,'parts':[{'name':'core_00'}]}]})
        previous=json.loads(self.release.read_text())
        previous.update(verification_run=True,ready_to_print=False,cache_context='same-auditor',
                        preparation_sha256=digest(preparation))
        executable=self.folder/'slicer.exe';executable.write_bytes(b'pinned executable')
        library=self.folder/'slicer.dll';library.write_bytes(b'pinned library')
        tool={'executable':str(executable),'executable_sha256':digest(executable),
              'library':str(library),'library_sha256':digest(library)}
        return previous,tool

    def test_speculative_proof_reuses_only_identical_verified_bytes(self):
        previous,tool=self.speculative_proof()
        write_json(self.release,previous)
        with patch.object(slicer,'BAMBU',tool),patch.object(slicer,'cache_context',return_value='same-auditor'), \
             patch.object(slicer,'package') as package,patch.object(slicer.subprocess,'run') as launch:
            report=slicer.run(self.folder)
            package.assert_not_called();launch.assert_not_called()
        self.assertTrue(report['ready_to_print'])
        self.assertFalse(report['verification_run'])
        self.assertTrue(report['plates'][0]['speculative_slice_reused'])
        self.assertEqual(report['review_approval_sha256'],digest(self.approval))
        self.assertEqual(self.store.artifact(self.job,self.name),self.target)

    def test_speculative_proof_rejects_every_mutated_dependency(self):
        previous,tool=self.speculative_proof()
        files=[self.manifest,self.part,self.target,self.folder/'print/preparation.json',Path(tool['executable']),Path(tool['library']),self.approval]
        manifest_digest=digest(self.manifest);approval_digest=digest(self.approval)
        with patch.object(slicer,'BAMBU',tool),patch.object(slicer,'cache_context',return_value='same-auditor'):
            for path in files:
                with self.subTest(path=path.name):
                    original=path.read_bytes();path.write_bytes(original+b'changed')
                    self.assertIsNone(slicer.reuse_verified(self.folder,previous,manifest_digest,approval_digest,False))
                    path.write_bytes(original)
            with patch.object(slicer,'cache_context',return_value='new-code-or-settings'):
                self.assertIsNone(slicer.reuse_verified(self.folder,previous,manifest_digest,approval_digest,False))
        for field,value in (('verification_run',False),('slicing_verified',False),('ready_to_print',True)):
            with self.subTest(field=field):
                self.assertIsNone(slicer.reuse_verified(self.folder,{**previous,field:value},manifest_digest,approval_digest,False))

    def test_ready_release_opens_exact_validated_file_in_bambu_studio(self):
        with patch('workflow_store.find_bambu_studio',return_value=Path('C:/Program Files/Bambu Studio/bambu-studio.exe')), \
             patch('workflow_store.subprocess.Popen') as launch:
            result=self.store.open_print_in_bambu(self.job,{'manifest_sha256':digest(self.manifest)})
        self.assertEqual(result,{'opened':True,'plate_count':1})
        command=launch.call_args.args[0]
        self.assertEqual(command[1:], [str(self.target)])
        with self.assertRaisesRegex(ValueError,'最新'):
            self.store.open_print_in_bambu(self.job,{'manifest_sha256':'stale'})

    def test_changed_model_manifest_invalidates_prior_release(self):
        write_json(self.manifest,{'parts':[],'joints':[]})
        with self.assertRaises(KeyError):self.store.artifact(self.job,self.name)

    def test_changed_part_with_unchanged_manifest_invalidates_prior_release(self):
        self.part.write_bytes(b'human corrected model')
        with self.assertRaises(KeyError):self.store.artifact(self.job,self.name)

    def test_changed_approval_requires_new_print_preparation(self):
        data=json.loads(self.approval.read_text());data['pose']={'new_joint':[0,0,0]}
        write_json(self.approval,data)
        with self.assertRaises(KeyError):self.store.artifact(self.job,self.name)

    def test_invalid_release_flags_and_duplicate_records_fail_closed(self):
        original=json.loads(self.release.read_text())
        for change in ({'ready_to_print':False},{'ready_to_print':'true'},
                       {'verification_run':True},{'slicing_verified':False},
                       {'review_approval_sha256':None},{'plates':[self.record,self.record]}):
            with self.subTest(change=change):
                write_json(self.release,{**original,**change})
                with self.assertRaises(KeyError):self.store.artifact(self.job,self.name)

    def test_changed_print_or_record_cannot_be_downloaded(self):
        self.target.write_bytes(b'changed output')
        with self.assertRaises(KeyError):self.store.artifact(self.job,self.name)
        release=json.loads(self.release.read_text());release['plates'][0]['sha256']=digest(self.target)
        write_json(self.release,release)
        with self.assertRaises(KeyError):self.store.artifact(self.job,self.name)

    def test_malformed_and_missing_metadata_fail_closed(self):
        self.release.write_text('{')
        with self.assertRaises(KeyError):self.store.artifact(self.job,self.name)
        self.release.unlink()
        with self.assertRaises(KeyError):self.store.artifact(self.job,self.name)

    def test_failed_packaging_revokes_previous_ready_release_and_preserves_it(self):
        with patch.object(slicer,'package',side_effect=ValueError('pack failed')):
            with self.assertRaisesRegex(ValueError,'pack failed'):slicer.run(self.folder)
        self.assertFalse(json.loads(self.release.read_text())['ready_to_print'])
        backups=list(self.release.parent.glob('release_before_*.json'))
        self.assertEqual(len(backups),1)
        self.assertTrue(json.loads(backups[0].read_text())['ready_to_print'])
        self.assertEqual(self.target.read_bytes(),b'previous checked output')
        with self.assertRaises(KeyError):self.store.artifact(self.job,self.name)

    def test_zero_exit_without_fresh_outputs_never_reuses_old_slicing(self):
        reports=[{'plate':1,'parts':[{'name':'core_00'}]}]
        attempts=[]
        def no_output(command,**kwargs):
            cwd=kwargs['cwd'];attempts.append(cwd)
            self.assertNotEqual(cwd,self.plate)
            self.assertFalse((cwd/'result.json').exists())
            self.assertFalse((cwd/self.filename).exists())
            self.assertTrue((cwd/'input.3mf').is_file())
            self.assertEqual(Path(command[command.index('--outputdir')+1]),cwd)
            return SimpleNamespace(returncode=0)
        with patch.object(slicer,'package',return_value=reports), \
             patch.object(slicer.subprocess,'run',side_effect=no_output), \
             patch.object(slicer,'audit_input') as audit:
            for _ in range(2):
                with self.assertRaises(FileNotFoundError):slicer.run(self.folder)
            audit.assert_not_called()
        self.assertEqual(len(set(attempts)),2)
        self.assertFalse(json.loads(self.release.read_text())['ready_to_print'])
        self.assertEqual(self.target.read_bytes(),b'previous checked output')

    def test_nonzero_slicer_exit_is_not_released(self):
        with patch.object(slicer,'package',return_value=[{'plate':1}]), \
             patch.object(slicer.subprocess,'run',return_value=SimpleNamespace(returncode=1)):
            with self.assertRaisesRegex(ValueError,'slicing failed'):slicer.run(self.folder)
        self.assertFalse(json.loads(self.release.read_text())['ready_to_print'])

    def test_empty_preparation_cannot_be_ready(self):
        with patch.object(slicer,'package',return_value=[]):
            with self.assertRaisesRegex(ValueError,'No print plates'):slicer.run(self.folder)
        self.assertFalse(json.loads(self.release.read_text())['ready_to_print'])


if __name__=='__main__':unittest.main()
