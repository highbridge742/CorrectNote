# -*- coding: utf-8 -*-
"""打った記録の無い行の、読みを替えない辞書の表記の直し（CN_RECONVERT_SAME_BIG_UNTYPED、2026-11-08 手分けA）。例は作った文。
IME は語ごとの読みを返し、行の読みの変換では元の行をそのまま返す（IME が自分の選んだ表記を第1候補に返す）代わりの物。"""
import os
import unittest

import ime_reconvert as M
from morphology import tokenize


class _SameIME:
    available = True
    error = None

    def __init__(self, text, words):
        self.text, self.words = text, words

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def reverse_words(self, text):
        phon, out, i = '', [], 0
        for face, r in self.words:
            j = text.index(face, i)
            out.append((j, j + len(face), len(phon), len(phon) + len(r), 0, 0))
            phon += r
            i = j + len(face)
        return phon, tuple(out)

    def convert(self, reading):
        return self.text


LINE = 'お客彷徨うの駐車場です。'
WORDS = (('お客', 'おきゃく'), ('彷徨う', 'さまよう'), ('の', 'の'), ('駐車場', 'ちゅうしゃじょう'), ('です', 'です'), ('。', '。'))


class SameBigUntyped(unittest.TestCase):
    def test_fix_without_record(self):
        self.assertEqual(M.propose(LINE, 'kana', _SameIME(LINE, WORDS)), [(0, 5, 'お客様用の駐車場です。')])

    def test_fix_without_ime(self):
        # IME の無い道でも、名詞＋う と切れた所は同梱の表の読み（さまよう）で見る
        self.assertEqual(M.propose(LINE, 'kana', None), [(0, 5, 'お客様用の駐車場です。')])

    def test_fix_ime_split_reading(self):
        # PC の IME は 彷徨｜う を2語（さまよ・う）で返す。つないで見る
        line = 'お客彷徨うの資料'
        words = (('お客', 'おきゃく'), ('彷徨', 'さまよ'), ('う', 'う'), ('の', 'の'), ('資料', 'しりょう'))
        self.assertEqual(M.propose(line, 'kana', _SameIME(line, words)), [(0, 5, 'お客様用の資料')])

    def test_correct_verb_kept(self):
        line = '森を彷徨う。'
        words = (('森', 'もり'), ('を', 'を'), ('彷徨う', 'さまよう'), ('。', '。'))
        self.assertEqual(M.propose(line, 'kana', _SameIME(line, words)), [])

    def test_broken_noun_aux(self):
        toks = list(tokenize('お客彷徨う'))
        self.assertTrue(M._broken_noun_aux(toks, 2, 5))
        toks = list(tokenize('資料を作った'))
        self.assertFalse(M._broken_noun_aux(toks, 0, 6))

    def test_switch(self):
        os.environ['CN_RECONVERT_SAME_BIG_UNTYPED'] = '0'
        try:
            self.assertEqual(M.propose(LINE, 'kana', _SameIME(LINE, WORDS)), [])
            self.assertEqual(M.propose(LINE, 'kana', None), [])
        finally:
            del os.environ['CN_RECONVERT_SAME_BIG_UNTYPED']


if __name__ == '__main__':
    unittest.main()
