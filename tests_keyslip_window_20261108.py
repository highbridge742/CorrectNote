# -*- coding: utf-8 -*-
"""keyslip_window（かな入力の1キーの打ち違い・巻き込みで崩れた語の並びを打鍵の単位で戻す・2026-11-08 手分けB）。
例は作った文。"""
import os
import unittest

import keyslip_window as K


def fixed(text):
    """直しを置いた行（紫だけの所はそのまま）。"""
    out = text
    for s, e, face, _src in sorted(K.propose(text), key=lambda m: -m[0]):
        if face:
            out = out[:s] + face + out[e:]
    return out


class KeyUnits(unittest.TestCase):
    def test_voiced_key_neighbour(self):
        # じ＝し＋゛。し の隣の と を打つと ど（字では じ→ど の2つの違いに見える）
        self.assertIn('へんじ', K._variants('へんど'))

    def test_shift_and_neighbour(self):
        # や の Shift 忘れ＋ゃ と ゅ の隣（ちやくしゃ → ちゃくしゅ）
        self.assertIn('ちゃくしゅ', K._variants('ちやくしゃ'))

    def test_rolled_in_key(self):
        self.assertIn('これから', K._variants('これかにら'))
        self.assertIn('がいとうのはんいを', K._variants('がいとうあのはんいを'))

    def test_double_press_is_not_rollin(self):
        # 同じ字の2度押しは別の型（まとめない）
        self.assertNotIn('かたい', K._variants('かたたい', drops_only=True))


class Lines(unittest.TestCase):
    def test_rare_noun_run(self):
        self.assertEqual(fixed('先方の質問に変度を書いた'), '先方の質問に返事を書いた')
        self.assertEqual(fixed('来週から工事に血役者する'), '来週から工事に着手する')

    def test_particle_slip_before_noun_run(self):
        self.assertEqual(fixed('メモなどの下場合は保存する'), 'メモなどにした場合は保存する')

    def test_rolled_in_fragments(self):
        self.assertEqual(fixed('これカニら会議に出ます'), 'これから会議に出ます')
        self.assertEqual(fixed('こみれから家に帰る'), 'これから家に帰る')

    def test_kana_line(self):
        self.assertEqual(fixed('がいとうあのはんいをえらぶ'), '該当の範囲を選ぶ')

    def test_correct_lines_untouched(self):
        for s in ('返事を書いた', 'これから会議に出ます', 'メモなどにした場合は保存する', '該当の範囲を選ぶ',
                  '来週から工事に着手する', '明日って何時集合だっけ。', 'お昼何食べる？', 'いま駅に着いたよ。',
                  '図書館で借りた本を今日返しに行く', '来期の予算案を作成中です。', '週末は家でのんびりしてた',
                  'せんたくものをそとにほしておいた', 'らいげつのよさんをとりあげてはなしあう。',
                  'ご不明な点があれば、いつでもお気軽にお声がけください', 'ちゃんと戸締まりしといてね'):
            self.assertEqual(K.propose(s), [], s)

    def test_inflected_kanji_not_touched(self):
        # 漢字の活用する語（取り掛か｜する）は窓に入れない（送り仮名・活用の直しは別の段）
        self.assertNotIn('取り掛かする', [m[3] for m in K.propose('会議に取り掛かする。')])

    def test_switch(self):
        os.environ['CN_KEYSLIP_WINDOW'] = '0'
        try:
            self.assertEqual(K.propose('先方の質問に変度を書いた'), [])
        finally:
            del os.environ['CN_KEYSLIP_WINDOW']


class Records(unittest.TestCase):
    def test_mark_apart_in_record(self):
        # 打った記録で ゛ が字から離れている形（へんと゛）も、前の字に付けてから戻す
        self.assertEqual(K._compose_marks('へんと゛'), 'へんど')
        self.assertEqual(K._compose_marks('て゛んじ'), 'でんじ')
        self.assertEqual(K._compose_marks('゛んじ'), '゛んじ')
        import kanji_guess
        rec = {'変度': ['へんと゛']}
        kanji_guess.set_ime_readings_provider(lambda f: rec.get(f, []))
        try:
            self.assertEqual(fixed('先方の質問に変度を書いた'), '先方の質問に返事を書いた')
        finally:
            kanji_guess.set_ime_readings_provider(None)


