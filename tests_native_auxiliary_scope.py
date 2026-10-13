# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import ime_spelling as I,morphology as M

class NativeAuxiliaryScopeTests(unittest.TestCase):
    def test_actual_adjective_and_auxiliary_predecessors_remain_attached(self):
        for text,start,end,face in [('高くない',2,4,'内'),('読みたかった',5,6,'田'),('学生だった',4,5,'田')]:
            with self.subTest(text=text):
                self.assertTrue(I._reinterprets_function_attachment(text,start,end,face))

    def test_same_reading_real_verb_after_long_independent_fields_is_not_attached(self):
        prefix='資料を確認しました。'*48
        text=prefix+'勢いがましました';start=len(prefix)+3
        self.assertFalse(I._reinterprets_function_attachment(text,start,start+2,'増し'))

    def test_long_field_proved_auxiliary_does_not_require_hypothetical_negative_splits(self):
        text='資料を確認しました。'*48;start=text.rindex('まし')
        with patch.object(I,'_crosses_negative_attachment',side_effect=AssertionError('A proved single auxiliary is not a negative + noun span')):
            self.assertTrue(I._reinterprets_function_attachment(text,start,start+2,'増し'))

    def test_missing_predecessor_proof_keeps_the_previous_attachment_fallback(self):
        real=M.dictionary_inflections
        def inflections(word):return () if word=='読み' else real(word)
        with patch.object(M,'dictionary_inflections',side_effect=inflections):
            self.assertTrue(I._reinterprets_function_attachment('読みまして',2,4,'増し'))

    def test_independent_field_and_original_nominal_predecessor_do_not_attach(self):
        for text,start,end,face in [('読み。まし',3,5,'増し'),('読み\tまし',3,5,'増し'),('学生だ',2,3,'打')]:
            with self.subTest(text=text):
                self.assertFalse(I._reinterprets_function_attachment(text,start,end,face))

    def test_unproved_internal_copula_keeps_whole_range_checks_without_new_substring_searches(self):
        source='資料を確認しました。'*47+'学生だ';face=source[:-1]+'打'
        original=I._crosses_negative_attachment;seen=[]
        def inspect(text,start,end):
            seen.append((start,end))
            self.assertEqual((start,end),(0,len(source)))
            return original(text,start,end)
        with patch.object(I,'_crosses_negative_attachment',side_effect=inspect):
            self.assertFalse(I._reinterprets_function_attachment(source,0,len(source),face))
        self.assertEqual(seen,[(0,len(source))])

if __name__=='__main__':unittest.main()
