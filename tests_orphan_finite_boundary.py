# -*- coding: utf-8 -*-
import unittest
import morphology as M
import app,corrector as C,contextual_repair as Q
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class OrphanFiniteBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a=initial();cls.tok=staticmethod(C.make_tokenizer(cls.a.store))
    def test_case_without_argument_does_not_certify_a_completed_prefix(self):
        self.assertTrue(Q._orphan_case_finite_predicate('のひっています'))
        for text in ('のこっています','ののしっています','のぼっています','がんばっています',
                     'ともします','のことです','にゅうりょくちゃう','のひって','のひっていま',
                     'のひっていますプネラ','のひっ・ています'):
            with self.subTest(text=text):self.assertFalse(Q._orphan_case_finite_predicate(text))
        targets=Q.targets_for_line('のひっています',self.tok,self.a.store,self.a.dict_index)
        self.assertTrue(any(t.start==0 and t.end==7 and t.boundary_kind=='auxiliary_connection' for t in targets))
    def test_normal_originals_and_unfinished_or_quoted_text_are_kept(self):
        from janome_import import import_from_janome
        a=self.a
        for phase in ('seed','fresh'):
            if phase=='fresh':import_from_janome(a.store)
            rows=[('のひっています','残っています'),('のこっています','残っています')]
            rows += [(t,t) for t in ('ののしっています','のぼっています','がんばっています',
                     'ともします','これをかいています。','これをみてください。',
                     '「のひっています」と書きます。','残っています','ひっています')]
            for text,expected in rows:
                with self.subTest(phase=phase,text=text):
                    r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                        context_vec=a.context_vec if phase=='fresh' else None,decisions=a.decisions)
                    self.assertEqual(r['corrected'],expected)
                    self.assertEqual(r.get('odd_spans'),[])
if __name__=='__main__':unittest.main()
