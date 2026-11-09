# -*- coding: utf-8 -*-
"""kata_copula（名詞＋です を IME が片仮名の1語にした所を戻す）と、kana_piece_word の 置いた名詞の後ろの1字・
動詞の連用形＋置いた名詞（2026-11-08 手分けA その6）。例は作った文。"""
import os
import unittest

import kanji_guess
import kana_piece_word as KP
import kata_copula as K


def _with(rec, fn):
    kanji_guess.set_ime_readings_provider(lambda f: rec.get(f, []))
    try:
        return fn()
    finally:
        kanji_guess.set_ime_readings_provider(None)


class KataCopula(unittest.TestCase):
    def test_noun_suffix_copula(self):
        # きかく＋あん＋です を IME が 企画｜アンデス にした
        got = _with({'企画アンデス': ['きかくあんです']}, lambda: K.propose('これは企画アンデス。'))
        self.assertEqual(got, [(3, 9, 'これは企画案です。')])

    def test_previous_clause_typed(self):
        # 前の名詞が別の打った文節でも、すぐ前なら選び直す
        rec = {'企画': ['きかく'], 'アンデス': ['あんです']}
        self.assertEqual(_with(rec, lambda: K.propose('これは企画アンデス。')), [(3, 9, 'これは企画案です。')])

    def test_real_place_name_untouched(self):
        rec = {'アンデス': ['あんです']}
        self.assertEqual(_with(rec, lambda: K.propose('夏休みにアンデスへ行った。')), [])
        # 前に名詞が無い1字の名詞＋です は見ない
        self.assertEqual(_with(rec, lambda: K.propose('これが新しいアンデス。')), [])

    def test_no_record_with_noun(self):
        # 行に打った記録が無い（開き直した行）: すぐ前の漢字の名詞と組にできれば選び直す（2026-11-08 手分けB）
        self.assertEqual(_with({}, lambda: K.propose('これは企画アンデス。')), [(3, 9, 'これは企画案です。')])

    def test_no_record_without_noun(self):
        # 前に漢字の名詞が無ければ、記録が無いときは見ない
        self.assertEqual(_with({}, lambda: K.propose('旅行先はアンデスです。')), [])
        self.assertEqual(_with({}, lambda: K.propose('これが新しいアンデス。')), [])

    def test_other_clause_typed_no_change(self):
        # 行のほかの所に記録が在り、片仮名の語には無い（片仮名の語は前に書いた・貼った）なら前のまま
        self.assertEqual(_with({'今日': ['きょう']}, lambda: K.propose('今日は企画アンデス。')), [])

    def test_no_record_switch(self):
        os.environ['CN_KATA_COPULA_NOREC'] = '0'
        try:
            self.assertEqual(_with({}, lambda: K.propose('これは企画アンデス。')), [])
        finally:
            del os.environ['CN_KATA_COPULA_NOREC']

    def test_switch(self):
        os.environ['CN_KATA_COPULA'] = '0'
        try:
            self.assertEqual(_with({'企画アンデス': ['きかくあんです']}, lambda: K.propose('これは企画アンデス。')), [])
        finally:
            del os.environ['CN_KATA_COPULA']


class PlacedNounKana(unittest.TestCase):
    def test_one_char_after_placed_noun(self):
        # かなの行で置いた名詞の後ろに残った1字（じどう＋か → 自動化）
        out = KP.repair_line('じどうか', {'corrected': '自動か', 'odd_spans': []})
        self.assertEqual(out['corrected'], '自動化')

    def test_question_particle_kept(self):
        out = KP.repair_line('じどうか？', {'corrected': '自動か？', 'odd_spans': []})
        self.assertEqual(out['corrected'], '自動か？')

    def test_renyou_before_placed_noun(self):
        # 動詞の連用形のかな＋置いた名詞 → 連用形も漢字に（とりあつかい説明 → 取り扱い説明）
        out = KP.repair_line('とりあつかいせつめい', {'corrected': 'とりあつかい説明', 'odd_spans': []})
        self.assertEqual(out['corrected'], '取り扱い説明')


class SuffixFace(unittest.TestCase):
    """ime_reconvert: 名詞＋接尾の名詞（〜用）を格子の表記に足す・打った読みのままの表記で行の費用がとても下がる所。"""

    def test_lattice_suffix_face(self):
        import ime_reconvert as R
        R._lattice_faces.cache_clear()
        self.assertIn('子供用', R._lattice_faces('こどもよう'))
        self.assertIn('会議用', R._lattice_faces('かいぎよう'))
        os.environ['CN_RECONVERT_SUFFIX_FACE'] = '0'
        try:
            R._lattice_faces.cache_clear()
            self.assertNotIn('子供用', R._lattice_faces('こどもよう'))
        finally:
            del os.environ['CN_RECONVERT_SUFFIX_FACE']
            R._lattice_faces.cache_clear()

    def test_rare_suffix_marked(self):
        import ime_reconvert as R
        got = _with({'子供擁': ['こどもよう']}, lambda: R.propose('子供擁の机を買った。', 'kana', None))
        self.assertEqual(got, [(2, 3, None)])

    def test_correct_rare_word_untouched(self):
        import ime_reconvert as R
        rec = {'森': ['もり'], '彷徨う': ['さまよう']}
        self.assertEqual(_with(rec, lambda: R.propose('森を彷徨う。', 'kana', None)), [])
        rec = {'夜': ['よる'], '街': ['まち'], '彷徨った': ['さまよった']}
        self.assertEqual(_with(rec, lambda: R.propose('夜の街を彷徨った。', 'kana', None)), [])


if __name__ == '__main__':
    unittest.main()
