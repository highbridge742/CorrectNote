# -*- coding: utf-8 -*-
"""Native nominal readings keep ordinary input out of typo search (48-AGH)."""
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
                     ('さぎょうをじたんしなす。','さぎょうをじたんします。'),
                     ('でーたをせほぞんします。','でーたをほぞんします。'),
                     ('ふれーむのいろをせかえます。','ふれーむのいろをかえます。'))
        for source,expected in [(text,text) for text in normal]+list(corrections):
            with self.subTest(text=source):
                r=app.correct_line(source,a.store,input_method='kana',dict_index=a.dict_index,
                                   context_vec=a.context_vec,decisions=a.decisions)
                self.assertEqual(r['corrected'],expected)
                self.assertFalse(r['odd_spans'])
        r=app.correct_line('もんじにゅうりょく',a.store,input_method='kana',dict_index=a.dict_index)
        self.assertNotEqual(r['corrected'],'もじにゅうりょく')

if __name__=='__main__':unittest.main()
