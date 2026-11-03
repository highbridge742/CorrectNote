"""漢字の後・片仮名の前のかなは、片仮名の語の中の字ではないので品詞のつながりを見る
（2026-10-30・補正担当。例文は作った文）"""
import unittest
import pos_grammar as P


class KanaBeforeKatakanaTests(unittest.TestCase):
    def test_marked_after_kanji(self):
        self.assertTrue(P._impossible_connection_spans('画面の歯車りボタンを押す。'))

    def test_inside_katakana_word_skipped(self):
        for line in ('シャつを着る。', 'スクりーンを見る。'):
            self.assertEqual(P._impossible_connection_spans(line), (), line)

    def test_correct_not_marked(self):
        for line in ('東京のカフェで会う。', '猫がソファで寝る。', '明日もテストがある。'):
            self.assertEqual(P._impossible_connection_spans(line), (), line)


if __name__ == '__main__':
    unittest.main()
