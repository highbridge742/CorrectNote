# -*- coding: utf-8 -*-
"""Ordinary avoidance uses the exact native verb and its own object roles."""
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('避ける'), 'requires native dictionary')
class AvoidanceRoleTests(unittest.TestCase):
    def test_shared_positive_roles_do_not_spread_to_homophones_or_other_actions(self):
        for noun in ('湿気','多湿','高温','熱','日光','直射日光','雨','風','冷気'):
            with self.subTest(noun=noun):
                self.assertTrue(S.support(noun,'避ける'))
                self.assertTrue(S.support(noun,'回避'))
                for action in ('裂ける','裂く','読む','食べる'):
                    self.assertFalse(S.support(noun,action))
        for verb,expected in (('さけ',True),('避け',True),('裂け',False)):
            self.assertEqual('exposure' in S.native_verb_roles(verb,'連用形','さけ',tail='ます'),expected)

    def test_source_noun_and_verb_need_their_own_native_reading_and_inflection(self):
        for text in ('しっけをさけます','たしつをさけます','あめをさけます',
                     'しっけをさけてほかんします'):
            with self.subTest(text=text):self.assertTrue(R.intact_native_reading(text))
        for text in ('しっけをよみます','しっけをたべます',
                     'しっけをさくてほかんします','しっけをさけなます'):
            with self.subTest(text=text):
                self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True))
                self.assertFalse(R.completed_native_reading_sequence(text))

    def test_initial_application_keeps_practical_storage_and_avoidance_phrases(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text in ('しっけをさけてほかんします。','たしつをさけます。',
                     'あめをさけます。','湿気を避けて保管します。'):
            with self.subTest(text=text):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],text)
                self.assertEqual(result.get('odd_spans'),[])


if __name__=='__main__':unittest.main()
