# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import corrector as C
import halfwidth as H
import romaji_source as R
from tests_analysis_async import initial
from last_choice import set_active
from correction_entry import correct_line
from analysis_context import request_scope,SupersededAnalysis


class SourceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.a=initial();self.tok=C.make_tokenizer(self.a.store)
        self.addCleanup(set_active,None)
    def test_common_gate_rechecks_original_raw_keys_after_restoration(self):
        method=C._CORRECTION_INPUT_METHOD.set('romaji')
        path=C._CORRECTION_PATH.set(('yubinkyoku','ゆびんきょく'))
        try:
            for text in ('yubinkyoku','ゆびんきょく'):
                accepted,reason=C._check_replacement(text,(0,len(text),'勉強','かな入力'),self.a.store,self.tok)
                self.assertIsNone(accepted);self.assertEqual(reason,'unproven_original_romaji_keys')
        finally:C._CORRECTION_PATH.reset(path);C._CORRECTION_INPUT_METHOD.reset(method)
    def test_literal_same_reading_and_written_completion_keep_their_keys(self):
        method=C._CORRECTION_INPUT_METHOD.set('romaji')
        try:
            for text,surface in (('gakkou','学校'),('mojinyuuryoku','文字入力'),
                    ('shoruinohozon','書類の保存'),('naoshimasu','治します'),
                    ('ｇａｋｋｏｕ','学校')):
                self.assertIsNone(R.candidate_evidence(text,0,len(text),surface,self.tok),(text,surface))
        finally:C._CORRECTION_INPUT_METHOD.reset(method)
    def test_generator_must_prove_actual_keys_even_when_lookup_proposes_word(self):
        result=H.correct_romaji('yubinkyoku',self.a.store,lambda *a,**k:[('べんきょう',3.5,3)])
        self.assertIsNone(result)
    def test_limit_is_visible_at_the_application_result(self):
        evidence=R.KeyEvidence('state_limit',False,-1,'',(),20000)
        with patch.object(R,'source_keys',return_value=evidence):
            row=correct_line('yubinkyoku',self.a.store,context_vocab={},decisions=self.a.decisions,
                input_method='romaji',context_vec=self.a.context_vec,dict_index=self.a.dict_index)
        self.assertEqual(row['corrected'],'yubinkyoku')
        self.assertEqual(row['analysis_status'],'limited')
        self.assertTrue(any(x['scope']=='romaji_source_keys' and x['state']=='truncated'
                            for x in row['search_reports']))
        self.assertIsNone(R._LIMITS.get())
    def test_current_request_cancellation_is_never_a_negative_candidate(self):
        with request_scope(lambda:True):
            with self.assertRaises(SupersededAnalysis):R.source_keys('yubinkyoku','べんきょう')
    def test_existing_repeat_option_reaches_generator_proof(self):
        for enabled in (False,True):
            with patch.dict('os.environ',{'CN_NO_DUP':'0' if enabled else '1'}):
                evidence=R.checked_source_keys('gakkkou','がっこう')
            self.assertEqual(evidence.proved,enabled)

    def test_kana_does_not_invent_raw_keys_without_an_ascii_ancestor(self):
        method=C._CORRECTION_INPUT_METHOD.set('romaji')
        try:
            for source,start,end,changed in [('ゆびんきょく',0,2,'べん'),
                    ('たんほのつながり',0,3,'単語'),('もんじにゅうりょく',0,9,'文字入力')]:
                path=C._CORRECTION_PATH.set((source,))
                try:
                    with patch.object(R,'source_keys',side_effect=AssertionError('kana is not original ASCII')):
                        self.assertIsNone(R.candidate_evidence(source,start,end,changed,self.tok))
                finally:C._CORRECTION_PATH.reset(path)
        finally:C._CORRECTION_INPUT_METHOD.reset(method)

    def test_existing_kana_spelling_keeps_the_common_gate_result(self):
        source='しやしんを保存します'
        method=C._CORRECTION_INPUT_METHOD.set('romaji')
        path=C._CORRECTION_PATH.set((source,))
        try:
            edit=(0,4,'写真','かな入力')
            accepted,reason=C._check_replacement(source,edit,self.a.store,self.tok)
            self.assertEqual(accepted,edit);self.assertEqual(reason,'accepted')
        finally:C._CORRECTION_PATH.reset(path);C._CORRECTION_INPUT_METHOD.reset(method)

    def test_mixed_width_fallback_does_not_invent_original_ascii(self):
        from unittest.mock import Mock
        finder=Mock(return_value=[('べんきょう',3.5,3)])
        with patch.object(H,'correct_halfwidth',return_value=None), \
             patch.object(R,'checked_source_keys',side_effect=AssertionError('mixed kana is not observed ASCII')):
            H.correct_zenkaku_input('ｙｕびｎｋｙｏｋｕ',self.a.store,finder)
        finder.assert_called_once()
        finder.reset_mock()
        with patch.object(H,'correct_halfwidth',return_value=None), \
             patch.object(R,'checked_source_keys',wraps=R.checked_source_keys) as checked:
            self.assertIsNone(H.correct_zenkaku_input('ｙｕｂｉｎｋｙｏｋｕ',self.a.store,finder))
        self.assertEqual(checked.call_args.args[:2],('yubinkyoku','べんきょう'))

    def test_interrupted_application_call_releases_limit_scope(self):
        with patch.object(R,'source_keys',side_effect=SupersededAnalysis()):
            with self.assertRaises(SupersededAnalysis):
                correct_line('yubinkyoku',self.a.store,context_vocab={},decisions=self.a.decisions,
                    input_method='romaji',context_vec=self.a.context_vec,dict_index=self.a.dict_index)
        self.assertIsNone(R._LIMITS.get())


if __name__=='__main__':unittest.main()
