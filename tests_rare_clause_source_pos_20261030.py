"""直した行の上で見つけた紫は、元の行の位置で返す（長さの変わる直しの後に紫が行の外へずれると、
行全体が「解析が終わらない」扱いになる。2026-10-30・作り例）。"""
import unittest
from unittest import mock

import last_keystroke as LK


class RareClauseSourcePosition(unittest.TestCase):
    def test_rare_word_after_longer_fix(self):
        line = '犬の糸を察して晩景'
        result = {'original': line, 'corrected': '犬の意図を察して晩景', 'changed': True,
                  'original_spans': [(2, 3)], 'spans': [(2, 4)], 'odd_spans': []}
        with mock.patch.object(LK, '_restricted_face', lambda s: s == '晩景'):
            out = LK._mark_rare_clauses(result, line, {'input_method': 'romaji'})
        self.assertIn((7, 9), [tuple(x[:2]) for x in out['odd_spans']])
        self.assertTrue(all(0 <= a < b <= len(line) for a, b, *_ in out['odd_spans']))

    def test_mark_inside_fix_is_dropped(self):
        self.assertEqual(LK._source_positions('あ糸い', 'あ意図い', [(1, 3), (3, 4)]), [(2, 3)])

    def test_leftover_letters_after_longer_fix(self):
        line = '犬の糸を見てやsみます'
        shown = '犬の意図を見てやsみます'
        out = LK._mark_leftover_letters({'corrected': shown, 'original_spans': [(2, 3)], 'odd_spans': []}, line)
        for a, b in out.get('odd_spans') or ():
            self.assertTrue(0 <= a < b <= len(line))
            self.assertIn('s', line[a:b])


if __name__ == '__main__':
    unittest.main()
