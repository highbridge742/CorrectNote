# -*- coding: utf-8 -*-
"""An actual action prefix participates in the full candidate grammar."""
from tests_spelling_reference import assert_reviewed_result_spelling
from tests_spelling_reference import assert_reviewed_source_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
from dataclasses import replace
import morphology as M
import reading_segments as R
import contextual_repair as CR
import corrector as C


@unittest.skipUnless(M.dictionary_inflections('保存'),'requires native dictionary')
class ActionAttachmentTests(unittest.TestCase):
    def test_native_prefix_and_longest_source_action_are_shared(self):
        import morphology as M, reading_segments as R, contextual_repair as Q
        self.assertEqual(M.native_sahen_compound_reading('再確認'),'さいかくにん')
        self.assertEqual(Q._native_sahen_reading_heads('さいかくにんくします')[0][1],'さいかくにん')
        self.assertTrue(R.completed_sahen_reading('さいかくにんします',finite_only=True))
        for text in ('さいかくにんくします','さいかくにんれます'):
            self.assertFalse(R.completed_sahen_reading(text,finite_only=True),text)
        for text in ('確認してた','確認してない','確認していない'):
            self.assertTrue(Q._productive_predicate(text,'確認'),text)
        self.assertFalse(M.native_sahen_compound_reading('再ぷねら'))
        for noun in ('各忍苦','各確認','各保管'):
            self.assertFalse(M.native_sahen_compound_reading(noun),noun)
        self.assertTrue(R.native_attested_prefix_noun_readings('各確認'))

    def test_prefix_inverse_does_not_require_a_shipped_whole_word(self):
        import reading_segments as R
        self.assertIn('再送信',R.native_bare_action_faces('さいそうしん'))
        self.assertEqual(CR._native_sahen_reading_heads('さいそうしんくします')[0][1],'さいそうしん')
        self.assertFalse(R.native_attested_prefix_noun_faces('さいぷねら'))
        self.assertFalse(CR._sahen_grammatical_tail('はします'))
        self.assertTrue(CR._sahen_grammatical_tail('します'))

    def test_known_modifier_is_not_a_sahen_head_before_an_unknown_noun(self):
        import app,corrector,contextual_repair as Q
        from tests_analysis_async import initial
        state=initial();tok=corrector.make_tokenizer(state.store)
        for source in ('かんたんなぽねです','しずかなぷねです'):
            with self.subTest(source=source):
                targets=Q.targets_for_line(source,tok,state.store,state.dict_index)
                self.assertFalse(any(t.boundary_kind=='sahen_tail' and t.start==0 for t in targets))

    def test_complete_action_boundary_precedes_homophonic_adverb(self):
        self.assertNotIn(2,R.native_adverbial_reading_cuts('かくにんくします'))
        self.assertFalse(R.intact_native_reading('かくにんくします'))
        self.assertIn(2,R.native_adverbial_reading_cuts('かくにんたいします'))
        self.assertTrue(R.intact_native_reading('かくにんたいします'))
        self.assertTrue(R.intact_native_reading('かくにんします'))
        self.assertFalse(CR.changed_native_action_attachment_allowed('かくにんくします',3,8,'危惧します'))
        self.assertFalse(CR.changed_native_action_attachment_allowed('かくにんくします',0,8,'危惧します'))
        self.assertTrue(CR.changed_native_action_attachment_allowed('かくにんくします',4,8,'します'))
        self.assertTrue(CR.changed_native_action_attachment_allowed('かくにんくします',0,8,'確認します'))

    def test_original_action_and_polite_end_are_shared_with_target(self):
        self.assertEqual(R.native_polite_action_prefixes('ほぞんくします'),(3,))
        self.assertEqual(R.native_polite_action_prefixes('かくにんくします'),(4,))
        self.assertEqual(R.native_polite_action_prefixes('ぷねらくします'),())
        self.assertEqual(R.native_polite_action_prefixes('ほぞんくし'),())
        self.assertEqual(R.native_polite_action_prefixes('ひょうきがありました'),())
        self.assertEqual(R.native_polite_action_prefixes('きかかんがありました'),())
        source='しゃしんをえらんでほぞんくします'
        target=CR.RepairTarget(source,9,len(source),0,len(source),
            (('品詞文法','未説明のかな語尾',9,len(source)),),True,'','kana_request')
        derived=[t for t in CR._native_action_tail_targets((target,)) if t!=target]
        self.assertEqual(len(derived),1)
        self.assertEqual((derived[0].text,derived[0].preserved_head),('ほぞんくします','ほぞん'))
        self.assertEqual(derived[0].anomalies,target.anomalies)
        self.assertEqual(derived[0].context,target.context)
        for item in (replace(target,anomalies=()),replace(target,structural=False)):
            self.assertEqual(CR._native_action_tail_targets((item,)),[item])

    def test_common_final_proof_covers_wide_narrow_and_written_candidates(self):
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        text='しゃしんをえらんでほぞんくします'
        for start,end,candidate in ((12,16,'かします'),(12,14,'かし'),
                (12,14,'燃し'),(9,16,'ほぞんかします')):
            result,why=C._check_replacement(text,(start,end,candidate,'かな入力'),
                a.store,tokenize,a.dict_index,a.decisions)
            self.assertIsNone(result)
            self.assertEqual(why,'unproven_native_action_attachment')
        for tail in ('します','もします','はします'):
            self.assertTrue(CR.changed_native_action_attachment_allowed(text,12,16,tail))
        self.assertFalse(CR.changed_native_action_attachment_allowed('かくにんくします',3,6,'隠し'))

    def test_complete_repairs_and_native_alternatives(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for source,expected in (
                ('しゃしんをえらんでほぞんくします。','しゃしんをえらんで保存します。'),
                ('ほぞんくします。','保存します。'),
                ('かくにんくします。','確認します。'),
                ('しゃしんをえらんでほぞんします。','しゃしんをえらんでほぞんします。')):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_result_spelling(self, result, expected)
            self.assertEqual(result.get('odd_spans'),[])
        for source in ('ほぞんもします。','ほぞんはします。','かくにんします。',
                       '保存先を開きます。',
                       'ごまをすります。','入力にします。','保存や検索をします。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], source)


if __name__=='__main__':unittest.main()
