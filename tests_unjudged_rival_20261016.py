"""同じ読みの語の選び方（2026-10-16・`kana_spelling._unjudged_rival`）。

かなの語を漢字の表記にするとき、使い方の判定がある語（数奇・盾）だけが
候補に残り、判定の無いふつうの語（好き・縦）が先に落ちていた。判定が
無いことは「まれ」の証拠ではない。同梱の表ではっきりよく使う、判定の
無い同じ読みの名詞があれば、かなのまま残す。カタカナの表記（ツケ・
ハク）も、判定の無い漢字の語があれば同じ。動詞も同じで、入る の判定
（はいる の読み）が いってきます の いっ を 入っ にしていた。

ここの例はすべて作った文。
"""
import unittest

import morphology as M
import kana_spelling as KS


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class RivalTests(unittest.TestCase):
    def test_unjudged_common_rival_holds_the_judged_face(self):
        self.assertTrue(KS._unjudged_rival('すき', '数奇', {'好き', '数奇'}))
        self.assertTrue(KS._unjudged_rival('たて', '盾', {'縦', '盾'}))

    def test_katakana_spelling_of_an_unjudged_kanji_word(self):
        self.assertTrue(KS._unjudged_rival('つけ', 'ツケ', {'付け', '漬け'}))
        self.assertTrue(KS._unjudged_rival('はく', 'ハク', {'泊', '箔'}))
        # 判定のあるカタカナ語は表に無くても止めない
        self.assertFalse(KS._unjudged_rival('ぼたん', 'ボタン', {'牡丹'}))

    def test_rarer_or_close_rival_does_not_hold_the_face(self):
        # 飢え は 上 よりまれ。渡し の表の費用 0 は使い方の目安ではない
        self.assertFalse(KS._unjudged_rival('うえ', '上', {'飢え'}))
        self.assertFalse(KS._unjudged_rival('わたし', '私', {'渡し'}))
        # 表の費用が近い語どうし（検索・研削）では決めない
        self.assertFalse(KS._unjudged_rival('けんさく', '検索', {'検索', '研削'}))
        self.assertFalse(KS._unjudged_rival('じっこう', '実行', {'実効', '実行'}))

    def test_unjudged_kanji_face_is_left_to_the_other_gates(self):
        # 判定の無い漢字の表記どうしは、今までどおり同じ重さの候補として扱う
        self.assertFalse(KS._unjudged_rival('さいけんとう', '再健闘', {'再検討'}))

    def test_okurigana_variant_is_not_another_sense(self):
        self.assertFalse(KS._unjudged_rival('しめきり', '締め切り', {'締切', '締め切り'}))

    def test_count_is_not_held_by_the_table(self):
        # 三枚 のような数え方は表に載らない。表に無いことは まれ の証拠ではない
        self.assertFalse(KS._unjudged_rival('さんまい', '三枚', {'三枚', '三昧'}))

    def test_judged_verb_against_a_common_unjudged_sense(self):
        # 入る の判定は はいる のもの。いっ では表に 行っ・言っ があり 入っ が無い
        self.assertTrue(KS._unjudged_verb_rival('いっ', '入っ', {'行っ', '言っ'}))
        self.assertFalse(KS._unjudged_verb_rival('いっ', '行っ', {'行っ'}))


@unittest.skipUnless(M.HAS_JANOME, 'real native dictionary required')
class SpellingLineTests(unittest.TestCase):
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

    def test_rare_same_reading_spelling_is_not_chosen(self):
        for line, rare in (('すきなものをえらんでください。', '数奇'),
                           ('ねこがすき', '数奇'),
                           ('たてにのばすようにしました。', '盾')):
            with self.subTest(line=line):
                self.assertNotIn(rare, self.run_line(line)['corrected'])

    def test_katakana_spelling_of_a_kanji_word_is_not_chosen(self):
        for line, rare in (('めじるしをつけ、じゅんにたどります。', 'ツケ'),
                           ('はんかくくうはくがはいったれいです。', 'ハク'),
                           ('タブのみだしのうえでまわします。', 'ダシ')):
            with self.subTest(line=line):
                self.assertNotIn(rare, self.run_line(line)['corrected'])

    def test_stopped_spelling_does_not_pass_to_a_katakana_spelling(self):
        # 数奇 を止めても、判定の無いカタカナの表記（スキ）が代わりに選ばれない
        self.assertNotIn('スキ', self.run_line('ねこがすき')['corrected'])

    def test_ambiguous_verb_is_not_given_a_rare_reading(self):
        for line, rare in (('いってきます。', '入'),
                           ('はっきりいってください。', '入'),
                           ('いっていました。', '入'),
                           ('いぬを3びきかっています。', '買')):
            with self.subTest(line=line):
                self.assertNotIn(rare, self.run_line(line)['corrected'])

    def test_verb_with_its_own_proof_is_still_spelled(self):
        for line, expected in (('がっこうにいってきます。', '学校に行ってきます。'),
                               ('はいってきます。', '入ってきます。'),
                               ('タブをひらきます。', 'タブを開きます。'),
                               ('てがみをかいてください。', '手紙を書いてください。')):
            with self.subTest(line=line):
                self.assertEqual(self.run_line(line)['corrected'], expected)

    def test_common_spellings_are_kept(self):
        for line, face in (('ばすにのりおくれました', 'バス'),
                           ('わたしはりんごがすきです', '私'),
                           ('しごとがおわったらでかけます。', '仕事'),
                           ('マウスをうえへうごかします。', '上')):
            with self.subTest(line=line):
                self.assertIn(face, self.run_line(line)['corrected'])


if __name__ == '__main__':
    unittest.main()
