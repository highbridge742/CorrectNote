import unittest
from unittest.mock import patch
import reading_segments as R,morphology as M
from analysis_context import request_scope,SupersededAnalysis

class ReopenedVerbFinalScopeTests(unittest.TestCase):
    def test_actual_dearuku_and_name_interiors_cannot_borrow_a_case(self):
        for source in ('よるにであるきます','あさはであるきます','がくせいがであるきます'):
            start=source.index('あるき')
            with self.subTest(source=source):
                self.assertFalse(R.native_reopened_verb_spelling_boundary(source,start,start+3,'歩き'))
        self.assertFalse(R.native_reopened_verb_spelling_boundary('ちよがきます',0,1,'血'))

    def test_unicode_fields_require_exact_source_case_and_full_original_verb(self):
        source='👩‍💻 資料。こうえんであるきます。\tこうえんであるきました。'
        for start in (source.index('あるき'),source.rindex('あるき')):
            with self.subTest(start=start):
                self.assertTrue(R.native_reopened_verb_spelling_boundary(source,start,start+3,'歩き'))
                self.assertFalse(R.native_reopened_verb_spelling_boundary(source,start,start+3,'歩く'))
                self.assertFalse(R.native_reopened_verb_spelling_boundary(source,start-1,start+3,'出歩き'))
                self.assertFalse(R.native_reopened_verb_spelling_boundary(source,start,start+2,'在る'))

    def test_last_shared_proof_cannot_return_after_request_becomes_obsolete(self):
        source='こうえんであるきます'
        self.assertTrue(R.native_reopened_verb_case_frames(source))
        stale=[False];original=R.preserves_reopened_verb_case_spelling
        def proof(*a,**k):
            result=original(*a,**k)
            if result:stale[0]=True
            return result
        with request_scope(lambda:stale[0],poll_interval=1000),patch.object(R,'preserves_reopened_verb_case_spelling',side_effect=proof):
            with self.assertRaises(SupersededAnalysis):
                R.native_reopened_verb_spelling_boundary(source,5,8,'歩き')
        self.assertTrue(stale[0])

    def test_local_final_C_rejection_preserves_only_the_other_accepted_word(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        from correction_entry import correct_line
        import corrector as C
        a=initial();self.addCleanup(set_active,None)
        original=C._check_replacement;denied=[]
        def gate(source,replacement,*args,**kwargs):
            if '歩' in replacement[2]:
                denied.append((source,tuple(replacement[:3])))
                return None,'independent_walk90_final_gate'
            return original(source,replacement,*args,**kwargs)
        with patch.object(C,'_check_replacement',side_effect=gate):
            result=correct_line('kouendearukimasu',a.store,input_method='romaji',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        self.assertIn(('公園であるきます',(3,6,'歩き')),denied)
        self.assertEqual(result['corrected'],'公園であるきます')
        self.assertEqual(result['odd_spans'],[])
        self.assertEqual(result['analysis_status'],'complete')

if __name__=='__main__':unittest.main()
