"""動詞の て形の後ろの で＋いた に紫を立てない（2026-10-15）。

説明書の更新で、初期状態の写しに自然な文「花びらが水面に浮かんでいた」を
入れると、でいた に紫が付いた。文末の語尾の1打崩れ（でした → でいた）を
探す判定（`pos_grammar._broken_polite_end_frames`）が、ひらがなの並び
`かんでいた` だけを見て、浮か｜ん の かん を缶・勘と読み、かん＋でした が
読めるので崩れと見ていた。動詞の て形には でした は付かないので、書いた
語尾（で＋補助動詞）が文法どおりなら崩れと見ない。判定は行の語の区切りで見る。

同日、うにさんの選択（紫を消す）で、名詞・形容動詞の語幹・副詞の後ろの
で＋いる（ひとりでいた・きれいでいた・そのままでいた）も崩れと見ない。
でした の打ち間違い（あめでいた）とも見分けられないが、それも紫を付けない。

ここの例はすべて作った文。
"""
import unittest

import morphology as M


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class TeAuxiliaryPurpleTests(unittest.TestCase):
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

    def test_te_form_with_auxiliary_is_not_marked(self):
        for line in ('花びらが水面に浮かんでいた', '浮かんでいた。', '膨らんでいた',
                     '旅行を楽しんでいた', '気持ちが揺らいでいた', '少し楽しんでみた',
                     'ガムをかんでいた', 'となりのまちにすんでいた', '痛みが和らいでいた'):
            with self.subTest(line=line):
                row = self.run_line(line)
                self.assertEqual(row['corrected'], line)
                self.assertEqual(row['odd_spans'], [])

    def test_noun_with_de_iru_is_not_marked(self):
        for line in ('ずっとひとりでいた', '一人でいた', 'きのうは元気でいました',
                     'このままでいる', 'そのままでいて', 'みんな笑顔でいた',
                     '友達でいましょう', 'しばらく静かでいようと思った'):
            with self.subTest(line=line):
                self.assertEqual(self.run_line(line)['odd_spans'], [])

    def test_broken_polite_endings_are_still_found(self):
        from pos_grammar import _broken_polite_end_spans as spans
        di = self.state.dict_index
        self.assertEqual(spans('でんきをけしてくだそい', di), ((6, 11),))
        for source, expected in (('あさごはんをたべした', '朝ご飯を食べました'),
                                 ('まどをあけてもいいでかす', '窓を開けてもいいですか'),
                                 ('やくそくをわすれいました', 'やくそくをわすれていました')):
            with self.subTest(source=source):
                self.assertEqual(self.run_line(source)['corrected'], expected)

    def test_written_ending_must_be_a_real_auxiliary_chain(self):
        from pos_grammar import _auxiliary_chain_ok as ok
        for text in ('いた', 'いました', 'いません', 'いなかった', 'みた', 'しまった',
                     'おいた', 'もらった'):
            self.assertTrue(ok(text), text)
        # 補助動詞として続かない並び（いま＋いた・ます＋た・いまう）は崩れの候補のまま
        for text in ('いまいた', 'いますた', 'いまう', 'いたい'):
            self.assertFalse(ok(text), text)

    def test_only_after_a_verb_te_form(self):
        from morphology import tokenize
        from pos_grammar import _written_te_auxiliary as te_aux
        for line, a, expected in (('浮かんでいた', 3, True), ('書いていた', 2, True),
                                  # て／で が動詞の形と合わない（読ん＋て）
                                  ('読んていた', 2, False),
                                  # 名詞の後ろは別の判定（_written_nominal_de_iru）
                                  ('あめでいた', 2, False)):
            with self.subTest(line=line):
                self.assertIs(te_aux(line, a, len(line), tokenize(line)), expected)

    def test_after_a_noun_only_de_iru(self):
        from morphology import tokenize
        from pos_grammar import _broken_polite_end_spans as spans
        from pos_grammar import _written_nominal_de_iru as nominal
        di = self.state.dict_index
        # かなだけの名詞は行の解析が切り損ねる（へいき を へ＋いき）が、候補の読みで見る。
        # 候補が ています でも、行の解析が頭を名詞と読むなら見ない（はだし・がくせい）。
        # でした の崩れ（あめでいた・きのうでいた）とは区別が付かないので、それも見ない
        for line in ('ずっとへいきでいた', 'わたしはかぞくでいた', 'ひとりでいた',
                     'しずかでいよう', 'ともだちでいましょう', 'はだしでいます',
                     '私はがくせいでいます', 'あめでいた', 'きのうでいた'):
            with self.subTest(line=line):
                self.assertEqual(spans(line, di), ())
        # で＋みた（一人で見た）・読めない語尾（でしら）・頭が動詞（わすれ＋で）は候補のまま
        self.assertEqual(spans('ひとりでみた', di), ((3, 6),))
        self.assertEqual(spans('あめでしら', di), ((2, 5),))
        self.assertEqual(spans('やくそくをわすれでいます', di), ((8, 12),))

        def judge(line, a, tail):
            return nominal(line, a, len(line), tail, tokenize(line))
        self.assertTrue(judge('あめでいた', 2, 'でした'))
        self.assertTrue(judge('ひとりでおりました', 3, 'でした'))
        self.assertTrue(judge('がくせいでいます', 4, 'ています'))
        self.assertFalse(judge('ひとりでいまいた', 3, 'でした'))
        self.assertFalse(judge('ひとりでみた', 3, 'でした'))
        self.assertFalse(judge('わすれでいます', 3, 'ています'))

if __name__ == '__main__':
    unittest.main()
