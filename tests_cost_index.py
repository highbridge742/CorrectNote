"""Bundled index integrity, compatibility and original-parser fallback."""
import gc,gzip,hashlib,io,pickle,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import cost_index as I

class CostIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(self.temp.cleanup)
        self.source=Path(self.temp.name)/'source.gz';self.index=Path(self.temp.name)/'index.gz'
        self.source.write_bytes(gzip.compress('かめい\t仮名:60\nかな\t仮名:40\n'.encode('utf-8'),mtime=0))
        self.source_hash=hashlib.sha256(self.source.read_bytes()).hexdigest()
        self.data=dict(schema=1,source_sha256=self.source_hash,readings={'仮名':[(40,'かな'),(60,'かめい')]},costs={'仮名':40},surfaces={'かめい':[(60,'仮名')],'かな':[(40,'仮名')]})
        index_patch=patch.object(I,'INDEX_SHA256',I.INDEX_SHA256);index_patch.start();self.addCleanup(index_patch.stop)
        self.save(self.data)
        self.source_patch=patch.object(I,'SOURCE_SHA256',self.source_hash);self.source_patch.start();self.addCleanup(self.source_patch.stop)
    def save(self,data):
        packed=gzip.compress(pickle.dumps(data,protocol=4),mtime=0);self.index.write_bytes(packed)
        I.INDEX_SHA256=hashlib.sha256(packed).hexdigest()
    def test_exact_pair_order_types_and_source_costs(self):
        got=I.load(self.source,self.index)
        self.assertEqual(got,tuple(self.data[k] for k in ('readings','costs','surfaces')))
        self.assertIs(type(got[0]['仮名'][0]),tuple)
    def test_stale_source_and_absent_files_decline_index(self):
        self.source.write_bytes(b'different source');self.assertIsNone(I.load(self.source,self.index))
        self.source.unlink();self.assertIsNone(I.load(self.source,self.index))
        self.source.write_bytes(gzip.compress('かめい\t仮名:60\nかな\t仮名:40\n'.encode('utf-8'),mtime=0))
        self.index.unlink();self.assertIsNone(I.load(self.source,self.index))
    def test_changed_bytes_are_rejected_before_deserialization(self):
        self.index.write_bytes(b'corrupt')
        with patch.object(I._PrimitiveOnly,'load',side_effect=AssertionError('unverified data decoded')):
            self.assertIsNone(I.load(self.source,self.index))
    def test_schema_and_table_container_mismatch_decline(self):
        for data in (dict(self.data,schema=2),dict(self.data,costs=[])):
            self.save(data);self.assertIsNone(I.load(self.source,self.index))
    def test_global_and_external_pickle_instructions_are_rejected(self):
        for raw in (b'cos\nsystem\n.',b'Pexternal\n.'):
            with self.assertRaises(pickle.UnpicklingError):I._PrimitiveOnly(io.BytesIO(raw)).load()
    def test_original_source_parser_runs_when_index_is_unavailable(self):
        import corrector as C
        globals_before=tuple(getattr(C,k) for k in ('_TABLE_READINGS','_TABLE_COST','_TABLE_SURFACES'))
        try:
            C._TABLE_READINGS=C._TABLE_COST=C._TABLE_SURFACES=None
            with patch.object(I,'load',return_value=None),patch('gzip.open',side_effect=lambda *a,**k:io.StringIO('かめい\t仮名:60\nかな\t仮名:40\n')):
                self.assertEqual(C._table_readings_for_surface('仮名'),['かな','かめい'])
            self.assertEqual(C._TABLE_COST,{'仮名':40})
        finally:C._TABLE_READINGS,C._TABLE_COST,C._TABLE_SURFACES=globals_before

    def test_loader_restores_existing_collector_state_after_success(self):
        original=gc.isenabled()
        try:
            for enabled in (True,False):
                (gc.enable if enabled else gc.disable)()
                result=I.load(self.source,self.index)
                self.assertEqual(result,tuple(self.data[k] for k in ('readings','costs','surfaces')))
                self.assertEqual(gc.isenabled(),enabled)
        finally:(gc.enable if original else gc.disable)()

    def test_loader_restores_collector_after_decode_failure_or_unexpected_error(self):
        original=gc.isenabled()
        try:
            for enabled in (True,False):
                (gc.enable if enabled else gc.disable)()
                with patch.object(I._PrimitiveOnly,'load',side_effect=EOFError('broken verified fixture')):
                    self.assertIsNone(I.load(self.source,self.index))
                self.assertEqual(gc.isenabled(),enabled)
                with patch.object(I._PrimitiveOnly,'load',side_effect=RuntimeError('unexpected decoder failure')):
                    with self.assertRaises(RuntimeError):I.load(self.source,self.index)
                self.assertEqual(gc.isenabled(),enabled)
        finally:(gc.enable if original else gc.disable)()

    def test_fingerprint_rejection_does_not_change_collector(self):
        self.index.write_bytes(b'not the pinned public index')
        with patch.object(I.gc,'disable') as disable,patch.object(I.gc,'enable') as enable:
            self.assertIsNone(I.load(self.source,self.index))
        disable.assert_not_called();enable.assert_not_called()
