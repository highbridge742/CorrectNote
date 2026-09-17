# -*- coding: utf-8 -*-
"""An unchanged noun/case proof never certifies its malformed predicate."""
import unittest
from types import SimpleNamespace
import morphology as M
import reading_segments as R
import corrector as C
import oddness


@unittest.skipUnless(M.dictionary_inflections('箱'), 'requires native dictionary')
class NominalSourceRangeTests(unittest.TestCase):
    def setUp(self):
        from tests_analysis_async import initial
        self.a=initial();self.a.context_vec=None
        self.tok=C.make_tokenizer(self.a.store)

    def test_source_range_is_shared_by_entry_and_anomaly(self):
        text='このはこをまどのちかくにおきなます。'
        self.assertIn((0,5),R.native_context_ranges(text))
        anomalies=oddness.is_odd_run(text,self.tok,with_spans=True)
        self.assertNotIn(('この','は',0,3),anomalies)
        self.assertIn(('な','ます',14,17),anomalies)
        token=C._CORRECTION_SOURCE.set(text)
        try:
            context=SimpleNamespace(text='このは',structural=True,anomalies=(('この','は',0,3),))
            self.assertTrue(C._chunk_is_intact('このは',self.tok,repair_context=context))
            context=SimpleNamespace(text='なます',structural=True,anomalies=(('な','ます',14,17),))
            self.assertFalse(C._chunk_is_intact('なます',self.tok,repair_context=context))
        finally:C._CORRECTION_SOURCE.reset(token)

    def test_original_unknowns_and_extra_case_particles_are_not_certified(self):
        self.assertFalse(R.native_context_ranges('このしらゆほをおきなます。'))
        text='このはこをはおきなます。'
        anomalies=oddness.is_odd_run(text,self.tok,with_spans=True)
        self.assertTrue(any(a<6 and b>4 for _,_,a,b in anomalies))
        text='このはこをまどのちかくにおきなます。\tこのはこをしらゆほます。'
        ranges=R.native_context_ranges(text)
        self.assertTrue(all(text[a:b]=='このはこを' for a,b in ranges))
        self.assertEqual(len(ranges),2)

    def test_corrected_tail_no_longer_leaves_a_false_nominal_mark(self):
        import app
        text='このはこをまどのちかくにおきなます。'
        result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
            decisions=self.a.decisions,context_vec=None,input_method='kana')
        self.assertEqual(result['corrected'],'このはこをまどのちかくにおきます。')
        self.assertEqual(result['odd_spans'],[])
        self.assertEqual(result['diagnosis']['unreplaced_odd_spans'],[])
        self.assertEqual(result['original_spans'],[(14,15)])

    def test_unknown_tail_remains_separate_from_proved_nominal(self):
        import app
        text='このはこをしらゆほます。'
        result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
            decisions=self.a.decisions,context_vec=None,input_method='kana')
        self.assertEqual(result['corrected'],text)
        self.assertTrue(result['odd_spans'])
        self.assertFalse(C._chunk_is_intact(text,self.tok))


if __name__=='__main__':unittest.main()
