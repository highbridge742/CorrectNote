# -*- coding: utf-8 -*-
"""Candidate edits must explain the case following an unchanged te form."""
import unittest
import morphology as M
import oddness as O


@unittest.skipUnless(M.dictionary_inflections('聞く'),'requires native dictionary')
class ConjunctiveCaseTests(unittest.TestCase):
    def test_changed_verb_cannot_leave_a_conjunctive_clause_as_an_object(self):
        for text,end in (('きいてをにだいならべます。',2),
                         ('きえいてをにだいならべます。',3),
                         ('書いてを読みます。',2),('読んでを買います。',2),
                         ('聞かせてを選びます。',2),('見てを選びます。',1)):
            with self.subTest(text=text):
                self.assertFalse(O.changed_conjunctive_case_allowed(text,0,end))

    def test_independent_nominal_readings_and_nominalizers_are_available(self):
        for text in ('きってをにまいかいます。','このきってをにまいかいます。',
                     'あてをさがします。','たてをそろえます。',
                     '読んだのを買います。','書いたものを読みます。',
                     '読んでから本を買います。','彼への手紙を読みます。'):
            with self.subTest(text=text):
                self.assertTrue(O.changed_conjunctive_case_allowed(text,0,len(text)))

    def test_only_the_affected_chain_is_checked(self):
        for text in ('本を買います。「書いてを読む」',
                     '本を買います。書いてを読む。','本を買い、書いてを読む。',
                     '本は書いてを読む。'):
            with self.subTest(text=text):
                self.assertTrue(O.changed_conjunctive_case_allowed(text,0,1))
        self.assertTrue(O.changed_conjunctive_case_allowed('「書いて」を読みます。',1,3))

    def test_shared_final_check_rejects_partial_repair_and_uses_the_noun(self):
        import app
        import corrector as C
        from tests_analysis_async import initial
        a=initial();source='きかいてをにだいならべます。'
        accepted,reason=C._check_replacement(source,(0,3,'きい','かな入力'),
            a.store,C.make_tokenizer(a.store),a.dict_index,a.decisions)
        self.assertIsNone(accepted)
        self.assertEqual(reason,'native_conjunctive_case')
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],'機械をにだいならべます。')
        self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
