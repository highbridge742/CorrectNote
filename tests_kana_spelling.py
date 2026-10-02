# -*- coding: utf-8 -*-
"""Kana spelling preserves meaning, explicit choices, fields and original coordinates."""
import unittest
from unittest.mock import patch
import morphology as M

class KanaSpellingCoordinateTests(unittest.TestCase):
    def test_mixed_ime_reading_maps_back_to_original_positions(self):
        from types import SimpleNamespace as T
        from unittest.mock import Mock
        from ime_spelling import source_first_words
        tokens=[T(surface='資料',start=0,end=2,reading='しりょう',has_reading=True),
                T(surface='を',start=2,end=3,reading='を',has_reading=True),
                T(surface='よむ',start=3,end=5,reading='よむ',has_reading=True)]
        ime=Mock();ime.convert_words.return_value=('資料を読む',(
            (0,2,0,4,100,0),(2,3,4,5,0,0),(3,5,5,7,200,0)))
        with patch('morphology.tokenize',return_value=tokens),patch('morphology.native_spelling_only',return_value=True):
            first,words,reading,offsets=source_first_words('資料をよむ',ime)
        ime.convert_words.assert_called_once_with('しりょうをよむ')
        self.assertEqual(words,((0,2,0,2,100,0),(2,3,2,3,0,0),(3,5,3,5,200,0)))
        self.assertNotIn(1,offsets);self.assertNotIn(2,offsets)
        self.assertEqual(offsets[5],3)
        tokens[0].has_reading=False;ime.reset_mock()
        with patch('morphology.tokenize',return_value=tokens):
            self.assertIsNone(source_first_words('資料をよむ',ime))
        ime.convert_words.assert_not_called()

    def test_source_coordinates_survive_shortened_repairs_and_emoji(self):
        import corrector as E
        from kana_spelling import _compose_result
        source='😀しゅうありょうが\tのひっています'
        old=dict(corrected='😀しゅうりょうが\tのこっています',
                 original_spans=[(4,5),(11,12)],spans=[(4,4),(10,11)])
        result=_compose_result(source,old,[(1,7,'終了'),(9,12,'残っ')],E)
        self.assertEqual(result['corrected'],'😀終了が\t残っています')
        self.assertEqual(result['original_spans'],[(1,8),(10,13)])
        self.assertEqual(result['spans'],[(1,3),(5,7)])
        self.assertEqual([source[a:b] for a,b in result['original_spans']],['しゅうありょう','のひっ'])

    def test_adjacent_edits_and_repeated_words_keep_separate_source_ranges(self):
        import corrector as E
        from kana_spelling import _compose_result
        source='ゆうせんほせい\tゆうせん'
        r=_compose_result(source,dict(corrected=source),[(0,4,'優先'),(4,7,'補正'),(8,12,'優先')],E)
        self.assertEqual(r['corrected'],'優先補正\t優先')
        self.assertEqual(r['original_spans'],[(0,4),(4,7),(8,12)])
        self.assertEqual(r['spans'],[(0,2),(2,4),(5,7)])

    def test_spelling_touching_a_deleted_key_keeps_the_deletion(self):
        import corrector as E
        from kana_spelling import _compose_result
        left=dict(corrected='つたえたことで',original_spans=[(3,4)],spans=[(3,3)])
        result=_compose_result('つたえふたことで',left,[(0,3,'伝え')],E)
        self.assertEqual(result['corrected'],'伝えたことで')
        self.assertEqual(result['original_spans'],[(0,4)])
        self.assertEqual(result['spans'],[(0,2)])
        right=dict(corrected='ゆうせん',original_spans=[(0,1)],spans=[(0,0)])
        result=_compose_result('ふゆうせん',right,[(0,4,'優先')],E)
        self.assertEqual(result['corrected'],'優先')
        self.assertEqual(result['original_spans'],[(0,5)])

    def test_invalid_prior_mapping_is_not_guessed(self):
        import corrector as E
        from kana_spelling import _compose_result
        original='のひっています'
        old=dict(corrected='全く別の文章',original_spans=[(1,2)],spans=[(1,2)])
        self.assertIs(_compose_result(original,old,[(0,2,'残る')],E),old)

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class KanaSpellingNativeTests(unittest.TestCase):
    def test_mark_clusters_and_unknown_nouns_have_different_host_evidence(self):
        import reading_segments as R
        self.assertNotIn((0,3),R.native_adnominal_modifier_ranges('かたい゛゜に取り掛かる'))
        self.assertIn((0,5),R.native_adnominal_modifier_ranges('かんたんなぽねです。'))

    def test_potential_auxiliary_stays_bound_in_spelling(self):
        from ime_spelling import _reinterprets_function_attachment
        text='かみにかいておけます。'
        self.assertTrue(_reinterprets_function_attachment(text,6,8,'置け'))
        self.assertFalse(_reinterprets_function_attachment('箱におけます。',2,4,'置け'))

    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.a=initial();cls.a.context_vec=None
    @classmethod
    def tearDownClass(cls):
        from last_choice import set_active
        set_active(None)
    def run_line(self,text):
        import app
        return app.correct_line(text,self.a.store,dict_index=self.a.dict_index,
                                decisions=self.a.decisions,context_vec=None,input_method='kana')

    def test_complete_words_counts_focus_and_greetings_keep_their_meaning(self):
        pairs=[('ありがとうと言いました。','ありがとうと言いました。'),
               ('ありがとうございます','ありがとうございます'),('こんにちはという声がしました。','こんにちはという声がしました。'),
               ('やりがい','やりがい'),('およぎがいがあります。','およぎがいがあります。'),
               ('これはひなたです','これはひなたです'),('けいたいそ','けいたいそ'),
               ('お待ちくださいませ','お待ちくださいませ'),
               ('ほんをにさつかいます。','本をにさつかいます。'),('りんごをみっつかいます。','リンゴをみっつかいます。'),
               ('さんさつめをよみます。','さんさつめをよみます。'),
               ('ほんをねんまつかいます。','本をねんまつかいます。'),('ほんをげつまつかいます。','本をげつまつかいます。'),
               ('かいてはみます。','かいてはみます。'),('かんがえてはけっします。','かんがえてはけっします。'),
               ('かいてはけしなます。','かいては消します。'),
               ('としょかんでかりたほんをかえします。','としょかんでかりたほんをかえします。'),
               ('おきやくさまにおちゃをだします。','お客様にお茶を出します。'),
               ('大きさをかえます。','大きさを変えます。')]
        for source,expected in pairs:
            with self.subTest(source=source):
                r=self.run_line(source);self.assertEqual(r['corrected'],expected)
                self.assertEqual(r.get('odd_spans'),[])

    def test_native_projection_changes_spelling_only(self):
        for source,output in [('ゆうせんしてほせい','優先して補正'),('ほかのぎょうとおなじ','他の行と同じ'),
                              ('😀4ばい','😀4倍'),('しゅうりょうが','終了が')]:
            self.assertTrue(M.native_spelling_only(source,output),(source,output))
        for source,output in [('用船して補正','優先して補正'),('1-2+3','2'),('つたえた','伝えない'),
                              ('もんじにゅうりょく','字入力'),('ゆうせん','優勢')]:
            self.assertFalse(M.native_spelling_only(source,output),(source,output))

    def test_original_kana_and_repaired_kana_use_their_own_readings(self):
        # 48-APK: 用船 is a valid unchanged action, not a typo of 優先.
        pairs=[('ようせんしてほせい','用船して補正'),('ゆうせんしてほせい','優先して補正'),
               ('きりがないようにも','キリがないようにも'),('にゅうりょくちゅう','入力中'),
               ('つたえたことで','伝えたことで'),('つたえふたことで','伝えたことで'),('のひっています','残っています'),
               ('のこっています','残っています'),('などにしたばあい','などにした場合'),
               ('4ばい','4倍'),('しゅうりょうが','終了が'),('もーしょん','モーション'),
               ('ほかのぎょうとおなじ','他の行と同じ'),('さしこみで、','差し込みで、')]
        for source,expected in pairs:
            with self.subTest(source=source):
                r=self.run_line(source+'\t');self.assertEqual(r['corrected'],expected+'\t')
                self.assertEqual(r.get('odd_spans'),[])

    def test_small_vowel_same_key_needs_whole_word_evidence(self):
        from small_vowel_repair import proposed_keys

        source = 'ごにゅぅりょくしたきー'
        self.assertEqual(proposed_keys(source, self.a.store,
                         self.a.dict_index, self.a.decisions),
                         ())
        result = self.run_line(source + '\t')
        self.assertEqual(result['corrected'], '誤入力したキー\t')
        self.assertEqual(result.get('odd_spans'), [])
        self.assertEqual(result.get('original_spans'), [(0, 7), (9, 11)])
        self.assertEqual(result.get('spans'), [(0, 3), (5, 7)])
        for untouched in ('きゅぅん', 'きゅぅっと', 'にゅぅす',
                          'ごにゅぅりょくしたき'):
            with self.subTest(untouched=untouched):
                self.assertEqual(proposed_keys(untouched, self.a.store,
                                 self.a.dict_index, self.a.decisions), ())
        result = self.run_line(source + '\t別の入力欄')
        self.assertEqual(result['corrected'], '誤入力したキー\t別の入力欄')

    def test_ime_first_words_keep_source_meaning_and_expressive_voice(self):
        import sys
        if sys.platform!='win32':self.skipTest('Windows Japanese IME')
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('Japanese IME unavailable')
        for source,expected in (
                ('じょうほうをきょうゆうします','情報を共有します'),
                ('しごとをしゅうりょうします','仕事を終了します'),
                ('がめんをきりかえます','画面を切り替えます'),
                ('こどもにえほんをよみます','子供に絵本を読みます'),
                ('ほんをとしょかんにかえします','本を図書館に返します'),
                ('本を図書館にかぇします','本を図書館に返します'),
                ('じょぅほうをきょうゆうします','情報を共有します'),
                ('しごとをしゅぅりょうします','仕事を終了します'),
                ('がめんをきりかぇます','画面を切り替えます'),
                ('こどもにぇほんをよみます','子供に絵本を読みます'),
                ('ほんをとしょかんにかぇします','本を図書館に返します'),
                ('ないようをかくにんします','内容を確認します')):
            with self.subTest(source=source):
                result=self.run_line(source+'\t')
                self.assertEqual(result['corrected'],expected+'\t')
                self.assertEqual(result.get('odd_spans'),[])
        for source in ('本を図書館に還します','猫がふぅっと息を吐く。',
                       '思わずふぅと息をついた','きゅぅん',
                       'ぶんしょうをにゅうりょくしないようをかくにんします。'):
            with self.subTest(keep=source):
                self.assertEqual(self.run_line(source)['corrected'],source)

    def test_closed_ime_first_keeps_original_grammar_and_meaning(self):
        import sys
        if sys.platform!='win32':self.skipTest('Windows Japanese IME')
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('Japanese IME unavailable')
            for source,expected in (
                    ('しゅうりょうします','終了します'),
                    ('きょうゆうします','共有します'),
                    ('ほっかいどうにいきます','北海道に行きます'),
                    ('しょうひんをかいます','商品を買います'),
                    ('てぃっしゅをとります','ティッシュを取ります'),
                    ('でぃすぷれいをかくにんします','ディスプレイを確認します'),
                    ('ほんをとしょかんにかえします','本を図書館に返します')):
                with self.subTest(source=source):
                    result=self.run_line(source+'\t')
                    self.assertEqual(result['corrected'],expected+'\t')
                    self.assertEqual(result.get('odd_spans'),[])
            for source in ('しようひんをかいます','きようゆうします'):
                with self.subTest(missed_shift=source):
                    self.assertNotEqual(self.run_line(source+'\t')['corrected'],
                                        ime.convert(source)+'\t')
        for source in (
                'ぶんしょうをにゅうりょくしたますないようをかくにんします。',
                'がぞうのほぞんしてないようをかくにんします。'):
            with self.subTest(malformed=source):
                result=self.run_line(source+'\t')
                self.assertEqual(result['corrected'],source+'\t')
                self.assertTrue(result.get('odd_spans'))

    def test_original_continuative_clause_is_not_a_negative_attachment(self):
        # 48-APK: 入力し + 内容を確認 is a valid source-only continuation.
        source='ぶんしょうをにゅうりょくしないようをかくにんします'
        for ending in ('。', '\t'):
            with self.subTest(ending=ending):
                result=self.run_line(source+ending)
                self.assertEqual(result['corrected'],source+ending)
                self.assertEqual(result.get('odd_spans'),[])

    def test_shift_field_finishes_and_keeps_complete_source_words(self):
        import sys
        if sys.platform!='win32':self.skipTest('Windows Japanese IME')
        from ime_language import JapaneseIME
        with JapaneseIME() as ime:
            if not ime.available:self.skipTest('Japanese IME unavailable')
        for source,expected in (
                ('ちよつとまちます','ちょっと待ちます'),
                ('ていつしゆです','ティッシュです'),
                ('ていっしゅをとります','ティッシュを取ります'),
                ('でいすぷれいをかくにんします','ディスプレイを確認します'),
                ('しやしんをせんたくします','写真を選択します'),
                ('ほつかいどうにいきます','北海道に行きます'),
                ('きようゆうします','きようゆうします'),
                ('しようひんをかいます','しようひんをかいます'),
                ('ちよです','ちよです'),
                ('ちよはほんをよみます','ちよはほんを読みます')):
            with self.subTest(source=source):
                result=self.run_line(source+'\t')
                self.assertEqual(result['corrected'],expected+'\t')
                self.assertEqual(result.get('odd_spans'),[])
        source='ちよつとかえまそ'
        result=self.run_line(source+'\t')
        self.assertEqual(result['corrected'],source+'\t')
        self.assertTrue(result.get('odd_spans'))
        combined=self.run_line(source+'\tきょうゆうします\t')
        self.assertEqual(combined['corrected'],source+'\t共有します\t')
        self.assertTrue(combined.get('odd_spans'))

    def test_attested_compound_and_relative_noun_keep_independent_evidence(self):
        for source,expected in (
                ('ごにゅうりょくしたきー','誤入力したキー'),
                ('ごへんかんしたきー','誤変換したキー'),
                ('入力したきー','入力したキー'),
                ('入力するきー','入力するキー'),
                ('入力しているきー','入力しているキー'),
                ('保存したきー','保存したキー')):
            with self.subTest(source=source):
                result=self.run_line(source+'\t')
                self.assertEqual(result['corrected'],expected+'\t')
                self.assertEqual(result.get('odd_spans'),[])
        for source in ('入力したき','ご連絡した件','ご入力したキー','誤入力したキー'):
            with self.subTest(source=source):
                self.assertEqual(self.run_line(source)['corrected'],source)
        result=self.run_line('ごにゅうりょくしたきー\t無関係な答え')
        self.assertEqual(result['corrected'],'誤入力したキー\t無関係な答え')
        self.assertEqual(result.get('original_spans'),[(0,7),(9,11)])

    def test_unrelated_answer_column_cannot_supply_the_output(self):
        for annotation in ('用船','有線','無関係な文章','999999'):
            text='ゆうせんしてほせい\t'+annotation
            r=self.run_line(text)
            self.assertEqual(r['corrected'].split('\t')[0],'優先して補正')
        r=self.run_line('4ばい ⇒ 4ばい\t100倍')
        self.assertEqual(r['corrected'],'4倍 ⇒ 4倍\t100倍')

    def test_function_words_native_word_boundaries_and_explicit_choices_survive(self):
        for text in ('必要になりました。','かもしれません。','ではないでしょうか。',
                     'その後、向かいます。','なかなか進みません。','そういうことです。',
                     'ものをそのまま残す','もともとはとてもよいです。','きちんと片付けます。',
                     'うとうとしています。','やきもきしています。','たいてい大丈夫です。',
                     'よいはとてもよいです。','あとでそのままをおくります。',
                     '「もーしろょん」と入力します。','ほせいがきかない','薬がききます。','ほぞ'):
            with self.subTest(text=text):self.assertEqual(self.run_line(text)['corrected'],text)
        self.assertEqual(self.run_line('おんがくをききます。')['corrected'],'音楽を聴きます。')
        self.assertEqual(self.run_line('しゃしんをえらんでほぞんします。')['corrected'],'写真を選んで保存します。')
        self.assertEqual(self.run_line('すべてのもの')['corrected'],'すべてのもの')
        from contextual_repair import key_repairs
        self.assertFalse(any(r.operation=='adjacent_intrusion' and r.reading=='もじにゅうりょく'
                             for r in key_repairs('もんじにゅうりょく')))
        from kana_spelling import finish
        import corrector as E
        tok=E.make_tokenizer(self.a.store)
        text='ゆうせんしてほせい'
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:rd):
            self.assertEqual(finish(text,dict(corrected=text),self.a.store,tok,self.a.dict_index,self.a.decisions)['corrected'],text)
        with patch.object(E,'_check_replacement',return_value=(None,'blocked')):
            self.assertEqual(finish(text,dict(corrected=text),self.a.store,tok,self.a.dict_index,self.a.decisions)['corrected'],text)


# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch
import app,corrector,morphology as M,oddness
from tests_analysis_async import initial

@unittest.skipUnless(M.HAS_JANOME,'requires native Janome dictionary')
class UnclosedNativeSpellingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.state=initial();cls.state.context_vec=None
    def line(self,source):
        s=self.state
        return app.correct_line(source,s.store,input_method='kana',dict_index=s.dict_index,
            decisions=s.decisions,context_vec=None)
    def test_image_inputs_are_independent_and_finish_in_written_form(self):
        for source in ('入力茶う','にゅうりょくちゃう','にゅうりょくちゅう'):
            with self.subTest(source=source):
                result=self.line(source)
                self.assertEqual(result['corrected'],'入力中')
                self.assertEqual(result['odd_spans'],[])
    def test_source_line_end_does_not_become_a_fragment_boundary(self):
        source='入力茶う';parts=corrector.make_tokenizer(self.state.store)(source)
        a,b=parts[-2:]
        self.assertFalse(oddness.closed_nominal_volitional_mismatch(source,a,b))
        self.assertTrue(oddness.closed_nominal_volitional_mismatch(source,a,b,allow_line_end=True))
    def test_native_spelling_does_not_require_an_answer_field(self):
        for source,expected in (('ゆうせんしてほせい','優先して補正'),
                ('4ばい','4倍'),('もじにゅうりょく','文字入力'),('ほぞんちゅう','保存中')):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])
    def test_later_noun_is_not_split_after_an_earlier_spelling(self):
        for source,expected in (
                ('ないようをかくにんしてがぞうをほぞんします。','内容を確認して画像を保存します。'),
                ('かくにんしてがぞうをほぞんします。','確認して画像を保存します。')):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])
    def test_written_object_and_following_clause_each_supply_their_own_proof(self):
        for text,expected in (
                ('内容をかくにんしてがぞうをほぞんします。','内容を確認して画像を保存します。'),
                ('資料をせいりしてがぞうをほぞんします。','資料を整理して画像を保存します。')):
            with self.subTest(text=text):
                r=self.line(text);self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])
    def test_first_clause_cannot_certify_an_unfinished_or_conflicting_tail(self):
        import reading_segments as R
        for text in ('内容をかくにんしてがぞう','内容をかくにんしてぷねらします',
                     '内容をかくにんしてがぞうのほぞんします',
                     '日程を送電してがぞうをほぞんします'):
            with self.subTest(text=text):
                self.assertNotIn((0,len(text)),R.native_context_ranges(text))
    def test_explicit_kana_choice_and_literal_example_are_kept(self):
        text='にゅうりょくちゅう'
        with patch('last_choice.surface_for_reading',side_effect=lambda rd:rd):
            self.assertEqual(self.line(text)['corrected'],text)
        text='文字列「にゅうりょくちゅう」'
        self.assertEqual(self.line(text)['corrected'],text)
    def test_first_ime_partial_word_does_not_supply_bare_source_meaning(self):
        text='かんりょうちゅう'
        r=self.line(text);self.assertEqual(r['corrected'],text)
        self.assertEqual(r['odd_spans'],[])
    def test_native_colloquial_form_and_unresolved_source_keep_their_state(self):
        for text in ('入力ちゃう。','入力しちゃう。','お茶を飲もう。','会社に行こう。'):
            with self.subTest(text=text):
                r=self.line(text);self.assertEqual(r['corrected'],text)
                self.assertEqual(r['odd_spans'],[])
        text='ぷねらちゅう';r=self.line(text)
        self.assertEqual(r['corrected'],text);self.assertTrue(r['odd_spans'])

    def test_native_grammar_does_not_become_a_content_homophone(self):
        for text in ('増すことで解決','自然であること','ページを閉じまい',
                     '画像を保存するまい','こさせます','はわはわ',
                     'みんな下がれい。','下がれい'):
            with self.subTest(text=text):
                r=self.line(text);self.assertEqual(r['corrected'],text)
                self.assertEqual(r['odd_spans'],[])
    def test_actual_following_activity_ranks_the_same_reading_sense(self):
        for source,expected in (('すいこうしててんさく','推敲して添削'),
                ('こうせいしててんさく','校正して添削'),
                ('遂行して添削','遂行して添削'),('構成して添削','構成して添削')):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])

    def test_whole_native_action_finishes_before_a_following_clause(self):
        for source,expected in (
                ('設定をへんこうして画面を開きます。','設定を変更して画面を開きます。'),
                ('せっていをへんこうしてしりょうをほぞんします。','設定を変更して資料を保存します。'),
                ('へんこうして画面を開きます。','変更して画面を開きます。')):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])
    def test_real_conjunction_and_literal_action_remain_their_own_words(self):
        for source in ('こうして画面を開きます。','設定をこうして画面を開きます。',
                       'そうして資料を保存します。','そして画面を開きます。',
                       '文字列「へんこうして」'):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],source)
                self.assertEqual(r['odd_spans'],[])

    def test_action_and_following_object_finish_even_when_the_source_split_crosses_them(self):
        for source,expected in (
                ('しりょうをせいりしてよていをかくにんします。','資料を整理して予定を確認します。'),
                ('資料をせいりしてよていを確認します。','資料を整理して予定を確認します。'),
                ('がぞうをほぞんしてないようをかくにんします。','画像を保存して内容を確認します。')):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])
    def test_lexical_seam_does_not_certify_an_unknown_source_tail(self):
        source='資料をせいりしてぷねらを確認します。'
        r=self.line(source);self.assertEqual(r['corrected'],source)
        self.assertTrue(r['odd_spans'])
        for source in ('もんだいがかいけつし','文字列「せいりしてよてい」'):
            with self.subTest(source=source):
                r=self.line(source);self.assertEqual(r['corrected'],source)
                self.assertEqual(r['odd_spans'],[])

    def test_action_head_beats_longer_noun_only_with_source_argument(self):
        cases=(
            ('文章をせんたくして削除','文章を選択して削除'),
            ('衣服をせんたくして干します。','衣服を洗濯して干します。'),
            ('資料をせんたくして保存します。','資料を選択して保存します。'),
            ('せんたくしてかんそう','せんたくしてかんそう'),
            ('候補をせんたくして決めます。','候補をせんたくして決めます。'),
        )
        for source,expected in cases:
            with self.subTest(source=source):
                r=self.line(source)
                self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])

    def test_explicit_action_spelling_still_beats_automatic_role(self):
        def remembered(reading):return '洗濯' if reading=='せんたく' else None
        with patch('last_choice.surface_for_reading',side_effect=remembered):
            r=self.line('文章をせんたくして削除')
        self.assertEqual(r['corrected'],'文章を洗濯して削除')

    def test_proved_action_link_does_not_protect_a_crossing_conjunction(self):
        cases=(
            ('入力してかくにん','入力して確認'),
            ('にゅうりょくしてかくにん','入力して確認'),
            ('実行してかくにん','実行して確認'),
            ('文章を入力してかくにん','文章を入力して確認'),
            ('保存してから','保存してから'),
            ('「てか」を確認','「てか」を確認'),
            ('入力してかえる','入力してかえる'),
            ('入力してかう','入力してかう'),
        )
        for source,expected in cases:
            with self.subTest(source=source):
                r=self.line(source)
                self.assertEqual(r['corrected'],expected)
                self.assertEqual(r['odd_spans'],[])

    def test_unfinished_native_sahen_is_not_split_into_another_verb(self):
        source='もんだいがかいけつし'
        r=self.line(source);self.assertEqual(r['corrected'],source)
        self.assertEqual(r['odd_spans'],[])

    def test_written_object_and_native_kana_action_note_keep_the_source_reading(self):
        cases=(
            ('文章をにゅうりょくしてかくにんしてほぞん',
             '文章を入力して確認して保存'),
            ('資料をにゅうりょくしてかくにん','資料を入力して確認'),
            ('文章をそうじしてかんそう','文章をそうじしてかんそう'),
            ('文章をにゅうりょくして確認します。',
             '文章を入力して確認します。'),
        )
        for source,expected in cases:
            with self.subTest(source=source):
                r=self.line(source)
                self.assertEqual(r['corrected'],expected)
                if source==cases[0][0]:
                    self.assertEqual(r['odd_spans'],[])
                    self.assertEqual(r['original_spans'],[(3,9),(11,15),(17,20)])

    def test_written_object_and_native_finite_action_keep_source_reading(self):
        for text,expected in (
                ('文章をにゅうりょくして確認します。','文章を入力して確認します。'),
                ('文章をにゅうりょくして確定します。','文章を入力して確定します。'),
                ('文章をにゅうりょくしてほぞんします。','文章を入力して保存します。'),
                ('「文章をにゅうりょくして確認します。」',
                 '「文章をにゅうりょくして確認します。」')):
            with self.subTest(text=text):
                r=self.line(text)
                self.assertEqual(r['corrected'],expected)
                if text.startswith('文章を'):
                    self.assertEqual(r['odd_spans'],[])

    def test_native_source_spelling_respects_whole_line_rejection(self):
        for source,finished in (
                ('文章をにゅうりょくして確認します。','文章を入力して確認します。'),
                ('文章をにゅうりょくしてかくにんしてほぞん',
                 '文章を入力して確認して保存')):
            with self.subTest(source=source):
                state=initial();state.context_vec=None
                state.decisions.reject(source,finished)
                r=app.correct_line(source,state.store,input_method='kana',
                    dict_index=state.dict_index,decisions=state.decisions,
                    context_vec=None)
                self.assertEqual(r['corrected'],source)

if __name__=='__main__':unittest.main()