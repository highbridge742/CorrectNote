# -*- coding: utf-8 -*-
"""Native request-word repairs from independently anomalous kana tails."""
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

    def test_native_request_repaired_at_original_boundaries(self):
        for prefix in ('','窓を開けて','泳いで','お茶を','おちゃを','ゆっくり歩いて'):
            for bad in ('くたせさい','くだせさい'):
                source=prefix+bad+'。';wanted=prefix+'ください。'
                with self.subTest(source=source):
                    result=self.correct(source)
                    self.assertEqual(result['corrected'],wanted)
                    self.assertFalse(result['odd_spans'])
                    again=self.correct(wanted)
                    self.assertEqual(again['corrected'],wanted)
                    self.assertFalse(again['odd_spans'])

    def test_small_vowel_and_separate_adjacent_slip(self):
        for prefix in ('','本を','ほんを','歩いて','説明して'):
            for bad in ('くたせさぃ','くだせさぃ'):
                with self.subTest(prefix=prefix,bad=bad):
                    result=self.correct(prefix+bad+'。')
                    self.assertEqual(result['corrected'],prefix+'ください。')
                    self.assertFalse(result['odd_spans'])
        result=self.correct('歩いてくたせさぃ。\t歩いてください。')
        self.assertEqual(result['corrected'],'歩いてください。\t歩いてください。')
        self.assertEqual(self.correct(result['corrected'])['corrected'],result['corrected'])

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
                self.assertEqual(result['corrected'],source)
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

    def test_fresh_import_keeps_existing_lexical_repairs(self):
        import app
        from tests_analysis_async import initial
        from janome_import import import_from_janome
        a=initial();import_from_janome(a.store)
        for source,wanted in (('かしゅあるをみます。','カジュアルをみます。'),
                              ('ぴっづぁをみます。','ピッツァをみます。'),
                              ('まじゅまろをみます。','ましゅまろをみます。')):
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,dict_index=a.dict_index,
                    context_vec=a.context_vec,decisions=a.decisions,input_method='kana')
                self.assertEqual(result['corrected'],wanted)
                self.assertFalse(result['odd_spans'])

    def test_two_columns_preserve_usable_original_ranges(self):
        source='歩いてくたせさい。  泳いでくだせさい。'
        result=self.correct(source)
        self.assertEqual(result['corrected'],'歩いてください。  泳いでください。')
        self.assertTrue(result['original_spans'])
        self.assertTrue(all(a<b for a,b in result['original_spans']))

if __name__=='__main__':unittest.main()
