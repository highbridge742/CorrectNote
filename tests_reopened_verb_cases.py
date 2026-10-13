import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as R
import semantic_roles as S

@unittest.skipUnless(M.HAS_JANOME,'native dictionary required')
class ReopenedVerbCaseTests(unittest.TestCase):
    def tearDown(self):
        R.completed_native_reading_clause.cache_clear()
        R.completed_native_reading.cache_clear()
        R.native_reopened_verb_case_frames.cache_clear()

    def test_same_native_noun_case_and_completed_predicate(self):
        for source in ('こうえんであるきます','わたしはこうえんであるきます','がくせいがこうえんであるきます'):
            with self.subTest(source=source):
                self.assertTrue(R.completed_native_reading_clause(source,require_object_fit=True))
        for source in ('がくせいであるきます','しりょうであるきます','あさであるきます',
                       'こうえんである','こうえんであります','こうえんであるき','ぷねらであるきます',
                       'しりょうであるきます。こうえんであるきます','しりょうであるきます\tこうえんであるきます'):
            with self.subTest(source=source):self.assertFalse(R.completed_native_reading_clause(source,require_object_fit=True))

    def test_missing_meaning_or_finite_tail_does_not_reopen(self):
        source='こうえんであるきます'
        for module,name,value in ((S,'native_verb_roles',frozenset()),(R,'completed_native_verb_reading',False)):
            with self.subTest(name=name):
                R.completed_native_reading_clause.cache_clear()
                with patch.object(module,name,return_value=value):
                    self.assertFalse(R.completed_native_reading_clause(source,require_object_fit=True))

    def test_modifier_and_same_nominal_constraint_are_kept(self):
        source='こうえんであるきます'
        self.assertFalse(R.completed_native_reading_clause(source,modifier_reading='たべる'))
        self.assertFalse(R.completed_native_reading_clause(source,nominal_constraint=('こうえん',('公演','講演'))))
        for face in ('部屋','道路'):
            with self.subTest(source_absent_face=face):
                self.assertEqual(R.native_reopened_verb_case_faces(source,M.tokenize(source),4,'で',(face,)),())
                self.assertFalse(R.completed_native_reading_clause(source,nominal_constraint=('こうえん',(face,))))
        self.assertTrue(R.completed_native_reading_clause(source,nominal_constraint=('こうえん',('公園',))))

    def test_common_gate_checks_actual_written_noun_for_local_and_wide_spelling(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        import corrector as C
        state=initial();self.addCleanup(set_active,None)
        native=C.make_tokenizer(state.store)
        source='がくせいがこうえんであるきます'
        for start,end,face in ((5,9,'講演'),(5,9,'公演'),(0,len(source),'学生が講演であるきます'),(0,len(source),'学生が公演で歩きます')):
            with self.subTest(face=face):
                result,reason=C._check_replacement(source,(start,end,face,'かな入力'),state.store,native,
                    state.dict_index,state.decisions,spelling=True,conv_taken=((start,end),))
                self.assertIsNone(result)
                self.assertEqual(reason,'original_nominal_argument_meaning')
        for start,end,face in ((5,9,'公園'),(0,len(source),'学生が公園で歩きます')):
            with self.subTest(face=face):
                result,reason=C._check_replacement(source,(start,end,face,'かな入力'),state.store,native,
                    state.dict_index,state.decisions,spelling=True,conv_taken=((start,end),))
                self.assertIsNotNone(result,reason)

    def test_completed_field_obeys_original_common_gate_and_original_ascii_block(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        from correction_entry import correct_line
        import corrector as C
        state=initial();self.addCleanup(set_active,None)
        source='kouendearukimasu'
        def run():return correct_line(source,state.store,context_vocab={},input_method='romaji',dict_index=state.dict_index,
            decisions=state.decisions,context_vec=state.context_vec)
        self.assertEqual(run()['corrected'],'公園で歩きます')
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
            self.assertEqual(run()['corrected'],source)
        state.decisions.protect('kouen')
        self.assertEqual(run()['corrected'],source)

    def test_cancelled_cached_proof_does_not_return_a_spelling_decision(self):
        from analysis_context import request_scope,SupersededAnalysis
        source='こうえんであるきます'
        self.assertTrue(R.native_reopened_verb_case_frames(source))
        with request_scope(lambda:True):
            with self.assertRaises(SupersededAnalysis):
                R.preserves_reopened_verb_case_spelling(source,0,4,'公園')

    def test_last_semantic_and_dictionary_checks_do_not_publish_after_cancellation(self):
        from analysis_context import request_scope,SupersededAnalysis
        source='こうえんであるきます'
        original=S.candidate_evidence
        stale=False
        def stop_after_meaning(*args,**kwargs):
            nonlocal stale
            result=original(*args,**kwargs)
            if result and result['shared_roles']:stale=True
            return result
        with request_scope(lambda:stale,poll_interval=1000),patch.object(S,'candidate_evidence',stop_after_meaning):
            with self.assertRaises(SupersededAnalysis):
                R.preserves_reopened_verb_case_spelling(source,0,4,'公園')
        R.native_reopened_verb_case_frames.cache_clear()
        stale=False;original_faces=R.native_reopened_verb_case_faces
        def stop_after_faces(*args,**kwargs):
            nonlocal stale
            result=original_faces(*args,**kwargs)
            if result:stale=True
            return result
        with request_scope(lambda:stale,poll_interval=1000),patch.object(R,'native_reopened_verb_case_faces',stop_after_faces):
            with self.assertRaises(SupersededAnalysis):R.native_reopened_verb_case_frames(source)
        self.assertEqual(R.native_reopened_verb_case_frames.cache_info().currsize,0)

    def test_unchanged_kana_noun_keeps_existing_predicate_only_spelling(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        import corrector as C
        state=initial();self.addCleanup(set_active,None)
        native=C.make_tokenizer(state.store)
        for source,start,end,face in (
                ('こうえんであるきます',5,8,'歩き'),
                ('こうえんであるきます',0,10,'こうえんで歩きます'),
                ('わたしはこうえんであるきます',9,12,'歩き')):
            with self.subTest(source=source,face=face):
                result,reason=C._check_replacement(source,(start,end,face,'かな入力'),state.store,native,
                    state.dict_index,state.decisions,spelling=True,conv_taken=((start,end),))
                self.assertIsNotNone(result,reason)
        self.assertFalse(R.preserves_reopened_verb_case_spelling('こうえんであるきます',0,10,'講演で歩きます'))

    def test_concatenated_content_clauses_do_not_reparse_growing_predicate_suffixes(self):
        source='こうえんであるきます'*32
        native=R.completed_native_verb_reading
        seen=[]
        def observe(text,*args,**kwargs):
            seen.append(text)
            return native(text,*args,**kwargs)
        with patch.object(R,'completed_native_verb_reading',observe):
            frames=R.native_reopened_verb_case_frames(source)
        self.assertEqual(len(frames),1)
        self.assertEqual(frames[0][2],310)
        self.assertEqual(seen,['あるきます'])
        # This independent manner predicate remains valid; its whole source
        # has no native self-standing owner at the cut, as before the change.
        manner='こうえんであるくようにします'
        self.assertTrue(R.completed_native_verb_reading(manner[5:],True,require_roles=False))
        self.assertEqual(R.native_reopened_verb_case_faces(manner,M.tokenize(manner),4,'で',('公園',)),())
        past='こうえんであるきました'
        self.assertEqual(R.native_reopened_verb_case_faces(past,M.tokenize(past),4,'で',('公園',)),('公園',))
        self.assertEqual(R.native_reopened_verb_case_faces('こうえんであるきますしりょうをよみます',
            M.tokenize('こうえんであるきますしりょうをよみます'),4,'で',('公園',)),())

if __name__=='__main__':unittest.main()
