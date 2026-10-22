"""僅差の2つの戻し・紫と迷いのずれ・片仮名に巻き込んだ1字（2026-10-20・v1.15 の報告から。例文は作った文）"""
import unittest
import tests_last_keystroke_20261016 as _T


class CloseRivalTests(unittest.TestCase):
    setUpClass = _T.LastKeystrokeLineTests.__dict__['setUpClass']
    setUp = _T.LastKeystrokeLineTests.setUp
    run_line = _T.LastKeystrokeLineTests.run_line

    def test_leader_on_both_scores_is_decided(self):
        # ました と まいた が僅差でも、費用と読みの並びの両方で上回り、読みの並びが大きく良くなる方を決める
        for line, want in (('花をたくさんかいまひた。', '花をたくさんかいました。'),):
            with self.subTest(line=line):
                self.assertEqual(self.run_line(line, input_method='romaji')['corrected'], want)

    def test_purple_and_doubt_overlap_are_read_together(self):
        # 紫（をか）と迷い（かいまひ）が重なるだけのときは、両方を覆う並びを読み直す
        self.assertEqual(self.run_line('パンをかいまひた。', input_method='romaji')['corrected'], 'パンをかいました。')

    def test_small_reading_gain_stays_purple(self):
        # 読みの並びの良くなりが小さい僅差（行使くばる）は決めない
        got = self.run_line('冬になると温かい鍋料理が行使くなる。', input_method='romaji')
        self.assertNotIn('くばる', got['corrected'])

    def test_extra_key_absorbed_into_katakana_word(self):
        # これ＋カニ＋ら は語の読みに無く、カニ の端の1字を抜いた これ＋か＋ら は在る
        got = self.run_line('これカニら宿題に取り掛かる。', input_method='romaji')
        self.assertEqual(got['corrected'], 'これから宿題に取り掛かる。')
        self.assertEqual(self.run_line('これカニを食べる。')['corrected'], 'これカニを食べる。')


if __name__ == '__main__':
    unittest.main()
