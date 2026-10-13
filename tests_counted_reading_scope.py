import unittest
from unittest.mock import patch
import reading_segments as R
from analysis_context import request_scope, SupersededAnalysis

class CountedReadingScopeTests(unittest.TestCase):
    def test_00_real_first_ascii_then_kana_then_written_quantity_loads_on_demand(self):
        for fn in (R._counted_nominal_index,R.native_counter_readings,R.native_ordinal_readings):fn.cache_clear()
        self.assertEqual(R.native_counted_nominal_evidence('2'),())
        self.assertEqual(R.native_counter_readings.cache_info().misses,0)
        self.assertEqual(R.native_ordinal_readings.cache_info().misses,0)
        self.assertEqual(R._counted_nominal_index.cache_info().misses,0)
        self.assertEqual(R.native_counted_nominal_evidence('ひとつ'),(('つ',False),))
        self.assertEqual(R._counted_nominal_index.cache_info().misses,0)
        self.assertEqual(R.native_counted_nominal_evidence('２人目'),(('人',True),))
        self.assertEqual(R._counted_nominal_index.cache_info().misses,1)
        self.assertEqual(R.native_counted_nominal_evidence('ふたりめ'),(('人',True),))
        self.assertEqual(R._counted_nominal_index.cache_info().misses,1)

    def test_non_kana_scripts_and_controls_keep_original_index_fallback(self):
        # These are scope probes, not new lexical expectations. A future
        # native sense at the same complete surface must still be queried.
        for surface in ('フタリ','ﾌﾀﾘ','ふた\u3099り','\ufeffふたり','二人','2人','２','\u3000','ふたり\t',''):
            seen=[]
            class Index(dict):
                def get(self,key,default=None):
                    seen.append(key)
                    return (('人',False),) if key==surface else default
            with self.subTest(surface=surface),patch.object(R,'_counted_nominal_index',return_value=Index()):
                self.assertEqual(R.native_counted_nominal_evidence(surface),(('人',False),))
                self.assertEqual(seen,[surface])

    def test_cancelled_partial_reading_does_not_survive_next_request(self):
        cancelled=[False]
        class Faces(tuple):
            def __iter__(self):
                for face in tuple.__iter__(self):
                    cancelled[0]=True
                    yield face
        source={'ふたり':Faces(('二人',))}
        with patch.object(R,'native_counter_readings',return_value=source),patch.object(R,'native_ordinal_readings',return_value={}):
            with request_scope(lambda:cancelled[0],poll_interval=600):
                with self.assertRaises(SupersededAnalysis):R.native_counted_nominal_evidence('ふたり')
            source['ふたり']=('二枚','二人','二人')
            with request_scope(lambda:False):
                self.assertEqual(R.native_counted_nominal_evidence('ふたり'),(('人',False),('枚',False)))
            source.clear()
            with request_scope(lambda:False):
                self.assertEqual(R.native_counted_nominal_evidence('ふたり'),())

    def test_written_numeric_spans_keep_original_unicode_offsets_and_notation(self):
        text='💡 １，２３４.５個／2.5人目／３人目／１,２３人／一億二千万個'
        spans=R.native_numeric_quantity_spans(text)
        self.assertEqual(tuple(text[s:e] for s,e in spans),('１，２３４.５個','３人目'))
        self.assertEqual(spans,((2,10),(17,20)))
        self.assertEqual(R.native_counted_nominal_evidence('一億二千万個'),(('個',False),))

if __name__=='__main__':unittest.main()
