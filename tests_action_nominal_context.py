# -*- coding: utf-8 -*-
"""Native action nouns, exact kana compounds and closed object meaning."""
from tests_spelling_reference import assert_repaired_spelling,assert_preserved_source_spelling
import unittest
from unittest.mock import patch
import morphology as M
import reading_segments as R
import semantic_roles as S


@unittest.skipUnless(M.dictionary_inflections('する'), 'requires native dictionary')
class ActionNominalContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.a=initial();cls.a.context_vec=None

    def correct(self,text,decisions=None):
        import app
        return app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
            context_vec=None,decisions=decisions or self.a.decisions,input_method='kana')

    def legacy(self,text):
        return [(t.surface,t.pos+(':'+t.pos_sub if t.pos_sub else ''),t.reading,
                 t.start,t.end,t.has_reading,t.infl_form) for t in M.tokenize(text)]

    def test_written_action_needs_its_own_spelling_before_reading_projection(self):
        source='大切な結果を機録します'
        frames=R.native_object_predicate_contexts(source,allow_written_predicate=True)
        self.assertTrue(frames)
        for begin,cut,faces in frames:
            self.assertFalse(R.native_object_predicate_proof(source[begin:],cut-begin,faces))
        self.assertNotIn((0,len(source)),R.native_context_ranges(source))
        fixed=self.correct(source+'。')
        self.assertEqual(fixed['corrected'],'大切な結果を記録します。')
        self.assertFalse(fixed['odd_spans'])
        self.assertEqual(fixed['analysis_status'],'complete')
        for text in ('資料を記録します。','資料を再記録します。','データを画像処理します。',
                     '資料を電子化します。','問題を具体化します。','旅行の日程を田中と相談しました。'):
            with self.subTest(text=text):
                result=self.correct(text)
                self.assertEqual(result['corrected'],text)
                self.assertFalse(result['odd_spans'])

    def test_native_action_noun_keeps_argument_roles_and_process_use(self):
        for word in ('入力','作成','検索','文字入力','資料作成','平仮名入力'):
            with self.subTest(word=word):self.assertIn('process',S.nominal_roles(word))
        self.assertTrue(S.support('情報','検索'))
        self.assertTrue(S.support('資料','作成'))
        self.assertFalse(S.support('情報','食事'))
        for word in ('情報食事','未知入力','猫入力','入力者','入力太郎'):
            with self.subTest(word=word):self.assertNotIn('process',S.nominal_roles(word))

    def test_reading_compounds_need_both_native_nouns_and_semantic_connection(self):
        for text in ('じょうほうけんさく','しりょうさくせい','ひらがなにゅうりょく'):
            with self.subTest(text=text):self.assertTrue(R.native_relational_compound_heads(text))
        for text in ('じょうほうしょくじ','ひらがなりょく','ひらがにゅうりょく',
                     'ねこにゅうりょく','みちなにゅうりょく'):
            with self.subTest(text=text):self.assertFalse(R.native_relational_compound_heads(text))
        for text in ('きょじんかくにん','じょうほうけんさくをためします。','ひらがなにゅうりょくをためします。',
                     'しりょうさくせいをためします。','もじにゅうりょくをためします。'):
            with self.subTest(text=text):
                r=self.correct(text)
                assert_preserved_source_spelling(self,r,text)
                self.assertEqual(r['odd_spans'],[])

    def test_attested_compound_identity_is_shared_with_source_preservation(self):
        for word in ('こくごじてん','でんしじしょ','らんちょんまっと'):
            self.assertTrue(R.native_relational_compound_heads(word),word)
        for text in ('こくごじてんをよみます。','でんしじしょをかいます。',
                     'まちあわせをかくにんします。','らんちょんまっとをかいます。'):
            result=self.correct(text)
            assert_preserved_source_spelling(self,result,text)
            self.assertFalse(result['odd_spans'],text)
        self.assertTrue(S.support('辞典','読む'))
        self.assertTrue(S.support('待ち合わせ','確認'))
        self.assertFalse(S.support('待ち合わせ','食べる'))
        self.assertFalse(S.support('マット','読む'))
        # Cost-table presence alone cannot certify an arbitrary two-noun join.
        self.assertFalse(S.relational_nominal_support('情報','食事'))
        self.assertFalse(S.relational_nominal_support('猫','入力'))

    def test_registered_property_prefix_keeps_exact_reading_and_head(self):
        heads=R.native_relational_compound_heads('あおりんご')
        self.assertTrue(heads)
        self.assertTrue(all('food' in S.nominal_roles(face) for face in heads))
        for text in ('あおりんごをたべます。','あおりんごをみっつかいます。'):
            result=self.correct(text)
            assert_preserved_source_spelling(self,result,text)
            self.assertFalse(result['odd_spans'])
        for text in ('あおりんぎ','あおぷねら','にせりんご','むりんご'):
            self.assertFalse(R.native_relational_compound_heads(text),text)
        self.assertFalse(S.support('林檎','読む'))

    def test_field_relation_requires_both_native_words_and_the_same_head(self):
        for field in ('日本語','英和','漢和','医学'):
            self.assertTrue(S.field_nominal_support(field,'辞典'),field)
        self.assertTrue(S.field_nominal_support('日本語','教師'))
        for left,right in (('猫','教師'),('ぷねら','辞典'),('日本語','食事')):
            self.assertFalse(S.field_nominal_support(left,right),(left,right))
        for text in ('えいわじてんをよみます。','かんわじてんをかいます。',
                     'にほんごきょうしをさがします。','すうがくきょうしをさがします。'):
            result=self.correct(text)
            assert_preserved_source_spelling(self,result,text)
            self.assertFalse(result['odd_spans'],text)
        # 48-AMI: a separate sourced common sense does not forge native rows.
        self.assertFalse(any(row[-1]=='わえい' for row in M.dictionary_inflections('和英')))
        self.assertTrue(R.native_common_noun_reading('和英','わえい'))
        self.assertFalse(R.native_common_noun_reading('和英','かずひで'))
        self.assertFalse(R.native_relational_compound_heads('ぷねらきょうし'))

    def test_repair_meaning_and_written_name_keep_original_boundaries(self):
        # 54's 欠点 expectation assumed an unregistered noun role.
        # Use the existing attribute 名称; do not add a meaning to fit a test.
        for obj in ('文章','機械','名称'):
            self.assertTrue(S.support(obj,'直す'),obj)
        # 56's 時間 counterexample was invalid: its representation is information.
        self.assertFalse(S.support('水','直す'))
        for text in ('ぶんしょうをなおします。','文章を直しました。',
                     '旅行の日程を相談しました。'):
            result=self.correct(text)
            assert_preserved_source_spelling(self,result,text)
            self.assertFalse(result['odd_spans'],text)
        # Explicit ぇ can now release Shift and replace the same physical key.
        # The two operations retain the original object/predicate proof.
        for text in ('あしたまでにぶんしょうをなおしまぅ。',
                     'あしたまでにぶんしょうをなおそします。'):
            result=self.correct(text)
            self.assertEqual(result['corrected'],'あしたまでに文章を直します。')
            self.assertFalse(result['odd_spans'],text)
        malformed='旅行の日程を素左右田んしました'
        self.assertFalse(R.native_object_predicate_proof(malformed,6,('日程',)))
        self.assertNotIn((0,len(malformed)),R.native_context_ranges(malformed))
        self.assertTrue(self.correct(malformed+'。')['odd_spans'])
        # The name remains a separate nominal when its actual case survives.
        named='旅行の日程を田中と相談しました'
        parts=M.tokenize(named)
        self.assertTrue(R._written_predicate_reading_preserved(parts,6,
            ''.join(t.surface if all('ぁ'<=c<='ゖ' or c=='ー' for c in t.surface)
                         else t.reading for t in parts)))

    def test_written_nominal_auxiliary_keeps_its_actual_direct_object(self):
        for text,cut,face in (('資料を男子ました',3,'資料'),
                              ('日程を相談ました',3,'日程'),
                              ('友人を招待ました',3,'友人')):
            self.assertIn((0,cut,(face,)),R.native_object_predicate_contexts(text),text)
        # v2 / 48-AOH: a written mismatch shares its original object
        # across an intervening argument; the narrower kana discovery does
        # not. v1's direct-only expectation would retain unsuitable 分しました.
        for text in ('資料を保存しました','資料を田中ました'):
            self.assertFalse(R.native_object_predicate_contexts(text),text)
        for text in ('資料を沿うて男子ました','本を友人に男子ました'):
            self.assertTrue(R.native_object_predicate_contexts(text),text)
            self.assertFalse(R.native_object_predicate_contexts(text,
                include_written_mismatch=False),text)
            self.assertFalse(R.native_object_predicate_cuts(text),text)
        # The existing all-kana frame for an unknown head is unchanged;
        # having a frame does not certify a word or a complete predicate.
        self.assertEqual(R.native_object_predicate_contexts('資料をぷねらました'),
            R.native_object_predicate_contexts('資料をぷねらました',include_written_mismatch=False))
        for text in ('資料を男子ました','友人を招待ました'):
            self.assertFalse(R.native_object_predicate_cuts(text),text)
        for text,begin,cut in (('保存後に資料を男子ました',4,7),
                               ('文章を読んで資料を男子ました',6,9),
                               ('今日は資料を男子ました',3,6)):
            self.assertIn((begin,cut,('資料',)),R.native_object_predicate_contexts(text),text)
            self.assertFalse(R.native_object_predicate_cuts(text),text)
        for text in ('今日は未知資料を男子ました','今日はぷねら資料を男子ました'):
            self.assertFalse(R.native_object_predicate_contexts(text),text)
        self.assertTrue(R.native_object_predicate_proof('資料を保存しました',3,('資料',)))
        self.assertTrue(R.native_object_predicate_proof('日程を相談しました',3,('日程',)))
        for text,face in (('資料を分しました','資料'),('日程を騙しました','日程'),
                          ('本を分しました','本')):
            self.assertFalse(R.native_object_predicate_proof(text,len(face)+1,(face,)),text)

    def test_written_nominal_candidate_zero_retains_source_and_purple(self):
        for source in ('資料を男子ました。','日程を男子ました。','本を男子ました。',
                       '保存後に資料を男子ました。','文章を読んで資料を男子ました。'):
            result=self.correct(source)
            self.assertEqual(result['corrected'],source)
            self.assertTrue(result['odd_spans'],source)
        for source in ('資料を保存しました。','日程を相談しました。',
                       '「資料を男子ました」という誤字の例。',
                       '「資料を男子ました」と入力しました。',
                       '「資料を男子ました」という文字列。'):
            result=self.correct(source)
            self.assertEqual(result['corrected'],source)
            self.assertFalse(result['odd_spans'],source)
        # A bare quote is ordinary prose under the existing literal policy.
        result=self.correct('「資料を男子ました」と書きました。')
        self.assertEqual(result['corrected'],'「資料を男子ました」と書きました。')
        self.assertTrue(result['odd_spans'])

    def test_roster_membership_does_not_invent_a_compound_head_meaning(self):
        from seed_japanese import is_unit
        import oddness as O
        for left,right in (('シ','マス'),('画','僧')):
            self.assertTrue(is_unit(left+right))
            self.assertFalse(S.relational_nominal_support(left,right))
        for left,right in (('電子','辞書'),('ランチョン','マット'),('国語','辞典')):
            self.assertTrue(S.relational_nominal_support(left,right))
        self.assertFalse(R.native_relational_compound_heads('します'))
        self.assertFalse(R.native_relational_compound_heads('がそう'))
        text='かいてはけさしますです'
        self.assertFalse(R.completed_native_reading_sequence(text))
        self.assertFalse(O.changed_auxiliary_chain_allowed(text,0,len(text)))
        # This does not declare the written rare word wrong or forbid names.
        self.assertEqual(self.correct('画僧')['corrected'],'画僧')
        self.assertEqual(self.correct('シマス')['corrected'],'シマス')

    def test_closed_source_frames_preserve_compounds_voice_and_clause_scope(self):
        for text in ('交通費を生産します。','宿泊費を製造しました。','出張費を量産します。'):
            with self.subTest(text=text):self.assertTrue(S.conflicting_object_predicates(text,self.legacy(text)))
        for text in ('部品を生産します。','金を生産します。','経費を生産する仕組みと比較します。',
                     '交通費を生産費に加えます。','経費を生産させます。','経費を生産して調整します。',
                     '未知交通費を生産します。'):
            with self.subTest(text=text):self.assertFalse(S.conflicting_object_predicates(text,self.legacy(text)))
        for text in ('意見を繁栄します。','要望を繁盛します。'):
            with self.subTest(text=text):self.assertTrue(S.subject_only_predicate_spans(text,self.legacy(text)))
        for text in ('町が繁栄します。','地域を繁栄させます。','地域を繁栄する町にします。'):
            with self.subTest(text=text):self.assertFalse(S.subject_only_predicate_spans(text,self.legacy(text)))

    def test_actual_adjacent_repairs_retain_original_nominal_and_normal_alternatives(self):
        for text in ('もじにゅうりょくをためはます。','もじにゅうりょくをためさします。',
                     'もじにゅうりょくをためしまくす。'):
            with self.subTest(text=text):
                r=self.correct(text)
                assert_repaired_spelling(self, r, 'もじにゅうりょくを試します。')
                self.assertEqual(r['odd_spans'],[])
        # Native 文字 has an attested もんじ reading; spelling is not a key deletion.
        normal=self.correct('もんじにゅうりょく')
        assert_preserved_source_spelling(self,normal)
        self.assertFalse(normal['odd_spans'])
        for text in ('もじにゅうりょくく',
                     '町が繁栄します。','意見を反映します。','部品を生産します。',
                     '交通費を精算します。','旅費を清算します。'):
            with self.subTest(text=text):self.assertEqual(self.correct(text)['corrected'],text)
        self.assertEqual(self.correct('意見を繁栄します。')['corrected'],'意見を反映します。')
        # Both native settlement senses fit expenses; no exact 精算 claim.
        self.assertIn(self.correct('交通費を生産します。')['corrected'],
                      ('交通費を精算します。','交通費を清算します。'))

    def test_common_stop_final_validation_and_purple_ledger_remain_distinct(self):
        from decisions import DecisionStore
        import corrector as C
        source='意見を繁栄します。'
        decisions=DecisionStore();decisions.protect('繁栄')
        self.assertEqual(self.correct(source,decisions)['corrected'],source)
        decisions=DecisionStore();decisions.leave_odd_alone('繁栄')
        self.assertEqual(self.correct(source,decisions)['corrected'],'意見を反映します。')
        with patch.object(C,'_check_replacement',return_value=(None,'test_rejected')):
            r=self.correct(source)
        self.assertEqual(r['corrected'],source)
        self.assertTrue(r['odd_spans'])


    def test_recorded_content_transfer_keeps_actual_spelling_and_destination(self):
        for text,cut,faces in (('内容をファイルに移します',3,('内容',)),
                              ('資料を文書に移します',3,('資料',)),
                              ('メモの内容を別のファイルに移します',6,('内容',))):
            self.assertTrue(R.native_object_predicate_proof(text,cut,faces),text)
        for text in ('内容をファイルに映します','水をファイルに移します',
                     'ぷねらをファイルに移します'):
            self.assertFalse(R.native_object_predicate_proof(text,text.index('を')+1,
                R.native_surface_nominal_heads(text[:text.index('を')])),text)
        text='メモの内容を別のファイルに移歯ます。'
        result=self.correct(text)
        self.assertEqual(result['corrected'],'メモの内容を別のファイルに移します。')
        self.assertFalse(result['odd_spans'])
        for text in ('内容をファイルに移します。','ファイルを開きます。','メモを読みます。',
                     '内容を別のファイルに写します。'):
            result=self.correct(text)
            self.assertEqual(result['corrected'],text)
            self.assertFalse(result['odd_spans'])

    def test_written_modifier_and_storage_head_use_original_roles(self):
        self.assertEqual(R.native_surface_nominal_heads('新しい本'),('本',))
        self.assertEqual(R.native_surface_nominal_heads('古い本'),('本',))
        self.assertFalse(R.native_surface_nominal_heads('新しい太郎'))
        self.assertIn('container',S.nominal_roles('本棚'))
        self.assertIn('container',S.nominal_roles('本箱'))
        self.assertIn('text',S.nominal_roles('書'))
        self.assertIn('container',S.nominal_roles('書棚'))
        for source,expected in (
                ('本棚に新しい本をみどします。','本棚に新しい本を戻します。'),
                ('本箱に古い本をみどします。','本箱に古い本を戻します。'),
                ('書棚に新しい本をみどします。','書棚に新しい本を戻します。'),
                ('書棚に新しい書をみどします。','書棚に新しい書を戻します。'),
                ('棚に面白い本をみどしました。','棚に面白い本を戻しました。'),
                ('本棚へ新しい本をみどします。','本棚へ新しい本を戻します。'),
                ('書棚へ新しい本をみどします。','書棚へ新しい本を戻します。'),
                ('倉庫へ資料をみどします。','倉庫へ資料を戻します。'),
                # A shop is an existing place role, not a negative container test.
                ('書店に新しい本をみどします。','書店に新しい本を戻します。'),
                ('書店へ新しい本をみどします。','書店へ新しい本を戻します。')):
            result=self.correct(source)
            self.assertEqual(result['corrected'],expected,source)
            self.assertFalse(result['odd_spans'],source)
        for source in ('本棚に新しい本を戻します。','本棚に新しい本を読みます。',
                       '書棚に新しい本を戻します。',
                       '本棚に新しい本をもどします。',
                       '本棚へ新しい本を戻します。',
                       '本棚へ新しい本を読みます。',
                       '本棚へ新しい本をもどします。'):
            result=self.correct(source)
            assert_preserved_source_spelling(self,result,source)
            self.assertFalse(result['odd_spans'],source)
        self.assertEqual(self.correct('本棚に新しい本をみどし')['corrected'],
                         '本棚に新しい本をみどし')
        for source in ('友人に新しい本をみどします。',
                       '本棚に新しい話をみどします。',
                       '書棚に新しい話をみどします。',
                       '友人へ新しい本をみどします。',
                       '本棚へ新しい話をみどします。'):
            result=self.correct(source)
            assert_preserved_source_spelling(self,result,source)
            self.assertTrue(result['odd_spans'],source)