class VerbChain(unittest.TestCase):
    def test_rare_second_verb(self):
        # つくり｜のす: ます の ま の所で隣の の
        self.assertEqual(fixed('シチューをつくりのす'), 'シチューをつくります')

    def test_compound_verbs_untouched(self):
        for s in ('げんかんのかぎをしめわすれた', 'あたらしいせいどのせつめいかいをかいさいします。',
                  'このねはきどうじにいちどだけよみこむ。', 'とりひきさきのいこうをかくにんしたうえではんだんします。',
                  'シチューをつくりなおす'):
            self.assertEqual(K.propose(s), [], s)


class RareWord(unittest.TestCase):
    """紫の付いた珍しい2字の漢語（作った例: 連接）。1キーの戻し先（隣接・面接・建設）のうち、同じファイルタブに
    書かれている語が1つだけならそれに直す。書かれていなければ紫のまま。"""
    LINE = '・連接キーの打ち違えを直す'

    def _with(self, ctx):
        tok = K.DOC_CONTEXT.set(ctx)
        try:
            return K.propose(self.LINE, odd=[(1, 3)])
        finally:
            K.DOC_CONTEXT.reset(tok)

    def test_word_in_tab(self):
        self.assertEqual(self._with({'りんせつ': ('隣接', 'その他')}), [(1, 3, '隣接', '連接')])

    def test_no_word_in_tab(self):
        self.assertEqual(self._with(None), [])
        self.assertEqual(self._with({'はれ': ('晴れ', 'その他')}), [])

    def test_two_words_in_tab(self):
        self.assertEqual(self._with({'りんせつ': ('隣接', 'その他'), 'めんせつ': ('面接', 'その他')}), [])

    def test_homophone_left_to_other_stage(self):
        # 同じ読みに身近な語が在る（捨身／写真）のは変換の選び違いの型なので、この段は見ない
        tok = K.DOC_CONTEXT.set({'しゃいん': ('社員', 'その他')})
        try:
            self.assertEqual(K.propose('捨身を並べて飾った', odd=[(0, 2)]), [])
        finally:
            K.DOC_CONTEXT.reset(tok)

    def test_switch(self):
        os.environ['CN_KEYSLIP_RARE_WORD'] = '0'
        try:
            self.assertEqual(self._with({'りんせつ': ('隣接', 'その他')}), [])
        finally:
            del os.environ['CN_KEYSLIP_RARE_WORD']


