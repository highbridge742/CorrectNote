# -*- coding: utf-8 -*-
import unittest
import morphology

@unittest.skipUnless(morphology.HAS_JANOME,'requires native dictionary')
class SpellingFunctionalBoundaryTests(unittest.TestCase):
    def check(self,texts):
        from tests_analysis_async import initial
        from last_choice import set_active
        import app
        a=initial();a.context_vec=None
        try:
            for case in texts:
                text,expected=case if isinstance(case,tuple) else (case,case)
                with self.subTest(text=text):
                    r=app.correct_line(text,a.store,dict_index=a.dict_index,decisions=a.decisions,context_vec=None,input_method='kana')
                    self.assertEqual(r['corrected'],expected)
                    self.assertEqual(r.get('odd_spans'),[])
        finally:set_active(None)
    def test_native_final_particle_chain_keeps_its_grammatical_spelling(self):
        self.check(('ありますかな？','ありますかね？','ありますかい？','ありますかな','ありますか？'))
    def test_native_inchoative_noun_does_not_detach_its_last_verb(self):
        self.check(('のみかけ','たべかけ','書きかけ',('よみかけ','読みかけ'),'言いかけ'))

if __name__=='__main__':unittest.main()