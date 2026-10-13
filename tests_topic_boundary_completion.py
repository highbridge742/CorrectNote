# -*- coding: utf-8 -*-
"""The full source topic and predicate jointly resolve an internal noun cut."""
import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class TopicBoundaryReadingTests(unittest.TestCase):
    def setUp(self):
        R.completed_native_reading_clause.cache_clear()
        R.completed_native_reading.cache_clear()
    tearDown=setUp

    def test_whole_original_topic_has_the_same_complete_predicate(self):
        for source in ('がくせいははなします','がくせいははなしません',
                       'がくせいははなしました','がくせいははなしませんでした'):
            with self.subTest(source=source):
                self.assertTrue(R.native_reopened_topic_spelling(source,0,4,'学生'))
                self.assertTrue(R.completed_native_reading_clause(source,require_object_fit=True))
                self.assertTrue(R.completed_native_reading(source))

    def test_boundary_alone_and_missing_either_meaning_supply_no_completion(self):
        source='がくせいははなします'
        for module,name,empty in ((S,'native_verb_roles',frozenset()),
                                  (S,'nominal_roles',frozenset()),
                                  (R,'native_nominal_case_boundary',None)):
            with self.subTest(name=name):
                self.setUp()
                with patch.object(module,name,return_value=empty):
                    self.assertFalse(R.native_reopened_topic_spelling(source,0,4,'学生'))
                    self.assertFalse(R.completed_native_reading_clause(source))

    def test_first_word_other_subject_and_unfinished_predicate_are_preserved(self):
        for source,a,b,face in (('せいははなします',0,2,'生'),
                ('がくせいはとどきます',0,4,'学生'),
                ('しりょうははなします',0,4,'資料'),
                ('がくせいははなして',0,4,'学生'),
                ('がくせいははなしますです',0,4,'学生'),
                ('がくせいはしょるいがとどきます',0,4,'学生'),
                ('がくせいははなします',1,4,'学生'),
                ('がくせいははなします',0,4,'書類'),
                ('がくせいのはなします',0,4,'学生'),
                ('ぷねらははなします',0,3,'学生')):
            with self.subTest(source=source,a=a,b=b,face=face):
                self.assertFalse(R.native_reopened_topic_spelling(source,a,b,face))

    def test_other_field_and_whole_nominal_interpretation_cannot_lend_a_boundary(self):
        for sep in ('。','\t','⇒','→','\n','  '):
            source='がくせいははなして'+sep+'がくせいははなします'
            self.assertFalse(R.native_reopened_topic_spelling(source,0,4,'学生'))
        source='がくせいははなします';original=R.native_nominal_phrase_faces
        def full_prefix(text):
            return ('学制派',) if text=='がくせいは' else original(text)
        with patch.object(R,'native_nominal_phrase_faces',side_effect=full_prefix):
            self.assertFalse(R.native_reopened_topic_spelling(source,0,4,'学生'))


@unittest.skipUnless(M.HAS_JANOME,'native dictionary')
class TopicBoundaryAppTests(unittest.TestCase):
    def setUp(self):
        from tests_analysis_async import initial
        from last_choice import set_active
        self.state=initial();self.addCleanup(set_active,None)
    def run_line(self,source):
        from correction_entry import correct_line
        s=self.state
        return correct_line(source,s.store,context_vocab={},input_method='romaji',
            dict_index=s.dict_index,decisions=s.decisions,context_vec=s.context_vec)
    def assert_complete(self,source,expected):
        result=self.run_line(source)
        self.assertEqual(result['corrected'],expected)
        self.assertEqual(result['odd_spans'],[])
        self.assertEqual(result['analysis_status'],'complete')
        self.assertFalse(result.get('search_reports'))

    def test_finished_original_topic_retains_positive_meaning_in_written_form(self):
        for source,expected in (('gakuseihahanashimasu','学生は話します'),
                ('gakuseihahanashimasen','学生は話しません'),
                ('gakuseihahanashimashita','学生は話しました'),
                ('gakuseihahanashimasendeshita','学生は話しませんでした')):
            with self.subTest(source=source):self.assert_complete(source,expected)

    def test_original_common_gate_and_partial_user_stop_remain_effective(self):
        import corrector as C
        source='gakuseihahanashimasu'
        with patch.object(C,'_check_replacement',return_value=(None,'forced_common_gate')):
            self.assert_complete(source,source)
        self.state.decisions.protect('seihahana')
        self.assert_complete(source,source)

    def test_full_ascii_context_and_explicit_quote_are_preserved(self):
        for source in ('print( gakuseihahanashimasu )', 'obj . gakuseihahanashimasu',
                       'const gakuseihahanashimasu = 1;', 'value == gakuseihahanashimasu',
                       '「gakuseihahanashimasu」と入力します。'):
            with self.subTest(source=source):self.assert_complete(source,source)

    def test_each_column_keeps_its_own_original_scope_after_length_changes(self):
        source='shoruihatodokimasu\tgakuseihahanashimasen'
        self.assert_complete(source,'書類は届きます\t学生は話しません')
        self.state.decisions.protect('seihahana')
        self.assert_complete(source,'書類は届きます\tgakuseihahanashimasen')


if __name__=='__main__':unittest.main()
