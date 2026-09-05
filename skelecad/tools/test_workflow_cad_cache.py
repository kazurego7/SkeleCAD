import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from workflow_cad_cache import cache_key,read_entry,save_entry


class CadCacheTests(unittest.TestCase):
    def test_dependency_changes_invalidate_only_affected_keys(self):
        context={'code':'v1','settings':{'diameter':6}}
        joint={'center':[1,2,3],'direction':[0,0,1],'socket_anchor':[1,2,0],
               'calculation_source':'computed'}
        original=cache_key(context,joint)
        self.assertEqual(original,cache_key(context,{**joint,'calculation_source':'validated_local_cache'}))
        for change in ({'center':[1,2,4]},{'direction':[1,0,0]},{'socket_anchor':[1,2,-1]}):
            self.assertNotEqual(original,cache_key(context,{**joint,**change}))
        self.assertNotEqual(original,cache_key({**context,'code':'v2'},joint))
        self.assertNotEqual(original,cache_key({**context,'settings':{'diameter':6.1}},joint))

    def test_complete_entry_roundtrip_and_corruption_rejection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);src=root/'source';src.mkdir();(src/'part.stl').write_bytes(b'exact bytes')
            key=cache_key({},{});cache=root/'cache'
            self.assertIsNone(read_entry(cache,key))
            save_entry(cache,key,src,['part.stl'],[],[])
            directory,record=read_entry(cache,key)
            self.assertEqual((directory/'part.stl').read_bytes(),b'exact bytes')
            (directory/'part.stl').write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError,'integrity'):read_entry(cache,key)


if __name__=='__main__':unittest.main()
