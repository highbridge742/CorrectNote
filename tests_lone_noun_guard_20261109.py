# -*- coding: utf-8 -*-
"""読み直しが漢字1字の名詞＋助詞を用言に替える直しを採らない（2026-11-09 手分けA）。例は作った文。"""
import os
import unittest

import odd_respell as O


def _res(line):
    return {'original': line, 'corrected': line, 'changed': False, 'details': [],
            'odd_spans': [[2, 4, 'odd']], 'odd_reasons': []}


class LoneNounGuard(unittest.TestCase):
    def test_keep_noun(self):
        line = '海と山は遠くない。'
        res = _res(line)
        out = dict(res, corrected='海と止まる遠くない。', changed=True)
        self.assertIs(O._lone_kanji_noun_guard(res, out, line), res)

    def test_no_before_verb(self):
        # 連体の の の後ろに用言が来る（文の形が立たない）なら守らない
        line = '駅で李の換えた'
        res = _res(line)
        out = dict(res, corrected='駅で乗り換えた', changed=True)
        self.assertIs(O._lone_kanji_noun_guard(res, out, line), out)

    def test_switch(self):
        line = '海と山は遠くない。'
        res = _res(line)
        out = dict(res, corrected='海と止まる遠くない。', changed=True)
        os.environ['CN_RESPELL_LONE_NOUN_GUARD'] = '0'
        try:
            self.assertIs(O._lone_kanji_noun_guard(res, out, line), out)
        finally:
            del os.environ['CN_RESPELL_LONE_NOUN_GUARD']


if __name__ == '__main__':
    unittest.main()
