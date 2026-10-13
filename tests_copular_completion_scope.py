import unittest
from unittest.mock import patch
import morphology as M,reading_segments as R

@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class CopularCompletionScopeTests(unittest.TestCase):
    def setUp(self):R.completed_native_reading_clause.cache_clear()
    def tearDown(self):R.completed_native_reading_clause.cache_clear()

    def test_finite_return_action_keeps_actual_written_reading_and_never_completes_open_tail(self):
        self.assertEqual(R.native_case_predicate_witness('公園','で','歩いています',return_action=True,finite_only=True),'歩い')
        self.assertEqual(R.native_case_predicate_witness('公園','で','歩かなかった',return_action=True,finite_only=True),'歩か')
        for predicate in ('歩いて','歩き','歩きた','生きています','講演しています'):
            with self.subTest(predicate=predicate):
                self.assertFalse(R.native_case_predicate_witness('公園','で',predicate,return_action=True,finite_only=True))
        self.assertFalse(R.completed_native_reading_clause('こうえんであるいています',modifier_reading='たべる',modifier_constraint=('しりょう',('資料',)),require_object_fit=True))
        self.assertFalse(R.completed_native_reading_clause('こうえんで\tあるいています',require_object_fit=True))

    def test_negative_final_action_result_after_cancel_cannot_publish_completion_or_cache(self):
        from analysis_context import request_scope,SupersededAnalysis
        native=R.native_case_predicate_witness;stale=[False];called=[]
        def witness(*args,**kwargs):
            result=native(*args,**kwargs)
            if kwargs.get('return_action'):
                called.append(result);stale[0]=True;return False
            return result
        with request_scope(lambda:stale[0],poll_interval=1000),patch.object(R,'native_case_predicate_witness',side_effect=witness):
            with self.assertRaises(SupersededAnalysis):R.completed_native_reading_clause('こうえんであるいています',require_object_fit=True)
        self.assertTrue(called)
        self.assertEqual(R.completed_native_reading_clause.cache_info().currsize,0)

    def test_local_completion_cannot_bypass_original_ascii_rejection_in_one_field(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        from correction_entry import correct_line
        import corrector as C
        first='kouendearuiteimasu';second='gakuseigakouendearuiteimasu';source=first+'\t'+second
        a=initial();self.addCleanup(set_active,None);native=C._check_replacement;rejected=[];local=[]
        def check(line,replacement,*args,**kwargs):
            start,end,face,category=replacement
            if (line==source and start<len(first) and end<=len(first)) or line==first:
                rejected.append((line,replacement));return None,'independent_original_field_reject'
            if 'あるいています' in line:local.append((line,replacement))
            return native(line,replacement,*args,**kwargs)
        with patch.object(C,'_check_replacement',side_effect=check):
            row=correct_line(source,a.store,input_method='romaji',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
        self.assertTrue(rejected)
        self.assertTrue(local)
        self.assertEqual(row['corrected'],first+'\t学生が公園で歩いています')
        self.assertEqual(row['original_spans'],[(len(first)+1,len(source))])
        self.assertEqual(row['odd_spans'],[])
        self.assertEqual(row['analysis_status'],'complete')

if __name__=='__main__':unittest.main()
