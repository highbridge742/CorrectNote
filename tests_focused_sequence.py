# -*- coding: utf-8 -*-
"""Source focus links and actual auxiliary identity share native evidence."""
from tests_spelling_reference import assert_reviewed_source_spelling
import unittest
from dataclasses import replace
import morphology as M
import reading_segments as R
import contextual_repair as C

@unittest.skipUnless(M.dictionary_inflections('読む'),'requires native dictionary')
class FocusedSequenceTests(unittest.TestCase):
    def test_motion_does_not_borrow_the_first_actions_object(self):
        for source in ('荷物を置いて出かけます','荷物を置いて帰ります'):
            self.assertTrue(R.native_object_predicate_proof(source,3,('荷物',)),source)
        self.assertFalse(R.native_object_predicate_proof('荷物を起きて出かけます',3,('荷物',)))
        import semantic_roles as S
        self.assertFalse(S._motion_tail_cannot_take_object('渡ります','道'))
        self.assertFalse(S._motion_tail_cannot_take_object('渡る人に貸します','資料'))
        self.assertFalse(S._motion_tail_cannot_take_object('出かけま','荷物'))

    def test_auxiliary_proof_cannot_invent_relative_word_boundaries(self):
        self.assertFalse(R.native_relative_action('しや'))
        self.assertFalse(R.native_modified_argument_slots('しやしんをせんたくします'))
        self.assertEqual(R.native_modified_argument_slots('せんせいのしりょにうをよみます'),
                         ((0,5,10,15,None),))
        self.assertTrue(R.native_relative_action('よんだ'))
        self.assertFalse(R.native_source_finite_verb('につつかいます'))
        self.assertTrue(R.native_source_finite_verb('よみます'))

    def test_spelling_keeps_temporal_word_and_actual_topic(self):
        for old,new in (('きのう借りた本','機能借りた本'),
                        ('あしたは早く起きます','明日葉早く起きます')):
            self.assertFalse(M.preserves_native_adverbial_word(old,new),(old,new))
        for old,new in (('きのう借りた本','昨日借りた本'),
                        ('あしたは早く起きます','明日は早く起きます'),
                        ('けさは新聞を読みます','今朝は新聞を読みます')):
            self.assertTrue(M.preserves_native_adverbial_word(old,new),(old,new))

    def test_negative_auxiliary_does_not_become_an_unrelated_adjective(self):
        for old,new in (('してないようです','したないようです'),
                        ('読んでないようです','読んだないようです')):
            self.assertFalse(R.preserves_native_negative_auxiliary(old,new),(old,new))
        self.assertTrue(R.preserves_native_negative_auxiliary('ほんをよんでないようです','本を読んでないようです'))

    def test_whole_noun_reading_is_not_a_negative_auxiliary(self):
        for original,changed in (('しゃしんをとった','写真を撮った'),
                                 ('しないをふる','竹刀を振る')):
            with self.subTest(original=original):
                self.assertFalse(R.native_negative_auxiliary_chains(original))
                self.assertTrue(R.preserves_native_negative_auxiliary(original,changed))
        for original,changed in (('仕事をしない','仕事をする'),
                                 ('本を読まないで置く','本を読んで置く')):
            with self.subTest(original=original):
                self.assertFalse(R.preserves_native_negative_auxiliary(original,changed))

    def test_completed_focus_links_and_independent_clauses(self):
        for text in ('かいては','よんでは','かいても','ほんをよんでは'):
            with self.subTest(text=text):self.assertTrue(R.completed_native_reading_link(text))
        for text in ('かくては','よみでは','しらゆほては','ては','かいてはは'):
            with self.subTest(text=text):self.assertFalse(R.completed_native_reading_link(text))
        for text in ('かいてはけします','よんでもかきます','てがみをかいてはけします'):
            with self.subTest(text=text):self.assertTrue(R.completed_native_reading_sequence(text))
        for text in ('かいてはしらゆほます','かくてはけします','よみではかきます',
                     'かいてはけしますです','かいてはけしま'):
            with self.subTest(text=text):self.assertFalse(R.completed_native_reading_sequence(text))

    def test_linked_plain_final_uses_native_finite_tail_not_an_open_link(self):
        for text in ('かくにんした','はなした','かいた','けした'):
            self.assertTrue(R.completed_native_link_clause(text),text)
        for text in ('かくにんして','はなして','かいて','かくにんし',
                     'かくにんしたする','けしますです','ぷねらます'):
            self.assertFalse(R.completed_native_link_clause(text),text)
        for text in ('しりょうをよんでかくにんした','ゆうじんをしょうたいしてはなした',
                     'かいてはけした','よんでもかいた'):
            self.assertTrue(R.completed_native_reading_sequence(text),text)
        for text in ('しりょうをよんでかくにんして','かいてはけして',
                     'かくてはけした','しりょうをよんでかくにんしたする'):
            self.assertFalse(R.completed_native_reading_sequence(text),text)

    def test_sleep_wake_meaning_is_subject_evidence_only(self):
        import semantic_roles as S
        for surface,form,reading in (('寝','連用形','ね'),('眠り','連用形','ねむり'),
                                     ('起き','連用形','おき'),('目覚め','連用形','めざめ')):
            self.assertIn('person',S.native_verb_roles(surface,form,reading,subject=True))
            self.assertNotIn('person',S.native_verb_roles(surface,form,reading))
        self.assertIn('issue',S.SUBJECT_VERB_ROLES['起きる'])
        for text in ('ねました','ねむった','おきた','めざめました'):
            self.assertTrue(R.completed_native_link_clause(text),text)
        self.assertTrue(R.native_object_predicate_proof('資料を保存して寝ました',3,('資料',)))
        self.assertFalse(R.native_object_predicate_proof('資料を寝ました',3,('資料',)))
        for text in ('ねま','ねむりて','ぷねらました'):
            self.assertFalse(R.completed_native_link_clause(text),text)

    def test_actual_subject_fit_reaches_source_preservation(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text in ('かんじゃがねています。','びょうにんがねています。',
                     'けがにんがやすみます。','かんじゃがめざめた。','かんじゃがねま',
                     'てがみがあります。','こどもがいます。','はなみずがでます。'):
            result=app.correct_line(text,a.store,dict_index=a.dict_index,
                decisions=a.decisions,context_vec=None,input_method='kana')
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertFalse(result['odd_spans'],text)
        # An unfinished source can be retained without proving completion.
        self.assertFalse(R.completed_native_link_clause('ねま'))
        self.assertTrue(R.completed_native_reading_clause('かんじゃがねています',
            require_nominal=True,require_object_fit=True))

    def test_classified_subject_addition_keeps_existing_basic_predicates(self):
        for text in ('しりょうがあります','かんじゃがねています'):
            self.assertTrue(R.completed_native_reading_clause(text,require_object_fit=True),text)
        for text in ('しりょうがありた','しりょうがありますかん'):
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)
        parts=M.tokenize('がありました')
        legacy=[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                 t.start,t.end,t.has_reading,t.infl_form) for t in parts]
        # The classified existence subject now has positive native evidence.
        self.assertTrue(R._native_nominal_functional_tail(legacy,
            content_subject_faces=('資料',),source_prefix='資料'))
        self.assertTrue(R._native_nominal_functional_tail(legacy,
            content_subject_faces=('資料',),source_prefix='資料',strict_subject_fit=False))

    def test_actual_auxiliary_does_not_borrow_homographic_verb(self):
        import oddness
        def legacy(t):
            return (t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),
                    t.reading,t.start,t.end,t.has_reading,t.infl_form)
        parts=M.tokenize('かいて吐けなします')
        self.assertTrue(oddness.polite_aux_mismatch(legacy(parts[-2]),legacy(parts[-1])))
        self.assertFalse(C._productive_predicate('吐けなします','吐け',before='かいて'))
        for text in ('読み続けます','寝させます','読まれます','読みます','なくします'):
            with self.subTest(text=text):
                head=M.tokenize(text)[0]
                self.assertTrue(C._productive_predicate(text,head.surface))

    def test_verb_type_auxiliary_keeps_its_native_continuative_form(self):
        import oddness
        def legacy(t):
            return (t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),
                    t.reading,t.start,t.end,t.has_reading,t.infl_form)
        for text in ('ございません','ございませんでした','であります','ではありません'):
            parts=M.tokenize(text)
            for left,right in zip(parts,parts[1:]):
                with self.subTest(text=text,left=left.surface):
                    self.assertFalse(oddness.polite_aux_mismatch(legacy(left),legacy(right)))
        # A different verb sharing the spelling must still not license these.
        for text in ('かいて吐けなします','ござるます','書きまします','書きでします'):
            parts=M.tokenize(text)
            with self.subTest(text=text):
                self.assertTrue(any(oddness.polite_aux_mismatch(legacy(a),legacy(b))
                                    for a,b in zip(parts,parts[1:])))

    def test_source_keeps_focus_and_rejects_ungrammatical_generated_spelling(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text in ('かいてはけします。','よんでもかきます。','かいてはみます。',
                     'よんでもらいます。','ございません。','ございませんでした。',
                     'であります。','ではありません。'):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                expected='かいては消します。' if text=='かいてはけします。' else text
                self.assertEqual(r['corrected'],expected);self.assertEqual(r['odd_spans'],[])
        # Existing incomplete lexical coverage may still mark 手筈; the
        # connective rule must not alter that whole lexical spelling.
        text='てはずをかくにんします。'
        r=app.correct_line(text,a.store,dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None,input_method='kana')
        self.assertEqual(r['corrected'],text)
        text='かいてはけしなます。'
        r=app.correct_line(text,a.store,dict_index=a.dict_index,
            decisions=a.decisions,context_vec=None,input_method='kana')
        # AHR supplies the original focus edge; AHH's incomplete hold is superseded.
        self.assertIn(r['corrected'],('かいては消します。','書いては消します。'))
        self.assertEqual(r['odd_spans'],[])


    def test_native_focus_edges_require_actual_euphony(self):
        for text,edge in (('かいてはけしなます',4),('読んでも書きなます',4),
                           ('書いては消しなます',4)):
            with self.subTest(text=text):self.assertIn(edge,C._native_focused_te_edges(text))
        for text in ('読むてもかきます','よみではかきます','泳いてはけします','ぬぉてはけします'):
            with self.subTest(text=text):self.assertEqual(C._native_focused_te_edges(text),())

    def test_swallowed_focus_keeps_original_anomaly_and_wide_interpretation(self):
        text='かいてはけしなます'
        target=C.RepairTarget(text,3,7,0,len(text),(('しな','ます',5,9),),True,text[7:])
        targets=C._native_focused_prefix_targets([target])
        self.assertIn(target,targets)
        narrow=next(t for t in targets if t.start==4)
        self.assertEqual(narrow.text,'けしな')
        self.assertEqual(narrow.anomalies,target.anomalies)
        self.assertEqual(narrow.context,target.context)
        self.assertEqual(C._native_focused_prefix_targets(targets),targets)
        for blocked in (replace(target,anomalies=(('は','け',3,5),)),
                        replace(target,preserved_head='はけ'),replace(target,spelling=('source-fact',)),
                        replace(target,boundary_kind='kana_request')):
            with self.subTest(target=blocked):
                self.assertEqual(C._native_focused_prefix_targets([blocked]),[blocked])

    def test_complete_words_after_connective_keep_their_original_text(self):
        import app
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        for text in ('描いたらハケを洗って','読んでものを考えます。',
                     'よんでものをかんがえます。','はしってはころびます。',
                     '食べても空腹です。','あそんでもねむくありません。'):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,dict_index=a.dict_index,
                    decisions=a.decisions,context_vec=None,input_method='kana')
                assert_reviewed_source_spelling(self, r['corrected'], text)
                self.assertEqual(r['odd_spans'],[])

    def test_waiting_state_keeps_native_host_while_its_copula_changes(self):
        import reading_segments as R
        for old,new in (('しょうにんまちでうす','承認待ちです'),
                        ('にゅうりょくまちでしあた','入力まちでした')):
            self.assertTrue(R.preserves_native_waiting_source(old,new),(old,new))
        for old,new in (('しょうにんまちでうす','承認までうす'),
                        ('にゅうりょくまちでうす','入力までうす')):
            self.assertFalse(R.preserves_native_waiting_source(old,new),(old,new))
        self.assertTrue(R.preserves_native_waiting_source('ぷねらまちでうす','ぷねらまでうす'))

    def test_illness_transmission_does_not_inherit_all_healable_conditions(self):
        import semantic_roles as S
        self.assertTrue(S.support('病気','移す'))
        self.assertTrue(S.support('風邪','移す'))
        self.assertTrue(S.case_action_support('人','に','移す'))
        self.assertFalse(S.support('怪我','移す'))
        self.assertFalse(S.support('骨折','移す'))

    def test_longer_original_action_owns_internal_temporal_parse(self):
        self.assertTrue(M.preserves_native_adverbial_word('きょうゆうします','共有します'))
        self.assertFalse(M.preserves_native_adverbial_word('きょうは休みです','京は休みです'))
        self.assertFalse(M.preserves_native_adverbial_word('きのう資料を借りた','機能資料を借りた'))

    def test_actual_input_instrument_has_its_own_case(self):
        import semantic_roles as S
        self.assertTrue(S.nominal_role_matches('キーボード',S.CASE_VERB_ROLES['で']['打つ']))
        self.assertTrue(S.nominal_role_matches('キー',S.CASE_VERB_ROLES['で']['入力']))
        self.assertFalse(S.nominal_role_matches('水',S.CASE_VERB_ROLES['で']['打つ']))
        self.assertTrue(R.native_object_predicate_proof('キーボードで文字を打ちます',9,('文字',)))

    def test_spelling_cannot_turn_a_bound_verb_into_a_noun(self):
        from ime_spelling import _reinterprets_function_attachment
        self.assertTrue(_reinterprets_function_attachment('よんで知識を得ます',0,2,'四'))
        self.assertFalse(_reinterprets_function_attachment('よんで知識を得ます',0,2,'読ん'))
        self.assertFalse(_reinterprets_function_attachment('かみを切ります',0,2,'紙'))

    def test_independent_malformed_clauses_keep_their_own_object_proof(self):
        import app,corrector as E
        from tests_analysis_async import initial
        a=initial()
        source='予定を聞く人して画素背うを保存します。'
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                decisions=a.decisions,context_vec=None)
        self.assertEqual(result['corrected'],'予定を確認して画像を保存します。')
        self.assertFalse(result['odd_spans'])
        self.assertEqual(result['analysis_status'],'complete')
        for following,allowed in (('保存します。',True),('飲みます。',False)):
            line='予定を聞く人して画素背うを'+following
            checked,reason=E._check_replacement(line,(8,12,'画像','かな入力'),
                a.store,E.make_tokenizer(a.store),a.dict_index,a.decisions)
            self.assertEqual(checked is not None,allowed,reason)

    def test_unedited_negative_chain_survives_a_separate_repair(self):
        source='とうろくしたたんごをいちらんあ゛かくにんできます'
        self.assertTrue(R.preserves_native_negative_auxiliary(source,
            'とうろくしたたんごをいちらんでかくにんできます'))
        self.assertFalse(R.preserves_native_negative_auxiliary('資料を読まないで置きます',
            '資料を読んで置きます'))


    def test_broken_small_kana_head_is_not_an_intact_written_verb(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for source,expected in (('この道具をっ買いました。','この道具を使いました。'),
                                ('あっ買いました。','あっ買いました。'),
                                ('昨日買いました。','昨日買いました。')):
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,input_method='kana',
                    dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])

    def test_original_case_boundary_survives_unknown_whole_line_parse(self):
        import pos_grammar as P,corrector as E
        from tests_analysis_async import initial
        a=initial();tokenize=E.make_tokenizer(a.store)
        source='かいてじょうほうをほぞかします'
        self.assertTrue(list(P._orphaned_particle_before_sahen_action_windows(tokenize(source),source)))
        for source in ('資料を何かします。','柱をほぞにします。','家を購入か賃貸します。','本を読むかします。'):
            self.assertFalse(list(P._orphaned_particle_before_sahen_action_windows(tokenize(source),source)),source)

if __name__=='__main__':unittest.main()