class Gates(unittest.TestCase):
    """直し先が語として組めないときは直さない（2026-11-08 v4）。例は作った文。"""

    def test_glued_kanji_words(self):
        # 品詞の違う漢字の語がかなを挟まずに並ぶ（副詞＋名詞）のは崩れ
        self.assertTrue(K._odd_tokens('如何軸'))
        self.assertFalse(K._odd_tokens('家族'))

    def test_solo_in_record(self):
        os.environ["CN_KEYSLIP_SOLO_REC"] = "1"
        self.addCleanup(os.environ.pop, "CN_KEYSLIP_SOLO_REC", None)
        # 打った記録が2語をまたいでも、読みが1字の語（氏＝し）の字は抜かない
        from morphology import tokenize
        toks = list(tokenize('朝氏'))
        self.assertEqual(K._solo_in_record('朝氏', toks, 'あさし'), frozenset({2}))

    def test_suru_before_noun(self):
        # する の連用形のすぐ後ろに名詞は文の形にならない
        line = '予定をし家族で話す'
        self.assertFalse(K._clean(line, 2, 6, 'を以下族'))

    def test_placed_word_familiar(self):
        # 置いた行で1語に読まれた所が身近でない（安｜さ）
        line = '手紙と安さが届いた'
        self.assertFalse(K._clean(line, 3, 5, '矢伊佐'))

    def test_pair_misfit(self):
        # 置いた名詞（よく出る）と後ろの述語（よく出る）の組が例文に1度も無い
        from morphology import tokenize
        t = list(tokenize('的を開ける'))
        self.assertTrue(K._pair_misfit(t, 0))
        t = list(tokenize('窓を開ける'))
        self.assertFalse(K._pair_misfit(t, 0))

    def test_unsure_purple(self):
        # 戻せば行が良くなるのに戻し先が語として組めない並び（以下｜族）は紫だけ
        self.assertEqual(K.propose('旅行の予定を以下族で話し合った'), [(6, 9, None, '以下族')])

    def test_unsure_not_on_word_split(self):
        # 1語の正しい語が 誤判｜定 のように切れる所（判定 が身近）には紫を付けない
        self.assertEqual(K.propose('・誤判定'), [])
        self.assertEqual(K.propose('誤判定の例を集める'), [])

    def test_swap_rival(self):
        # 隣り合う2字の入れ替え（かさな → さかな）でも良い語に組めるなら、1キーの戻しと決めきれないので紫だけ
        self.assertEqual(K.propose('近所の店で新鮮な傘名を安く変えた'), [(8, 10, None, '傘名')])
        os.environ['CN_KEYSLIP_SWAP_RIVAL'] = '0'
        try:
            self.assertEqual(K.propose('近所の店で新鮮な傘名を安く変えた'), [(8, 10, '加算', '傘名')])
        finally:
            del os.environ['CN_KEYSLIP_SWAP_RIVAL']

    def test_purple_spot_kanji_rival(self):
        # 前の段が紫にした所で、語の確かめで落ちた漢字の戻し方（三時から）のほうが良いなら決めない（後ろの段に任せる）
        got = K.propose('会議室の予約を差化時から取っておきます', [(7, 10)])
        self.assertTrue(got and all(m[2] is None for m in got), got)
        self.assertTrue(K._kanji_core('三時から', '差化時から'))
        self.assertFalse(K._kanji_core('好きは', '駅派'))

    def test_purple_spot_margin(self):
        # 紫の所では2番目の候補との差を広く求める（変化／本 は決めない・返事／本土 は決める）
        import kanji_guess
        kanji_guess.set_ime_readings_provider(lambda s: {'本化': ['ほんか'], '本化を': ['ほんかを']}.get(s, []))
        try:
            got = K.propose('図書館で借りた本化を強化絵師に行く', [(7, 9)])
        finally:
            kanji_guess.set_ime_readings_provider(lambda s: [])
        self.assertTrue(got and all(m[2] is None for m in got), got)
        self.assertEqual(K.propose('先方の質問に変度を書いた', [(6, 8)]), [(6, 8, '返事', '変度')])

    def test_no_new_lone_kanji(self):
        # 元に無い1字の漢字の語は、数（四）や例文で1語として使われない字（工）なら作らない
        self.assertFalse(K._clean('会議室の四を取る', 4, 6, '余屋を'))
        self.assertFalse(K._clean('飛行機が工になった', 3, 6, '掛け校'))

    def test_particle_not_from_kanji(self):
        # 漢字の所（掛）から助詞（が）を作らない。かなの所（の）からはよい（の下 → にした）
        self.assertFalse(K._clean('飛行機が無効になった', 3, 6, '掛け校'))
        self.assertTrue(K._clean('メモなどにした場合', 4, 7, 'の下'))

    def test_switch_unsure(self):
        os.environ['CN_KEYSLIP_UNSURE_PURPLE'] = '0'
        try:
            self.assertEqual(K.propose('旅行の予定を以下族で話し合った'), [])
        finally:
            del os.environ['CN_KEYSLIP_UNSURE_PURPLE']