if __name__=='__main__':unittest.main()


class ReferenceInvestigationTests(unittest.TestCase):
    def test_reference_nominals_fit_the_same_native_investigation_predicate(self):
        import reading_segments as R,semantic_roles as S
        for noun in ('辞典','辞書','索引','一覧'):
            self.assertTrue(S.nominal_role_matches(noun,S.predicate_roles('調べる')),noun)
        for reading in ('こくごじてんをしらべます','えいわじてんをしらべます',
                        'じしょをしらべます','さくいんをしらべます'):
            self.assertTrue(R.completed_native_reading_clause(reading),reading)
        for reading in ('ぷねらをしらべます','こくごぷねらをしらべます'):
            self.assertFalse(R.completed_native_reading_clause(reading),reading)

    def test_reference_readings_use_validated_written_forms(self):
        import app
        from tests_analysis_async import initial
        for source,expected in (('こくごじてんをしらべます。','国語辞典を調べます。'),
                                ('えいわじてんをしらべます。','英和辞典を調べます。'),
                                ('さくいんをしらべます。','索引を調べます。')):
            with self.subTest(source=source):
                a=initial();r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,decisions=a.decisions,context_vec=None)
                self.assertEqual(r['corrected'],expected,source)
                self.assertFalse(r['odd_spans'],source)
                self.assertEqual(r['analysis_status'],'complete',source)
