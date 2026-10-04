# -*- coding: utf-8 -*-
"""The existing source noun head constrains an anomalous compound repair."""
import unittest,os
from unittest.mock import patch
import contextual_repair as C
import reading_segments as R
import kana_layout as K

class NominalFieldRepairTests(unittest.TestCase):
    def test_voicing_omission_is_one_added_physical_mark(self):
        rows=[r for r in C.key_repairs('かんし') if r.operation=='omission']
        self.assertIn('がんし',[r.reading for r in rows])
        self.assertIn('かんじ',[r.reading for r in rows])
        for row in rows:
            self.assertEqual(row.pressed,'')
            self.assertIn(row.intended,'゛゜')
            self.assertEqual(sum(len(K.keystrokes(c)) for c in row.reading),4)
            self.assertEqual(row.cost,K.MISSING_KEY_COST)
        with patch.dict(os.environ,{'CN_MARK_SLIP':'0'}):
            self.assertFalse(any(r.operation=='omission' for r in C.key_repairs('かんし')))
    def test_native_head_and_reading_must_both_survive(self):
        heads=R.native_nominal_tail_heads('れんらくしりょう')
        self.assertIn('連絡資料',R.native_nominal_tail_spellings('れんらくしりょう',heads))
        self.assertEqual(R.native_nominal_tail_spellings('れんらくじりょう',heads),())
        self.assertEqual(R.native_nominal_tail_spellings('ぷねらしりょう',heads),())
    def test_original_known_nominal_compound_has_no_extra_repair_scope(self):
        from tests_analysis_async import initial
        from corrector import make_tokenizer
        a=initial()
        rows=C.targets_for_line('れんらくしりょう\t',make_tokenizer(a.store),a.store,a.dict_index)
        self.assertFalse(any(t.boundary_kind=='nominal_field' for t in rows))

    def test_native_action_document_spelling_retains_whole_topic_boundary(self):
        from tests_analysis_async import initial
        from kana_spelling import project
        a=initial()
        for reading,face in (('てんぷがぞうは','添付画像は'),
                ('てんぷしりょうは','添付資料は'),('ほぞんがぞうは','保存画像は')):
            result=project(reading,a.store,a.dict_index,a.decisions)
            self.assertIsNotNone(result,reading)
            self.assertEqual(result[0],face)
        self.assertFalse(R.native_nominal_spelling_faces('ぷねらがぞう'))

    def test_closed_subject_topic_preserves_native_clauses_and_literal_input(self):
        from pos_grammar import closed_subject_topic_spans
        from tests_analysis_async import initial
        import app
        a=initial()
        for source in ('添付が砂像は','てんぷがぞうは'):
            result=app.correct_line(source+'\t',a.store,input_method='kana',
                dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(result['corrected'],'添付画像は\t',source)
            self.assertFalse(result['odd_spans'])
            self.assertEqual(result['analysis_status'],'complete')
        for source in ('添付画像は\t','てんぷがぞうは\t','添付が写真を含みます。\t',
                '私が本は読みます。\t','画像が好きな人は\t','画像がある資料は\t',
                '添付が砂像は','「添付が砂像は」と入力しました。\t'):
            self.assertFalse(closed_subject_topic_spans(source),source)

    def test_ime_word_alignment_prefers_native_homophone_in_its_own_scope(self):
        from tests_analysis_async import initial
        from kana_spelling import project
        from unittest.mock import MagicMock
        a=initial()
        cases=(
            ('こくごじてんをよみます。','国語辞典を読みます。',
             ((0,2,0,3,0,0),(2,4,3,6,0,0),(4,5,6,7,0,0),
              (5,7,7,9,0,0),(7,9,9,11,0,0),(9,10,11,12,0,0))),
            ('てんぷしりょうとこくごじてんは','添付資料と国語辞典は',
             ((0,2,0,3,0,0),(2,4,3,7,0,0),(4,5,7,8,0,0),
              (5,7,8,11,0,0),(7,9,11,14,0,0),(9,10,14,15,0,0))))
        for reading,face,words in cases:
            with self.subTest(reading=reading):
                ime=MagicMock();ime.available=True;ime.convert_words.return_value=(face,words)
                ime.__enter__.return_value=ime
                with patch('ime_language.JapaneseIME',return_value=ime):
                    unresolved=project(reading,a.store,a.dict_index,a.decisions)
                    if unresolved:
                        self.assertNotIn('辞典',unresolved[0])
                        self.assertNotIn('事典',unresolved[0])
                    # First IME choice alone is not a semantic preference.
                    # An explicit user spelling choice resolves that ambiguity.
                    with patch('last_choice.surface_for_reading',side_effect=lambda rd:
                            '国語辞典' if rd=='こくごじてん' else None):
                        result=project(reading,a.store,a.dict_index,a.decisions)
                self.assertIsNotNone(result,reading)
                self.assertEqual(result[0],face)

class WrittenRelativeTests(unittest.TestCase):
    def test_preserves_actual_native_predicate_and_occupied_cases(self):
        for source,action,cases in (('資料を保存した','保存',('を',)),('人が読んだ','読んだ',('が',)),('画像がある','ある',('が',))):
            with self.subTest(source=source):self.assertEqual(R.native_written_relative_action(source),(action,cases))
    def test_missing_arguments_can_be_a_source_noun_head(self):
        for source,head in (('本を読んだ人','人'),('資料を保存した箱','箱'),('画像がある資料','資料'),('人がいる部屋','部屋'),('資料が届いた日','日')):
            with self.subTest(source=source):self.assertEqual(R.native_surface_nominal_heads(source),(head,))
    def test_source_topic_uses_same_whole_nominal_proof(self):
        legacy=lambda source:[(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,t.start,t.end,t.has_reading,t.infl_form) for t in __import__('morphology').tokenize(source)]
        for source in ('画像がある資料は','本を読む人は','資料を保存した箱は'):
            with self.subTest(source=source):self.assertTrue(R.native_lexical_phrase(source,legacy))
    def test_unknown_and_malformed_predicates_do_not_supply_proof(self):
        for source in ('保存したぷねら','資料を保存します画像','資料を保存したます画像','画像がます資料','人が読んだます本'):
            with self.subTest(source=source):self.assertFalse(R.native_written_relative_nominal_heads(source))
    def test_occupied_object_cannot_be_reused_as_the_relative_head(self):
        for source in ('資料を保存した画像','画像を食べた本','本を嗅いだ人'):
            with self.subTest(source=source):self.assertFalse(R.native_written_relative_nominal_heads(source))
    def test_locative_head_does_not_override_its_occupied_case(self):
        S=__import__('semantic_roles')
        self.assertFalse(S.relative_action_support('箱','保存',('を',)))
        self.assertTrue(S.relative_action_support('箱','保存',('を',),source_head=True))
        self.assertFalse(S.relative_action_support('箱','保存',('を','に'),source_head=True))
        self.assertFalse(S.relative_action_support('画像','保存',('を',),source_head=True))
    def test_preference_relative_retains_native_experiencer_and_target(self):
        for source,head in (('画像が好きな人','人'),('本が嫌いな先生','先生'),('先生が好きな本','本')):
            with self.subTest(source=source):self.assertEqual(R.native_surface_nominal_heads(source),(head,))
        for source in ('画像が好きな本','画像を好きな人','画像が好きだ人','画像が好きなぷねら'):
            with self.subTest(source=source):self.assertFalse(R.native_written_relative_nominal_heads(source))

class SourceRelativeNegativeTests(unittest.TestCase):
    def test_malformed_negative_cannot_borrow_a_locative_homophone(self):
        import app
        from tests_analysis_async import initial
        for source in ('がぞうをほぞんしたない',):
            a=initial()
            r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],source)
            self.assertTrue(r['odd_spans'])
            self.assertEqual(r['analysis_status'],'complete')
        self.assertFalse(R.native_nominal_phrase_faces('がぞうをほぞんしたない'))
        # Written したない lacks a new relative proof; its pre-existing
        # whole-app missing purple is tracked separately from this regression.
        self.assertFalse(R.native_written_relative_nominal_heads('資料を保存したない'))
        self.assertEqual(R.native_written_relative_nominal_heads('資料を保存した箱'),('箱',))

