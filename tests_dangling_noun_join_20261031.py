"""動詞と読まれた所を、前後の漢字の名詞の読みとつないで辞書の1語にする（2026-10-31・補正担当。例文は作った文）"""
import unittest
import dangling_verb as D


class NounJoinTests(unittest.TestCase):
    def test_kanji_before_kana_reading_joined(self):
        # やくいん を IME が 役 だけ漢字にした形（役＋いん）。字を足さずに 役員 で説明が付く
        line = '会社の役いんが来た'
        got = D.repair_line(line, {'corrected': line})
        self.assertEqual(got['corrected'], '会社の役員が来た')

    def test_missing_letter_still_added(self):
        line = '提案してみてくだい。'
        self.assertEqual(D.repair_line(line, {'corrected': line})['corrected'], '提案してみてください。')

    def test_no_join_word_stays_purple(self):
        line = '木を置い'
        got = D.repair_line(line, {'corrected': line})
        self.assertEqual(got['corrected'], line)
        self.assertTrue(got.get('odd_spans'))


if __name__ == '__main__':
    unittest.main()
