# -*- coding: utf-8 -*-
"""Candidate edits must explain the case following an unchanged te form."""
import unittest
import morphology as M
import oddness as O


@unittest.skipUnless(M.dictionary_inflections('聞く'),'requires native dictionary')
class ConjunctiveCaseTests(unittest.TestCase):
    def test_nominalized_existential_requires_its_case(self):
        from particle_frames import nominalized_existential_case_frames as frames
        for source in ('書くことかあります','よんだことかある','読むのかあります'):
            with self.subTest(source=source):
                self.assertTrue(frames(source))
                self.assertFalse(O.changed_auxiliary_chain_allowed(source,0,len(source)))

    def test_original_case_cannot_be_hidden_by_changing_the_previous_verb(self):
        for before,after in (('書くことかあります','核ことかあります'),
                ('伝えることかあります','伝えれことかあります')):
            with self.subTest(after=after):
                self.assertFalse(O.changed_auxiliary_chain_allowed(after,0,len(after),original=before))
        self.assertTrue(O.changed_auxiliary_chain_allowed('書くことがあります',0,9,
                                                        original='書くことかあります'))

    def test_native_case_repairs_without_an_answer_or_another_column(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for source,expected in (('書くことかあります','書くことがあります'),
                ('何かあります','何かあります'),('書くこともあります','書くこともあります')):
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertEqual(result['odd_spans'],[])

    def test_nominalization_question_and_indefinite_are_not_the_same_case(self):
        from particle_frames import nominalized_existential_case_frames as frames
        for source in ('書くことがあります','書いたこともあります','何かあります',
                'なにかあります','書くことかと思います','書くことから始めます',
                '書くことしかありません','書くことかもしれません','何のことか分かります',
                '書くことか読むことがあります','書くことかあるいは読むことです',
                '書くことか、ありますか','書くことかあり','書くことか',
                '「書くことかあります」という誤入力'):
            with self.subTest(source=source):self.assertEqual(frames(source),())
        self.assertTrue(O.changed_auxiliary_chain_allowed('本を読みます。書くことかあります',0,1))

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
        self.assertIn(result['corrected'],('機械をにだいならべます。','機械をにだい並べます。'))
        self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
