import unittest
from unittest.mock import patch
import morphology as M,ime_spelling as I,corrector as C
from tests_analysis_async import initial
from correction_entry import correct_line
from last_choice import set_active

@unittest.skipUnless(M.HAS_JANOME,'native dictionary required')
class CompoundArgumentTests(unittest.TestCase):
    def setUp(self):
        self.a=initial();self.tok=C.make_tokenizer(self.a.store)
        self.addCleanup(set_active,None)
    def helper(self,text,first,parts):
        return I._first_compound_arguments(text,first,parts,M.tokenize(text))
    def project(self,text):
        return I.project_first_words(text,self.a.store,self.a.dict_index,self.a.decisions,self.tok,subject_completion=True)
    def run_line(self,text,mode='romaji'):
        return correct_line(text,self.a.store,input_method=mode,dict_index=self.a.dict_index,decisions=self.a.decisions,context_vec=None)
    def test_complete_noun_range_retains_native_case_and_finite_predicate(self):
        for source,first in (('ゆうびんきょくにいきます','郵便局に行きます'),('かいぎしつにいきます','会議室に行きます')):
            spans=self.helper(source,first,M.tokenize(first))
            self.assertIsNotNone(spans)
            begin,end,face,edge=spans[0]
            self.assertTrue(M.native_spelling_only(source[begin:end],face))
            self.assertEqual(source[end],'に')
            self.assertEqual(first[edge],'に')
        self.assertIsNone(self.helper('ゆうびんきょくをたべます','郵便局を食べます',M.tokenize('郵便局を食べます')))
        self.assertIsNone(self.helper('ゆうびんきょくに','郵便局に',M.tokenize('郵便局に')))
        self.assertIsNone(self.helper('ゆうびんきょくにおきます','郵便局に行きます',M.tokenize('郵便局に行きます')))
    def test_unproved_long_compound_reuses_original_tokens_without_full_reparse(self):
        source='しりょう'*96+'にいきます';first='資料'*96+'に行きます'
        source_parts=M.tokenize(source);parts=M.tokenize(first);seen=[];real=M.tokenize
        def tokenize(value):seen.append(value);return real(value)
        with patch.object(M,'tokenize',side_effect=tokenize):
            self.assertIsNone(I._first_compound_arguments(source,first,parts,source_parts))
        self.assertNotIn(source,seen)

    def test_candidate_predicate_cannot_borrow_original_homophone_meaning(self):
        source='ゆうびんきょくにいきます';first='郵便局に生きます'
        self.assertIsNone(self.helper(source,first,M.tokenize(first)))

    def test_missing_meaning_or_native_identity_never_becomes_positive_proof(self):
        source='ゆうびんきょくにいきます';first='郵便局に行きます';parts=M.tokenize(first)
        with patch('semantic_roles.candidate_evidence',return_value=None):
            self.assertIsNone(self.helper(source,first,parts))
        with patch('reading_segments.native_common_noun_reading',return_value=False):
            self.assertIsNone(self.helper(source,first,parts))
        self.assertIsNone(self.helper('かいきけにいきます','会期毛に行きます',M.tokenize('会期毛に行きます')))
    def test_native_compound_projection_checks_local_original_range(self):
        gate=C._check_replacement;seen=[]
        def checked(line,edit,*args,**kwargs):
            seen.append((line,edit))
            if edit[2]=='郵便局':return None,'test_original_gate'
            return gate(line,edit,*args,**kwargs)
        with patch.object(C,'_check_replacement',side_effect=checked):
            self.assertIsNone(self.project('ゆうびんきょくにいきます'))
        self.assertIn(('ゆうびんきょくにいきます',(0,7,'郵便局','かな入力')),seen)
    def test_original_raw_rejection_and_partial_block_remain_authoritative(self):
        source='yuubinkyokuniikimasu'
        self.a.decisions.reject(source,'郵便局に行きます')
        self.assertEqual(self.run_line(source)['corrected'],source)
        self.a=initial()
        self.a.decisions.protect('binkyoku')
        result=self.run_line(source)
        lo=source.index('binkyoku');hi=lo+len('binkyoku')
        self.assertTrue(all(b<=lo or hi<=a for a,b in result.get('original_spans',())))
        self.assertIn('binkyoku',result['corrected'])
    def test_original_offsets_survive_earlier_shorter_field(self):
        source='shoruiwohozonshimasu\tyuubinkyokuniikimasu'
        row=self.run_line(source)
        self.assertEqual(row['corrected'],'書類を保存します\t郵便局に行きます')
        self.assertEqual(row['odd_spans'],[])
        self.assertEqual(row['analysis_status'],'complete')
    def test_ordinary_written_negative_quote_and_code_keep_their_scope(self):
        for source in ('郵便局に行きます','会議室に行きます','郵便局を食べます'):
            self.assertEqual(self.run_line(source,'kana')['corrected'],source)
        for source in ('「yuubinkyokuniikimasu」','print( yuubinkyokuniikimasu )','obj . yuubinkyokuniikimasu'):
            self.assertEqual(self.run_line(source)['corrected'],source)
        self.assertEqual(self.run_line('yubinkyokuniikimasu')['corrected'],'yubinkyokuniikimasu')

if __name__=='__main__':unittest.main()
