# -*- coding: utf-8 -*-
"""Executable SP/SR contracts. Tests use empty stores, never personal data."""
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import analysis_work as W
import contextual_repair as R


class WorkContracts(unittest.TestCase):
    def test_old_same_text_work_is_not_current(self):
        doc=W.Document('tab','A');work=doc.work(('kana',1))
        doc.update('B');doc.update('A')
        self.assertFalse(doc.accepts(work,('kana',1)))
        self.assertFalse(W.Document('other','A').accepts(work,('kana',1)))
        self.assertTrue(doc.accepts(doc.work(('kana',2)),('kana',2)))
        self.assertFalse(doc.accepts(doc.work(('kana',2)),('romaji',2)))

    def test_current_reading_is_for_one_occurrence(self):
        doc=W.Document('tab','未知と未知')
        self.assertTrue(doc.remember(3,5,'未知','ﾐﾁ'))
        with W.current_input(doc.text,doc.occurrences):
            self.assertEqual(W.occurrence_readings(doc.text,0,2),())
            self.assertEqual(W.occurrence_readings(doc.text,3,5),('みち',))
            self.assertEqual(W.occurrence_readings('試作と未知',3,5),())
        self.assertEqual(W.occurrence_readings(doc.text,3,5),())

    def test_move_then_overlap_expires(self):
        doc=W.Document('tab','資料');doc.remember(0,2,'資料','しりょう')
        doc.update('新資料',edit=(0,0))
        self.assertEqual(doc.occurrences[0].start,1)
        doc.update('新資材',edit=(2,3))
        self.assertFalse(doc.occurrences)

    def test_identical_repeated_text_uses_actual_edit_position(self):
        doc=W.Document('tab','資料資料');doc.remember(0,2,'資料','しりょう')
        doc.update('資料資料資料',edit=(0,0))
        self.assertEqual(doc.occurrences[0].start,2)

    def test_paste_does_not_copy_reading_and_undo_drops_it(self):
        doc=W.Document('tab','資料');doc.remember(0,2,'資料','しりょう')
        doc.update('資料資料',edit=(2,2))
        self.assertEqual(len(doc.occurrences),1)
        doc.update('資料',discard_readings=True)
        self.assertFalse(doc.occurrences)

    def test_readings_require_exact_live_surface(self):
        doc=W.Document('tab','資料')
        self.assertFalse(doc.remember(0,1,'資料','しりょう'))
        self.assertFalse(doc.remember(0,2,'資料','abc'))
        self.assertFalse(doc.occurrences)

    def test_line_ranges_are_codepoints_not_utf16(self):
        doc=W.Document('tab','😀\n資料')
        doc.remember(2,4,'資料','しりょう')
        row=doc.line_readings(2,'資料')[0]
        self.assertEqual((row.start,row.end),(0,2))


