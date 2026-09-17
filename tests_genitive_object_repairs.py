# -*- coding: utf-8 -*-
"""An already anomalous genitive object uses its unchanged first predicate."""
import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as R
import contextual_repair as CR
import corrector as C
import kana_layout as K


@unittest.skipUnless(M.dictionary_inflections('窓'),'requires native dictionary')
class GenitiveObjectRepairTests(unittest.TestCase):
    def test_source_boundaries_require_native_modifier_and_actual_action(self):
        for text in ('へやのまとべをあけます','へやのまとづをあけます',
                     'せんせいのしりょにうをよみます'):
            with self.subTest(text=text):
                slots=R.native_genitive_object_slots(text)
                self.assertTrue(slots)
                begin,head,case,finish=slots[0]
                self.assertEqual(text[begin:head][-1:],'の')
                self.assertEqual(text[case],'を')
                self.assertEqual(finish,len(text))
        for text in ('ぷねらのまとべをあけます','へやのまとべをぷねら',
                     'へやにまとべをあけます','へやのまど',
                     'あしたのかいぎでしるょうをくばります',
                     'あしたのかえぎでしりょうをくばります'):
            self.assertFalse(R.native_genitive_object_slots(text),text)

    def test_targets_reuse_anomaly_and_preserve_context(self):
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        text='へやのまとべをあけてくうきをいれかえます'
        targets=CR._unexplained_kana_request_targets(text,0,len(text),tokenize,a.store,a.dict_index)
        lexical=[t for t in targets if t.boundary_kind=='lexical']
        self.assertEqual([t.text for t in lexical],['まとべ'])
        self.assertEqual(lexical[0].context,text)
        self.assertTrue(lexical[0].anomalies)
        with patch('pos_grammar.odd_kana_spans',return_value=[]):
            self.assertEqual(CR._unexplained_kana_request_targets(
                text,0,len(text),tokenize,a.store,a.dict_index),[])
        normal=text.replace('まとべ','まど')
        self.assertFalse([t for t in CR._unexplained_kana_request_targets(
            normal,0,len(normal),tokenize,a.store,a.dict_index) if t.boundary_kind=='lexical'])

    def test_common_final_checks_the_first_predicate_and_wide_edits(self):
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        text='へやのまちどをあけてくうきをいれかえます'
        for start,end,surface in ((3,6,'まちかど'),(3,6,'街角'),
                                  (0,len(text),text.replace('まちど','まちかど'))):
            self.assertFalse(CR._changed_genitive_object_allowed(text,start,end,surface))
            value,why=C._check_replacement(text,(start,end,surface,'かな入力'),
                a.store,tokenize,a.dict_index,a.decisions)
            self.assertIsNone(value)
            self.assertEqual(why,'unproven_original_object_predicate')
        for surface in ('まど','窓'):
            self.assertTrue(CR._changed_genitive_object_allowed(text,3,6,surface))
        self.assertFalse(CR._changed_genitive_object_allowed(text,0,6,'やまの街角'))

    def test_repairs_share_native_noun_and_physical_evidence(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for broken,expected in (
                ('へやのまとべをあけてくうきをいれかえます。','へやのまどをあけてくうきをいれかえます。'),
                ('へやのまとづをあけます。','へやのまどをあけます。'),
                ('へやのまちどをあけます。','へやのまどをあけます。'),
                ('せんせいのしりょにうをよみます。','せんせいのしりょうをよみます。')):
            with self.subTest(text=broken):
                result=app.correct_line(broken,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                reading=''.join(t.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface)
                                else t.reading if t.has_reading else t.surface
                                for t in M.tokenize(result['corrected']))
                self.assertEqual(reading,expected)
                self.assertEqual(result.get('odd_spans'),[])

    def test_genitive_swallowed_by_irrealis_keeps_the_same_argument_gate(self):
        text='へやのまんどをあけてくうきをいれかえます'
        self.assertEqual(R.native_genitive_object_slots(text),((0,3,6,10),))
        self.assertFalse(CR._changed_genitive_object_allowed(text,3,6,'まんと'))
        self.assertTrue(CR._changed_genitive_object_allowed(text,3,6,'まど'))
        self.assertFalse(R.native_genitive_object_slots('ぷねらのまんどをあけます'))
        self.assertFalse(R.native_genitive_object_slots('へやのまんどをぷねら'))

    def test_native_dictionary_import_cannot_bypass_original_genitive(self):
        import app
        from tests_analysis_async import initial
        from janome_import import import_from_janome
        a=initial();import_from_janome(a.store)
        text='へやのまんどをあけてくうきをいれかえます。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=a.context_vec,decisions=a.decisions)
        reading=''.join(t.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface)
                        else t.reading if t.has_reading else t.surface for t in M.tokenize(result['corrected']))
        self.assertEqual(reading,'へやのまどをあけてくうきをいれかえます。')
        self.assertEqual(result.get('odd_spans'),[])
        for text in ('へやのまどをあけます。','へやのマントを見ます。','「へやのまんど」という誤入力例です。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=a.context_vec,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)

    def test_native_text_and_disallowed_deletions_stay(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        self.assertFalse(K.single_key_drop_adjacency('まほど','まど'))
        self.assertTrue(K.single_key_drop_is_duplicate('ままど','まど'))
        for text in ('へやのまどをあけます。','へやのとびらをあけます。',
                     'せんせいのしりょうをよみます。','せんせいの資料を読みます。',
                     'へやのまどをあけてくうきをいれかえます。',
                     'へやのまほどをあけます。','へやのままどをあけます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            if 'まほど' not in text and 'ままど' not in text:
                self.assertEqual(result.get('odd_spans'),[],text)


if __name__=='__main__':unittest.main()