class WrittenSahenObjectTests(unittest.TestCase):
    def test_actual_native_suru_and_finite_tail_attest_only_the_source_slot(self):
        for source in ('しりゃうを保存します','しりゃうを保存した','しりゃうを登録しました',
                       'しりゃうを保存しません','しりゃうを保存してください'):
            with self.subTest(source=source):self.assertIn((5,(0,)),C._original_counted_object_slots(source,True))
        for source in ('しりゃうを保存したます','しりゃうを保存資料','しりゃうをぷねらします','しりゃうを保存'):
            with self.subTest(source=source):self.assertFalse(C._original_counted_object_slots(source,True))

    def test_same_written_predicate_constrains_the_repaired_object_meaning(self):
        self.assertTrue(C._changed_object_slot_allowed('しりゃうを保存します',0,4,'資料',True))
        self.assertFalse(C._changed_object_slot_allowed('しりゃうを食べます',0,4,'資料',True))
        self.assertFalse(C._changed_object_slot_allowed('しりゃうを飛びます',0,4,'資料',True))
        self.assertFalse(C._changed_object_slot_allowed('しりゃうを保存したます',0,4,'資料',True))

    def test_original_key_and_native_context_repair_without_a_word_answer_table(self):
        import app
        from tests_analysis_async import initial
        for source,expected in (('がぞせうを保存します。','画像を保存します。'),
                                ('しりゃうを保存します。','資料を保存します。'),
                                ('しりゃうを登録します。','資料を登録します。')):
            a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],expected);self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')

    def test_whole_native_words_unknown_input_and_quotation_do_not_gain_a_target(self):
        import corrector as E
        from tests_analysis_async import initial
        a=initial();tok=E.make_tokenizer(a.store)
        for source in ('画像を保存します。','ぷねらを保存します。','「がぞせう」を保存します。'):
            rows=C.targets_for_line(source,tok,a.store,a.dict_index)
            self.assertFalse(any(t.boundary_kind=='nominal_object' for t in rows),source)

