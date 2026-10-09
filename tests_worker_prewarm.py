"""Optional public-index prewarm yields to real input and never caches partial data."""
from unittest.mock import patch,Mock
import unittest
from analysis_worker import Runtime
from analysis_context import request_scope,SupersededAnalysis,check_current_request

class WorkerPrewarmTests(unittest.TestCase):
 def test_prepare_does_not_require_optional_index(self):
  import contextual_repair as R
  rt=Runtime();rt.prepare_tables=Mock();rt.prepare=Mock(return_value={'context':{}})
  with patch.object(R,'_native_written_nominal_readings') as extra:
   self.assertEqual(rt.execute(dict(kind='prepare',lines=['資料'])),{'context':{}})
   extra.assert_not_called();rt.prepare.assert_called_once_with(['資料'])
 def test_warmup_prepares_existing_index_after_tables(self):
  import contextual_repair as R
  calls=[];rt=Runtime();rt.prepare_tables=lambda:calls.append('tables')
  with patch.object(R,'_native_written_nominal_readings',side_effect=lambda:calls.append('index')):
   rt.execute(dict(kind='warmup'))
  self.assertEqual(calls,['tables','index'])
 def test_new_request_stops_before_or_during_optional_walk(self):
  import contextual_repair as R
  for during in (False,True):
   with self.subTest(during=during):
    rt=Runtime();rt.prepare_tables=Mock();checks=[]
    def cancelled():checks.append(True);return len(checks)>(1 if during else 0)
    with patch.object(R,'_native_written_nominal_readings',side_effect=check_current_request) as extra,request_scope(cancelled):
     with self.assertRaises(SupersededAnalysis):rt.execute(dict(kind='warmup'))
     self.assertEqual(extra.call_count,1 if during else 0)
 def test_cancelled_dictionary_walk_is_not_retained_as_complete(self):
  import contextual_repair as R,janome_import
  R._native_written_nominal_readings.cache_clear()
  def interrupted(**kw):
   yield ('資料','しりょう','名詞','一般','*',1)
   raise SupersededAnalysis()
  try:
   with patch.object(janome_import,'iter_janome_entries',side_effect=interrupted):
    with self.assertRaises(SupersededAnalysis):R._native_written_nominal_readings()
   self.assertEqual(R._native_written_nominal_readings.cache_info().currsize,0)
   rows=[('資料','しりょう','名詞','一般','*',1),('書類','しょるい','名詞','一般','*',1)]
   with patch.object(janome_import,'iter_janome_entries',return_value=iter(rows)):
    self.assertEqual(R._native_written_nominal_readings(),{'しりょう':('資料',),'しょるい':('書類',)})
  finally:R._native_written_nominal_readings.cache_clear()
 def test_optional_failure_retries_and_does_not_hide_actual_prepare_errors(self):
  import contextual_repair as R,analysis_worker
  rt=Runtime();rt.tables_ready=True;rt.prepare_tables=Mock()
  with patch.object(R,'_native_written_nominal_readings',side_effect=[OSError('unavailable'),{}]) as extra,patch.object(analysis_worker.traceback,'print_exc') as reported:
   self.assertEqual(rt.execute(dict(kind='warmup')),{'ready':True})
   rt.execute(dict(kind='warmup'));self.assertEqual(extra.call_count,2);reported.assert_called_once()
  rt.prepare_tables.side_effect=ValueError('real prepare failed')
  with self.assertRaisesRegex(ValueError,'real prepare failed'):rt.execute(dict(kind='prepare',lines=['資料']))

if __name__=='__main__':unittest.main()