class CandidateContracts(unittest.TestCase):
    def test_reading_provenance_order_and_duplicates(self):
        weak=R.Reading('しりょう','character_guess',3)
        strong=R.Reading('しりょう','current_ime_occurrence',0)
        a=R.merge_readings([weak,strong,strong])
        self.assertEqual(a,R.merge_readings([strong,weak]))
        self.assertEqual(a[0].source,'current_ime_occurrence')
        self.assertEqual(len(a[0].provenance),2)

    def test_raw_kana_and_current_ime_have_same_direct_grade(self):
        a=R.Reading('か','token_sequence',0,((0,1,'か','literal_kana'),))
        b=R.Reading('か','current_ime_occurrence',0)
        self.assertEqual(R._reading_strength(a)[0],R._reading_strength(b)[0])
        self.assertLess(R._reading_strength(a)[0],R._reading_strength(R.Reading('か','saved_ime_pair',0))[0])

    @staticmethod
    def candidate(surface,cost=None):
        evidence=dict(direct=0,added=0,meaning=0,edits=1,physical=1.0,
            bases=0,script=0,proper=0,terminal=0,guesses=0,
            usage=1,context=0,cost=cost,continuation=0,parse_cost=0,start=0,end=2)
        return dict(surface=surface,reading=dict(text='かな'),rank_evidence=evidence,
                    repair=dict(reading='かな',position=0,operation='adjacent_substitution',pressed='x',intended='y'))

    def test_rank_is_total_and_order_independent(self):
        rows=[self.candidate('仮名'),self.candidate('かな')]
        self.assertEqual([r['surface'] for r in R.rank_candidates(rows)],
                         [r['surface'] for r in R.rank_candidates(reversed(rows))])

    def test_missing_optional_number_is_omitted_for_entire_group(self):
        rows=R.rank_candidates([self.candidate('仮名',10),self.candidate('かな',None)])
        self.assertTrue(all('cost' in r['omitted_numeric_evidence'] for r in rows))
        rows2=R.rank_candidates([self.candidate('仮名',10000),self.candidate('かな',None)])
        self.assertEqual([r['surface'] for r in rows],[r['surface'] for r in rows2])

    def test_duplicate_routes_are_not_votes(self):
        a,b=self.candidate('仮名'),self.candidate('かな')
        self.assertEqual(len(R.rank_candidates([a,a,b])),2)

    def test_bounded_zero_and_completed_zero_are_different(self):
        @R._with_search_report
        def search(limit):
            R._bounded([1,2],limit,'readings')
            return None,dict(status='no_candidate')
        self.assertEqual(search(2)[1]['status'],'no_candidate')
        self.assertEqual(search(1)[1]['status'],'unexplored_no_valid_candidate')

    def test_truncation_keeps_valid_observed_choice(self):
        @R._with_search_report
        def search():
            R._bounded([1,2],1,'readings')
            return '仮名',dict(status='selected')
        result,report=search()
        self.assertEqual(result,'仮名')
        self.assertEqual(report['search']['state'],'truncated')

    def test_purple_suppression_is_not_protection(self):
        from decisions import DecisionStore
        decisions=DecisionStore();decisions.leave_odd_alone('でしょぅ')
        self.assertFalse(decisions.blocks('でしょぅ','でしょう'))
        decisions.reject('でしょぅ','でしょう')
        self.assertTrue(decisions.blocks('でしょぅ','でしょう'))
        self.assertFalse(decisions.blocks('でしょぅ','別候補'))

    @staticmethod
    def option(start,end,surface,rank,anomalies):
        return dict(start=start,end=end,surface=surface,rank=(rank,),
                    anomalies=tuple(anomalies),context=(0,10))

    def test_independent_repairs_beat_a_wide_first_arrival(self):
        from joint_candidates import choose
        rows=[self.option(0,4,'wide',0,('one',)),
              self.option(0,1,'A',2,('one',)),self.option(3,4,'B',2,('two',))]
        selected,report=choose(rows,lambda rows:True,256)
        self.assertEqual([r['surface'] for r in selected],['A','B'])
        self.assertEqual(report['resolved'],2)
        again,_=choose(list(reversed(rows)),lambda rows:True,256)
        self.assertEqual(selected,again)

    def test_two_insertions_at_same_point_are_competing(self):
        from joint_candidates import choose
        rows=[self.option(2,2,'A',0,('one',)),self.option(2,2,'B',1,('two',))]
        selected,_=choose(rows,lambda rows:True,256)
        self.assertEqual([r['surface'] for r in selected],['A'])

    def test_same_anomaly_cannot_be_counted_twice(self):
        from joint_candidates import choose
        rows=[self.option(0,1,'A',1,('same',)),self.option(3,4,'B',0,('same',))]
        selected,report=choose(rows,lambda rows:True,256)
        self.assertEqual([r['surface'] for r in selected],['B'])
        self.assertEqual(report['resolved'],1)

    def test_rejected_first_joint_choice_tries_next(self):
        from joint_candidates import choose
        rows=[self.option(0,1,'A',0,('one',)),self.option(0,1,'B',1,('one',))]
        selected,_=choose(rows,lambda rows:all(r['surface']!='A' for r in rows),256)
        self.assertEqual([r['surface'] for r in selected],['B'])

    def test_joint_cutoff_keeps_best_verified_set_and_reports_it(self):
        from joint_candidates import choose
        rows=[self.option(0,1,'A',0,('one',)),self.option(0,1,'B',1,('one',))]
        selected,report=choose(rows,lambda rows:True,1)
        self.assertEqual([r['surface'] for r in selected],['A'])
        self.assertEqual(report['state'],'truncated')

    def test_cycle_restores_only_original_anomaly(self):
        import corrector as C
        @C._with_correction_source
        def cycling(text,*args,**kwargs):return cycling('trial' if text=='原文' else '原文',*args,**kwargs)
        def original_evidence(text,*args,**kwargs):
            self.assertEqual(text,'原文')
            kwargs['reasons_out'].append((0,2,'original fact'))
            return [(0,2)]
        with patch.object(C,'_odd_spans_for_line',side_effect=original_evidence):
            result=cycling('原文',None,lambda text:[])
        self.assertEqual(result['corrected'],'原文')
        self.assertEqual(result['odd_spans'],[(0,2)])
        self.assertEqual(result['stop_reason'],'cycle')


class TkWorkContracts(unittest.TestCase):
    def test_mutations_do_not_wait_for_idle_and_undo_forgets_readings(self):
        import tkinter as tk
        try:root=tk.Tk()
        except tk.TclError as exc:self.skipTest(str(exc))
        root.withdraw()
        try:
            widget=tk.Text(root,undo=True);doc=W.Document('tab')
            W.observe_text(widget,lambda text,discard,edit:doc.update(text,discard,True,edit))
            widget.insert('1.0','😀資料');widget.edit_separator()
            doc.remember(1,3,'資料','しりょう');work=doc.work()
            widget.insert('1.0','新');widget.edit_separator()
            self.assertEqual(doc.occurrences[0].start,2)
            widget.edit_undo()
            self.assertEqual(doc.text,'😀資料')
            self.assertFalse(doc.accepts(work))
            self.assertFalse(doc.occurrences)
        finally:root.destroy()


class SpellingEngineContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import morphology as M
        if not M.HAS_JANOME:raise unittest.SkipTest('requires native dictionary')
        import corrector as C
        from vocabulary import VocabularyStore
        from seed_vocabulary import load_seed
        cls.store=VocabularyStore();load_seed(cls.store)
        cls.tok=staticmethod(C.make_tokenizer(cls.store))

    def correct(self,text,**kwargs):
        import corrector as C
        from vocabulary import find_known_readings_flex
        return C.correct_line(text,self.store,self.tok,find_known_readings_flex,**kwargs)

    def test_required_auxiliary_and_adjective_changes(self):
        for text,expected in [('よいでしょぅか。','よいでしょうか。'),
                              ('確認しましょぅ。','確認しましょう。'),
                              ('寒ぃ日だ。','寒い日だ。'),('寒ぃ！','寒い！')]:
            with self.subTest(text=text):
                result=self.correct(text)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])
                self.assertEqual(self.correct(expected)['corrected'],expected)

    def test_hypothetical_adjective_does_not_take_a_foreign_word_fragment(self):
        import morphology as M
        for text in ('うぃんどう','うぃどう','こぃしん','こぃもく','ぺーすぃ','かくてぅ'):
            with self.subTest(text=text):self.assertFalse(M.original_spelling_facts(text))
        self.assertEqual(self.correct('さむぃですね。')['corrected'],'さむいですね。')
        self.assertEqual(self.correct('これはおもぃ日だ。')['corrected'],'これはおもい日だ。')

    def test_voice_and_explicit_spelling_mention_are_preserved(self):
        for text in ('寒ぃ〜','そうでしょぅ〜','ふぅ。','ふぇぇん。',
                     '「でしょぅ」という表記です。','寒ぃという名前です。'):
            with self.subTest(text=text):
                result=self.correct(text)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])

    def test_literal_protection_does_not_spread_to_dialogue(self):
        self.assertEqual(self.correct('「よいでしょぅか」と聞く。')['corrected'],
                         '「よいでしょうか」と聞く。')

    def test_two_changes_and_emoji_use_original_codepoint_ranges(self):
        text='😀寒ぃ日、確認しましょぅ。'
        result=self.correct(text)
        self.assertEqual(result['corrected'],'😀寒い日、確認しましょう。')
        self.assertEqual(result['original_spans'],[(2,3),(11,12)])

    def test_romaji_is_spelling_repair_without_invented_shift(self):
        import corrector as C
        with patch.object(C,'TRACE',[]):
            result=self.correct('よいでしょぅか。',input_method='romaji')
        self.assertEqual(result['corrected'],'よいでしょうか。')
        rows=result['contextual_diagnostics'][0]['candidates']
        self.assertTrue(rows)
        self.assertTrue(all(r['repair']['operation']=='small_kana_spelling' for r in rows))
        self.assertTrue(all(r['repair']['pressed']=='' for r in rows))

    def test_exact_scope_protection_keeps_other_error_repairable(self):
        from decisions import DecisionStore
        decisions=DecisionStore();decisions.protect('寒ぃ')
        result=self.correct('寒ぃ日、確認しましょぅ。',decisions=decisions)
        self.assertEqual(result['corrected'],'寒ぃ日、確認しましょう。')

    def test_purple_suppression_does_not_stop_repair(self):
        from decisions import DecisionStore
        decisions=DecisionStore();decisions.leave_odd_alone('でしょぅ')
        self.assertEqual(self.correct('よいでしょぅか。',decisions=decisions)['corrected'],
                         'よいでしょうか。')

    def test_rejecting_the_displayed_diff_blocks_the_whole_word_candidate(self):
        from decisions import DecisionStore
        decisions=DecisionStore();decisions.reject('ぅ','う')
        self.assertEqual(self.correct('よいでしょぅか。',decisions=decisions)['corrected'],
                         'よいでしょぅか。')

    def test_no_valid_output_keeps_original_anomaly(self):
        import corrector as C
        with patch.object(C,'_check_replacement',return_value=(None,'test_rejected')):
            result=self.correct('よいでしょぅか。')
        self.assertEqual(result['corrected'],'よいでしょぅか。')
        self.assertTrue(result['odd_spans'])

    def test_original_spelling_evidence_does_not_authorize_stem_changes(self):
        import morphology as M
        text='寒ぃ日だ。';facts=M.original_spelling_facts(text)
        self.assertEqual(len(facts),1)
        self.assertTrue(M.spelling_edit_allowed(text,0,2,'寒い'))
        self.assertFalse(M.spelling_edit_allowed(text,0,2,'暑い'))
        self.assertEqual(text[facts[0].change_start], 'ぃ')


if __name__=='__main__':unittest.main(verbosity=2)