class Evening(unittest.TestCase):
    """2026-11-08 夕方の手分けB（作った例）。"""

    def test_bad_small_kana(self):
        # 小さい ゅ は い段の字の後ろだけ（と｜ゅ は成り立たない）。その所だけ戻す
        self.assertEqual(K.propose('しとゅうがくりょこうにいく'), [(0, 13, '修学旅行に行く', 'しとゅうがくりょこうにいく')])
        # 決まらなければ紫（その字の前後だけ）
        self.assertEqual(K.propose('あしたはしとゅうがくです'), [(5, 7, None, 'とゅ')])
        for s in ('きょうはびょういんにいく', 'しゅくだいをする'):
            self.assertEqual(K.propose(s), [], s)

    def test_tail_particle(self):
        # 終助詞の後ろの助詞（よね｜も: ね の隣の も の巻き込み）
        self.assertEqual(K.propose('明日ならできるよねも'), [(7, 10, 'よね', 'よねも')])
        for s in ('それもいいかも', 'そうだよねえ', '明日ならできるよね。'):
            self.assertEqual(K.propose(s), [], s)

    def test_chain_raw(self):
        # 打ったままが組めない 動詞＋動詞（たべ｜のまし｜た）。前の動詞は動詞のまま
        self.assertEqual(K.propose('箱にいれのました'), [(2, 8, '入れました', 'いれのました')])
        self.assertEqual(K.propose('このねはきどうじにいちどだけよみこむ。'), [])

    def test_odd_hira(self):
        # 前の段が紫にした ひらがなの並び（かいす｜せき）で巻き込みの抜き
        self.assertEqual(K.propose('データのかいすせきがおわった', [(7, 9)]), [(4, 9, '解析', 'かいすせき')])
        self.assertEqual(K.propose('データのかいすせきがおわった'), [])

    def test_switches(self):
        for env, line in (('CN_KEYSLIP_BAD_KANA', 'しとゅうがくりょこうにいく'), ('CN_KEYSLIP_TAIL_PARTICLE', '明日ならできるよねも'),
                          ('CN_KEYSLIP_CHAIN_RAW', '箱にいれのました')):
            os.environ[env] = '0'
            try:
                self.assertEqual(K.propose(line), [], env)
            finally:
                del os.environ[env]


class NumeralSlip(unittest.TestCase):
    """数の字が打ち違いから出た形（作った例）。correction_entry._keep_numerals がこれを見て数を守らない。"""

    def _with(self, rec, fn):
        import kanji_guess
        kanji_guess.set_ime_readings_provider(lambda s: rec.get(s, []))
        try:
            return fn()
        finally:
            kanji_guess.set_ime_readings_provider(lambda s: [])

    def test_slip(self):
        self.assertTrue(self._with({'貸す九人': ['かすくにん']}, lambda: K.numeral_slip('内容を貸す九人する', 3, 7, '確認')))

    def test_plain_count_kept(self):
        self.assertFalse(self._with({'三人': ['さんにん']}, lambda: K.numeral_slip('三人で行く', 0, 2, '参院')))

    def test_katakana_piece_kept(self):
        self.assertFalse(self._with({'ミウ一': ['みういち']}, lambda: K.numeral_slip('寒いからミウ一撒いて', 4, 7, '身内')))

    def test_no_record(self):
        # 打った記録が無い行（v11）: 数の字の読み（九＝く）でも見る
        self.assertTrue(self._with({}, lambda: K.numeral_slip('貸す九人', 0, 4, '確認')))
        self.assertTrue(self._with({}, lambda: K.numeral_slip('内容を貸す九人する', 3, 7, '確認')))

    def test_no_record_count_kept(self):
        self.assertFalse(self._with({}, lambda: K.numeral_slip('九人で行く', 0, 2, '区人')))
        self.assertFalse(self._with({}, lambda: K.numeral_slip('寒いからミウ一撒いて', 4, 7, '身内')))

    def test_no_record_switch(self):
        os.environ['CN_KEYSLIP_NUM_READ'] = '0'
        try:
            self.assertFalse(self._with({}, lambda: K.numeral_slip('貸す九人', 0, 4, '確認')))
        finally:
            del os.environ['CN_KEYSLIP_NUM_READ']

    def test_switch(self):
        os.environ['CN_NUMERAL_SLIP'] = '0'
        try:
            self.assertFalse(self._with({'貸す九人': ['かすくにん']}, lambda: K.numeral_slip('内容を貸す九人する', 3, 7, '確認')))
        finally:
            del os.environ['CN_NUMERAL_SLIP']


class RepairLine(unittest.TestCase):
    def test_result_shape(self):
        line = '先方の質問に変度を書いた'
        out = K.repair_line(line, {'original': line, 'corrected': line, 'changed': False, 'details': [],
                                   'odd_spans': [(6, 8)]})
        self.assertEqual(out['corrected'], '先方の質問に返事を書いた')
        self.assertEqual(out['odd_spans'], [])
        self.assertTrue(out['changed'])

    def test_romaji_untouched(self):
        line = '先方の質問に変度を書いた'
        res = {'original': line, 'corrected': line, 'changed': False}
        self.assertIs(K.repair_line(line, res, input_method='romaji'), res)


if __name__ == '__main__':
    unittest.main()
