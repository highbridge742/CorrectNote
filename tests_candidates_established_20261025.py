# CorrectNote — 誤字補正メモ帳
# Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""成り立っている語の再変換候補（2026-10-25）: 表記そのものが語彙・索引・世の中の読みで成り立つ語には、
2打違いの打ち間違い候補と遠い取り違えの候補を出さない。元が意味をなさない語は今までどおり広く出す。
例は作ったもの。"""
import unittest

import candidates
from vocabulary import VocabularyStore, find_known_readings_flex
from seed_vocabulary import load_seed


class EstablishedCandidateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from dict_index import DictIndex
        cls.store = VocabularyStore()
        load_seed(cls.store)
        cls.index = DictIndex()
        cls.index.ensure_built()

    def _typos(self, surface, reading):
        out = candidates.build_candidates(surface, reading, self.store, find_known_readings_flex,
                                          dict_index=self.index)
        return [c['surface'] for c in out if c['kind'] == 'typo']

    def test_established_word_is_recognised(self):
        self.assertTrue(candidates._surface_established('コーヒー', 'こーひー', self.store, self.index))
        self.assertTrue(candidates._surface_established('問題', 'もんだい', self.store, self.index))
        self.assertFalse(candidates._surface_established('乱後', 'らんご', self.store, self.index))

    def test_established_word_gets_no_two_edit_typos(self):
        # 2打違いの読みから作られた候補は出ない（1打違いの読みはあってよい）
        typos = self._typos('コーヒー', 'こーひー')
        for s in typos:
            r = candidates.resolve_reading(s, '', self.store) or ''
            self.assertLessEqual(_edits('こーひー', r), 1, (s, r)) if r else None

    def test_kana_input_ignores_phonetic_swaps(self):
        # かな入力では れ→ら・か→く のような音の取り違えを打ち間違いに数えない
        # （キーの隣ではない）。ローマ字入力・指定なしは今までどおり
        from kana_layout import nearby_candidates
        kana = {c for c, _d in nearby_candidates('れ', include_phonetic=False, input_method='kana')}
        self.assertNotIn('ら', kana)
        out = candidates.build_candidates('コーヒー', 'こーひー', self.store, find_known_readings_flex,
                                          dict_index=self.index, input_method='kana')
        for c in out:
            if c['kind'] != 'typo':
                continue
            r = c.get('reading') or ''
            self.assertNotEqual(r, 'こーふー', c)   # ひ→ふ（同じ行）は出ない

    def test_katakana_stem_with_kana_tail_is_not_offered(self):
        # 辞書の ツクれ・メデタい のような綴りは打ち間違いの候補に出ない
        self.assertTrue(candidates._kata_stem_kana_tail('ツクれ'))
        self.assertTrue(candidates._kata_stem_kana_tail('メデタい'))
        self.assertFalse(candidates._kata_stem_kana_tail('カレー'))
        self.assertFalse(candidates._kata_stem_kana_tail('つくれ'))
        self.assertTrue(candidates._kata_stem_kana_tail('サボる'))   # 同じ形なので打ち間違いの候補からは外れる（同音・漢字の候補は別）
        for s in self._typos('つくり', 'つくり'):
            self.assertFalse(candidates._kata_stem_kana_tail(s), s)

    def test_meaningless_word_still_gets_wide_candidates(self):
        self.assertTrue(self._typos('乱後', 'らんご'))


def _edits(a, b):
    # 置換・脱字・余分を1と数えるざっくりした距離（1打違いかどうかを見るだけ）
    if a == b:
        return 0
    if len(a) == len(b):
        return sum(x != y for x, y in zip(a, b))
    if abs(len(a) - len(b)) == 1:
        s, l = (a, b) if len(a) < len(b) else (b, a)
        for i in range(len(l)):
            if l[:i] + l[i + 1:] == s:
                return 1
    return 2


if __name__ == '__main__':
    unittest.main()
