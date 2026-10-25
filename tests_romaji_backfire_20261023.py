"""ローマ字の1打の戻しが別の語を作る誤補正を止める（2026-10-23・補正C）。

- 英字の後ろの母音の抜けも1打の戻しとして並べる
- 残った英字を抜くだけの戻しと、英字を残して読む戻しが並ぶ点で通るなら、直さない（迷うなら紫）
- 2度押し（っ の重ね・同じ母音の重ね）を残したまま、ほかの字を替える戻しはしない
- て・で に続く補助動詞（置いて**き**て）は語として切り出す

ここの例はすべて作った文。
"""
import unittest

import morphology as M
import last_keystroke as LK


class LetterEditTests(unittest.TestCase):
    def test_vowel_dropped_after_a_leftover_letter_is_a_candidate(self):
        # 英字の後ろの母音の抜け（yapumi の u）も、英字を抜く戻し（やみます）と並べる
        edits = LK._romaji_letter_edits('やpみます', 0, 6)
        self.assertIn('やぷみます', edits)
        self.assertIn('やみます', edits)

    def test_same_key_twice_is_still_dropped(self):
        # kk の片方は2度押し。英字を抜く戻しとして並べる
        self.assertIn('かきます', LK._romaji_letter_edits('かkきます', 0, 6))

    def test_drops_letter(self):
        self.assertTrue(LK._drops_letter('やsみます', 'やみます'))
        self.assertFalse(LK._drops_letter('やsみます', 'やすみます'))
        self.assertFalse(LK._drops_letter('やすみます', 'やみます'))


class DoublePressTests(unittest.TestCase):
    def test_small_tsu_before_a_consonant_and_repeated_vowel(self):
        # 2つ目の っ（後ろが た）が2度押しの跡
        self.assertEqual(LK._double_press_spots('はしっった', 0, 5), [3])
        self.assertEqual(LK._double_press_spots('くうう', 0, 3), [1, 2])
        # っ の後ろが母音・ん なら2度押しの跡ではない
        self.assertEqual(LK._double_press_spots('あっあ', 0, 3), [])
        self.assertEqual(LK._double_press_spots('かお', 0, 2), [])

    def test_tripled_key(self):
        # 同じキーが3つ続くのは2度押しが確か（ttt・uuu）。2つ（をお・かぎい・いった）はふつうの綴りにもある
        self.assertTrue(LK._tripled_key('はしっった', 3))
        self.assertTrue(LK._tripled_key('ちきゅうう', 4))
        for text, k in (('かぎい', 2), ('をおくる', 1), ('いった', 1), ('おおきい', 1)):
            with self.subTest(text=text):
                self.assertFalse(LK._tripled_key(text, k))


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class AuxiliaryAfterTeTests(unittest.TestCase):
    def test_auxiliary_after_te_is_a_word(self):
        line = '本を机に置いてきた'
        toks = M.tokenize(line)
        k = line.index('き')
        frags = LK._clause_fragments(toks, k, k + 1)
        self.assertFalse(any(toks[i].start == k for i in frags))


class DropGateTests(unittest.TestCase):
    def test_only_drops_keys(self):
        self.assertTrue(LK._only_drops_keys('いまkれた', 'いまけた'))      # ikre → ike
        self.assertTrue(LK._only_drops_keys('かいだnの', 'かいだの'))
        self.assertFalse(LK._only_drops_keys('のみまうs', 'のみます'))    # 入れ替わり us → su
        self.assertFalse(LK._only_drops_keys('やpみます', 'やぷみます'))

    def test_letter_next_to_converted_characters(self):
        self.assertTrue(LK._letter_by_converted('海辺kで遊ぶ'))
        self.assertTrue(LK._letter_by_converted('テレビtを見る'))
        self.assertFalse(LK._letter_by_converted('やpみます'))

    def test_dangling_small_tsu(self):
        self.assertTrue(LK._dangling_small_tsu('本をかたづけt', '本をかたづけっ'))
        self.assertFalse(LK._dangling_small_tsu('いtた', 'いった'))

    @unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
    def test_words_stand_after_the_drop(self):
        self.assertFalse(LK._reads_as_words_at('きせの変わり目', 2))      # 連用形＋の
        self.assertFalse(LK._reads_as_words_at('夜遅くで仕事', 3))        # 連用形＋で
        self.assertTrue(LK._reads_as_words_at('鍵をなくしてしまった', 4))


class LeftoverLetterMarkTests(unittest.TestCase):
    def test_unfixed_leftover_letter_gets_purple(self):
        import correction_entry as CE
        out = CE._mark_leftover_letters('きょうはやpみます', {'corrected': 'きょうはやpみます', 'odd_spans': []})
        self.assertEqual(out['odd_spans'], [(5, 6)])

    def test_fullwidth_letters_seen_as_halfwidth_only_for_leftovers(self):
        import correction_entry as CE
        self.assertEqual(CE._halfwidth_letters('やｐみます・ｉＰｈｏｎｅで'), 'やpみます・ｉＰｈｏｎｅで')
        out = CE._restore_fullwidth('やｐみますｋ', 'やpみますk', {'corrected': 'やすみますk'})
        self.assertEqual(out['corrected'], 'やすみますｋ')

    def test_fixed_line_and_english_words_are_left(self):
        import correction_entry as CE
        r = {'corrected': 'きょうはやすみます', 'odd_spans': []}
        self.assertIs(CE._mark_leftover_letters('きょうはやpみます', r), r)
        r = {'corrected': 'Wi-Fiにつなぐ', 'odd_spans': []}
        self.assertIs(CE._mark_leftover_letters('Wi-Fiにつなぐ', r), r)


if __name__ == '__main__':
    unittest.main()
