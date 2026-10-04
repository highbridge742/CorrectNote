# -*- coding: utf-8 -*-
"""Native nominal readings keep ordinary input out of typo search (48-AGH)."""
from tests_spelling_reference import assert_reviewed_result_spelling
from tests_spelling_reference import assert_reviewed_source_spelling
from tests_spelling_reference import assert_repaired_spelling
import unittest
import morphology as M

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class NativeNominalTests(unittest.TestCase):
    def test_action_use_keeps_native_lexicon_honest(self):
        from semantic_roles import classified_nominal_action
        rows=M.dictionary_inflections('時短')
        self.assertTrue(rows)
        self.assertFalse(any(p.startswith('名詞,サ変接続,') for p,f,b,r in rows))
        self.assertTrue(classified_nominal_action('時短','じたん'))
        self.assertFalse(classified_nominal_action('時短','しだん'))
        self.assertFalse(classified_nominal_action('制度','せいど'))
        self.assertEqual(M.tokenize('時短します')[0].pos_sub,'サ変接続')
        self.assertEqual(M.tokenize('時短の方法')[0].pos_sub,'一般')

    def test_dictionary_whole_katakana_noun_and_suffix(self):
        for text in ('モーション名','モーションシート','モーションを表示する'):
            with self.subTest(text=text):
                tokens=M.tokenize(text)
                self.assertEqual(tokens[0].surface,'モーション')
                self.assertEqual(tokens[0].reading,'もーしょん')
                self.assertTrue(tokens[0].has_reading)
                self.assertNotIn('固有名詞',tokens[0].pos_sub)
                self.assertEqual(''.join(t.surface for t in tokens),text)

    def test_native_merge_does_not_cross_gaps_or_invent_words(self):
        for text in ('モー ション名','ブルクリック','モーションョ名'):
            with self.subTest(text=text):
                tokens=M.tokenize(text)
                forbidden='モーションョ' if text=='モーションョ名' else ('ブルクリック' if text=='ブルクリック' else 'モーション')
                self.assertFalse(any(t.surface==forbidden and t.has_reading for t in tokens))
                if text=='モーションョ名':
                    self.assertTrue(any(t.start<=5<t.end and not t.has_reading for t in tokens))
                for t in tokens:self.assertEqual(text[t.start:t.end],t.surface)

    def test_suffix_attachment_preserves_person_names(self):
        for text in ('対象外行','範囲外行','指定外行'):
            with self.subTest(text=text):
                tokens=M.tokenize(text)
                self.assertEqual([t.surface for t in tokens], [text[:-2],'外','行'])
                self.assertEqual(tokens[1].pos_sub,'接尾:一般')
                self.assertEqual(tokens[1].reading,'がい')
                self.assertEqual(tokens[2].pos_sub,'一般')
                for t in tokens:self.assertEqual(text[t.start:t.end],t.surface)
        for text in ('外行さん','田中外行さん','対象外行氏'):
            with self.subTest(text=text):
                self.assertTrue(any(t.surface=='外行' and '人名' in t.pos_sub for t in M.tokenize(text)))

    def test_prefix_requires_native_noun_on_both_sides(self):
        tokens=M.tokenize('映像総尺')
        self.assertEqual([t.surface for t in tokens],['映像','総尺'])
        self.assertEqual(tokens[1].reading,'そうしゃく')
        for text in ('数値総','数値総ヌョ','数値 総尺'):
            with self.subTest(text=text):
                self.assertFalse(any(t.surface=='総尺' for t in M.tokenize(text)))

    def test_source_kana_action_and_candidate_grammar_share_evidence(self):
        from reading_segments import intact_native_reading,completed_sahen_reading
        for text in ('じたんする','じたんしない','じたんします','じたんした'):
            with self.subTest(text=text):self.assertTrue(intact_native_reading(text))
        for text in ('じたんしす','じたんしまず','せいどする'):
            with self.subTest(text=text):self.assertFalse(completed_sahen_reading(text,allow_nonpolite=True))

    def test_nominal_prefix_keeps_actual_verb_auxiliary_validation(self):
        from tests_analysis_async import initial
        import corrector as C,contextual_repair as R
        a=initial();tk=C.make_tokenizer(a.store)
        for verb,tail,expected in (('見','ています。',True),('読み','ます。',True),
                ('書い','ています。',True),('見','ていました。',True),
                ('読む','ています。',False),('書い','でいます。',False),
                ('見','ますです。',False)):
            prefix='乳リュク'+verb;source=prefix+tail;candidate='入力'+verb
            target=R.RepairTarget(source,0,len(prefix),0,len(source),
                    (('乳','リュク',0,4),),True,tail)
            with self.subTest(text=source):
                valid,reason=R.validate(target,candidate,C,tk,a.store,a.dict_index)
                self.assertEqual(valid,expected,reason)

    def test_written_continuative_is_preserved_only_in_its_original_nominal_slot(self):
        import reading_segments as R,corrector as C
        from tests_analysis_async import initial
        a=initial();tk=C.make_tokenizer(a.store)
        for text,head in (('読み乳力を確認','読み'),('巻き込み乳力を確認','巻き込み'),
                          ('読み乳力します','読み'),('読み乳力','読み')):
            self.assertEqual(R.native_nominal_verb_prefix_ranges(text),((0,len(head)),))
            changed='良く'+text[len(head):]
            self.assertFalse(R.preserves_native_nominal_verb_prefix(text,changed))
            for start,end,surface in ((0,len(head),'良く'),(0,len(text),changed)):
                value,reason=C._check_replacement(text,(start,end,surface,'test'),
                    a.store,tk,a.dict_index,a.decisions)
                self.assertIsNone(value,(text,reason))
                self.assertEqual(reason,'native_nominal_verb_prefix')
            self.assertTrue(R.preserves_native_nominal_verb_prefix(text,text.replace('乳力','入力')))
        for text in ('読みの入力を確認','読ん乳力を確認',
                     'よみ乳力を確認','目もち長を確認','読みきれます'):
            self.assertFalse(R.native_nominal_verb_prefix_ranges(text),text)
        source='今日は休みです。読み乳力を確認'
        self.assertTrue(R.preserves_native_nominal_verb_prefix(source,source.replace('今日','明日')))
        self.assertFalse(R.preserves_native_nominal_verb_prefix(source,source.replace('読み','良く')))

    def test_legacy_word_pair_does_not_rewrite_the_unmarked_written_verb(self):
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('読み乳力','読み乳力を確認','読み乳力を確認します。','巻き込み乳力を確認'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            self.assertEqual(result['corrected'],text.replace('乳力','入力'))
        # With an actual malformed suru attachment the existing narrower
        # nominal candidate can still repair the tail without changing 読み.
        text='読み乳力します'
        result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        self.assertEqual(result['corrected'],'読み入力します')

    def test_relative_action_keeps_all_and_only_fitting_native_homophones(self):
        import reading_segments as R
        made=R.native_nominal_phrase_faces('つくったしりょう')
        self.assertIn('資料',made)
        self.assertIn('史料',made)
        read=R.native_nominal_phrase_faces('よんだしりょう')
        self.assertIn('資料',read)
        self.assertIn('史料',read)
        self.assertNotIn('飼料',read)
        eaten=R.native_nominal_phrase_faces('たべたしりょう')
        self.assertIn('飼料',eaten)
        self.assertNotIn('資料',eaten)
        self.assertNotIn('史料',eaten)

    def test_application_preserves_nominal_sentences_and_repairs_real_keys(self):
        from tests_analysis_async import initial
        import app
        a=initial()
        normal=('夕食の準備を時短します。','朝の作業を時短したい。',
                '不正を指弾する記事を読む。','じたんする。','じたんしない。',
                'さぎょうをじたんします。','モーション名を一覧に追加する。',
                '別のモーションシートを開く。','対象外行を灰色で表示する。',
                '映像総尺を確認する。','A列期待値を表示する。',
                '行合計を求める。','列平均を計算する。','文章の構成を考える。')
        corrections=(('乳リュク見ていますが、画面は変わりません。','入力見ていますが、画面は変わりません。'),
                     ('乳リュク読んでいます。','入力読んでいます。'),
                     ('乳リュク書いています。','入力書いています。'),
                     ('でーたをせほぞんします。','でーたを保存します。'),
                     ('ふれーむのいろをせかえます。','フレームの色を変えます。'))
        for source,expected in [(text,text) for text in normal]+list(corrections):
            with self.subTest(text=source):
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                   context_vec=a.context_vec,decisions=a.decisions)
                assert_reviewed_result_spelling(self, r, expected)
                self.assertFalse(r['odd_spans'])
        r=app.correct_line('もんじにゅうりょく',a.store,input_method='kana',dict_index=a.dict_index)
        self.assertNotEqual(r['corrected'],'もじにゅうりょく')

    def test_ambiguous_adjacent_auxiliary_keeps_both_native_readings(self):
        # 48-AKZ / 2026-09-20: old gold was only します because the valid
        # しない candidate was rejected as accidental じ+た auxiliaries.
        # な→ま and す→い are both adjacent single-key repairs. Both full
        # meanings are natural here; preserve the ranked first candidate.
        import app
        import corrector as C
        from tests_analysis_async import initial
        a=initial();a.context_vec=None
        source='さぎょうをじたんしなす。'
        accepted=('さぎょうをじたんします。','さぎょうをじたんしない。')
        tokenize=C.make_tokenizer(a.store)
        for text in accepted:
            result,reason=C._check_replacement(source,(5,11,text[5:-1],'かな入力'),
                a.store,tokenize,a.dict_index,a.decisions)
            self.assertIsNotNone(result,reason)
            normal=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, normal['corrected'], text)
            self.assertFalse(normal['odd_spans'])
        result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
            context_vec=None,decisions=a.decisions)
        assert_repaired_spelling(self, result, accepted)
        self.assertFalse(result['odd_spans'])

    def test_visual_subject_relation_keeps_the_native_compound_head(self):
        import reading_segments as RS
        import semantic_roles as S
        self.assertTrue(S.genitive_nominal_support('風景','写真'))
        self.assertTrue(S.genitive_nominal_support('人物','映像'))
        self.assertFalse(S.genitive_nominal_support('精度','写真'))
        for text in ('風景写真','人物写真'):
            self.assertEqual(RS._native_written_nominal_faces(text),('写真',))
        self.assertIn('写真',RS.native_nominal_phrase_faces('ふうけいしゃしん'))
        self.assertFalse(RS._native_written_nominal_faces('精度写真'))
        # The photograph remains a representation, not the pictured food.
        self.assertFalse(RS.completed_native_reading_clause('ふうけいしゃしんをたべます',require_object_fit=True))
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('ふうけいしゃしんをみます。','ふうけいのしゃしんをみます。',
                     'じんぶつのえいぞうをみます。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertFalse(result['odd_spans'])

    def test_notifications_and_table_textiles_keep_their_own_nominal_senses(self):
        import reading_segments as RS
        import semantic_roles as S
        import app
        from tests_analysis_async import initial
        a=initial()
        normal=('てーぶるくろすをかいます。','てーぶるくろすをあらいます。',
                'なぷきんをあらいます。','ごうかくつうちをかくにんします。',
                'ふごうかくのつうちをよみます。','とうせんのつうちをよみます。',
                'さいようつうちをかくにんします。','合格通知を確認します。')
        for text in normal:
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                assert_reviewed_source_spelling(self, r['corrected'], text)
                self.assertFalse(r['odd_spans'])
        for text in ('てーぶるくろすをのみます','ごうかくつうちをたべます',
                     'ごうかくつうちをかくにんしま','ごうかくつうちをかくにんしますです',
                     'ごうかくをかいさいします','ふごうかくをさいかいします'):
            with self.subTest(text=text):
                self.assertFalse(RS.completed_native_reading_clause(text,require_object_fit=True))
        # 59 treated selection outcomes as events and falsely accepted
        # holding a pass / resuming a failure. Use informational content.
        self.assertFalse(S.genitive_nominal_support('合格','水'))
        self.assertFalse(S.support('合格','開催'))
        self.assertFalse(S.support('不合格','再開'))
        self.assertFalse(S.support('テーブルクロス','飲む'))

    def test_container_suffix_uses_native_rendaku_and_keeps_container_meaning(self):
        import reading_segments as RS
        import app
        from tests_analysis_async import initial
        a=initial()
        for text in ('みかんばこ','みかん箱'):
            self.assertEqual(RS.native_container_nominal_heads(text),('箱',))
        for text in ('みかんはこ','せいどばこ','ぬょばこ','みかん 箱'):
            self.assertFalse(RS.native_container_nominal_heads(text),text)
        for text in ('みかんばこをはこびます。','みかん箱を運びます。',
                     'みかんのはこをはこびます。','みかんの箱を運びます。'):
            with self.subTest(text=text):
                r=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                assert_reviewed_source_spelling(self, r['corrected'], text)
                self.assertFalse(r['odd_spans'])
        for text in ('みかんばこをたべます','みかんばこをはこびま',
                     'みかんばこをはこびますです'):
            self.assertFalse(RS.completed_native_reading_clause(text,require_object_fit=True),text)

    def test_possession_and_decoration_share_full_native_predicate_senses(self):
        import reading_segments as R
        import semantic_roles as S
        for noun,verb in (('箱','持つ'),('費用','持つ'),('意味','持つ'),
                          ('会議','持つ'),('写真','飾る'),('部屋','飾る'),('言葉','飾る')):
            self.assertTrue(S.support(noun,verb),(noun,verb))
        for text in ('りんごばこをもちます','ふうけいのしゃしんをかざります'):
            self.assertTrue(R.completed_native_reading_clause(text,require_object_fit=True),text)
        for text in ('りんごばこをもちま','りんごばこをもちますです',
                     'ふうけいのしゃしんをかざりま','ふうけいのしゃしんをかざりますです',
                     'りんごばこをたべます','ふうけいのしゃしんをたべます'):
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)

    def test_partitive_genitive_retains_the_original_whole(self):
        import semantic_roles as S
        for left,right in (('本','残り'),('布','一部'),('資料','部分'),('時間','残り'),('作業','残り')):
            with self.subTest(left=left,right=right):
                self.assertTrue(S.genitive_nominal_support(left,right))
        for left,right in (('未知語','残り'),('度','ファイル'),('一部','資料'),('本','居間')):
            self.assertFalse(S.genitive_nominal_support(left,right),(left,right))
        import app
        from tests_analysis_async import initial
        a=initial()
        for source,expected in (('本の残り','本の残り'),('布の一部','布の一部'),
                                ('水の残り','水の残り'),('紙の部分','紙の部分'),
                                ('度のファイルを開く。','どのファイルを開く。'),
                                ('度の強い眼鏡','度の強い眼鏡')):
            with self.subTest(source=source):
                result=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                self.assertEqual(result['corrected'],expected)
                self.assertFalse(result['odd_spans'])

    def test_material_container_relation_keeps_native_head_and_reading(self):
        import reading_segments as R
        import semantic_roles as S
        for material in ('紙','木材','布','ガラス'):
            self.assertTrue(S.genitive_nominal_support(material,'箱'),material)
        for text in ('かみばこ','紙箱'):
            self.assertEqual(R.native_container_nominal_heads(text),('箱',))
        for material in ('画面','精度','情報'):
            self.assertFalse(S.genitive_nominal_support(material,'箱'),material)
        for text in ('かみはこ','ぬょばこ','かみ 箱'):
            self.assertFalse(R.native_container_nominal_heads(text),text)
        self.assertTrue(R.completed_native_reading_clause('かみばこをはこびます',require_object_fit=True))
        self.assertFalse(R.completed_native_reading_clause('かみばこをたべます',require_object_fit=True))
        self.assertFalse(R.completed_native_reading_clause('かみばこをはこびま',require_object_fit=True))

    def test_error_senses_support_correction_without_document_or_food_roles(self):
        import semantic_roles as S
        import reading_segments as R
        for noun in ('間違い','誤り','誤字','脱字','入力ミス','エラー'):
            for verb in ('直す','正す','修正','訂正','指摘'):
                self.assertTrue(S.support(noun,verb),(noun,verb))
            self.assertFalse(S.support(noun,'食べる'),noun)
            self.assertNotIn('text',S.nominal_roles(noun),noun)
        self.assertFalse(S.support('マテガイ','修正'))
        for text in ('まちがいをなおします','あやまりをていせいします',
                     'ごじをしゅうせいします','だつじをしてきします'):
            self.assertTrue(R.completed_native_reading_clause(text,require_object_fit=True),text)
        for text in ('まちがいをなおしま','あやまりをていせいしますです',
                     'まちがいをたべます'):
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)

    def test_physical_materials_share_tangible_actions_without_food_or_abstract_roles(self):
        import semantic_roles as S
        import reading_segments as R
        for noun in ('木材','紙','鉄','ガラス','樹脂'):
            for verb in ('運ぶ','並べる','買う','洗う'):
                self.assertTrue(S.support(noun,verb),(noun,verb))
            self.assertFalse(S.support(noun,'食べる'),noun)
            self.assertFalse(S.support(noun,'飲む'),noun)
        for noun in ('情報','精度','画面','木曜日','意思'):
            self.assertNotIn('material',S.nominal_roles(noun),noun)
        for text in ('かみとぬのをはこびます','もくざいをならべます','てつをかいます'):
            self.assertTrue(R.completed_native_reading_clause(text,require_object_fit=True),text)
        for text in ('かみとぬのをはこびま','もくざいをはこびますです','てつをたべます'):
            self.assertFalse(R.completed_native_reading_clause(text,require_object_fit=True),text)
        # A lexical unit reading is real, but does not prove a physical-material sense.
        self.assertTrue(R.native_common_noun_reading('石','こく'))
        self.assertFalse(R.completed_native_reading_clause('こくをはこびます',require_object_fit=True))

    def test_ongoing_nominal_uses_native_host_suffix_and_keeps_whole_sense(self):
        import semantic_roles as S
        import reading_segments as R
        import app
        from tests_analysis_async import initial
        a=initial()
        for word,reading in (('入力中','にゅうりょくちゅう'),('作業中','さぎょうちゅう'),
                             ('勉強中','べんきょうちゅう'),('会議中','かいぎちゅう'),
                             ('食事中','しょくじちゅう'),('使用中','しようちゅう')):
            self.assertEqual(R.native_temporal_nominal_faces(reading),(word,))
            self.assertEqual(R._native_written_nominal_faces(word),(word,))
            self.assertIn(word,R.native_nominal_phrase_faces(reading))
            import corrector as C
            self.assertEqual(C._compose_kana_run_fixes(reading,a.store,a.dict_index,
                source_tokenize=C.make_tokenizer(a.store)),[])
            for text in (reading,reading+'です。'):
                result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                    context_vec=None,decisions=a.decisions)
                assert_reviewed_source_spelling(self, result['corrected'], text)
                self.assertFalse(result.get('odd_spans'),text)
            self.assertFalse(S.support(word,'食べる'))
            self.assertNotIn('place',S.nominal_roles(word))
        for text in ('精度中','完了中','死亡中','ぷねら中','入力 中','中入力',
                     'にゅうりょくちゅ','にゅうりょくじゅう','せいどちゅう','ぷねらちゅう'):
            self.assertFalse(R.native_temporal_nominal_faces(text),text)
        for text in ('にゅうりょくちゅうます','にゅうりょくちゅうですです'):
            self.assertFalse(R.completed_native_nominal_predicate(text),text)

    def test_seeing_display_and_writing_surface_is_not_eating_or_hearing_it(self):
        import semantic_roles as S
        import reading_segments as R
        import app
        from tests_analysis_async import initial
        for noun in ('画面','タブ','プレビュー','黒板','白板','紙面'):
            self.assertTrue(S.support(noun,'見る'),noun)
            self.assertFalse(S.support(noun,'食べる'),noun)
            self.assertFalse(S.support(noun,'聞く'),noun)
        a=initial()
        for text in ('がめんをみます。','こくばんをみます。','さぎょうちゅうのがめんをみます。'):
            self.assertTrue(R.completed_native_reading_clause(text,require_object_fit=True),text)
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertFalse(result.get('odd_spans'),text)

    def test_activity_interruption_and_completion_keep_their_object_sense(self):
        import semantic_roles as S,reading_segments as R,app
        from tests_analysis_async import initial
        for predicate in ('中断','完了'):
            for noun in ('作業','入力','会議','試合'):
                self.assertTrue(S.support(noun,predicate),(noun,predicate))
            for noun in ('薬袋','水','黒板','和英'):
                self.assertFalse(S.support(noun,predicate),(noun,predicate))
            self.assertFalse(S.ongoing_nominal_support(predicate),predicate)
        a=initial()
        for text in ('さぎょうちゅうだんです。','にゅうりょくかんりょうです。',
                     'さぎょうをちゅうだんします。','さぎょうをかんりょうします。'):
            result=app.correct_line(text,a.store,input_method='kana',dict_index=a.dict_index,
                context_vec=None,decisions=a.decisions)
            assert_reviewed_source_spelling(self, result['corrected'], text)
            self.assertFalse(result.get('odd_spans'),text)
        self.assertFalse(R.native_temporal_nominal_faces('かんりょうちゅう'))
        self.assertFalse(R.native_nominal_phrase_faces('みずちゅうだん'))

if __name__=='__main__':unittest.main()
