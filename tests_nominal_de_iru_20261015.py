"""名詞＋で＋いる（むごんでいた・ふあんでいました）を、名詞＋だった と同じく
読める文として扱う（2026-10-15）。

うにさんの選択「名詞の後ろの でいた に紫を付けない」の続き。かなだけで書いた
名詞（むごん・ふあん・すなお）は行の解析が切り損ねる（ふ＋あん・す＋なお）ので、
でいた の判定を外しても、別の判定（かなの並びの読み・語のつなぎ）が紫を付けて
いた。で（だ の連用形）＋いる は、名詞＋だった が言えるところならどこでも言える
ので、で＋いる を だった に置き換えた行の読みの証拠を、元の行にもそのまま使う
（`reading_segments.nominal_de_iru_copula`）。

ここの例はすべて作った文。
"""
import unittest

import morphology as M


class CopulaFormTests(unittest.TestCase):
    def test_de_iru_tail_becomes_datta(self):
        from reading_segments import nominal_de_iru_copula as copula
        for text, expected in (('むごんでいた', 'むごんだった'),
                               ('ずっとふあんでいました', 'ずっとふあんだった'),
                               ('すなおでいて', 'すなおだった'),
                               ('へいきでいたい', 'へいきだった'),
                               ('むごんでおりました', 'むごんだった'),
                               ('れいせいでいなかった', 'れいせいだった')):
            with self.subTest(text=text):
                self.assertEqual(copula(text), expected)

    def test_other_tails_are_left_alone(self):
        from reading_segments import nominal_de_iru_copula as copula
        # で＋みた（一人で見た）・崩れた活用（いまいた）・で で終わる形は置き換えない
        for text in ('ひとりでみた', 'ひとりでいまいた', 'ふあんで', 'むごんでした', 'いた', ''):
            with self.subTest(text=text):
                self.assertIsNone(copula(text))


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class NominalDeIruLineTests(unittest.TestCase):
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

    def test_kana_noun_with_de_iru_is_not_marked(self):
        for line in ('ずっとむごんでいた', 'あの子はむごんでいました。', '私はむごんでいます',
                     'ずっとふあんでいました', 'あの子はすなおでいた', '私はすなおでいて',
                     'きのうはしあわせでいます', '私はずっとふあんでいました。',
                     # 読点の前の節にも同じく効く
                     '父はむごんでいて、こわかった'):
            with self.subTest(line=line):
                self.assertEqual(self.run_line(line)['odd_spans'], [])

    def test_kana_noun_is_not_rewritten(self):
        # 直す前は がくせいでいた → がくせいだいた・ふあんでいた → ふんでいた と壊していた
        for line in ('ずっとがくせいでいた', 'ずっとがくせいでいなかった'):
            with self.subTest(line=line):
                self.assertEqual(self.run_line(line)['corrected'], line)
        for line in ('わたしはふあんでいた', 'ふあんでいる'):
            with self.subTest(line=line):
                corrected = self.run_line(line)['corrected']
                self.assertNotIn('ふん', corrected)
                self.assertTrue('ふあん' in corrected or '不安' in corrected, corrected)

    def test_typos_are_still_marked(self):
        # 頭が動詞（わすれ＋で＝忘れて の て→で）・読めない語尾（でしら）は紫のまま。
        # 2026-10-16 から、1打を戻して読み直す直し（last_keystroke）で直ることもある。
        # 紫を消すだけにはしない
        for line, span, fixed in (('やくそくをわすれでいます', (8, 12), ('わすれています', '忘れています')),
                                  ('あめでしら', (2, 5), ('でしたら',))):
            with self.subTest(line=line):
                result = self.run_line(line)
                if result['odd_spans']:
                    self.assertIn(span, result['odd_spans'])
                else:
                    self.assertTrue(any(x in result['corrected'] for x in fixed), result['corrected'])


if __name__ == '__main__':
    unittest.main()
