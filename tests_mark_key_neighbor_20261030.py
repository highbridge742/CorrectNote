"""単独の ゛ を、印のキーの隣のかな（へ・ほ・せ・け）のつもりの打鍵として戻し、変換した形に置く（2026-10-30・補正担当。例文は作った文）"""
import unittest
import tests_last_keystroke_20261016 as _T
import last_keystroke as L


class MarkKeyNeighborTests(unittest.TestCase):
    setUpClass = _T.LastKeystrokeLineTests.__dict__['setUpClass']
    setUp = _T.LastKeystrokeLineTests.setUp
    run_line = _T.LastKeystrokeLineTests.run_line

    def test_mark_meant_as_he(self):
        got = self.run_line('メールを見て゛んじを書いた。')
        self.assertEqual(got['corrected'], 'メールを見て返事を書いた。')

    def test_variants_only_after_markable_kana(self):
        self.assertTrue(L._mark_key_neighbor_variants('見て゛んじ', 2))
        self.assertEqual(L._mark_key_neighbor_variants('あ゛ー', 1), [])

    def test_voice_mark_left_alone(self):
        self.assertEqual(self.run_line('あ゛ー疲れた。')['corrected'], 'あ゛ー疲れた。')


if __name__ == '__main__':
    unittest.main()
