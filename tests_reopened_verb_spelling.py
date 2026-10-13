import unittest
from unittest.mock import patch
import morphology as M,reading_segments as R

@unittest.skipUnless(M.HAS_JANOME,'native dictionary required')
class ReopenedVerbSpellingTests(unittest.TestCase):
    def test_actual_source_case_and_verb_range_are_required(self):
        cases=(('こうえんであるきます',5,8,'歩き'),
            ('わたしはこうえんであるきます',9,12,'歩き'),
            ('がくせいがこうえんであるきます',10,13,'歩き'),
            ('こうえんであるきました',5,8,'歩き'))
        for source,a,b,face in cases:
            with self.subTest(source=source):self.assertTrue(R.native_reopened_verb_spelling_boundary(source,a,b,face))
        for source,a,b,face in (('こうえんであるきます',4,8,'出歩き'),
                ('こうえんであるきます',5,7,'歩'),('こうえんであるきます',5,8,'走り'),
                ('こうえんであるきます',6,8,'歩き'),('へやであるきます',3,6,'歩き'),
                ('がくせいであるきます',5,8,'歩き'),('しりょうであるきます',5,8,'歩き')):
            with self.subTest(source=source,span=(a,b),face=face):self.assertFalse(R.native_reopened_verb_spelling_boundary(source,a,b,face))

    def test_actual_tail_owns_the_inflection_instead_of_isolated_noun_sense(self):
        self.assertEqual(M.tokenize('歩き')[0].pos,'名詞')
        self.assertEqual(M.tokenize('歩きます')[0].pos,'動詞')
        self.assertTrue(R.native_reopened_verb_spelling_boundary('こうえんであるきます',5,8,'歩き'))
        self.assertFalse(R.native_reopened_verb_spelling_boundary('こうえんであるき',5,8,'歩き'))
        self.assertFalse(R.native_reopened_verb_spelling_boundary('こうえんであるきましただ',5,8,'歩き'))

    def test_absent_source_or_candidate_semantics_supplies_no_boundary(self):
        with patch.object(R,'native_reopened_verb_case_frames',return_value=()):
            self.assertFalse(R.native_reopened_verb_spelling_boundary('こうえんであるきます',5,8,'歩き'))
        with patch.object(R,'preserves_reopened_verb_case_spelling',return_value=False):
            self.assertFalse(R.native_reopened_verb_spelling_boundary('こうえんであるきます',5,8,'歩き'))

    def test_final_proof_cannot_publish_after_request_changes(self):
        from analysis_context import request_scope,SupersededAnalysis
        stale=False;original=R.preserves_reopened_verb_case_spelling
        def proof(*args,**kwargs):
            nonlocal stale
            value=original(*args,**kwargs);stale=True;return value
        with request_scope(lambda:stale,poll_interval=1000),patch.object(R,'preserves_reopened_verb_case_spelling',proof):
            with self.assertRaises(SupersededAnalysis):
                R.native_reopened_verb_spelling_boundary('こうえんであるきます',5,8,'歩き')

    def test_original_ascii_entry_keeps_local_and_whole_common_validation(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        from correction_entry import correct_line
        import corrector as C
        state=initial();self.addCleanup(set_active,None)
        source='kouendearukimasu'
        def run():return correct_line(source,state.store,context_vocab={},input_method='romaji',
            dict_index=state.dict_index,decisions=state.decisions,context_vec=state.context_vec)
        actual=C._check_replacement;calls=[]
        def record(*args,**kwargs):
            calls.append((args[0],args[1]));return actual(*args,**kwargs)
        with patch.object(C,'_check_replacement',record):
            result=run()
        self.assertEqual(result['corrected'],'公園で歩きます')
        self.assertEqual(result['odd_spans'],[])
        self.assertEqual(result['analysis_status'],'complete')
        self.assertTrue(any(a==source and p[2]=='公園で歩きます' for a,p in calls))
        self.assertTrue(any(p[2]=='歩き' for a,p in calls))
        def reject_verb(*args,**kwargs):
            return (None,'forced_original_predicate') if args[1][2]=='歩き' else actual(*args,**kwargs)
        with patch.object(C,'_check_replacement',reject_verb):
            self.assertEqual(run()['corrected'],'公園であるきます')

if __name__=='__main__':unittest.main()
