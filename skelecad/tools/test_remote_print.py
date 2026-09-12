"""No live printer commands: review binding, confirmations and one-shot dispatch."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import threading

from remote_print import RemotePrint, digest
from workflow_store import write_json
from bambu_lan import identity, require_idle


class RemotePrintTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.job, self.revision, self.ticket = 'a'*32, 'b'*32, 'c'*32
        self.model = self.root/self.job/'machining'/self.revision
        self.model.mkdir(parents=True)
        (self.model/'part.stl').write_bytes(b'original')
        write_json(self.model/'manifest.json', {'parts':[{'filename':'part.stl','sha256':digest(self.model/'part.stl')}]})
        self.state = {'stage':'print_ready','manifest_sha256':digest(self.model/'manifest.json'),'mechanical_revision':self.revision}
        store = SimpleNamespace(root=self.root,lock=threading.RLock(),read=lambda _:self.state,directory=lambda _:self.root/self.job)
        self.manager = RemotePrint(store)
        self.cfg={'model':'A1 mini','serial':'testserial0001','host':'192.168.1.2','use_ams':False}
        self.folder=self.manager.path(self.ticket);self.folder.mkdir()
        self.package=self.folder/'model/print/plate_01/SkeleCAD_plate_01.gcode.3mf'
        self.package.parent.mkdir(parents=True);self.package.write_bytes(b'verified sliced package')
        self.record={'ticket':self.ticket,'job_id':self.job,'stage':'ready','revision':self.revision,
                     'print_context':'unchanged',
                     'manifest_sha256':self.state['manifest_sha256'],'printer_identity':identity(self.cfg),
                     'plates':[{'plate':1,'sha256':digest(self.package)}],'message':'ready'}
        write_json(self.folder/'state.json',self.record)
        self.payload={'ticket':self.ticket,'plate':1,'accepted':True,'bed_clear':True}
        self.context_patch=patch('print_cache.cache_context',return_value='unchanged')
        self.context_patch.start()

    def tearDown(self):self.context_patch.stop();self.temp.cleanup()

    def test_explicit_confirmation_required(self):
        for field in ('accepted','bed_clear'):
            with self.assertRaises(ValueError):self.manager.start(self.job,{**self.payload,field:False})

    def test_stale_geometry_printer_or_package_cannot_start(self):
        with patch('remote_print.configuration',return_value=self.cfg):
            self.state['manifest_sha256']='changed'
            with self.assertRaises(ValueError):self.manager.start(self.job,self.payload)
            self.state['manifest_sha256']=self.record['manifest_sha256']
            (self.model/'part.stl').write_bytes(b'changed')
            with self.assertRaises(ValueError):self.manager.start(self.job,self.payload)
            (self.model/'part.stl').write_bytes(b'original')
            self.cfg['host']='192.168.1.3'
            with self.assertRaises(ValueError):self.manager.start(self.job,self.payload)
            self.cfg['host']='192.168.1.2';self.package.write_bytes(b'changed')
            with self.assertRaises(ValueError):self.manager.start(self.job,self.payload)

    def test_start_persists_before_dispatch_and_retries_do_not_duplicate(self):
        with patch('remote_print.configuration',return_value=self.cfg),patch('remote_print.threading.Thread') as worker:
            result=self.manager.start(self.job,self.payload)
            self.assertEqual(result['stage'],'sending')
            self.assertEqual(json.loads((self.folder/'state.json').read_text())['stage'],'sending')
            self.manager.start(self.job,self.payload)
            self.assertEqual(worker.call_count,1)
        restarted=RemotePrint(self.manager.store)
        self.assertEqual(restarted.status(self.job,self.ticket)['stage'],'unknown')
        with patch('remote_print.threading.Thread') as worker:
            restarted.start(self.job,self.payload)
            worker.assert_not_called()

    def test_idle_guard_rejects_busy_error_unknown_and_missing_sd(self):
        report={'gcode_state':'IDLE','stg_cur':0,'sdcard':True,'hms':[]}
        require_idle(report)
        for change in ({'gcode_state':'RUNNING'},{'gcode_state':'PAUSE'},{'stg_cur':1},{'print_error':1},{'sdcard':False},{'hms':[1]}):
            with self.assertRaises(ValueError):require_idle({**report,**change})
        with self.assertRaises(ValueError):require_idle({})

    def test_no_start_after_upload_failure(self):
        printer=SimpleNamespace(report={'gcode_state':'IDLE','stg_cur':0,'sdcard':True},start=lambda _:self.fail('must not start'))
        with patch('remote_print.Printer') as factory,patch('remote_print.upload',side_effect=OSError):
            factory.return_value.__enter__.return_value=printer
            self.manager._start(self.folder,self.record,self.cfg,self.package)
        self.assertEqual(self.manager.status(self.job,self.ticket)['stage'],'failed')

    def test_lost_start_response_is_unknown_never_retried(self):
        with patch('remote_print.Printer') as factory,patch('remote_print.upload'):
            printer=factory.return_value.__enter__.return_value
            printer.report={'gcode_state':'IDLE','stg_cur':0,'sdcard':True}
            printer.start.side_effect=TimeoutError
            self.manager._start(self.folder,self.record,self.cfg,self.package)
            printer.start.assert_called_once()
        self.assertEqual(self.manager.status(self.job,self.ticket)['stage'],'unknown')

    def test_connect_transport_uses_official_runner_and_never_lan(self):
        cfg = {**self.cfg, 'transport': 'bambu_connect'}
        def completed(args, **kwargs):
            self.assertIn('--execute-print', args)
            output = Path(args[args.index('--output') + 1])
            write_json(output / 'result.json', {'status': 'started', 'message': 'matching job started'})
        with patch('remote_print.subprocess.run', side_effect=completed) as runner, patch('remote_print.Printer') as lan:
            self.manager._start(self.folder, self.record, cfg, self.package)
            runner.assert_called_once(); lan.assert_not_called()
        self.assertEqual(self.manager.status(self.job, self.ticket)['stage'], 'started')

    def test_connect_timeout_after_dispatch_is_unknown(self):
        def timeout(args, **kwargs):
            output = Path(args[args.index('--output') + 1])
            (output / 'dispatch.decision').write_text('send')
            raise TimeoutError
        with patch('remote_print.subprocess.run', side_effect=timeout):
            self.manager._start(self.folder, self.record, {**self.cfg, 'transport': 'bambu_connect'}, self.package)
        self.assertEqual(self.manager.status(self.job, self.ticket)['stage'], 'unknown')

    def test_cancellation_blocks_start_and_is_once_only_before_send(self):
        self.assertEqual(self.manager.cancel(self.job, {'ticket': self.ticket})['stage'], 'cancelled')
        with self.assertRaises(ValueError): self.manager.start(self.job, self.payload)
        self.manager.update(self.folder, stage='sending')
        with patch('remote_print.configuration', return_value={'transport': 'bambu_connect'}):
            self.manager.cancel(self.job, {'ticket': self.ticket})
            decision = self.folder / 'connect/dispatch.decision'
            self.assertEqual(decision.read_text(), 'cancel')
            self.manager.cancel(self.job, {'ticket': self.ticket})
            decision.write_text('send')
            with self.assertRaisesRegex(ValueError, 'Bambu Handy'):
                self.manager.cancel(self.job, {'ticket': self.ticket})


if __name__=='__main__':unittest.main()
