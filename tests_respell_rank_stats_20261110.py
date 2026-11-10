"""odd_respell: 候補を通した何回目を採ったかの集計（デバッグ、既定オフ）と通す回数の上限（作った例）。"""
import unittest

import odd_respell as O


class RankStatsTests(unittest.TestCase):
    def tearDown(self):
        O.set_rank_stats(False)
        O.set_attempt_limit(0)
        O.take_rank_stats()

    def test_counting_run_order_and_limit(self):
        book = {'n': 0, 'order': {}}
        run = O._counting_run(lambda t: {'corrected': t + '!'}, book, 2)
        self.assertEqual(run('あ')['corrected'], 'あ!')
        run('い')
        self.assertIsNone(run('う'))
        self.assertEqual(book['n'], 2)
        self.assertEqual(book['order']['い!'], 2)

    def test_note_rank_late_keeps_line(self):
        book = {'n': 9, 'order': {'正しい行': 8}}
        O._note_rank('まちがい行', {'corrected': 'まちがい行'}, {'corrected': '正しい行'}, book)
        got = O.take_rank_stats()
        self.assertEqual(got['rank'], {8: 1})
        self.assertEqual(got['tried'], {9: 1})
        self.assertEqual(got['late'], [[8, 9, 'まちがい行', '正しい行']])
        self.assertIsNone(O.take_rank_stats())

    def test_off_by_default(self):
        self.assertFalse(O.RANK_STATS_ON)
        self.assertEqual(O.ATTEMPT_LIMIT, 0)


if __name__ == '__main__':
    unittest.main()
