# -*- coding: utf-8 -*-
"""batch417: 身近な常用外の語は疑わない（kanji_doubt）・動詞＋接尾の中の直しはまとめて戻す（_aux_verb_keep）。"""
import os
import unittest

import kanji_doubt
import correction_entry as CE


class CommonKanjiAux(unittest.TestCase):
    def test_common_word_not_suspected(self):
        self.assertFalse([s for s in kanji_doubt.suspects('もう嘘だよ') if s[0] <= 2 < s[1]])

    def test_common_word_switch_off(self):
        os.environ['CN_KD_COMMON_WORD'] = '0'
        try:
            self.assertTrue([s for s in kanji_doubt.suspects('もう嘘だよ') if s[0] <= 2 < s[1]])
        finally:
            del os.environ['CN_KD_COMMON_WORD']

    def test_aux_unit_reverted_whole(self):
        line = '手伝わさせて。'
        res = {'original': line, 'corrected': '手つだわされて。', 'changed': True, 'details': [], 'odd_spans': []}
        out = CE._aux_verb_keep(line, res)
        self.assertEqual(out['corrected'], line)


if __name__ == '__main__':
    unittest.main()
