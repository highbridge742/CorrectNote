import unittest
from unittest.mock import patch
import morphology as M,reading_segments as R,semantic_roles as S

@unittest.skipUnless(M.HAS_JANOME,'native dictionary required')
class CopularCaseCompletionTests(unittest.TestCase):
    def setUp(self):
        self.tearDown()

    def tearDown(self):
        R.completed_native_reading_clause.cache_clear()
        R.completed_native_reading.cache_clear()
        R.native_reopened_verb_case_frames.cache_clear()

    def test_native_finite_case_keeps_modifiers_and_same_noun_constraints(self):
        for source in ('こうえんであるいています','こうえんであるかなかった','がくせいがこうえんであるいています'):
            with self.subTest(source=source):self.assertTrue(R.completed_native_reading_clause(source,require_object_fit=True))
        source='こうえんであるいています'
        self.assertFalse(R.completed_native_reading_clause(source,modifier_reading='たべる'))
        for faces in (('公演','講演'),('部屋','道路')):
            self.assertFalse(R.completed_native_reading_clause(source,nominal_constraint=('こうえん',faces)))
        self.assertTrue(R.completed_native_reading_clause(source,nominal_constraint=('こうえん',('公園',))))
        for source in ('こうえんである','がくせいであります','しりょうであるいています',
                       'こうえんであるきた','こうえんであるいて','しりょうであるいています。こうえんであるいています'):
            with self.subTest(source=source):self.assertFalse(R.completed_native_reading_clause(source,require_object_fit=True))

    def test_source_positive_meaning_is_required(self):
        with patch.object(R,'native_case_predicate_witness',return_value=False):
            self.assertFalse(R.completed_native_reading_clause('こうえんであるいています',require_object_fit=True))

    def test_original_ascii_reaches_both_local_and_full_common_checks(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        from correction_entry import correct_line
        import corrector as C
        s=initial();self.addCleanup(set_active,None);source='gakuseigakouendearuiteimasu';seen=[];native=C._check_replacement
        def observe(*args,**kwargs):
            seen.append((args[0],args[1]));return native(*args,**kwargs)
        def run():return correct_line(source,s.store,input_method='romaji',context_vocab={},dict_index=s.dict_index,decisions=s.decisions,context_vec=s.context_vec)
        with patch.object(C,'_check_replacement',observe):r=run()
        self.assertEqual(r['corrected'],'学生が公園で歩いています');self.assertEqual(r['odd_spans'],[])
        self.assertTrue(any(x==source for x,y in seen))
        self.assertTrue(any('あるいています' in x and y[2]=='歩い' for x,y in seen))
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
            self.assertEqual(run()['corrected'],source)

    def test_original_partial_block_does_not_move_to_other_field(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        from correction_entry import correct_line
        s=initial();self.addCleanup(set_active,None);s.decisions.protect('gakuseigakouen')
        source='kouendearuiteimasu\tgakuseigakouendearuiteimasu'
        r=correct_line(source,s.store,input_method='romaji',context_vocab={},dict_index=s.dict_index,decisions=s.decisions,context_vec=s.context_vec)
        self.assertEqual(r['corrected'],'公園で歩いています\tgakuseigakouendearuiteimasu')

    def test_completion_cannot_publish_after_last_case_witness_cancels(self):
        from analysis_context import request_scope,SupersededAnalysis
        native=R.native_case_predicate_witness;stale=False
        def obsolete(*args,**kwargs):
            nonlocal stale
            value=native(*args,**kwargs)
            if kwargs.get('return_action') and value:stale=True
            return value
        with request_scope(lambda:stale,poll_interval=1000),patch.object(R,'native_case_predicate_witness',obsolete):
            with self.assertRaises(SupersededAnalysis):
                R.completed_native_reading_clause('こうえんであるいています',require_object_fit=True)
        self.assertEqual(R.completed_native_reading_clause.cache_info().currsize,0)

if __name__=='__main__':unittest.main()
