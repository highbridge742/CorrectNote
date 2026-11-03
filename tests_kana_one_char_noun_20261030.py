"""かな1字が普通の名詞と読まれた切れ端に印を付ける。かぎかっこで囲んだ1字は付けない
（2026-10-30・補正担当。例文は作った文）"""
import unittest
import pos_grammar as P


class KanaOneCharNounTests(unittest.TestCase):
    def test_marked(self):
        for line in ('冬休みにぱ旅行に行く。', '打ち合わせの件で、こ相談いたします。', '昼ご飯を食べすに出かけた。'):
            self.assertTrue(P._impossible_connection_spans(line), line)

    def test_quoted_kana_not_marked(self):
        for line in ('「ょ」の書き忘れに気をつける。', '『ぱ』と『ば』を見分ける。'):
            self.assertEqual(P._impossible_connection_spans(line), (), line)

    def test_correct_not_marked(self):
        for line in ('木の下で絵を描く。', '目が疲れたので休みます。', 'この本を読みます。'):
            self.assertEqual(P._impossible_connection_spans(line), (), line)


if __name__ == '__main__':
    unittest.main()
