# -*- coding: utf-8 -*-
"""Keep the actual source relative clause and the role of its nominal head."""
import unittest
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('借りる'),'requires native dictionary')
class NativeRelativeRepairTests(unittest.TestCase):
    def test_location_is_not_the_lender_or_the_content(self):
        self.assertTrue(S.case_action_support('図書館','で','借りる'))
        self.assertTrue(S.case_action_support('店','で','買う'))
        self.assertTrue(S.case_action_support('先生','から','借りる'))
        self.assertFalse(S.case_action_support('本','で','借りる'))
        self.assertFalse(S.case_action_support('図書館','から','借りる'))

    def test_unknown_best_parse_uses_a_proved_finite_source_clause(self):
        self.assertTrue(R.native_attributive_predicate_end('としょかんでかりた'))
        self.assertTrue(R.native_attributive_predicate_end('みせでかった'))
        for text in ('としょかんでかります','としょかんでかり','ぷねらでかりた',
                     'としょかんでかりたほん','かきけり'):
            self.assertFalse(R.native_attributive_predicate_end(text),text)
        for text in ('としょかんでかりたほん','みせでかったやさい'):
            self.assertTrue(R.native_adnominal_reading_parts(text,True),text)

    def test_swallowed_explicit_object_does_not_become_an_empty_relative_slot(self):
        self.assertTrue(R.completed_native_reading_clause('しりょうをよんだ',
            allow_nonpolite=True,require_object_fit=True))
        self.assertFalse(R.native_adnominal_reading_parts('しりょうをよんだほん',True))

    def test_normal_relative_reading_keeps_text_and_purple(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('としょかんでかりたほんをかえします。',
                     'みせでかったやさいをあらいます。','図書館で借りた本を返します。',
                     'としょかんでかりた本をかえします。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)
            self.assertEqual(result.get('odd_spans'),[],text)


    def test_original_relative_slot_reuses_the_shared_action(self):
        text='としょかんでかりたほきんをかえします'
        self.assertIn((0,9,12,18,('かりた',('で',))),R.native_modified_argument_slots(text))
        for text in ('ぷねらでかりたほきんをかえします',
                     'としょかんでかりますほきんをかえします'):
            self.assertFalse(R.native_modified_argument_slots(text),text)

    def test_same_nominal_context_proves_literal_and_written_heads(self):
        for text,end in (('としょかんでかりたほんをかえします',11),
                         ('としょかんでかりた本をかえします',10)):
            self.assertTrue(any(head==9 and case==end
                for begin,head,case,finish,faces in R.native_modified_nominal_contexts(text)))
        for text in ('としょかんでかりた平和をかえします',
                     'しりょうをよんだ本をかえします',
                     'としょかんでかりたほきんをかえします'):
            self.assertFalse(R.native_modified_nominal_contexts(text),text)

    def test_relative_target_does_not_invent_an_anomaly(self):
        from unittest.mock import patch
        import corrector as C
        import contextual_repair as CR
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        text='としょかんでかりたほきんをかえします'
        targets=CR._unexplained_kana_request_targets(text,0,len(text),tokenize,a.store,a.dict_index)
        self.assertIn('ほきん',[t.text for t in targets if t.boundary_kind=='lexical'])
        with patch('pos_grammar.odd_kana_spans',return_value=[]):
            self.assertFalse(CR._unexplained_kana_request_targets(
                text,0,len(text),tokenize,a.store,a.dict_index))

    def test_changed_noun_must_fit_both_original_predicates(self):
        import contextual_repair as CR
        text='としょかんでかりたほきんをかえします'
        for face in ('ほん','本'):
            self.assertTrue(CR._changed_genitive_object_allowed(text,9,12,face),face)
        self.assertFalse(CR._changed_genitive_object_allowed(text,9,12,'平和'))
        self.assertFalse(CR._changed_genitive_object_allowed(
            text,0,len(text),'みせでかったほんをかえします'))
        occupied='しりょうをよんだほきんをかえします';start=occupied.index('ほきん')
        self.assertFalse(CR._changed_genitive_object_allowed(occupied,start,start+3,'本'))

    def test_relative_head_repair_and_physical_counterexamples(self):
        import app
        import kana_layout as K
        from tests_analysis_async import initial
        a=initial()
        self.assertTrue(K.single_key_drop_adjacency('ほきん','ほん'))
        self.assertFalse(K.single_key_drop_adjacency('ほこん','ほん'))
        text='としょかんでかりたほきんをかえします。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        reading=''.join(t.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface)
                        else t.reading if t.has_reading else t.surface for t in M.tokenize(result['corrected']))
        self.assertEqual(reading,text.replace('ほきん','ほん'))
        self.assertEqual(result.get('odd_spans'),[])
        for text in ('としょかんでかりたほんんをかえします。',
                     'としょかんでかりたほこんをかえします。',
                     '「としょかんでかりたほきんをかえします」という誤入力例です。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)



    def test_multi_character_case_uses_the_same_native_boundary(self):
        text='ともだちからかりた'
        self.assertEqual(R.native_case_positions(text,particles=('から',)),(4,))
        self.assertEqual(R.native_relative_action(text),('かりた',('から',)))
        self.assertEqual(R.native_relative_action('えきまえのみせでかった'),('かった',('で',)))
        for text in ('からいやさい','からかわれた','かりたからかえす'):
            self.assertFalse(R.native_case_positions(text,particles=('から',)),text)
        for text in ('ぷねらからかりた','ほんからかりた','ともだちからかり',
                     'ともだちからかります'):
            self.assertFalse(R.native_relative_action(text),text)
        self.assertFalse(R.native_adnominal_reading_parts('しりょうをともだちからかりたほん',True))

    def test_native_adverb_and_genitive_place_do_not_hide_the_head(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for prefix in ('きのうとしょかんでかりた','ともだちからかりた',
                       'きのうともだちからかりた','えきまえのみせでかった'):
            for head in ('ほん','本','ほきん'):
                text=prefix+head+'をかえします。'
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                output=result['corrected']
                if head=='ほきん':
                    reading=''.join(t.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface)
                                    else t.reading if t.has_reading else t.surface for t in M.tokenize(output))
                    self.assertEqual(reading,prefix+'ほんをかえします。',text)
                else:self.assertEqual(output,text)
                self.assertEqual(result.get('odd_spans'),[],text)
        for text in ('きのうとしょかんでかりたほんんをかえします。',
                     'ともだちからかりたほこんをかえします。',
                     '「ともだちからかりたほきんをかえします」という誤入力例です。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text)


if __name__=='__main__':unittest.main()
