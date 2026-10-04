# -*- coding: utf-8 -*-
"""Marked native nominal copulas retain source spelling, style and rejection scope."""
from tests_spelling_reference import assert_reviewed_source_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
from unittest.mock import patch
import morphology as M

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class NominalCopulaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.a=initial()

    def correct(self,text,decisions=None,input_method='kana'):
        import app
        from decisions import DecisionStore
        return app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
            decisions=decisions if decisions is not None else DecisionStore(),
            input_method=input_method,context_vec=None)

    def test_existing_mark_repairs_only_the_exact_nominal_tail(self):
        for head,bad,good in (('にゅうりょくまち','でうす','です'),
                             ('しょうにんまち','でうす','です'),
                             ('へんじまち','でうす','です'),
                             ('さぎょうまえ','でうす','です'),
                             ('にゅうりょくまち','でしそた','でした')):
            source=head+bad+'。';result=self.correct(source)
            assert_repaired_spelling(self, result, head+good+'。')
            self.assertFalse(result['odd_spans'])
            self.assertIn((bad,good,'かな入力'),result['details'])
            self.assertTrue(all(a<b for a,b in result['spans']))
        import reading_segments as R,kana_layout as K
        self.assertTrue(R.completed_native_nominal_predicate('にゅうりょくまちです',nominal_end=8))
        self.assertFalse(R.completed_native_nominal_predicate('にゅうりょくまちです',nominal_end=6))
        self.assertFalse(R.completed_native_nominal_predicate('にゅうりょくまちます',nominal_end=8))
        self.assertIn((0,8),R.native_context_ranges('さぎょうまえです'))
        for prefix in ('元気です','げんきです','にゅうりょくまちです'):
            for tail in ('か','かね','かい','かな','よね'):
                self.assertTrue(R.completed_native_nominal_predicate(prefix+tail,allow_written=True))
            for tail in ('かん','かんよ'):
                self.assertFalse(R.completed_native_nominal_predicate(prefix+tail,allow_written=True))
        self.assertFalse(K.single_key_drop_adjacency('でぬす','です'))
        self.assertFalse(K.single_key_drop_adjacency('もんじにゅうりょく','もじにゅうりょく'))
        self.assertEqual(self.correct('にゅうりょくまちでぬす。')['corrected'],'にゅうりょくまちでぬす。')
        assert_repaired_spelling(self, self.correct('もんじにゅうりょくでうす。'), 'もんじにゅうりょくです。')

    def test_original_style_is_shared_proof_and_not_a_generated_copula(self):
        import reading_segments as R,contextual_repair as X
        for source in ('にゅうりょくまちでおす。','しょうにんまちでおすよ。',
                       '入力待ちでおすね。','学生でおす。','にゅうりょくまちです。'):
            with patch.object(X,'resolve',wraps=X.resolve) as resolve:
                result=self.correct(source)
            assert_reviewed_source_spelling(self, result['corrected'], source)
            self.assertFalse(result['odd_spans'])
            self.assertFalse(any(call.args[0].boundary_kind=='kana_copula' for call in resolve.call_args_list))
        self.assertTrue(R.attested_nominal_polite_variant('にゅうりょくまちでおす'))
        self.assertFalse(R.completed_native_nominal_predicate('にゅうりょくまちでおす',nominal_end=8))
        for source in ('ぷねらでおす','にゅうりょくまちでうす','にゅうりょくまちでおすこ'):
            self.assertFalse(R.attested_nominal_polite_variant(source),source)
        for source in ('がくせいでうす。','とうちゃくまちでうす。','ぷねらでうす。'):
            with patch.object(X,'resolve',wraps=X.resolve) as resolve:
                result=self.correct(source)
            assert_reviewed_source_spelling(self, result['corrected'], source)
            self.assertFalse(any(call.args[0].boundary_kind=='kana_copula' for call in resolve.call_args_list))
        source='「にゅうりょくまちでうす」と入力します。'
        result=self.correct(source);assert_reviewed_source_spelling(self, result['corrected'], source)
        self.assertFalse(result['odd_spans'])
        source='にゅうりょくまちでうす。'
        self.assertEqual(self.correct(source,input_method='romaji')['corrected'],source)

    def test_menu_and_ledger_keep_a_nonempty_copula_pair(self):
        import app
        from types import SimpleNamespace
        from decisions import DecisionStore
        text='にゅうりょくまちでうす。';result=self.correct(text)
        for source in (False,True):
            calls=[]
            fake=SimpleNamespace(line_results=[result],_reject_correction=lambda o,c:calls.append((o,c)))
            unit=dict(start=8 if source else 4,end=11 if source else 6)
            items=app.CorrectNoteApp._result_correction_menu_items(fake,1,unit,source)
            undo=next(action for title,action in items if '元の入力に戻す' in title)
            undo();self.assertEqual(calls,[('でうす','です')])
            ledger=DecisionStore();self.assertTrue(ledger.reject(*calls[0]))
            self.assertEqual(self.correct(text,decisions=ledger)['corrected'],text)
            assert_reviewed_source_spelling(self, self.correct('しょうにんまちでしそた。',decisions=ledger)['corrected'], 'しょうにんまちでした。')
        ledger=DecisionStore();ledger.protect('でうす')
        self.assertEqual(self.correct(text,decisions=ledger)['corrected'],text)
        ledger=DecisionStore();ledger.leave_odd_alone('でうす')
        assert_reviewed_source_spelling(self, self.correct(text,decisions=ledger)['corrected'], '入力待ちです。')

    def test_common_source_entry_and_final_validation_remain_connected(self):
        import contextual_repair as X,corrector as C
        with patch.object(C,'_chunk_is_intact',wraps=C._chunk_is_intact) as entry, \
             patch.object(C,'_check_replacement',wraps=C._check_replacement) as final:
            result=self.correct('にゅうりょくまちでうす。')
        assert_repaired_spelling(self, result, 'にゅうりょくまちです。')
        self.assertTrue(any(call.kwargs.get('repair_context') is not None and
            call.kwargs['repair_context'].boundary_kind=='kana_copula' for call in entry.call_args_list))
        self.assertTrue(any(call.args[1][2]=='です' for call in final.call_args_list))
        with patch.object(X,'key_repairs',side_effect=AssertionError('premature key search')):
            targets=X.targets_for_line('にゅうりょくまちでうす。',C.make_tokenizer(self.a.store),
                                      self.a.store,self.a.dict_index)
        self.assertTrue(any(t.boundary_kind=='kana_copula' for t in targets))

    def test_explanatory_nominal_tail_uses_the_same_native_noun(self):
        import reading_segments as R
        for head in ('にゅうりょくまち','しょうにんまち','入力待ち'):
            for tail in ('なのです','なんです','なのだ','なんだ','だったのです','だったんです'):
                with self.subTest(head=head,tail=tail):
                    text=head+tail
                    self.assertTrue(R.completed_native_nominal_predicate(text,allow_written=True))
                    self.assertEqual(R.native_nominal_connective_boundaries(text),())
        for text in ('にゅうりょくまちなです','にゅうりょくまちだのです',
                     'にゅうりょくまちなのまうす','にゅうりょくまちなのですかん',
                     'ぷねらなのです','ぷねらなんです'):
            self.assertFalse(R.completed_native_nominal_predicate(text,allow_written=True),text)
        self.assertTrue(R.completed_native_nominal_predicate('にゅうりょくまちなのです',nominal_end=8))
        self.assertFalse(R.completed_native_nominal_predicate('にゅうりょくまちなのです',nominal_end=6))
        text='にゅうりょくまちなのでほんをよみまうす'
        self.assertIn(11,R.native_nominal_connective_boundaries(text))
        self.assertFalse(R.completed_native_nominal_predicate(text))

    def test_explanatory_sources_keep_text_without_a_copula_search(self):
        import contextual_repair as X
        for text in ('にゅうりょくまちなのです。','にゅうりょくまちなんです。',
                     'しょうにんまちだったのです。','入力待ちなんだ。',
                     'にゅうりょくまちなのですからほんをよみます。',
                     'にゅうりょくまちなのですがほんをよみます。'):
            with self.subTest(text=text),patch.object(X,'resolve',wraps=X.resolve) as resolve:
                result=self.correct(text)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result['odd_spans'])
            self.assertFalse(any(call.args[0].boundary_kind=='kana_copula' for call in resolve.call_args_list))
        result=self.correct('にゅうりょくまちなのでほんをよみまうす。')
        self.assertEqual(result['corrected'],'にゅうりょくまちなのでほんをよみまうす。')
        self.assertFalse(result['odd_spans'])


    def test_copula_scope_keeps_independent_lexical_repairs(self):
        for text,wanted in (('はそこん','パソコン'),('しゅうせあ','修正'),
                            ('ぶんしょす','文章'),('こうりさか','効率化')):
            result=self.correct(text)
            self.assertEqual(result['corrected'],wanted)
            self.assertFalse(result['odd_spans'])
        # This is two events at one position, never a one-key neighbor slip.
        from contextual_repair import key_repairs,neighbor_shift_key_repairs
        self.assertNotIn('しゅうせい',{r.reading for r in key_repairs('しにうせい')})
        pair=next(r for r in neighbor_shift_key_repairs('しにうせい') if r.reading=='しゅうせい')
        self.assertEqual(len(pair.steps),2)
        result=self.correct('しにうせい')
        self.assertEqual(result['corrected'],'修正')
        self.assertFalse(result['odd_spans'])
        import reading_segments as R
        for text in ('かくにんだぞん','にゅうりょくまちですん','にゅうりょくまちですかん'):
            self.assertFalse(R.completed_native_nominal_predicate(text),text)
        for text in ('にゅうりょくまちだぞ','にゅうりょくまちだよね','にゅうりょくまちですかい'):
            self.assertTrue(R.completed_native_nominal_predicate(text),text)
        # The old action-note output is still unresolved; merely blocking
        # the new malformed candidate is not counted as a successful repair.
        self.assertNotEqual(self.correct('かくにんたほぞん')['corrected'],'かくにんだぞん')

if __name__=='__main__':unittest.main()
