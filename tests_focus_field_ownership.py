import unittest
from unittest.mock import patch
import morphology as M,kana_spelling as K,reading_segments as R

@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class FocusFieldOwnershipTests(unittest.TestCase):
    def test_closed_native_focus_keeps_its_original_noun_in_each_field(self):
        from ime_spelling import _reinterprets_function_attachment as conflict
        for reading,face in (('もも','桃'),('はし','橋')):
            for focus in ('だけ','ばかり','など'):
                for separator in ('\t','→','  '):
                    source='👩‍💻 '+reading+focus+separator+'を置きます'
                    start=source.index(reading)
                    with self.subTest(source=source):
                        self.assertTrue(K._unresolved_focused_source_nominal(source,start,start+len(reading)))
                        self.assertTrue(conflict(source,start,start+len(reading)+len(focus),face+focus))
        for source,end in (('ねこだけ',2),('ぷねらだけ',3),('ももだけど',2)):
            self.assertFalse(K._unresolved_focused_source_nominal(source,0,end),source)

    def test_field_end_cannot_replace_missing_native_focus_evidence(self):
        source='ももだけ';parts=M.tokenize(source);members=set()
        with patch.object(R,'native_focused_nominal_parts',return_value=None):
            K._lexical_units(source,parts,members)
        self.assertNotIn((0,2),members)

    def test_obsolete_request_after_focus_probe_cannot_publish_a_new_boundary(self):
        from analysis_context import request_scope,SupersededAnalysis
        for source in ('ももだけ','ぷねらだけ'):
            parts=M.tokenize(source);members=set();stale=[False]
            original=R.native_focused_nominal_parts
            def probe(text):
                result=original(text)
                if text==source:stale[0]=True
                return result
            with self.subTest(source=source):
                with request_scope(lambda:stale[0],poll_interval=1000),patch.object(R,'native_focused_nominal_parts',side_effect=probe):
                    with self.assertRaises(SupersededAnalysis):K._lexical_units(source,parts,members)
                self.assertNotIn((0,2),members)

    def test_prior_field_shortening_keeps_unresolved_source_positions(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        from correction_entry import correct_line
        a=initial();self.addCleanup(set_active,None)
        left='しょるいをほぞんします';tail='はしだけ→を置きます。'
        result=correct_line(left+'\t'+tail,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        written,unchanged=result['corrected'].split('\t')
        self.assertEqual(unchanged,tail)
        self.assertLess(len(written),len(left))
        self.assertEqual(result['original_spans'],[(0,4),(5,8)])
        self.assertEqual(result['spans'],[(0,2),(3,5)])
        self.assertEqual([left[b:e] for b,e in result['original_spans']],['しょるい','ほぞん'])
        self.assertEqual([written[b:e] for b,e in result['spans']],['書類','保存'])
        self.assertEqual(result['odd_spans'],[])
        self.assertEqual(result['analysis_status'],'complete')

if __name__=='__main__':unittest.main()
