# -*- coding: utf-8 -*-
"""2026-11-05 挙動関連担当の作った例: してくらさい が してくらいさ に直る・読むう に紫が無い。
起こらない品詞のつながり（て＋くらい・言い切り＋う）に紫を付け、読み直しがそれを作る直しは採らない。"""
import unittest

import correction_entry as C
import pos_grammar as P


class PosCheckTests(unittest.TestCase):
    def test_marks(self):
        self.assertTrue(P._impossible_connection_spans('本を読むう。'))
        self.assertTrue(P._impossible_connection_spans('予定を確認してくらいさ。'))
        for line in ('本を読もう。', '明日は晴れるでしょう。', '少し休んでほしい。', '勉強してばかりいる', '食べるよう言った'):
            self.assertFalse(P._impossible_connection_spans(line), line)

    def test_fix_that_makes_one_is_dropped(self):
        line = '予定を確認してくらさい。'
        res = {'corrected': line, 'odd_spans': [(8, 12)]}
        out = {'corrected': '予定を確認してくらいさ。'}
        self.assertTrue(C._impossible_after_fix(line, res, out))
        self.assertFalse(C._impossible_after_fix(line, res, {'corrected': '予定を確認してください。'}))


if __name__ == '__main__':
    unittest.main()
