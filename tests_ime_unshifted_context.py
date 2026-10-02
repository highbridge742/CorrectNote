# -*- coding: utf-8 -*-
"""Compare attested source keys with Shift repairs using native argument roles."""
import unittest
import morphology
from semantic_roles import native_case_support

@unittest.skipUnless(morphology.HAS_JANOME,'native dictionary')
class NativeCandidateMeaningTests(unittest.TestCase):
    def test_subject_and_case_use_actual_inflected_predicate(self):
        for text in ('友人が歩きました','社員が座りました','規定が届きました','友人に連絡します'):
            with self.subTest(text=text):self.assertTrue(native_case_support(text))
        for text in ('規定が座りました','報告書に連絡します'):
            with self.subTest(text=text):self.assertFalse(native_case_support(text))
    def test_passive_and_causative_do_not_borrow_active_subject_roles(self):
        for text in ('友人が読まれました','友人が読ませました','社員が説明させられました'):
            with self.subTest(text=text):self.assertFalse(native_case_support(text))
    def test_later_clause_and_compound_tail_do_not_supply_support(self):
        for text in ('友人が消えて、資料を読む','友人が消えた後で歩く','作業員募集が歩きました'):
            with self.subTest(text=text):
                self.assertFalse(any(start==0 for start,end,case in native_case_support(text)))

@unittest.skipUnless(morphology.HAS_JANOME,'native dictionary')
class IMEUnshiftedContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:raise unittest.SkipTest('Japanese IME')
        from tests_analysis_async import initial
        cls.state=initial()
    def correct(self,text):
        import app
        a=self.state
        return app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                                decisions=a.decisions,context_vec=None)
    def test_keys_and_meaning_both_participate(self):
        for text,expected in (('きやくがかわりました','規約が変わりました'),
                              ('きやくがとどきました','規約が届きました'),
                              ('きやくがあるきました','客が歩きました'),
                              ('きやくがすわりました','客が座りました'),
                              ('きやくにれんらくします','客に連絡します'),
                              ('きやくがよまれました','規約が読まれました')):
            with self.subTest(text=text):
                result=self.correct(text);self.assertEqual(result['corrected'],expected)
                self.assertFalse(result.get('odd_spans'))
    def test_explicit_written_and_natural_kana_sources_stay_intact(self):
        for text in ('規約が歩きました','規約が来ました','客が読まれました','きやくをよみます'):
            with self.subTest(text=text):self.assertEqual(self.correct(text)['corrected'],text)

if __name__=='__main__':unittest.main()
