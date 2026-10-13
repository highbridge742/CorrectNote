# -*- coding: utf-8 -*-
"""2026-10-11 の補正の見直し（項目48-CA〜48-CS）の回帰テスト。

初期状態（`tests_analysis_async.initial`）で、かな入力の行を
`correction_entry.correct_line` に通す。IME は使わない。
"""
import unittest

import morphology as M


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class CorrectionReview20261011Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from tests_analysis_async import initial
        cls.state = initial()

    def setUp(self):
        from last_choice import set_active
        self.addCleanup(set_active, None)

    def run_line(self, line):
        from correction_entry import correct_line
        a = self.state
        return correct_line(line, a.store, context_vocab={}, input_method='kana',
                            dict_index=a.dict_index, decisions=a.decisions,
                            context_vec=a.context_vec)

    def test_broken_polite_predicates_are_repaired(self):
        # 48-CP（文末の ます の直前）・48-CQ（前置きの句）・48-CR（が の主語）・48-CS
        for source, expected in (
                # Windows では IME が名詞も漢字にする（どちらも正しい直し先）
                ('へやのそうじをとました', ('へやのそうじをしました', '部屋の掃除をしました')),
                ('こうえんでさんぽをとました', ('こうえんでさんぽをしました', '公園で散歩をしました')),
                ('にもつがとどきしまた', '荷物が届きました'),
                ('パソコンがこわれまとた', 'パソコンが壊れました'),
                # 48-CS（述語の語尾の中の1打抜け）
                ('あさごはんをたべまた', '朝ご飯を食べました'),
                ('びょういんにいきす', '病院に行きます'),
                ('パソコンがこわれまし', 'パソコンが壊れました')):
            with self.subTest(source=source):
                if isinstance(expected, tuple):
                    self.assertIn(self.run_line(source)['corrected'], expected)
                else:
                    self.assertEqual(self.run_line(source)['corrected'], expected)

    def test_polite_tail_after_non_continuative_is_marked(self):
        # 48-CP: ます の直前が連用形の字でない（いはます）。直せなくても紫は立てる。
        row = self.run_line('らいしゅうりょこうにいはます')
        self.assertTrue(row['odd_spans'])

    def test_polite_tail_rule_leaves_real_words_alone(self):
        from pos_grammar import _polite_tail_after_non_renyou_spans as spans
        for line in ('ますますさむくなります。', 'はしのました', 'さけとます',
                     'ぶんたいはですます。', 'あしたはやすみます。', 'いきますか？',
                     'たべませんでした', 'あそびましょう'):
            with self.subTest(line=line):
                self.assertEqual(spans(line), ())

    def test_distributive_goto_after_okurigana_noun(self):
        # 48-CN': 区切りごとに は紫にしないが、かなだけの しごと の打ち間違いは紫のまま。
        self.assertEqual(self.run_line('背景の区切りごとに文字を抜き出す')['odd_spans'], [])
        self.assertTrue(self.run_line('しごとがいがそしいです')['odd_spans'])

    def test_natural_sentences_stay_unchanged(self):
        for line in ('こうえんでさんぽをしました', 'もうすこしまってください。',
                     'ゆっくりやすんでください。', 'しゃしんをとりました。'):
            with self.subTest(line=line):
                row = self.run_line(line)
                self.assertEqual(row['odd_spans'], [])

    def test_bare_head_before_suru_is_marked_alone(self):
        # 48-CU: くるまの・かぎを・しました は成立し、にく だけが残る。
        row = self.run_line('くるまのかぎをにくしました')
        self.assertEqual(row['corrected'], 'くるまのかぎを無くしました')
        from pos_grammar import _bare_head_before_suru_spans as spans
        self.assertEqual(spans('くるまのかぎをにくしました', self.state.dict_index), ((7, 9),))

    def test_subject_becomes_misread_noun(self):
        # 48-CV: 〜が＋名詞＋になる の名詞が「じゃの」と打ち間違えられた。
        row = self.run_line('処理がじゃのになっていないだろうか')
        self.assertEqual(row['corrected'], '処理が邪魔になっていないだろうか')
        for line in ('処理が邪魔になっていないだろうか', 'これがきになっています。'):
            self.assertEqual(self.run_line(line)['corrected'], line)

    def test_attributive_like_before_particle_is_marked(self):
        # 48-CW: 「ような＋助詞」で終わる並びは連体形の後ろに名詞がない。
        # 行の終わり（打っている途中: ようなも＋の）は見ない。区切りで閉じたときだけ。
        row = self.run_line('きりがないようなも。')
        self.assertIn(row['corrected'], ('きりがないようにも。', 'キリがないようにも。'))  # Windows の IME は キリ
        from pos_grammar import _attributive_before_particle_spans as spans
        self.assertTrue(spans('きりがないようなも　　（キリがないようにも）'))
        self.assertFalse(spans('きりがないようなも'))
        for line in ('キリがないようにも', 'ゆめのようなもの。', 'ねこみたいなもの。', 'このようなことも'):
            self.assertEqual(self.run_line(line)['corrected'], line)
            self.assertFalse(spans(line), line)

    def test_sound_heads_before_suru_are_left_alone(self):
        from pos_grammar import _bare_head_before_suru_spans as spans
        for line in ('かぎをなくしました', 'しゅくだいをしました', 'ともだちにでんわしました',
                     'もじをおおきくしました', 'かれはがっかりしました', 'ゆっくりしました',
                     'よろしくおねがいします', 'ごめいわくをおかけしました', 'おまたせしました',
                     'けがをしました', 'ねぼうしました', 'どうしました', 'どきどきしました',
                     'へやをきれいにしました', 'みちをさがしました', 'ごれんらくします'):
            with self.subTest(line=line):
                self.assertEqual(spans(line, self.state.dict_index), ())

    def test_inverse_reading_keeps_written_words(self):
        # 48-CT: IME の逆読みは、書かれた語（処理速度・スレッド・取り消し線・※）を
        # 成立した塊として残し、残りだけを かなの文法で見る。
        from unittest.mock import patch
        import ime_inverse_gate as I
        from corrector import make_tokenizer
        from morphology import katakana_to_hiragana
        tokenize = make_tokenizer(self.state.store)

        def reading(surface):
            return ''.join(katakana_to_hiragana(t[2] or t[0]) if t[5] else t[0]
                           for t in tokenize(surface))

        class IME:
            available = True
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def reverse_words(self, s): return None
            def phonetic(self, s): return reading(s)
            def convert(self, r): return IME.fields.get(r)

        class Search:
            available = False
            def __enter__(self): return self
            def __exit__(self, *a): return False

        for line, field, whole_odd in (
                ('処理速度が犠牲になっていないか確認して。', '処理速度が犠牲になっていないか確認して', True),
                ('スレッドを新しくしているせいだと思う。', 'スレッドを新しくしているせいだと思う', False),
                ('取り消し線をメモ欄に付けたら、', '取り消し線をメモ欄に付けたら', True)):
            with self.subTest(line=line):
                IME.fields = {reading(field): field}
                # 読みだけを かなの文法で見ると、節まるごとが説明できない
                from pos_grammar import odd_kana_spans
                if whole_odd:
                    self.assertTrue(odd_kana_spans(reading(field) + '\t',
                                                   self.state.dict_index, self.state.store))
                with patch('ime_language.JapaneseIME', IME), \
                        patch('ime_candidates.SearchCandidates', Search):
                    self.assertEqual(I.anomalous_source_fields(
                        line, tokenize, self.state.store, self.state.dict_index), ())
        # 1字の漢字の切れ端（旧|明|井）は書かれた語として残さない
        self.assertEqual(I._written_unit_spans('旧明井します', tokenize), ())


    def test_ime_field_repairs_to_its_own_search_candidate(self):
        # 48-CX: IME が かなの誤字（きりがないようなも）を 霧が内容名も と変換した欄は、
        # 直した読み（きりがないようにも）の IME の候補を直し先に使う。
        # 2つ以上の空白（全角含む）は欄の区切り。
        from unittest.mock import patch
        import ime_inverse_gate as I
        from corrector import make_tokenizer
        tokenize = make_tokenizer(self.state.store)
        fields = {'きりがないようなも': '霧が内容名も', 'きりがないようにも': 'キリがないようにも'}
        readings = {v: k for k, v in fields.items()}

        class IME:
            available = True
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def reverse_words(self, s):
                r = readings.get(s)
                return (r, ((0, len(s), 0, len(r), '', 0),)) if r else None
            def phonetic(self, s): return readings.get(s)
            def convert(self, r): return fields.get(r)
            def convert_words(self, r):
                c = fields.get(r)
                return (c, ((0, len(c), 0, len(r), '', 0),)) if c else None

        class Search:
            available = True
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def candidates(self, r): return [fields[r]] if r in fields else []

        with patch('ime_language.JapaneseIME', IME), \
                patch('ime_candidates.SearchCandidates', Search):
            self.assertEqual(self.run_line('霧が内容名も')['corrected'], 'キリがないようにも')
            line = '霧が内容名も　　（キリがないようにも）'
            self.assertEqual([line[a:b] for a, b, r in I.anomalous_source_fields(
                line, tokenize, self.state.store, self.state.dict_index)], ['霧が内容名も'])


    def test_clause_object_of_mau_becomes_matsu(self):
        # 48-CY: 舞う は「〜のを」の節を目的語に取らない。同じ て形の 待つ に直る。
        # い抜きの 待ってられない も ていられない と同じ述語として確かめる。
        for source, expected in (
                ('補正が適用されるのを舞ってられないので、', '補正が適用されるのを待ってられないので、'),
                ('彼が来るのを舞った。', '彼が来るのを待った。')):
            with self.subTest(source=source):
                self.assertEqual(self.run_line(source)['corrected'], expected)
        for line in ('雪が舞っているので、外に出ない。', '鳥が空を舞っている。', '彼女は舞を舞った。',
                     '落ち葉が舞うのを眺めていた。', '雨がやむのを待ってられないので、出かけた。',
                     'それを捨てられないので、取っておく。', '見てられないので目をそらした。'):
            with self.subTest(line=line):
                row = self.run_line(line)
                self.assertEqual(row['corrected'], line)
                self.assertFalse(row.get('odd_spans'))


    def test_broken_polite_tail_is_marked(self):
        # 48-CZ: 連用形の後ろの ます類 が1字崩れて文が終わる（いきまか・いきす）。
        from pos_grammar import _broken_polite_tail_spans as spans
        di = self.state.dict_index
        self.assertEqual(spans('えきまでむかえにいきまか', di), ((10, 12),))
        self.assertEqual(spans('へんじをまっていまか', di), ((8, 10),))
        self.assertEqual(spans('らいしゅうりょこうにいきす', di), ((12, 13),))
        for line in ('それはいまか。', 'あたまか', 'ほんをかえす', 'かれをゆるす', 'めをさます',
                     'えきまでむかえにいきますか', 'へんじをまっています', 'ことばをかわす'):
            self.assertEqual(spans(line, di), (), line)

    def test_loanword_head_before_suru_is_sound(self):
        # 48-CU の続き: かなで打った外来語（ぷれい＝プレイ）＋します は壊れていない。
        from pos_grammar import _bare_head_before_suru_spans as spans
        self.assertEqual(spans('ぷれいします', self.state.dict_index), ())
        self.assertEqual(spans('すきゃんします', self.state.dict_index), ())


    def test_doubled_particle_is_marked(self):
        # 48-DA: 助詞1字が2回続く（へやののそうじ）。2つ目が次の語の頭なら見ない。
        from pos_grammar import _doubled_particle_spans as spans
        di = self.state.dict_index
        self.assertEqual(spans('へやののそうじをしました', di), ((3, 4),))
        self.assertEqual(spans('くるまのかぎををなくしました', di), ((7, 8),))
        for line in ('かれががっこうにいく', 'そこににもつをおく', 'しっぱいしたものの、またやる',
                     'あいてをののしる', 'ねこののみ', 'ににんさんきゃくではしる', '本ののこり'):
            self.assertEqual(spans(line, di), (), line)


    def test_permission_tail_is_composed_and_te_desu_is_not_made(self):
        # 48-DB: ても／てもいい は述語の語尾。2打の置き換えで いて＋です（射手です）を作らない。
        for source in ('まどをあけいもいいですか', 'まどをけあてもいいですか'):
            with self.subTest(source=source):
                row = self.run_line(source)
                self.assertNotIn('射手', row['corrected'])
                self.assertIn(row['corrected'], ('窓を開けてもいいですか', 'まどをあけてもいいですか'))

    def test_intrusion_is_not_justified_by_a_doubled_key(self):
        # 48-DC: か|きき の か を消して 聞きました にしない（連打の直しは本人の指定でオフ）。
        import contextual_repair as CR
        self.assertNotIn('ききました', [r.reading for r in CR.key_repairs('かききました')])
        self.assertNotIn('聞', self.run_line('てがみをかききました')['corrected'])
        self.assertIn('たべました', [r.reading for r in CR.key_repairs('たべまさした')])

    def test_fragment_beside_written_units_keeps_the_field_open(self):
        # 48-DD: 断片（的|買い・じ|ゆ|ぅに|設定）があれば、書かれた語を残さず
        # 欄の逆読みをまるごと見る。
        import ime_inverse_gate as I
        from corrector import make_tokenizer
        tokenize = make_tokenizer(self.state.store)
        for field in ('的買い', 'じゆぅに設定'):
            units = I._written_unit_spans(field, tokenize)
            self.assertTrue(I._orphan_fragment_outside(field, units, tokenize), field)
        for field in ('処理速度が犠牲になっていないか確認して', '取り消し線をメモ欄に付けたら'):
            units = I._written_unit_spans(field, tokenize)
            self.assertFalse(I._orphan_fragment_outside(field, units, tokenize), field)

    def test_question_is_not_attached_to_an_imperative(self):
        # 48-DE: くださいい を くださいか にしない（命令形＋か は作らない）。
        self.assertNotIn('くださいか', self.run_line('でんきをけしてくださいい')['corrected'])

    def test_tied_core_follows_the_object_of_the_next_predicate(self):
        # 48-DF: ししん の拮抗は、後ろの「をとりました」の目的語として合う 写真 に決める。
        self.assertEqual(self.run_line('ししんをとりました')['corrected'], '写真を撮りました')

    def test_terminal_form_before_purpose_ni_is_repaired(self):
        # 48-DG: 目的の に は連用形に付く。終止形＋に＋行く は崩れ。
        from pos_grammar import _terminal_before_purpose_spans as spans
        di = self.state.dict_index
        self.assertEqual(spans('むかうにいきます', di), ((2, 4),))
        for line in ('かいにいきます', 'あそびにいきます', 'いくにいけない', 'うみにいきます'):
            self.assertEqual(spans(line, di), (), line)
        self.assertEqual(self.run_line('えきにむかうにいきます')['corrected'], '駅に迎えにいきます')

    def test_unshifted_wo_is_marked_and_repaired(self):
        # 48-DH: を は Shift＋わ。Shift が抜けた わ を戻すと並びがまるごと成り立つ。
        from pos_grammar import _unshifted_wo_spans as spans
        di = self.state.dict_index
        self.assertEqual(spans('てがみわかきました', di), ((3, 4),))
        for line in ('ほんわかしました', 'でんわかけます', 'きょうはいくわ', 'にわでかきました'):
            self.assertEqual(spans(line, di), (), line)
        self.assertEqual(self.run_line('ほんわよみました')['corrected'], '本を読みました')

    def test_noun_reading_is_not_a_verb_stem(self):
        # 48-DI: びょう（病・秒）を五段の動詞として びょ＋え に活用させない。
        from pos_grammar import explain_kana_run
        self.assertFalse(explain_kana_run('びょえいんにいきます'))
        for run in ('もうかりました', 'ちがえました', 'かいにいきます'):
            self.assertTrue(explain_kana_run(run), run)

    def test_transposed_polite_past_is_repaired(self):
        # 48-DJ: ました の し と た が入れ替わった またし を紫にして戻す。
        self.assertEqual(self.run_line('にもつがとどきまたし')['corrected'], '荷物が届きました')

    def test_one_key_broken_polite_ending_is_repaired(self):
        # 48-DK: ください・ですか… が1打だけ崩れた文末を紫にして戻す。
        from pos_grammar import _broken_polite_end_spans as spans
        di = self.state.dict_index
        self.assertEqual(spans('でんきをけしてくだそい', di), ((6, 11),))
        for line in ('でんきをけしてください', 'あしたはあめですか', 'ほんをよみました'):
            self.assertEqual(spans(line, di), (), line)
        self.assertEqual(self.run_line('でんきをけしてくだそい')['corrected'], '電気を消してください')
        # 1字の打ち落とし（たべ［ま］した）と、崩れた字を消すだけで問いを落とさないこと
        self.assertEqual(self.run_line('あさごはんをたべした')['corrected'], '朝ご飯を食べました')
        self.assertEqual(self.run_line('まどをあけてもいいでかす')['corrected'], '窓を開けてもいいですか')
        for line in ('ふくをかえした', 'みずをください', 'あめですが', '気持ちを新たにした。'):
            self.assertEqual(spans(line, di), (), line)

    def test_voiced_kana_transposition_is_one_slip(self):
        # 48-DL: じ は2打でも、並べ違いは字の単位（そじう＝そうじ）。死蔵 にしない。
        import contextual_repair as CR
        self.assertIn('そうじ', [r.reading for r in CR.key_repairs('そじう')])
        self.assertEqual(self.run_line('へやのそじうをしました')['corrected'], '部屋の掃除をしました')

    def test_plain_noun_before_na_is_marked(self):
        # 48-DM: ただの名詞＋な＋名詞（かいしゃなでんわ）は紫。形容動詞・な で終わる語は見ない。
        from pos_grammar import _plain_noun_before_na_spans as spans
        di = self.state.dict_index
        self.assertEqual(spans('かいしゃなでんわをかけます', di), ((4, 5),))
        for line in ('げんきなこども', 'きれいなはな', 'みんななかよし', 'かいしゃなので', 'ひまなとき',
                     'しずかじゃなさすぎます', 'ひものながさをはかります。'):
            self.assertEqual(spans(line, di), (), line)


    def test_style_and_honorific_runs_stay_unmarked(self):
        # くださぃ（小さい仮名の崩し）は 48-DK で見ない。名詞の読みを止めるのは
        # 言い切り以外の形だけ（とうちゃく＋まち・お＋まち は前どおり読む）。
        from pos_grammar import odd_kana_spans, explain_kana_run
        di = self.state.dict_index
        for line in ('歩いてくださぃ。', 'おまちくださいませ。', 'とうちゃくまちでうす。'):
            self.assertEqual(odd_kana_spans(line, dict_index=di), [], line)
        self.assertEqual(self.run_line('歩いてくださぃ。')['corrected'], '歩いてくださぃ。')
        self.assertFalse(explain_kana_run('びょえいんにいきます'))
        # まか は ます に戻す（既存の試験どおり）
        self.assertIn(self.run_line('まどをしめてからほんをよみまか。')['corrected'],
                      ('窓をしめてから本を読みます。', '窓を閉めてから本を読みます。'))  # Windows の IME は 閉めて
        from pos_grammar import _broken_polite_end_of_run
        self.assertIsNone(_broken_polite_end_of_run('かんごしまち', di))  # まち は語の読み
        self.assertIsNone(_broken_polite_end_of_run('ほんをよみますぅ', di))  # ぅ は ますか の崩れではない

    def test_tail_swap_object_proof_and_permission_te(self):
        # 48-DN: 語の終わりの字を消す直し（しんぶんよ→新聞＋を見ます）は、並べ違い（よを＝をよ）
        # でも読めるなら採らない（読む を 見る に替えない）
        self.assertNotIn('見', self.run_line('しんぶんよをみます')['corrected'])
        # 48-DO: 文末の語尾の崩れを戻すだけの直しは、原文の目的語と述語をそのまま使う
        self.assertEqual(self.run_line('にほんごをべんきょうしいてます')['corrected'],
                         '日本語をべんきょうしています')
        # 48-DK: 語尾に近い助詞の後ろだけで確かめる・ていました の て の打ち落とし
        self.assertEqual(self.run_line('パソコンがこわれのした')['corrected'], 'パソコンが壊れました')
        self.assertEqual(self.run_line('やくそくをわすれいました')['corrected'], 'やくそくをわすれていました')
        self.assertEqual(self.run_line('ひとがいました')['corrected'], '人がいました')
        # 48-DP: 〜たもいい の た は て の打ち間違い
        from pos_grammar import _ta_for_te_permission_spans as spans
        di = self.state.dict_index
        self.assertEqual(spans('まどをあけたもいいですか', di), ((5, 6),))
        for line in ('これはまたもいい', 'かいたものがいい', 'あけてもいいですか'):
            self.assertEqual(spans(line, di), (), line)
        self.assertEqual(self.run_line('よんだもいい')['corrected'], '読んでもいい')

    def test_homophone_reselection_is_kept_with_its_neighbors(self):
        # うにさんの指定（2026-10-12）: 買える→変える を語だけで覚えると 金で買える が
        # 通らなくなる。同じ読みの別の語への選び直しは前後の語ごとに覚える
        import last_choice as L
        lc = L.LastChoiceStore()
        lc.bind(store=self.state.store, dict_index=self.state.dict_index)
        self.assertTrue(lc.record('買える', '変える', 'かえる', 'よって', '。'))
        self.assertEqual(lc.readings(), {})
        self.assertIsNone(lc.lookup('買える'))
        self.assertIsNone(lc.lookup('買える', '金で', '。'))
        self.assertEqual(lc.lookup('買える', 'よって', '。'), '変える')
        rec = [r for r in lc.all_records() if r['kind'] == 'context']
        self.assertEqual(rec[0]['original'], 'よって買える。')
        self.assertTrue(lc.forget_record(rec[0]))
        # 読みの違う選び直し・かなからの選び直しは前どおり
        lc.record('原文', '元気', 'げんき')
        self.assertEqual(lc.lookup('原文'), '元気')
        lc.record('こうえん', '講演', 'こうえん')
        self.assertEqual(lc.readings().get('こうえん'), '講演')

if __name__ == '__main__':
    unittest.main()
