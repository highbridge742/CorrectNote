# -*- coding: utf-8 -*-
"""付く先の無い ゛゜ を前の段がもう片付けた答えを、印の後ろの字まで替えた形に替えない（odd_respell._base_keeps_more・2026-11-01 B）。作った例だけ。"""
import unittest
import odd_respell as O


class BaseKeepsMoreTests(unittest.TestCase):
    def test_mark_only_removed_is_kept(self):
        line = '今日は風が゜吹くらしい'
        self.assertTrue(O._base_keeps_more(line, '今日は風が吹くらしい', '今日は風があるらしい', 5, {}))

    def test_purple_left_does_not_block(self):
        line = '今日は風が゜吹くらしい'
        self.assertFalse(O._base_keeps_more(line, '今日は風が吹くらしい', '今日は風があるらしい', 5,
                                            {'odd_spans': [(4, 6)]}))

    def test_untouched_line_does_not_block(self):
        line = '今日は風が゜吹くらしい'
        self.assertFalse(O._base_keeps_more(line, line, '今日は風が吹くらしい', 5, {}))


if __name__ == '__main__':
    unittest.main()
