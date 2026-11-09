# -*- coding: utf-8 -*-
"""かなの例文の誤った直し（b401）への一般の直し（2026-11-08 手分けA）。例は作った文。
OddRespellGuard は odd_respell.py.diff を入れたときだけ通る。"""
import os
import unittest

import ime_reconvert as I


class HomophoneTie(unittest.TestCase):
    def test_tie(self):
        # 同じ読みの身近な表記が並ぶ（風邪／風）なら決めない
        self.assertTrue(I._homophone_tie('すずしい巣瀬がふく', 'すずしい風邪がふく'))

    def test_no_tie(self):
        self.assertFalse(I._homophone_tie('ふくに荷物を置いた', '服に荷物を置いた'))
        self.assertFalse(I._homophone_tie('今日は晴天です', '今日は晴天です'))

    def test_switch(self):
        os.environ['CN_RECONVERT_HOMO_TIE'] = '0'
        try:
            self.assertFalse(I._homophone_tie('すずしい巣瀬がふく', 'すずしい風邪がふく'))
        finally:
            del os.environ['CN_RECONVERT_HOMO_TIE']


class DictFacesVerbKana(unittest.TestCase):
    def test_no_bare_kanji_verb(self):
        # 来（きた）のように活用の字を落とす動詞の表記は出さない
        self.assertNotIn('来', I._dict_faces('きた', 8))


class LatticeVerbTe(unittest.TestCase):
    def test_verb_te(self):
        self.assertIn('遊んで', I._lattice_faces('あそんで'))


class OddRespellGuard(unittest.TestCase):
    def test_ends_on_conjunction(self):
        import odd_respell as O
        t = '電車が遅れてなさて'
        self.assertTrue(O._ends_on_conjunction(t, len(t) - 3, len(t)))
        self.assertFalse(O._ends_on_conjunction('しかし雨だった', 0, 3))

    def test_guard_marks_purple(self):
        import odd_respell as O
        res = {'original': 'すずしい巣瀬がふく', 'corrected': 'すずしい巣瀬がふく', 'odd_spans': []}
        out = dict(res, corrected='すずしい風邪がふく', changed=True)
        kept = O._homophone_guard(res, out, 'すずしい巣瀬がふく')
        self.assertEqual(kept['corrected'], 'すずしい巣瀬がふく')
        self.assertIn([4, 6], kept['odd_spans'])


if __name__ == '__main__':
    unittest.main()
