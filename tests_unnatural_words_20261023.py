"""字の並びの検品が辞書の語を止めない（逆効果の判定の見直し・2026-10-23・例文は作った文）"""
import unittest
import charngram
import morphology
import naturalness


@unittest.skipUnless(charngram.available() and morphology.HAS_JANOME, '表か解析器が無い')
class UnnaturalWordsTests(unittest.TestCase):
    def test_ordinary_words_are_not_unnatural(self):
        # 表（アプリの文書）に出てこない日常の語でも、語の内側だけで止めない
        for w in ('返事', '課題', '電気', '会議', '天気', '写真', '買い物', '返事を', '会議室で'):
            self.assertFalse(naturalness._looks_unnatural(w), w)

    def test_non_words_still_stopped(self):
        # 語でない字の並びは、今までどおり止める
        for w in ('ぬゑっぉ', 'ゑ電気'):
            self.assertTrue(naturalness._looks_unnatural(w), w)

    def test_never_stops_more_than_before(self):
        # 見直しは止める側を緩めるだけ（今まで通したものを新たに止めない）
        for w in ('メモちょが', '始める', '確認', '単語の繋がり', 'きゃぴゅ', 'をを'):
            if not charngram.looks_unnatural(w):
                self.assertFalse(naturalness._looks_unnatural(w), w)

    def test_readable_gate_decides_by_line(self):
        # 2字の語を直し先にした行は、字の並びの検品でなく行の自然さで決まる
        line = '明日までに変事をください。'
        g = naturalness.gain_in_line(line, 5, 7, '返事')
        got = naturalness.worth_touching_readable_here(line, 5, 7, '返事', default=None)
        if g is not None:
            self.assertEqual(got, g >= naturalness.MIN_GAIN_READABLE)


class OrdinaryTierTests(unittest.TestCase):
    def test_judged_ordinary_noun_is_not_rare(self):
        # 旧表に無いだけの一般の名詞（AI 判定の名簿で一般語）は、珍しい語の段にしない
        import corrector
        import kango_tier
        for w in ('椅子', '映像', '動画'):
            if kango_tier.known_usage_tier(w) in (1, 2):
                self.assertLessEqual(corrector._kango_tier_of(w), 2, w)


if __name__ == '__main__':
    unittest.main()