class OriginalObjectPredicateSpellingTests(unittest.TestCase):
    def test_native_object_has_whole_source_heads(self):
        import contextual_repair as C
        for source,start,end in (('あしたまでにぶんしょうをなおしまぇ',12,17),('ぶんしょうをなおすします',6,12)):
            with self.subTest(source=source):
                frame=C._source_object_predicate_frame(source,start,end)
                self.assertIsNotNone(frame);self.assertIn('文章',frame[-1])
    def test_shift_and_real_adjacent_intrusion_share_the_original_object(self):
        import app
        from tests_analysis_async import initial
        for source in ('あしたまでにぶんしょうをなおしまぇ。','あしたまでにぶんしょうをなおすします。'):
            with self.subTest(source=source):
                a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],'あしたまでに文章を直します。')
                self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')
    def test_normal_predicate_and_literal_input_are_preserved(self):
        import app
        from tests_analysis_async import initial
        for source in ('文章を直します。','「ぶんしょうをなおすします」は入力例です。'):
            a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],source);self.assertFalse(r['odd_spans'])
            self.assertEqual(r['analysis_status'],'complete')
    def test_a_completed_earlier_clause_cannot_lend_its_object(self):
        import contextual_repair as C
        source='本を読んで笑います。';start=source.index('笑')
        self.assertIsNone(C._source_object_predicate_frame(source,start,len(source)-1))

if __name__=='__main__':unittest.main()


import semantic_roles as S


class MixedNominalSourceTests(unittest.TestCase):
    def test_actual_halves_share_only_their_proved_compound_relation(self):
        for source,head in (('国語じてん','辞典'),('英語じてん','辞典'),
                ('平仮名にゅうりょく','入力'),('資料ほぞん','保存'),
                ('こくご辞典','辞典'),('かたかな入力','入力')):
            with self.subTest(source=source):self.assertIn(head,R.native_mixed_nominal_heads(source))
        self.assertEqual(R.native_mixed_nominal_heads('こくご辞典'),('辞典',))

    def test_written_homophones_unknown_halves_and_native_words_are_not_reopened(self):
        for source in ('幹事じてん','飢餓じてん','国語ぷねら','ぷねら辞典',
                       '平仮名にゅうりょくく','平仮名入力','国語辞典','登録して','保存し'):
            with self.subTest(source=source):self.assertFalse(R.native_mixed_nominal_heads(source))
        self.assertEqual(R._native_written_nominal_faces('幹事'),('幹事',))
        self.assertFalse(S.nominal_compound_support('幹事','辞典'))

    def test_actual_mixed_argument_can_validate_its_repaired_finite_predicate(self):
        import app
        from tests_analysis_async import initial
        for source,expected in (('国語じてんをよみますた。','国語じてんを読みました。'),
                                ('資料ほぞんをためしますた。','資料ほぞんを試しました。')):
            with self.subTest(source=source):
                a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],expected)
                self.assertFalse(r['odd_spans']);self.assertEqual(r['analysis_status'],'complete')

    def test_nominal_proof_does_not_certify_an_unresolved_predicate_or_change_a_quote(self):
        import app
        from tests_analysis_async import initial
        for source in ('平仮名にゅうりょくをためしませた。','国語ぷねらをよみます。'):
            a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],source);self.assertTrue(r['odd_spans'])
        # Existing historical-auxiliary source proof is checked separately
        # from invalid finite tails; it must not be mislabeled as a typo.
        for source in ('資料ほぞんをためしまうす。','「国語じてんをよみますた」は入力例です。'):
            a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
            self.assertEqual(r['corrected'],source);self.assertFalse(r['odd_spans'])
