# -*- coding: utf-8 -*-
"""A complete action + time noun stays intact without a following predicate."""
import unittest
import morphology as M
import app,corrector as C,reading_segments as R
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class TemporalModifierPhraseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial()
        cls.tok=staticmethod(C.make_tokenizer(cls.a.store))

    def test_native_phase_and_auxiliary_connection_are_required(self):
        for text in ('したあと','やったあと','みたあと','かいたあと','きいたあと',
                     'よんだあと','およいだあと','いったあと','したあとで','したあとに',
                     'しないとき','するまえ','みるまえに','くるまえに','みているとき',
                     'たべたのち','よんだのちに','かえったあとで'):
            with self.subTest(text=text):self.assertTrue(R.native_temporal_nominal_reading(text))
        for text in ('ぷねったあと','するあと','したまえ','よむあと','よんだまえ',
                     'したあとえ','したあとをを','しるたあと','したあ','ぷねらのあと'):
            with self.subTest(text=text):self.assertFalse(R.native_temporal_nominal_reading(text))

    def test_initial_stages_keep_original_text_and_no_purple(self):
        from janome_import import import_from_janome
        a=self.a
        for phase in ('seed','fresh'):
            if phase=='fresh':import_from_janome(a.store)
            for text in ('したあと','したあとで','かいたあと','よんだあと','するまえ',
                         'したとき','した後','書いた後','およいだあと','くるまえに'):
                with self.subTest(phase=phase,text=text):
                    result=app.correct_line(text,a.store,dict_index=a.dict_index,
                        decisions=a.decisions,context_vec=a.context_vec if phase=='fresh' else None)
                    self.assertEqual(result['corrected'],text)
                    self.assertEqual(result.get('odd_spans'),[])

    def test_interior_fragment_and_final_candidate_use_the_same_source_proof(self):
        source='かいたあと';token=C._CORRECTION_SOURCE.set(source)
        try:self.assertTrue(C._chunk_is_intact('かいたあ',self.tok))
        finally:C._CORRECTION_SOURCE.reset(token)
        self.assertFalse(R.preserves_native_temporal_nominal('したあと','すたうと'))
        self.assertFalse(R.preserves_native_temporal_nominal('かいたあと','かいたいと'))
        candidate,reason=C._check_replacement('したあと',(0,4,'すたうと','かな入力'),
            self.a.store,self.tok,self.a.dict_index,conv_taken=((0,4),))
        self.assertIsNone(candidate,reason)
        self.assertTrue(R.preserves_native_temporal_nominal('したあと。寒ぃ日だ。','したあと。寒い日だ。'))
        self.assertTrue(R.preserves_native_temporal_nominal('ぷねったあと','ぷねたあと'))

if __name__=='__main__':unittest.main()
