# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import morphology as M,ime_spelling as I,corrector as C
from tests_analysis_async import initial
from last_choice import set_active

@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class NativeAuxiliarySpellingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state=initial();cls.tok=staticmethod(C.make_tokenizer(cls.state.store))
    @classmethod
    def tearDownClass(cls):set_active(None)
    def checked(self,source,start,end,face):
        a=self.state
        return C._check_replacement(source,(start,end,face,'かな入力'),a.store,self.tok,a.dict_index,a.decisions,spelling=True)
    def test_native_polite_inflections_do_not_become_lexical_verbs(self):
        for source,start,end,face in [('編集しましてた',3,5,'増し'),('保存しましてた',3,5,'増し'),('読みませ',2,4,'増せ'),('調査しませ',3,5,'増せ')]:
            with self.subTest(source=source):
                self.assertTrue(I._reinterprets_function_attachment(source,start,end,face))
                result,reason=self.checked(source,start,end,face)
                self.assertIsNone(result);self.assertEqual(reason,'original_function_attachment')
    def test_same_reading_lexical_verb_keeps_its_actual_role(self):
        for source,start,end,face in [('量がましています',2,4,'増し'),('勢いがましました',3,5,'増し'),('量をませ',2,4,'増せ')]:
            with self.subTest(source=source):
                self.assertFalse(I._reinterprets_function_attachment(source,start,end,face))
                result,reason=self.checked(source,start,end,face)
                self.assertIsNotNone(result,reason)
    def test_missing_native_evidence_does_not_invent_a_functional_role(self):
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertFalse(I._reinterprets_function_attachment('編集しましてた',3,5,'増し'))
    def test_closed_fields_keep_auxiliaries_and_convert_real_verbs(self):
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest(ime.error)
        import correction_entry as A
        a=self.state
        for source,expected in [('編集しましてた\t','編集しましてた\t'),('保存しましてた⇒','保存しましてた⇒'),('量がましています\t','量が増しています\t'),('勢いがましました⇒','勢いが増しました⇒')]:
            with self.subTest(source=source):
                r=A.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],expected);self.assertEqual(r['odd_spans'],[]);self.assertEqual(r['analysis_status'],'complete')
    def test_literal_mention_and_independent_clause_do_not_supply_attachment(self):
        self.assertFalse(I._reinterprets_function_attachment('読み。まし',3,5,'増し'))
        self.assertFalse(I._reinterprets_function_attachment('読み\tまし',3,5,'増し'))
        self.assertFalse(I._reinterprets_function_attachment('まし',0,2,'増し'))
    def test_whole_and_partial_fields_share_the_original_auxiliary(self):
        for source,start,end,face in [('編集しましてた',0,7,'編集し増してた'),
                ('編集しましてた',2,7,'し増してた'),('読みませ',0,4,'読み増せ'),
                ('読みました。保存しましてた',0,13,'読みました。保存し増してた')]:
            with self.subTest(source=source,start=start):
                self.assertTrue(I._reinterprets_function_attachment(source,start,end,face))
                value,reason=self.checked(source,start,end,face)
                self.assertIsNone(value);self.assertEqual(reason,'original_function_attachment')
    def test_wide_mapping_does_not_borrow_an_unchanged_auxiliary(self):
        for source,face in [('資料を読みました','資料を詠みました'),
                ('読みました。量がましています','読みました。量が増しています'),
                ('読みませ','読みました')]:
            with self.subTest(source=source):
                self.assertFalse(I._reinterprets_function_attachment(source,0,len(source),face))
        with patch.object(M,'dictionary_inflections',return_value=()):
            self.assertFalse(I._reinterprets_function_attachment('編集しましてた',0,7,'編集し増してた'))
    def test_native_literary_auxiliaries_keep_their_actual_attachment(self):
        for source,start,end,face in [('読まぬ',2,3,'布'),('読まざる',2,4,'笊'),
                ('行くまい',2,4,'舞'),('読みき',2,3,'木'),('読みけり',2,4,'蹴り')]:
            with self.subTest(source=source):
                self.assertTrue(I._reinterprets_function_attachment(source,start,end,face))
    def test_inflection_inside_a_named_word_is_not_a_native_auxiliary(self):
        for source,start,end,face in [('騙しました',0,2,'騙し'),('おこがましい',3,5,'増し'),('やましい',1,3,'増し')]:
            with self.subTest(source=source):
                self.assertFalse(I._reinterprets_function_attachment(source,start,end,face))

if __name__=='__main__':unittest.main()
