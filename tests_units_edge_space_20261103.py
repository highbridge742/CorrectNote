# -*- coding: utf-8 -*-
"""行頭・行末に空白がある行も語に分かれる（作った例・2026-11-03）。"""
import unittest
from units import _restore_edge_spaces, build_suspect_units, build_line_units


def tok(surface, start, pos='名詞:一般'):
    return (surface, pos, surface, start, start + len(surface), True, '')


def tokenize(text):
    """形態素解析と同じに、行頭・行末の空白を落とす（語の位置はそのまま）。"""
    body = text.strip(' \u3000')
    at = len(text) - len(text.lstrip(' \u3000'))
    out = []
    for word in body.split('|'):
        out.append(tok(word, at))
        at += len(word)
    return out


class Restore(unittest.TestCase):
    def test_tail(self):
        got = _restore_edge_spaces([tok('資料', 0), tok('作る', 2)], '資料作る ')
        self.assertEqual([t[0] for t in got], ['資料', '作る', ' '])
        self.assertEqual(got[-1][3:5], (4, 5))
        self.assertEqual(len(got[-1]), 7)

    def test_head(self):
        got = _restore_edge_spaces([tok('資料', 1)], '\u3000資料')
        self.assertEqual([t[0] for t in got], ['\u3000', '資料'])

    def test_nothing_missing_is_the_same(self):
        tokens = [tok('資料', 0)]
        self.assertEqual(_restore_edge_spaces(tokens, '資料'), tokens)

    def test_only_spaces_are_filled(self):
        tokens = [tok('資料', 0)]
        self.assertIs(_restore_edge_spaces(tokens, '資料x'), tokens)
        tokens = [tok('資料', 1)]
        self.assertIs(_restore_edge_spaces(tokens, 'x資料'), tokens)

    def test_wrong_positions_are_left(self):
        tokens = [tok('資料', 2)]
        self.assertIs(_restore_edge_spaces(tokens, '資料  '), tokens)

    def test_empty(self):
        self.assertEqual(_restore_edge_spaces([], ' '), [])


class Units(unittest.TestCase):
    def result(self, text):
        return dict(original=text, corrected=text, details=[], spans=[], original_spans=[], odd_spans=[], unsure_spans=[])

    def words(self, build, text):
        import units
        tokens = [tok(w, text.index(w)) for w in ('資料', '作成')]
        return [u['text'] for u in build(self.result(text), lambda t: tokens)[1]]

    def test_suspect_units_are_words_with_a_space_at_the_end(self):
        self.assertEqual(self.words(build_suspect_units, '資料作成 ')[:2], ['資料', '作成'])

    def test_line_units_too(self):
        self.assertEqual(self.words(build_line_units, '資料作成 ')[:2], ['資料', '作成'])

    def test_a_space_at_the_head(self):
        got = self.words(build_suspect_units, ' 資料作成')
        self.assertIn('資料', got)
        self.assertNotEqual(got, [' 資料作成'])


if __name__ == '__main__':
    unittest.main()
