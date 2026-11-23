"""2026-11-17: 守った所（引用した表記・守った語）は、補正の外側の段の後でも字も紫も変えない（作った例）。"""
import os
import unittest

import literal_guard as G


class Protected:
    def __init__(self, *words):
        self.words = words

    def protected_list(self):
        return [{'word': w} for w in self.words]


class LiteralGuard(unittest.TestCase):
    def test_declared_spelling_restored(self):
        line = 'ぽねという表記です。'
        r = G.guard(line, {'corrected': 'ホールという表記です。', 'changed': True, 'odd_spans': [(0, 2)],
                           'details': [('ぽね', 'ホール', 'x')]})
        self.assertEqual(r['corrected'], line)
        self.assertFalse(r['changed'])
        self.assertEqual(r['odd_spans'], [])

    def test_protected_word_and_outside_fix(self):
        line = 'ぺもらを閉じたます。'
        r = G.guard(line, {'corrected': '紙面を閉じてます。', 'changed': True, 'odd_spans': []},
                    Protected('ぺもら'))
        self.assertEqual(r['corrected'], 'ぺもらを閉じてます。')

    def test_unprotected_line_untouched(self):
        line = 'ぺもらを閉じたます。'
        res = {'corrected': '紙面を閉じてます。', 'changed': True, 'odd_spans': [(0, 3)]}
        self.assertIs(G.guard(line, res), res)

    def test_switch_off(self):
        os.environ['CN_LITERAL_GUARD'] = '0'
        try:
            res = {'corrected': 'ホールという表記です。'}
            self.assertIs(G.guard('ぽねという表記です。', res), res)
        finally:
            del os.environ['CN_LITERAL_GUARD']


if __name__ == '__main__':
    unittest.main()
