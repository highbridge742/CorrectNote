import unittest
from unittest.mock import patch
import reading_segments as R,morphology as M,semantic_roles as S
from analysis_context import request_scope,SupersededAnalysis

class ReopenedVerbScopeTests(unittest.TestCase):
    def tearDown(self):
        R.native_reopened_verb_case_frames.cache_clear()
        R.completed_native_reading_clause.cache_clear()

    def test_supplied_noun_face_requires_the_original_complete_reading(self):
        source='こうえんであるきます';parts=M.tokenize(source)
        self.assertEqual(R.native_reopened_verb_case_faces(source,parts,4,'で',('公園','講演','公演')),('公園',))
        for foreign in ('部屋','道路'):
            with self.subTest(foreign=foreign):
                self.assertEqual(R.native_reopened_verb_case_faces(source,parts,4,'で',(foreign,)),())
                self.assertFalse(R.completed_native_reading_clause(source,require_object_fit=True,nominal_constraint=('こうえん',(foreign,))))

    def test_true_native_dearuku_and_unrelated_clause_are_unchanged(self):
        for source in ('あさはであるきます','よるにであるきます','がくせいがであるきます','夜に出歩きます。','学生が出歩きます。'):
            with self.subTest(source=source):self.assertEqual(R.native_reopened_verb_case_frames(source),())
        source='資料を確認します。こうえんであるきます。'
        self.assertTrue(R.native_reopened_verb_case_frames(source))
        self.assertTrue(R.preserves_reopened_verb_case_spelling(source,0,2,'書類'))
        start=source.index('こうえん')
        self.assertTrue(R.preserves_reopened_verb_case_spelling(source,start,start+4,'公園'))
        self.assertFalse(R.preserves_reopened_verb_case_spelling(source,start,start+4,'講演'))

    def test_wide_change_preserves_original_clause_and_noun_role(self):
        source='しりょう。こうえんであるきます。'
        self.assertTrue(R.preserves_reopened_verb_case_spelling(source,0,len(source),'資料。公園で歩きます。'))
        self.assertFalse(R.preserves_reopened_verb_case_spelling(source,0,len(source),'資料。講演で歩きます。'))
        self.assertFalse(R.preserves_reopened_verb_case_spelling(source,0,len(source),'資料。公園で考えます。'))

    def test_existing_predicate_only_spelling_keeps_original_kana_noun(self):
        # All three changes were accepted by the unchanged baseline common C.
        for source,start,end,surface in (
            ('こうえんであるきます',5,8,'歩き'),
            ('こうえんであるきます',0,10,'こうえんで歩きます'),
            ('わたしはこうえんであるきます',9,12,'歩き')):
            with self.subTest(source=source,surface=surface):
                self.assertTrue(R.preserves_reopened_verb_case_spelling(source,start,end,surface))

    def test_unicode_prefix_and_two_fields_keep_the_actual_changed_noun(self):
        source='👩‍💻 資料。こうえんであるきます。\tこうえんであるきます。'
        starts=[source.index('こうえん'),source.rindex('こうえん')]
        for start in starts:
            with self.subTest(start=start):
                self.assertTrue(R.preserves_reopened_verb_case_spelling(source,start,start+4,'公園'))
                self.assertFalse(R.preserves_reopened_verb_case_spelling(source,start,start+4,'講演'))

    def test_cancel_after_actual_final_semantic_proof_cannot_publish(self):
        source='こうえんであるきます';self.assertTrue(R.native_reopened_verb_case_frames(source))
        cancelled=[False];original=S.candidate_evidence
        def evidence(*a,**k):
            result=original(*a,**k)
            if result and result['shared_roles']:cancelled[0]=True
            return result
        with request_scope(lambda:cancelled[0],poll_interval=600),patch.object(S,'candidate_evidence',side_effect=evidence):
            with self.assertRaises(SupersededAnalysis):R.preserves_reopened_verb_case_spelling(source,0,4,'公園')
        self.assertTrue(cancelled[0])

    def test_cancel_after_last_frame_probe_cannot_publish_lru_entry(self):
        import json
        from pathlib import Path
        source='こうえんであるきます';R.native_reopened_verb_case_frames.cache_clear()
        cancelled=[False];original=R.native_reopened_verb_case_faces
        def witness(*a,**k):
            result=original(*a,**k)
            if result:cancelled[0]=True
            return result
        try:
            with request_scope(lambda:cancelled[0],poll_interval=600),patch.object(R,'native_reopened_verb_case_faces',side_effect=witness):
                with self.assertRaises(SupersededAnalysis):R.native_reopened_verb_case_frames(source)
        finally:
            Path('frame_cancel_cache87.json').write_text(json.dumps({'cancelled':cancelled[0],'cache_size':R.native_reopened_verb_case_frames.cache_info().currsize})+'\n',encoding='utf-8')
        self.assertEqual(R.native_reopened_verb_case_frames.cache_info().currsize,0)

if __name__=='__main__':unittest.main()
