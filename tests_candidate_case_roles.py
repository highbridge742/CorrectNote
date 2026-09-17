# -*- coding: utf-8 -*-
"""Noun candidates share the same case roles as repaired predicates."""
import unittest
import morphology as M
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('戻る'),'requires native dictionary')
class CandidateCaseRoleTests(unittest.TestCase):
    def test_return_destinations_and_other_cases_share_exact_predicate_roles(self):
        for noun,following,role,case in (
                ('もと','に戻ります','origin','に'),('元','へ帰ります','origin','へ'),
                ('図書館','に戻ります','place','に'),('学校','へ向かいます','place','へ'),
                ('友達','に話します','person','に'),('辞書','で調べます','reference','で'),
                ('資料','を読みます','text','を')):
            with self.subTest(noun=noun,following=following):
                proof=S.candidate_object_evidence(noun,following)
                self.assertIsNotNone(proof)
                self.assertIn(role,proof['shared_roles'])
                self.assertEqual(proof['case'],case)

    def test_later_quoted_or_unknown_predicates_do_not_supply_fit(self):
        for following in ('に。戻ります','に「戻ります」',
                          'に置いてから戻ります','にしらゆほます','ので戻ります'):
            with self.subTest(following=following):
                proof=S.candidate_object_evidence('元',following)
                self.assertFalse(proof and proof['shared_roles'])
        proof=S.candidate_object_evidence('身元','に戻ります')
        self.assertFalse(proof and proof['shared_roles'])
        self.assertFalse('origin' in S.nominal_roles('身元'))

    def test_initial_application_uses_return_meaning_and_preserves_normal_context(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        result=app.correct_line('も水戸に戻ります',a.store,input_method='kana',
            dict_index=a.dict_index,context_vec=None,decisions=a.decisions)
        self.assertIn(result['corrected'],('もとに戻ります','元に戻ります'))
        self.assertEqual(result.get('odd_spans'),[])
        for text in ('もとに戻ります。','元に戻ります。','図書館へ戻ります。',
                     'これも水戸の名物です。','身元を確認します。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
