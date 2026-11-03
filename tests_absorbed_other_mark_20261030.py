"""片仮名に巻き込んだ1字の戻しは、行のほかの所に紫が残っていても採る（2026-10-30・補正担当。例文は作った文）"""
import unittest
import tests_last_keystroke_20261016 as _T


class AbsorbedOtherMarkTests(unittest.TestCase):
    setUpClass = _T.LastKeystrokeLineTests.__dict__['setUpClass']
    setUp = _T.LastKeystrokeLineTests.setUp
    run_line = _T.LastKeystrokeLineTests.run_line

    def test_absorbed_letter_fixed_beside_other_purple(self):
        # 行の後ろの 取り掛かする に紫が残っても、これ＋カニ＋ら の戻しはその紫と別の所
        got = self.run_line('これカニら宿題に取り掛かする。')
        self.assertTrue(got['corrected'].startswith('これから宿題に'), got['corrected'])

    def test_plain_katakana_word_is_kept(self):
        self.assertEqual(self.run_line('これカニを食べる。')['corrected'], 'これカニを食べる。')


if __name__ == '__main__':
    unittest.main()
