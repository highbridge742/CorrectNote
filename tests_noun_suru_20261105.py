# -*- coding: utf-8 -*-
"""2026-11-05 挙動関連担当: 試験の作った例「作業が官僚しました。」が直らず紫も無い。する の付かない名詞＋する は、
同じ読みで する の付く身近な語が1つなら直し、決まらなければ紫。例は作った例。"""
import unittest

import correction_entry as C


def run(line):
    return C._noun_suru(line, {'corrected': line, 'changed': False})


class NounSuruTests(unittest.TestCase):
    def test_fixed(self):
        self.assertEqual(run('作業が官僚しました。')['corrected'], '作業が完了しました。')

    def test_purple_when_undecided(self):
        got = run('試合で先生した。')
        self.assertEqual(got['corrected'], '試合で先生した。')
        self.assertTrue(got.get('odd_spans'))

    def test_natural_left(self):
        for line in ('仕事しました。', '電話しました。', '毎日勉強しています。', '会社として参加する。', '最高にする'):
            got = run(line)
            self.assertEqual(got['corrected'], line, line)
            self.assertFalse(got.get('odd_spans'), line)


if __name__ == '__main__':
    unittest.main()
