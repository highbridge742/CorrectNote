# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import romaji_repair as R
import halfwidth as H
import corrector as C
from correction_entry import correct_line
from tests_analysis_async import initial
from last_choice import set_active
from analysis_context import request_scope,SupersededAnalysis


class KeyCandidateTests(unittest.TestCase):
    def test_one_key_candidates_preserve_real_spelling_and_physical_operation(self):
        search=R.one_key_readings('shiryouwohozinshimasu')
        self.assertEqual(search.state,'complete')
        candidates=[row for row in search.candidates if row[0]=='しりょうをほぞんします']
        self.assertEqual(len(candidates),1)
        reading,cost,keys,operation=candidates[0]
        self.assertEqual(keys,'shiryouwohozonshimasu')
        self.assertEqual(operation,('adjacent_substitution',12,'i','o'))
        for reading,cost,keys,operation in search.candidates:
            self.assertEqual(H.romaji_to_kana(keys)[0],reading)
        missing=R.one_key_readings('tangonotuagari')
        self.assertTrue(any(row[0]=='たんごのつながり' and row[3]==('missing_key',9,'','n') for row in missing.candidates))
    def test_limits_and_cancel_are_not_candidate_zero(self):
        limited=R.one_key_readings('shiryouwohozinshimasu',state_limit=1)
        self.assertEqual(limited.state,'state_limit')
        self.assertEqual(limited.examined,1)
        self.assertEqual(R.one_key_readings('a'*97).state,'input_limit')
        with request_scope(lambda:True):
            with self.assertRaises(SupersededAnalysis):R.one_key_readings('tangonotuagari')


class KeyRepairIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.a=initial();self.addCleanup(set_active,None)
    def run_line(self,source,method='romaji'):
        return correct_line(source,self.a.store,decisions=self.a.decisions,input_method=method,
                            context_vec=self.a.context_vec,dict_index=self.a.dict_index)
    def test_independent_source_anomaly_and_completion(self):
        for source in ('shiryouwohozinshimasu','shiryouwohozinshimasu。'):
            with self.subTest(source=source):
                row=self.run_line(source)
                self.assertEqual(row['corrected'],'資料を保存します'+('。' if source.endswith('。') else ''))
                self.assertEqual(row['odd_spans'],[])
                self.assertEqual(row['analysis_status'],'complete')
                self.assertEqual(row['diagnosis']['language_state'],'anomaly_repaired')
    def test_source_unknown_is_not_an_anomaly_and_known_source_keeps_reading(self):
        with patch.object(R,'one_key_readings',side_effect=AssertionError('unproved source anomaly')):
            for source in ('tanhonotunagari','tangonotuagari','yubinkyoku',
                           'たんごのつながり','ｓｈｉｒｙｏｕｗｏｈｏｚｉｎｓｈｉｍａｓｕ'):
                with self.subTest(source=source):self.assertEqual(self.run_line(source)['corrected'],source)
        self.assertEqual(self.run_line('shiryouwohozonshimasu')['corrected'],'資料を保存します')
    def test_original_field_code_and_english_remain_protected(self):
        with patch.object(R,'one_key_readings',side_effect=AssertionError('not an entire original field')):
            for source in ('print( shiryouwohozinshimasu )','const shiryouwohozinshimasu = 1',
                           'obj . shiryouwohozinshimasu','value == shiryouwohozinshimasu',
                           'change remote delete manage','資料をhozinshimasu。'):
                with self.subTest(source=source):self.assertEqual(self.run_line(source)['corrected'],source)
    def test_original_offsets_survive_an_earlier_shorter_field(self):
        prefix='mojinyuuryoku\t';source=prefix+'shiryouwohozinshimasu'
        row=self.run_line(source)
        self.assertEqual(row['corrected'],'文字入力\t資料を保存します')
        self.assertIn([len(prefix),len(source)],row['diagnosis']['replaced_odd_spans'])
        self.assertEqual(row['odd_spans'],[])
    def test_rejected_replacement_remains_unresolved_and_display_policy_is_shared(self):
        source='shiryouwohozinshimasu'
        self.a.decisions.reject(source,'資料を保存します')
        row=self.run_line(source)
        self.assertEqual(row['corrected'],source)
        self.assertEqual(row['odd_spans'],[(0,len(source))])
        self.assertEqual(C.visible_odd_spans(source,row['odd_spans'],self.a.decisions),[])
    def test_partial_protection_keeps_original_ascii(self):
        source='shiryouwohozinshimasu'
        self.a.decisions.protect('hozin')
        row=self.run_line(source)
        # The previous engine also converts the independent unprotected prefix.
        # boundary68.json records the old/new equality; protect owns only hozin.
        self.assertEqual(row['corrected'],'資料をhozinshimasu')
        lo=source.index('hozin');hi=lo+len('hozin')
        self.assertTrue(all(b<=lo or hi<=a for a,b in row['original_spans']))
        self.assertEqual(C.visible_odd_spans(source,row['odd_spans'],self.a.decisions),[])
    def test_search_limit_keeps_anomaly_and_unknown_status(self):
        source='shiryouwohozinshimasu'
        with patch.object(R,'one_key_readings',return_value=R.ReadingSearch('state_limit',4096,())):
            row=self.run_line(source)
        self.assertEqual(row['corrected'],source)
        self.assertEqual(row['odd_spans'],[(0,len(source))])
        self.assertEqual(row['analysis_status'],'limited')
        self.assertTrue(any(report['scope']=='romaji_key_candidates' and report['unexplored'] for report in row['search_reports']))
        self.assertIsNone(R._DIAGNOSTICS.get())
    def test_cancellation_releases_source_scope(self):
        with patch.object(R,'one_key_readings',side_effect=SupersededAnalysis()):
            with self.assertRaises(SupersededAnalysis):self.run_line('shiryouwohozinshimasu')
        self.assertIsNone(R._DIAGNOSTICS.get())
    def test_completed_empty_search_is_distinct_from_an_unexplored_search(self):
        source='shiryouwohozinshimasu'
        with patch.object(R,'one_key_readings',return_value=R.ReadingSearch('complete',512,())):
            row=self.run_line(source)
        self.assertEqual(row['corrected'],source)
        self.assertEqual(row['odd_spans'],[(0,len(source))])
        self.assertEqual(row['analysis_status'],'complete')
        self.assertEqual(row.get('search_reports',[]),[])
    def test_existing_cost_limit_is_not_bypassed(self):
        from vocabulary import find_known_readings_flex
        source='shiryouwohozinshimasu'
        row=C.correct_line(source,self.a.store,C.make_tokenizer(self.a.store),find_known_readings_flex,
            max_dist=0.2,decisions=self.a.decisions,input_method='romaji',dict_index=self.a.dict_index,
            context_vec=self.a.context_vec)
        self.assertEqual(row['corrected'],source)
        self.assertEqual(row['odd_spans'],[(0,len(source))])
    def test_kana_mode_never_uses_the_new_key_search(self):
        source='shiryouwohozinshimasu'
        with patch.object(R,'one_key_readings',side_effect=AssertionError('romaji mode only')):
            self.assertEqual(self.run_line(source,'kana')['corrected'],source)


if __name__=='__main__':unittest.main()
