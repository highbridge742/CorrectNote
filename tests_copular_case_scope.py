import unittest
from unittest.mock import patch
import morphology as M,reading_segments as R,semantic_roles as S

@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class CopularCaseScopeTests(unittest.TestCase):
    def test_written_predicate_keeps_its_own_meaning_and_complete_form(self):
        self.assertTrue(R.native_case_predicate_witness('公園','で','歩かなかった'))
        self.assertFalse(R.native_case_predicate_witness('講演','で','歩かなかった'))
        self.assertFalse(R.native_case_predicate_witness('ぷねら','で','歩かなかった'))
        self.assertFalse(R.native_case_predicate_witness('公園','で','歩きた'))
        self.assertFalse(R.native_case_predicate_witness('公園','で','講演しています'))
        for source in ('こうえんである','これはこうえんであります','よるにであるきます',
                       'こうえんであるいて資料を保存します'):
            self.assertEqual(R.native_reopened_verb_case_frames(source),(),source)

    def test_unicode_source_keeps_nominal_and_changed_actual_verb_separate(self):
        source='👩🏽‍💻 こうえんであるかなかった。\t資料を保存します。'
        start=source.index('あるか')
        self.assertTrue(R.preserves_reopened_verb_case_spelling(source,start,start+3,'歩か'))
        noun=source.index('こうえん')
        self.assertFalse(R.preserves_reopened_verb_case_spelling(source,noun,noun+4,'講演'))
        other=source.index('資料')
        self.assertTrue(R.preserves_reopened_verb_case_spelling(source,other,other+2,'しりょう'))
        self.assertFalse(R.preserves_reopened_verb_case_spelling(source,start,start+3,'離さ'))

    def test_last_meaning_query_cannot_publish_stale_true_or_false(self):
        from analysis_context import request_scope,SupersededAnalysis
        original=S.nominal_role_matches
        for noun in ('公園','講演'):
            stale=[False];calls=[]
            def query(face,roles):
                value=original(face,roles);calls.append((face,value));stale[0]=True;return value
            with self.subTest(noun=noun),request_scope(lambda:stale[0],poll_interval=1000),patch.object(S,'nominal_role_matches',side_effect=query):
                with self.assertRaises(SupersededAnalysis):R.native_case_predicate_witness(noun,'で','歩かなかった')
            self.assertTrue(calls)

    def test_last_copular_frame_probe_cannot_fill_lru_after_cancellation(self):
        from analysis_context import request_scope,SupersededAnalysis
        source='こうえんであるかなかった';stale=[False];calls=[]
        R.native_reopened_verb_case_frames.cache_clear()
        original=R.native_copular_case_faces
        def query(*args,**kwargs):
            result=original(*args,**kwargs);calls.append(result);stale[0]=True;return result
        with request_scope(lambda:stale[0],poll_interval=1000),patch.object(R,'native_copular_case_faces',side_effect=query):
            with self.assertRaises(SupersededAnalysis):R.native_reopened_verb_case_frames(source)
        self.assertTrue(calls)
        self.assertEqual(R.native_reopened_verb_case_frames.cache_info().currsize,0)

if __name__=='__main__':unittest.main()
