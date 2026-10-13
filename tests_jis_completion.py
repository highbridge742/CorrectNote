# -*- coding: utf-8 -*-
"""Exact JIS keys use original-field proof before new native completion."""
import unittest
from unittest.mock import patch
import corrector as C
import halfwidth as H
import morphology as M
from correction_entry import correct_line
from tests_analysis_async import initial
from last_choice import set_active
from analysis_context import SupersededAnalysis

DOC='d).et@ss@gjr'
PERSON='t@hpet@fudjr'
VERB='u6djr'

@unittest.skipUnless(M.HAS_JANOME,'native dictionary required')
class JISCompletionTests(unittest.TestCase):
    def setUp(self):
        self.a=initial();self.addCleanup(set_active,None)
        self.tok=C.make_tokenizer(self.a.store)
    def run_line(self,text):
        a=self.a
        return correct_line(text,a.store,context_vocab={},input_method='kana',
            dict_index=a.dict_index,decisions=a.decisions,context_vec=a.context_vec)
    def check(self,source,expected):
        r=self.run_line(source)
        self.assertEqual(r['corrected'],expected,source)
        self.assertEqual(r['analysis_status'],'complete',source)
        self.assertEqual(r['odd_spans'],[],source)
        self.assertFalse(r.get('diagnosis',{}).get('search_reports',()),source)
        return r
    def finish(self,source,start,end,restored):
        a=self.a
        return C._finish_halfwidth_candidate(source,start,end,restored,a.store,
            self.tok,a.dict_index,a.decisions,input_method='kana',native_context_required=True)
    def test_exact_jis_reading_does_not_use_romaji_projection(self):
        for raw,reading in ((DOC,'しょるいがとどきます'),(PERSON,'がくせいがはなします'),(VERB,'なおします')):
            self.assertEqual(M.normalize_marks(H.halfwidth_to_kana(raw)[0]),reading)
        with patch.object(H,'romaji_to_kana',side_effect=AssertionError('inferred romaji used')):
            self.check(DOC,'書類が届きます')
            self.check(PERSON,'学生が話します')
            self.check('病気を'+VERB+'。','病気を治します。')
            self.check('機械を'+VERB+'。','機械を直します。')
    def test_original_field_retains_code_and_literal_context(self):
        for source in ('print( '+DOC+' )','func( '+PERSON+' );','obj . '+DOC,
                       'value == '+DOC,'const '+DOC+' = 1;',
                       '`'+DOC+'`','"'+DOC+'"',
                       'https://example.test/jis',r'C:\Reports\notes.txt',
                       'Please save the document.','2.5kg'):
            with self.subTest(source=source):self.check(source,source)
    def test_two_fields_preserve_original_key_spans(self):
        source=DOC+'\t'+PERSON
        r=self.check(source,'書類が届きます\t学生が話します')
        self.assertEqual(r['original_spans'],[(0,len(DOC)),(len(DOC)+1,len(source))])
        self.a.decisions.protect('hpet')
        self.check(source,'書類が届きます\t'+PERSON)
    def test_partial_source_and_pair_blocks_survive_length_change(self):
        source='前文。病気を'+VERB+'。後文。'
        self.a.decisions.protect('6dj')
        self.check(source,source)
        self.a.decisions.unprotect('6dj')
        self.a.decisions.reject(VERB,'治します')
        self.check(source,source)
    def test_original_common_gate_precedes_any_native_projection(self):
        with patch.object(C,'_check_replacement',return_value=(None,'forced_original')) as gate, \
             patch('ime_spelling.project_first_words') as project:
            self.assertIsNone(self.finish(DOC,0,len(DOC),'しょるいがとどきます'))
            project.assert_not_called()
        self.assertEqual(gate.call_args.args[0],DOC)
        self.assertEqual(gate.call_args.args[1][:3],(0,len(DOC),'しょるいがとどきます'))
    def test_new_restoration_requires_native_provider(self):
        with patch('ime_spelling.project_first_words',return_value=None):
            self.check(DOC,DOC)
        with patch('ime_spelling.project_first_words',side_effect=OSError('unavailable')):
            self.assertIsNone(self.finish(DOC,0,len(DOC),'しょるいがとどきます'))
        with patch('ime_spelling.project_first_words',side_effect=ValueError('programming error')):
            with self.assertRaises(ValueError):self.finish(DOC,0,len(DOC),'しょるいがとどきます')
    def test_final_common_gate_can_reject_finished_spelling(self):
        gate=C._check_replacement
        def checked(line,edit,*args,**kwargs):
            if line==DOC and edit[2]=='書類が届きます':return None,'forced_final'
            return gate(line,edit,*args,**kwargs)
        with patch.object(C,'_check_replacement',side_effect=checked):self.check(DOC,DOC)
    def test_ordinary_kana_unknown_and_spaces_are_not_new_restorations(self):
        for source in ('病気を治します。','書類が届きます。','資料が話します。',
                       '病気を '+VERB+'。','zzzzzzzz'):
            with self.subTest(source=source):
                r=self.run_line(source)
                self.assertEqual(r['corrected'],source)
                self.assertEqual(r['analysis_status'],'complete')
    def test_outer_cancel_cleans_source_and_search_state(self):
        with patch('ime_spelling.project_first_words',side_effect=SupersededAnalysis()):
            with self.assertRaises(SupersededAnalysis):self.run_line(DOC)
        self.assertIsNone(C._CORRECTION_SOURCE.get())
        self.assertEqual(C._CORRECTION_PATH.get(),())
        self.check(PERSON,'学生が話します')
    def test_outer_limit_returns_original_input_and_incomplete_state(self):
        for exception,reason in ((C._CorrectionLimit,'depth_limit'),(C._CorrectionCycle,'cycle')):
            with self.subTest(reason=reason),patch('ime_spelling.project_first_words',side_effect=exception()):
                row=self.run_line(DOC)
                self.assertEqual(row['corrected'],DOC)
                self.assertEqual(row['analysis_status'],'incomplete')
                self.assertEqual(row['stop_reason'],reason)
                self.assertEqual(row['spans'],[])
                self.assertEqual(row['original_spans'],[])
                self.assertIsNone(C._CORRECTION_SOURCE.get())
                self.assertEqual(C._CORRECTION_PATH.get(),())

if __name__=='__main__':unittest.main()
