# CorrectNote — 誤字補正メモ帳
# SPDX-License-Identifier: GPL-3.0-or-later
"""正しい文の機能語・伸ばしの形・行末の語を、1打の戻しで別の形にしない（2026-10-24・うにさんの誤判定・例文は作った文）"""
import unittest
from tests_readable_respell_20261024 import run_line


class SettledRunTests(unittest.TestCase):
    def test_functional_run_is_kept(self):
        # 機能語だけの並び（としてではなく）を できなく にしない。前の語の送り仮名が付いていても同じ
        for line, ime in (('目的としてではなく', [('目的', 'もくてき')]), ('遊びとしてではなく', [('遊び', 'あそび')])):
            self.assertEqual(run_line(line, [], ime)['corrected'], line)

    def test_expressive_run_is_kept(self):
        # 伸ばしの形（ないでぇ）の濁点を外さない
        for line in ('忘れないでぇ', '行かないでぇ'):
            self.assertEqual(run_line(line)['corrected'], line)

    def test_adnominal_needs_following_word(self):
        # 行末の 側 を、後ろに語を要する 我が（連体詞）にしない
        for line in ('見る側', '書く側'):
            self.assertEqual(run_line(line, [('わが', '我が', 2)], [('側', 'がわ')])['corrected'], line)


if __name__ == '__main__':
    unittest.main()
