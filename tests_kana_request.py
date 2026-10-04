# -*- coding: utf-8 -*-
"""Native request-word repairs from independently anomalous kana tails."""
from tests_spelling_reference import assert_reviewed_source_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
from unittest.mock import patch
import morphology

@unittest.skipUnless(morphology.HAS_JANOME,'native Janome dictionary')
class KanaRequestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.a=initial()

    def correct(self,text,**kw):
        import app
        from decisions import DecisionStore
        return app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
            input_method=kw.pop('input_method','kana'),
            decisions=kw.pop('decisions',DecisionStore()),**kw)

    def test_native_sahen_link_owns_written_head_before_unknown_tail(self):
        import contextual_repair as Q,corrector
        from types import SimpleNamespace
        tokenize=corrector.make_tokenizer(self.a.store)
        for head in ('解析','保存','確認'):
            source=head+'してぷねら'
            target=SimpleNamespace(context=source,source=source,context_start=0,
                start=0,end=len(head),anomalies=())
            self.assertIn(('surface',head),Q._source_preserved_verb_bases(target,tokenize))
            self.assertIn(('surface',head),Q._candidate_verb_bases(head+'します',tokenize))
        for source in ('電車してぷねら','解析せてぷねら'):
            target=SimpleNamespace(context=source,source=source,context_start=0,
                start=0,end=2,anomalies=())
            self.assertNotIn(('surface',source[:2]),Q._source_preserved_verb_bases(target,tokenize))

    def test_native_request_repaired_at_original_boundaries(self):
        for prefix in ('','窓を開けて','泳いで','お茶を','おちゃを','ゆっくり歩いて'):
            for bad in ('くたせさい','くだせさい'):
                source=prefix+bad+'。';wanted=prefix+'ください。'
                with self.subTest(source=source):
                    result=self.correct(source)
                    assert_repaired_spelling(self, result, wanted)
                    self.assertFalse(result['odd_spans'])
                    again=self.correct(wanted)
                    assert_reviewed_source_spelling(self, again['corrected'], wanted)
                    self.assertFalse(again['odd_spans'])

    def test_small_vowel_and_separate_adjacent_slip(self):
        for prefix in ('','本を','ほんを','歩いて','説明して'):
            for bad in ('くたせさぃ','くだせさぃ'):
                with self.subTest(prefix=prefix,bad=bad):
                    result=self.correct(prefix+bad+'。')
                    assert_repaired_spelling(self, result, prefix+'ください。')
                    self.assertFalse(result['odd_spans'])
        result=self.correct('歩いてくたせさぃ。\t歩いてください。')
        self.assertEqual(result['corrected'],'歩いてください。\t歩いてください。')
        self.assertEqual(self.correct(result['corrected'])['corrected'],result['corrected'])

    def test_explicit_shift_release_and_neighbor_retains_two_operations(self):
        import contextual_repair as cr
        from types import SimpleNamespace
        for source,expected in (('なおしまぇ','なおします'),('よみまぇ','よみます'),('あけまぇ','あけます')):
            target=SimpleNamespace(boundary_kind='kana_predicate',text=source)
            rows=[r for r in cr.request_shift_key_repairs(target,source) if r.reading==expected]
            self.assertEqual(len(rows),1)
            first,second=rows[0].steps
            self.assertEqual((first.operation,first.pressed,first.intended),('shift','ぇ','え'))
            self.assertEqual((second.operation,second.pressed,second.intended),('adjacent_substitution','え','す'))
            self.assertEqual(first.position,second.position)
            self.assertAlmostEqual(rows[0].cost,1.4)
        for source in ('すきにん','かくにん','なおしまえ','なおしまぇながら'):
            target=SimpleNamespace(boundary_kind='kana_predicate',text=source)
            self.assertFalse(tuple(cr.request_shift_key_repairs(target,source)))
        for source,expected in (('ほんをよみまぇ。','本を読みます。'),('まどをあけまぇ。','窓を開けます。')):
            result=self.correct(source)
            self.assertEqual(result['corrected'],expected)
            self.assertFalse(result['odd_spans'])
            self.assertEqual(self.correct(expected)['corrected'],expected)
        for source in ('ほんをよみます。','くださぃ。','「ほんをよみまぇ」と書きました。'):
            assert_reviewed_source_spelling(self, self.correct(source)['corrected'], source)
        from decisions import DecisionStore
        ledger=DecisionStore();ledger.protect('よみまぇ')
        assert_reviewed_source_spelling(self, self.correct('ほんをよみまぇ。',decisions=ledger)['corrected'], 'ほんをよみまぇ。')

    def test_written_shifted_tail_keeps_native_stem_and_both_physical_steps(self):
        import pos_grammar as P,contextual_repair as R
        from types import SimpleNamespace
        for source,reading,expected in (('読みまぇ','よみまぇ','読みます'),('書きまぇ','かきまぇ','書きます'),
                ('確認しまぇ','かくにんしまぇ','確認します'),('暗号化しまぇ','あんごうかしまぇ','暗号化します')):
            frames=P.unexplained_shifted_predicate_tails(source)
            self.assertEqual(frames,((0,len(source),len(source)-2,reading),))
            target=SimpleNamespace(boundary_kind='auxiliary_connection',text=source)
            repairs=[r for r in R.request_shift_key_repairs(target,reading) if r.reading==reading[:-1]+'す']
            self.assertEqual(len(repairs),1)
            self.assertEqual([step.operation for step in repairs[0].steps],['shift','adjacent_substitution'])
            result=self.correct(source+'。')
            if source=='確認しまぇ':
                # Native しまい is a valid negative-volition alternative;
                # it cannot be banned to force the synthetic intended ます.
                # NHK research: https://www.jstage.jst.go.jp/article/bunken/68/12/68_46/_article/-char/ja
                self.assertIn(result['corrected'],(expected+'。','確認しまい。'))
            else:
                self.assertEqual(result['corrected'],expected+'。')
            self.assertFalse(result['odd_spans'])
        import corrector as C
        tokenize=C.make_tokenizer(self.a.store)
        original='確認しまぇ。'
        for lo,hi,new in ((0,5,'確認し前'),(3,5,'前'),(0,len(original),'確認し前。')):
            accepted,reason=C._check_replacement(original,(lo,hi,new,'かな入力'),
                self.a.store,tokenize,self.a.dict_index)
            self.assertIsNone(accepted)
            self.assertEqual(reason,'unproven_native_action_attachment')
        self.assertTrue(R._changed_shifted_predicate_tail_allowed('資料を確認しまぇ。',0,9,'資料を確認します。'))
        for source in ('読みますぅ','読みまぁす','読んでくださぃ','読みまえ','書きぃ','しらゆほまぇ','「読みまぇ」','未知名しまぇ','確認しますぅ','確認しまえ','確認しまぁす'):
            self.assertFalse(P.unexplained_shifted_predicate_tails(source),source)
        for source in ('読みますぅ。','読みまぁす。','読んでくださぃ。','「読みまぇ」と書きました。','確認しまえ。','確認しまぁす。'):
            assert_reviewed_source_spelling(self, self.correct(source)['corrected'], source)

    def test_compound_slips_keep_original_key_evidence(self):
        import contextual_repair as cr
        from types import SimpleNamespace
        for source in ('くたせさぃ','くだせさぃ'):
            target=SimpleNamespace(boundary_kind='kana_request',text=source)
            got=[r for r in cr.request_shift_key_repairs(target,source) if r.reading=='ください']
            self.assertTrue(got)
            self.assertEqual(len(got[0].steps),2)
            self.assertEqual(got[0].steps[0].operation,'shift')
            self.assertTrue(cr._original_intrusion_allowed(source,got[0].steps[1]))
        for bad in ('くだんさぃ','くくださぃ','くだささぃ'):
            target=SimpleNamespace(boundary_kind='kana_request',text=bad)
            self.assertFalse(any(r.reading=='ください' for r in cr.request_shift_key_repairs(target,bad)))
        for prefix in ('','歩いて'):
            text=prefix+'くださぃ。'
            self.assertEqual(self.correct(text)['corrected'],text)
        from decisions import DecisionStore
        ledger=DecisionStore();ledger.protect('くたせさぃ')
        self.assertEqual(self.correct('歩いてくたせさぃ。',decisions=ledger)['corrected'],'歩いてくたせさぃ。')
        text='「くたせさぃ」という文字列を調べる。'
        result=self.correct(text)
        self.assertEqual(result['corrected'],text)
        self.assertFalse(any(a<6 and 1<b for a,b in result['odd_spans']))

    def test_request_menu_rejects_the_actual_candidate_in_both_panes(self):
        from types import SimpleNamespace
        from decisions import DecisionStore
        import app
        for prefix in ('','本を'):
            for bad in ('くたせさい','くだせさい','くたせさぃ','くだせさぃ'):
                text=prefix+bad+'。';result=self.correct(text)
                self.assertIn((bad,'ください','かな入力'),result['details'])
                self.assertTrue(all(a<b for a,b in result['spans']))
                for source in (False,True):
                    calls=[]
                    fake=SimpleNamespace(line_results=[result],_reject_correction=lambda o,c:calls.append((o,c)))
                    unit=dict(start=len(prefix),end=len(prefix)+len(bad if source else 'ください'))
                    items=app.CorrectNoteApp._result_correction_menu_items(fake,1,unit,source)
                    undo=next(action for title,action in items if '元の入力に戻す' in title)
                    undo();self.assertEqual(calls,[(bad,'ください')])
                    ledger=DecisionStore();self.assertTrue(ledger.reject(*calls[0]))
                    # reject is pair-specific: a genuinely different offered spelling
                    # is allowed; protect below freezes the original itself.
                    rejected=self.correct(text,decisions=ledger)
                    self.assertNotIn((bad,'ください','かな入力'),rejected['details'])
                    self.assertFalse(ledger.blocks(text,rejected['corrected']))
                    ledger.protect(bad)
                    self.assertEqual(self.correct(text,decisions=ledger)['corrected'],text)

    def test_natural_and_incomplete_forms_are_not_searched(self):
        import contextual_repair as repair
        for source in ('ください。','くださる。','下せ。','くだせ。','くだせる。',
            '窓を開けてください。','窓を開けてくださいます。','歩いてくだされ。',
            'くださいね。','くださいな。','くだはい。','窓を開けてくだはい。',
            'くださぁい。','くだはぃ。','しゅごぃ。','窓を開けてくださぁい。','窓を開けてくださぃ。',
            'かくにんしてくださぃ。','かくにんしてくださぁい。','よんでくださぃ。',
            'くたせさいという文字列。',
            'きりがないようなものです。','きりがないようなも'):
            with self.subTest(source=source):
                with patch.object(repair,'resolve',wraps=repair.resolve) as resolve:
                    result=self.correct(source)
                assert_reviewed_source_spelling(self, result['corrected'], source)
                self.assertFalse(any(call.args[0].boundary_kind=='kana_request'
                    for call in resolve.call_args_list))

    def test_original_judgement_precedes_key_search(self):
        import contextual_repair as repair,corrector
        source='窓を開けてくたせさい'
        fn=corrector.make_tokenizer(self.a.store)
        with patch.object(repair,'key_repairs',side_effect=AssertionError('early key search')):
            targets=repair.targets_for_line(source,fn,self.a.store,self.a.dict_index)
        self.assertTrue(any(t.boundary_kind=='kana_request' and t.text=='くたせさい' for t in targets))
        with patch.object(corrector,'_chunk_is_intact',wraps=corrector._chunk_is_intact) as entry,              patch.object(corrector,'_check_replacement',wraps=corrector._check_replacement) as final:
            self.assertEqual(self.correct(source)['corrected'],'窓を開けてください')
        self.assertTrue(any(c.kwargs.get('repair_context') is not None and
            c.kwargs['repair_context'].boundary_kind=='kana_request' for c in entry.call_args_list))
        self.assertTrue(any(c.args[1][2]=='ください' for c in final.call_args_list))

    def test_nonadjacent_and_duplicate_keys_are_not_deleted(self):
        for bad in ('くだんさい','くください','くだささい'):
            with self.subTest(bad=bad):
                self.assertNotEqual(self.correct(bad+'。')['corrected'],'ください。')
        self.assertEqual(self.correct('くたせさい。',input_method='romaji')['corrected'],'くたせさい。')

    def test_stop_ledger_is_distinct_from_purple_suppression(self):
        from decisions import DecisionStore
        for protect in (False,True):
            ledger=DecisionStore()
            if protect:ledger.protect('くたせさい')
            else:ledger.reject('くたせさい','ください')
            self.assertEqual(self.correct('歩いてくたせさい。',decisions=ledger)['corrected'],'歩いてくたせさい。')
        ledger=DecisionStore();ledger.leave_odd_alone('くたせさい')
        self.assertEqual(self.correct('歩いてくたせさい。',decisions=ledger)['corrected'],'歩いてください。')

    def test_fresh_import_distinguishes_repairs_from_unknown_source_names(self):
        import app
        from tests_analysis_async import initial
        from janome_import import import_from_janome
        a=initial();import_from_janome(a.store)
        for source,wanted in (('かしゅあるをみます。','カジュアルをみます。'),
                              # 48-AOL-1: formerly forced to ピッツァ from
                              # generation history; an unknown original name
                              # with a complete predicate is not a proved typo.
                              ('ぴっづぁをみます。','ぴっづぁをみます。'),
                              ('まじゅまろをみます。','ましゅまろをみます。')):
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,dict_index=a.dict_index,
                    context_vec=a.context_vec,decisions=a.decisions,input_method='kana')
                assert_repaired_spelling(self, result, wanted)
                self.assertFalse(result['odd_spans'])

    def test_two_columns_preserve_usable_original_ranges(self):
        source='歩いてくたせさい。  泳いでくだせさい。'
        result=self.correct(source)
        self.assertEqual(result['corrected'],'歩いてください。  泳いでください。')
        self.assertTrue(result['original_spans'])
        self.assertTrue(all(a<b for a,b in result['original_spans']))

    def test_kana_continuative_is_not_lost_inside_broken_small_vowel_tail(self):
        import pos_grammar as P
        for source in ('なおしまぅ','あしたまでにぶんしょうをなおしまぅ'):
            start=source.index('なおし')
            self.assertIn((start,len(source),start+3,'なおしまぅ'),P.unexplained_shifted_predicate_tails(source))
        for source in ('なおしますぅ','なおしまぁす','なおしまう','「なおしまぅ」','しらゆほまぅ'):
            self.assertFalse(P.unexplained_shifted_predicate_tails(source),source)


if __name__=='__main__':unittest.main()
