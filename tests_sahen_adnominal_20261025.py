# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""連体詞を守る門（reading_segments.native_adnominal_modifier_ranges）: サ変の名詞の直後に切れ目なく付く
連体詞（該当**あの**範囲）は守らない。名詞が する／の／読点なしにそこに立てないので、かなは滑った1打
（補正担当・2026-10-25。未解決タブ）。副詞になれる名詞の後（昨日あの店）は今までどおり守る。例文は作ったもの。"""
import unittest

import reading_segments as RS


class SahenAdnominalTests(unittest.TestCase):
    def test_modifier_after_bare_sahen_noun_is_not_protected(self):
        ranges = RS.native_adnominal_modifier_ranges('該当あの範囲を')
        self.assertFalse(any(lo <= 2 < hi for lo, hi in ranges), ranges)

    def test_modifier_after_adverbial_noun_is_protected(self):
        ranges = RS.native_adnominal_modifier_ranges('昨日あの店に行った。')
        self.assertTrue(any(lo <= 2 < hi for lo, hi in ranges), ranges)

    def test_modifier_after_sahen_noun_with_particle_is_protected(self):
        ranges = RS.native_adnominal_modifier_ranges('確認のあの件は済んだ。')
        self.assertTrue(any(lo <= 3 < hi for lo, hi in ranges), ranges)


if __name__ == '__main__':
    unittest.main()
