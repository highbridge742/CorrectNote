import unittest
from unittest.mock import patch
import morphology as M,reading_segments as R,semantic_roles as S

@unittest.skipUnless(M.HAS_JANOME,'native dictionary required')
class CopularCaseMeaningTests(unittest.TestCase):
    def tearDown(self):R.native_reopened_verb_case_frames.cache_clear()

    def test_each_same_reading_noun_owns_its_case_meaning(self):
        for suffix in ('あるかなかった','あるきそうです','あるいています'):
            source='こうえんで'+suffix
            with self.subTest(source=source):
                self.assertEqual(R.native_copular_case_faces(source,M.tokenize(source),4,'で',('公園','講演','公演')),('公園',))
                self.assertFalse(R.native_copular_case_faces(source,M.tokenize(source),4,'で',('部屋','道路')))
                self.assertTrue(R.preserves_reopened_verb_case_spelling(source,0,4,'公園'))
                for bad in ('講演','公演'):
                    self.assertFalse(R.preserves_reopened_verb_case_spelling(source,0,4,bad))

    def test_true_copula_invalid_inflection_and_other_clause_supply_no_witness(self):
        for source in ('がくせいであります','こうえんである','こうえんであるきた',
                       'こうえんであるいてしりょうをのみます','こうえんであるかなかったしりょうをよみます'):
            with self.subTest(source=source):
                self.assertFalse(R.native_copular_case_faces(source,M.tokenize(source),4,'で',R.native_nominal_phrase_faces(source[:4])))
        for predicate in ('あります','ある','あるきた','あるいて資料をのみます'):
            self.assertFalse(R.native_case_predicate_witness('公園','で',predicate))

    def test_predicate_only_spelling_and_written_actual_verb_are_distinguished(self):
        source='こうえんであるかなかった'
        self.assertTrue(R.preserves_reopened_verb_case_spelling(source,5,8,'歩か'))
        self.assertTrue(R.preserves_reopened_verb_case_spelling(source,0,len(source),'公園で歩かなかった'))
        self.assertFalse(R.preserves_reopened_verb_case_spelling(source,0,len(source),'講演で歩かなかった'))
        self.assertFalse(R.native_case_predicate_witness('公園','で','生きました'))
        self.assertFalse(R.native_case_predicate_witness('資料','で','歩かなかった'))

    def test_actual_original_spelling_gate_keeps_positive_and_rejects_different_noun(self):
        import corrector as C
        from tests_analysis_async import initial
        from last_choice import set_active
        s=initial();self.addCleanup(set_active,None);tok=C.make_tokenizer(s.store)
        source='こうえんであるかなかった'
        for face,good in (('公園',True),('講演',False),('公演',False)):
            result,reason=C._check_replacement(source,(0,4,face,'かな入力'),s.store,tok,s.dict_index,s.decisions,spelling=True,conv_taken=((0,4),))
            if good:self.assertIsNotNone(result,reason)
            else:self.assertEqual((result,reason),(None,'original_nominal_argument_meaning'))

    def test_final_meaning_cancellation_does_not_publish_or_cache(self):
        from analysis_context import request_scope,SupersededAnalysis
        native=S.native_verb_roles;stale=False
        def obsolete(*args,**kwargs):
            nonlocal stale
            value=native(*args,**kwargs)
            if value:stale=True
            return value
        with request_scope(lambda:stale,poll_interval=1000),patch.object(S,'native_verb_roles',obsolete):
            with self.assertRaises(SupersededAnalysis):R.native_reopened_verb_case_frames('こうえんであるかなかった')
        self.assertEqual(R.native_reopened_verb_case_frames.cache_info().currsize,0)

if __name__=='__main__':unittest.main()
