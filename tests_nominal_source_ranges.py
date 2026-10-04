# -*- coding: utf-8 -*-
"""An unchanged noun/case proof never certifies its malformed predicate."""
from tests_spelling_reference import assert_repaired_spelling
import unittest
from contextual_repair import RepairTarget
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
            context=RepairTarget(text,0,3,0,len(text),(('この','は',0,3),),True,text[3:])
            self.assertTrue(C._chunk_is_intact('このは',self.tok,repair_context=context))
            context=RepairTarget(text,14,17,0,len(text),(('な','ます',14,17),),True,text[17:])
            self.assertFalse(C._chunk_is_intact('なます',self.tok,repair_context=context))
        finally:C._CORRECTION_SOURCE.reset(token)

    def test_original_unknowns_and_extra_case_particles_are_not_certified(self):
        # The known modifier この survives; it does not prove the unknown noun.
        self.assertFalse(any(a<7 and 2<b for a,b in R.native_context_ranges('このしらゆほをおきなます。')))
        text='このはこをはおきなます。'
        anomalies=oddness.is_odd_run(text,self.tok,with_spans=True)
        self.assertTrue(any(a<6 and b>4 for _,_,a,b in anomalies))
        text='このはこをまどのちかくにおきなます。\tこのはこをしらゆほます。'
        ranges=R.native_context_ranges(text)
        self.assertTrue(all((offset,offset+5) in ranges for offset in (0,text.index('\t')+1)))
        for fragment in ('おきなます','しらゆほます'):
            start=text.index(fragment)
            self.assertFalse(any(a<=start and start+len(fragment)<=b for a,b in ranges))

    def test_corrected_tail_no_longer_leaves_a_false_nominal_mark(self):
        import app
        text='このはこをまどのちかくにおきなます。'
        result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
            decisions=self.a.decisions,context_vec=None,input_method='kana')
        assert_repaired_spelling(self, result, 'このはこをまどのちかくにおきます。')
        self.assertEqual(result['odd_spans'],[])
        self.assertEqual(result['diagnosis']['unreplaced_odd_spans'],[])
        # Equivalent spelling may combine or split visible correction units.
        # Each unit must reconstruct the result while retaining untouched text.
        original_end=corrected_end=0
        for (a,b),(c,d) in zip(result['original_spans'],result['spans']):
            self.assertLess(a,b);self.assertLess(c,d)
            self.assertEqual(text[original_end:a],result['corrected'][corrected_end:c])
            original_end,corrected_end=b,d
        self.assertEqual(text[original_end:],result['corrected'][corrected_end:])

    def test_unknown_tail_remains_separate_from_proved_nominal(self):
        import app
        text='このはこをしらゆほます。'
        result=app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
            decisions=self.a.decisions,context_vec=None,input_method='kana')
        self.assertEqual(result['corrected'],text)
        self.assertTrue(result['odd_spans'])
        self.assertFalse(C._chunk_is_intact(text,self.tok))


if __name__=='__main__':unittest.main()
