# -*- coding: utf-8 -*-
"""Keep the actual source relative clause and the role of its nominal head."""
from tests_spelling_reference import assert_reviewed_source_spelling
from tests_spelling_reference import assert_repaired_spelling
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

    def test_canonical_suru_action_keeps_its_literal_finite_suffix(self):
        for text,action,suffix in (
                ('しりょうをほぞんした','保存','ほぞんした'),
                ('しりょうをかくにんした','確認','かくにんした')):
            with self.subTest(text=text):
                self.assertEqual(R.completed_native_reading_clause(text,allow_nonpolite=True,
                    require_nominal=True,require_object_fit=True,return_action=True),action)
                self.assertEqual(R._native_completed_action_suffix(text,action),suffix)
                self.assertTrue(R.native_attributive_predicate_end(text))
        for text in ('しりょうをほぞんします','しりょうをほぞんして',
                     'しりょうをほぞんし','しりょうをほぞんしです'):
            self.assertFalse(R.native_attributive_predicate_end(text),text)
        self.assertFalse(R._native_completed_action_suffix('しりょうをほぞんした','保全'))
        self.assertFalse(R.native_adnominal_reading_parts('しりょうをほぞんしたほん',True))

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
            assert_reviewed_source_spelling(self,result['corrected'],text)
            self.assertEqual(result.get('odd_spans'),[],text)


    def test_original_relative_slot_reuses_the_shared_action(self):
        text='としょかんでかりたほなんをかえします'
        self.assertIn((0,9,12,18,('かりた',('で',))),R.native_modified_argument_slots(text))
        for text in ('ぷねらでかりたほなんをかえします',
                     'としょかんでかりますほなんをかえします'):
            self.assertFalse(R.native_modified_argument_slots(text),text)

    def test_same_nominal_context_proves_literal_and_written_heads(self):
        for text,end in (('としょかんでかりたほんをかえします',11),
                         ('としょかんでかりた本をかえします',10)):
            self.assertTrue(any(head==9 and case==end
                for begin,head,case,finish,faces in R.native_modified_nominal_contexts(text)))
        for text in ('としょかんでかりた平和をかえします',
                     'しりょうをよんだ本をかえします',
                     'としょかんでかりたほなんをかえします'):
            self.assertFalse(R.native_modified_nominal_contexts(text),text)

    def test_relative_target_does_not_invent_an_anomaly(self):
        from unittest.mock import patch
        import corrector as C
        import contextual_repair as CR
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        text='としょかんでかりたほなんをかえします'
        targets=CR._unexplained_kana_request_targets(text,0,len(text),tokenize,a.store,a.dict_index)
        self.assertIn('ほなん',[t.text for t in targets if t.boundary_kind=='lexical'])
        with patch('pos_grammar.odd_kana_spans',return_value=[]):
            self.assertFalse(CR._unexplained_kana_request_targets(
                text,0,len(text),tokenize,a.store,a.dict_index))

    def test_changed_noun_must_fit_both_original_predicates(self):
        import contextual_repair as CR
        text='としょかんでかりたほなんをかえします'
        for face in ('ほん','本'):
            self.assertTrue(CR._changed_genitive_object_allowed(text,9,12,face),face)
        self.assertFalse(CR._changed_genitive_object_allowed(text,9,12,'平和'))
        self.assertFalse(CR._changed_genitive_object_allowed(
            text,0,len(text),'みせでかったほんをかえします'))
        occupied='しりょうをよんだほなんをかえします';start=occupied.index('ほなん')
        self.assertFalse(CR._changed_genitive_object_allowed(occupied,start,start+3,'本'))

    def test_relative_head_repair_and_physical_counterexamples(self):
        import app
        import kana_layout as K
        from tests_analysis_async import initial
        a=initial()
        self.assertTrue(K.single_key_drop_adjacency('ほなん','ほん'))
        self.assertFalse(K.single_key_drop_adjacency('ほこん','ほん'))
        text='としょかんでかりたほなんをかえします。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        reading=''.join(t.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface)
                        else t.reading if t.has_reading else t.surface for t in M.tokenize(result['corrected']))
        self.assertEqual(reading,text.replace('ほなん','ほん'))
        self.assertEqual(result.get('odd_spans'),[])
        for text in ('としょかんでかりたほんんをかえします。',
                     'としょかんでかりたほこんをかえします。',
                     '「としょかんでかりたほなんをかえします」という誤入力例です。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self,result['corrected'],text)



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
            for head in ('ほん','本','ほなん'):
                text=prefix+head+'をかえします。'
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                output=result['corrected']
                if head=='ほなん':
                    reading=''.join(t.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface)
                                    else t.reading if t.has_reading else t.surface for t in M.tokenize(output))
                    self.assertEqual(reading,prefix+'ほんをかえします。',text)
                else:assert_reviewed_source_spelling(self, output, text)
                self.assertEqual(result.get('odd_spans'),[],text)
        for text in ('きのうとしょかんでかりたほんんをかえします。',
                     'ともだちからかりたほこんをかえします。',
                     '「ともだちからかりたほなんをかえします」という誤入力例です。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self,result['corrected'],text)


    def test_genitive_suffix_is_a_separate_known_head(self):
        self.assertEqual(R.native_genitive_nominal_splits('ほなんのぺーじ',True),
                         ((3,(),('ページ','頁')),))
        self.assertFalse(R.native_genitive_nominal_splits('ほなんのぺーじ'))
        for text in ('きもの','あけぼの','ほなんのぷねら','ほなんのこぎり'):
            self.assertFalse(R.native_genitive_nominal_splits(text,True),text)
        for noun in ('ほんのぺーじ','本のぺーじ'):
            self.assertTrue(R.native_relative_nominal_faces(noun,'かりた',('で',)),noun)
        for noun in ('へいわのぺーじ','平和のぺーじ','ほなんのぺーじ'):
            self.assertFalse(R.native_relative_nominal_faces(noun,'かりた',('で',)),noun)

    def test_genitive_target_reuses_only_the_original_noun_anomaly(self):
        from unittest.mock import patch
        import contextual_repair as CR
        import corrector as C
        from tests_analysis_async import initial
        a=initial();tokenize=C.make_tokenizer(a.store)
        text='としょかんでかりたほなんのぺーじをよみます'
        targets=CR._unexplained_kana_request_targets(text,0,len(text),tokenize,a.store,a.dict_index)
        lexical=[t for t in targets if t.boundary_kind=='lexical']
        self.assertEqual([t.text for t in lexical],['ほなん'])
        self.assertEqual(lexical[0].following,'のぺーじをよみます')
        with patch('pos_grammar.odd_kana_spans',return_value=[]):
            self.assertFalse(CR._unexplained_kana_request_targets(text,0,len(text),tokenize,a.store,a.dict_index))

    def test_common_final_retains_the_known_genitive_suffix(self):
        import contextual_repair as CR
        text='としょかんでかりたほなんのぺーじをよみます'
        for noun in ('本','ほん'):
            self.assertTrue(CR._changed_genitive_object_allowed(text,9,12,noun),noun)
            self.assertTrue(CR._changed_genitive_object_allowed(text,0,len(text),text.replace('ほなん',noun)),noun)
        for changed in (text.replace('ほなん','へいわ'),
                        text.replace('ほなんのぺーじ','ほんのもくじ'),
                        text.replace('ほなんのぺーじ','ほん'),
                        text.replace('としょかんでかりたほなん','みせでかったほん')):
            self.assertFalse(CR._changed_genitive_object_allowed(text,0,len(text),changed),changed)
        occupied='しりょうをよんだほなんのぺーじをよみます';start=occupied.index('ほなん')
        self.assertFalse(CR._changed_genitive_object_allowed(occupied,start,start+3,'本'))

    def test_repaired_genitive_is_stable_when_analyzed_again(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for prefix,tail in (('としょかんでかりた','よみます'),
                            ('きのうかりた','ひらきます'),
                            ('ともだちからかりた','よみます')):
            text=prefix+'ほなんのぺーじを'+tail+'。'
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_repaired_spelling(self, result, text.replace('ほなん','本'))
            self.assertEqual(result.get('odd_spans'),[],text)
            again=app.correct_line(result['corrected'],a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(again['corrected'],result['corrected'])
            self.assertEqual(again.get('odd_spans'),[],again['corrected'])

    def test_genitive_suffix_cannot_license_a_different_word(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        # A nonadjacent deletion cannot invent hon. Another physical edit
        # may yield a written report that fits both borrowing and pages.
        for noun,wanted,purple in (('ほこん','報告',False),('ほんん','ほんん',True)):
            text='ともだちからかりた'+noun+'のぺーじをよみます。'
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text.replace(noun,wanted))
            self.assertEqual(bool(result.get('odd_spans')),purple,text)
            self.assertNotIn('本のぺーじ',result['corrected'])

    def test_original_proof_does_not_cover_an_unexplained_tail(self):
        import pos_grammar as P
        from tests_analysis_async import initial
        a=initial()
        normal='としょかんでかりた本のぺーじをよみます'
        self.assertEqual(P.odd_kana_spans(normal,a.dict_index,a.store),[])
        for text in ('としょかんでかりた本のぺーじをぷねらします',
                     'としょかんでかりたほこんのぺーじをよみます'):
            self.assertTrue(P.odd_kana_spans(text,a.dict_index,a.store),text)


    def test_relative_subject_keeps_native_iru_without_a_bare_one_kana_word(self):
        import app,corrector
        from tests_analysis_async import initial
        a=initial()
        text='しりょうをかくにんしたひとがいます。'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        assert_reviewed_source_spelling(self, result['corrected'], text)
        self.assertEqual(result.get('odd_spans'),[])
        self.assertNotIn('い',corrector.BASIC_VERB_FORMS)
        self.assertFalse(R.completed_native_reading_clause('ほらい',require_object_fit=True))


    def test_bare_suru_relative_action_keeps_the_whole_following_noun(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        self.assertEqual(R.native_relative_action('ほぞんした'),('保存',()))
        self.assertTrue(R.native_adnominal_reading_parts('ほぞんしたがぞう',True))
        for text in ('ほぞんしたがくせい','しりょうをほぞんしたほん',
                     'ほぞんしてがぞう','ぷねらしたがぞう'):
            self.assertFalse(R.native_adnominal_reading_parts(text,True),text)
        source='ほぞんしたがぞうをかくにんしたます'
        self.assertIn((0,9,('画像',)),R.native_object_predicate_contexts(source))
        self.assertFalse(any(begin==6 for begin,cut,faces in R.native_object_predicate_contexts(source)))
        result=app.correct_line(source+'。',a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        assert_reviewed_source_spelling(self, result['corrected'], 'ほぞんしたがぞうを確認してます。')
        self.assertFalse(result.get('odd_spans'))
        for text in ('ほぞんしたがぞうをかくにんしました。','ほぞんしたほんをよみます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertFalse(result.get('odd_spans'))

    def test_occupied_object_retains_canonical_suru_event_for_relative_time(self):
        import reading_segments as R,semantic_roles as S
        for head,action in (('しりょうをほぞんした','保存'),('しりょうをかくにんした','確認')):
            with self.subTest(head=head):
                self.assertEqual(R.native_relative_action(head),(action,('を',)))
                self.assertTrue(S.relative_action_support('時間',action,('を',)))
                self.assertIn('時間',R.native_nominal_phrase_faces(head+'じかん'))
                self.assertFalse(S.relative_action_support('資料',action,('を',)))
                self.assertFalse(R.native_adnominal_reading_parts(head+'しりょう',True))
        for head in ('かんじゃをほぞんした','ぷねらをほぞんした','しりょうをほぞんします',
                     'しりょうをほぞんして'):
            self.assertFalse(R.native_relative_action(head),head)
        self.assertTrue(R.native_relative_action('ほんをよんだ'))
        self.assertTrue(R.native_relative_action('まどをしめた'))

    def test_relative_time_source_retains_text_and_clears_false_purple(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for source in ('しりょうをほぞんしたじかん','しりょうをほぞんしたじこく',
                       'しりょうをほぞんしたひづけ','しりょうをかくにんしたじかん',
                       'しりょうをほぞんしたじかんです。'):
            result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],source)
            self.assertFalse(result.get('odd_spans'),source)

    def test_one_kana_noun_head_requires_its_proved_modifier(self):
        import reading_segments as R,corrector as C,app
        from tests_analysis_async import initial
        a=initial()
        self.assertFalse(C.table_surfaces_for_reading('ひ',limit=12))
        for source in ('しりょうをほぞんしたひ','しりょうをかくにんしたひ','ほぞんしたひ',
                       'ほんをよんだひ','まどをしめたひ','よやくしたひ'):
            with self.subTest(source=source):
                self.assertIn('日',R.native_nominal_phrase_faces(source))
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                assert_reviewed_source_spelling(self, result['corrected'], source)
                self.assertFalse(result.get('odd_spans'),source)
        for source in ('ぷねらしたひ','しりょうをほぞんしてひ','しりょうをほぞんしますひ',
                       'しりょうをほぞんしたを','しりょうをほぞんしたに','かんじゃをほぞんしたひ'):
            self.assertFalse(R.native_adnominal_reading_parts(source,True),source)

    def test_adverbial_relative_clause_retains_predicate_and_occupied_case(self):
        import reading_segments as R,app
        from tests_analysis_async import initial
        a=initial()
        for source in ('きのうみたえ','きのうよんだほん','あしたよむほん',
                       'ゆっくりよんだほん','きのうほんをよんだひ',
                       'あしたしりょうをほぞんするじかん'):
            with self.subTest(source=source):
                self.assertTrue(R.native_adnominal_reading_parts(source,True),source)
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                assert_reviewed_source_spelling(self, result['corrected'], source)
                self.assertFalse(result.get('odd_spans'),source)
        self.assertIn('を',R.native_relative_action('きのうほんをよんだ')[1])
        for source in ('ぷねらみたえ','ほんよんだひ','きのうみてえ','きのうみますえ',
                       'きのうほんをたべたひ','きのうほんをよんだほん'):
            self.assertFalse(R.native_adnominal_reading_parts(source,True),source)

    def test_short_relative_head_keeps_its_actual_following_case_and_meaning(self):
        import app,contextual_repair as CR
        from tests_analysis_async import initial
        a=initial()
        for source in ('きのうみたえをほぞんします','みたえをほぞんします',
                       'みたえをうる','かいたえをみます'):
            with self.subTest(source=source):
                self.assertTrue(R.native_modified_nominal_contexts(source),source)
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                assert_reviewed_source_spelling(self, result['corrected'], source)
                self.assertFalse(result.get('odd_spans'),source)
        self.assertIn('絵',R.native_nominal_phrase_faces('みたえ'))
        for source in ('みますえをほぞんします','みてえをほぞんします',
                       'ぷねらえをほぞんします','みたえをたべます',
                       'ほんをよんだほんをほぞんします'):
            self.assertFalse(R.native_modified_nominal_contexts(source),source)
        source='きのうみたえをほぞんします'
        self.assertFalse(CR._changed_genitive_object_allowed(source,5,6,'平和'))

    def test_depiction_storage_does_not_borrow_the_depicted_subjects_role(self):
        for text in ('えをほぞんします','えをほかんします','えをかいます','えをうります',
                     'みたえをほぞんします','みたえをうります','いらすとをほぞんします'):
            self.assertTrue(R.completed_native_reading_clause(text,require_object_fit=True),text)
        for text in ('えをたべます','りんごのえをたべます','みたえをのみます'):
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)

if __name__=='__main__':unittest.main()
