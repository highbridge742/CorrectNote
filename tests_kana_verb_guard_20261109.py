# -*- coding: utf-8 -*-
"""紫の所の読み直しが、かなで書いた身近な用言（ほし｜がる）を別の語に替える直しを採らない（2026-11-09 手分けA）。例は作った文。"""
import os
import unittest

import odd_respell as O


def _res(line, odd):
    return {'original': line, 'corrected': line, 'changed': False, 'details': [],
            'odd_spans': [list(odd) + ['odd']], 'odd_reasons': [list(odd) + ['x']]}


class KanaVerbGuard(unittest.TestCase):
    def test_common_verbs(self):
        self.assertIn((2, 6), O._common_kana_verbs('妹がほしがる本'))
        self.assertIn((3, 7), O._common_kana_verbs('ぼくはたべたい'))
        self.assertEqual(O._common_kana_verbs('ほんをよんた'), [])
        self.assertEqual(O._common_kana_verbs('かいぎのしりょう'), [])

    def test_broken_runs(self):
        # 打ち違いで崩れた並びは用言として守らない（浮いた ゛・続きの無い活用の形）
        self.assertEqual(O._common_kana_verbs('友だちとい゛遊んだ'), [])
        self.assertEqual(O._common_kana_verbs('仕事がかかたっ'), [])

    def test_keep_verb(self):
        line = '妹がほしがる本を買った。'
        res = _res(line, (2, 5))
        out = dict(res, corrected='妹がしかける本を買った。', changed=True)
        kept = O._kana_verb_guard(res, out, line)
        self.assertEqual(kept['corrected'], line)
        self.assertEqual(kept['odd_spans'], [])

    def test_other_place(self):
        line = '妹がほしがる本をかっつた。'
        res = _res(line, (8, 12))
        out = dict(res, corrected='妹がほしがる本を買った。', changed=True)
        self.assertIs(O._kana_verb_guard(res, out, line), out)

    def test_switch(self):
        line = '妹がほしがる本を買った。'
        res = _res(line, (2, 5))
        out = dict(res, corrected='妹がしかける本を買った。', changed=True)
        os.environ['CN_RESPELL_KANA_VERB_GUARD'] = '0'
        try:
            self.assertIs(O._kana_verb_guard(res, out, line), out)
        finally:
            del os.environ['CN_RESPELL_KANA_VERB_GUARD']


if __name__ == '__main__':
    unittest.main()
