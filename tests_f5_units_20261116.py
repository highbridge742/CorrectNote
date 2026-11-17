# -*- coding: utf-8 -*-
"""F5 の渡り歩きで、語の頭・尻に付いた助詞「を」を切り離す（2026-11-16 うにさん「F5の範囲選択で遡ると、単語の前の
をが単語に付いてきた」）。作った例: 「みずをかう。」が み｜ずを｜かう と切れ、かう から遡ると「ずを」が選ばれた。"""
import unittest
from types import SimpleNamespace as NS

import f5_units as F


def unit(start, text, **kw):
    u = dict(start=start, end=start + len(text), text=text, base=text, reading=text, prev='', next='',
             kind='plain', detail=None, pos='名詞', infl='', atomic=True, known=True)
    u.update(kw)
    return u


class Split(unittest.TestCase):
    def test_wo_at_the_end_is_split_off(self):
        units = [unit(0, 'み'), unit(1, 'ずを', pos='助動詞'), unit(3, 'かう', detail="['かう','買う']"), unit(5, '。')]
        got = F.split_wo(units)
        self.assertEqual([u['text'] for u in got], ['み', 'ず', 'を', 'かう', '。'])
        self.assertEqual([(u['start'], u['end']) for u in got], [(0, 1), (1, 2), (2, 3), (3, 5), (5, 6)])
        wo = got[2]
        self.assertTrue(wo['f5_skip'])
        self.assertEqual((wo['pos'], wo['base'], wo['reading'], wo['detail']), ('助詞:格助詞:一般', 'を', 'を', None))
        self.assertEqual((got[1]['base'], got[1]['reading']), ('ず', 'ず'))
        self.assertEqual((wo['prev'], wo['next']), ('ず', 'かう'))
        self.assertIs(got[0], units[0])                       # 分けない単位は同じ dict（F5 の is の比べが効く）
        self.assertIs(got[3], units[2])

    def test_wo_at_the_head_is_split_off(self):
        got = F.split_wo([unit(0, '本'), unit(1, 'をよんだ'), unit(5, '。')])
        self.assertEqual([u['text'] for u in got], ['本', 'を', 'よんだ', '。'])
        self.assertTrue(got[1]['f5_skip'])
        self.assertNotIn('f5_skip', got[2])

    def test_untouched_cases(self):
        plain = [unit(0, '本'), unit(1, 'を'), unit(2, '読んだ')]
        self.assertIs(F.split_wo(plain), plain)                                  # 「を」だけの単位はそのまま
        proposed = [unit(0, 'ずを', detail="['ずを','図を']")]
        self.assertIs(F.split_wo(proposed), proposed)                              # 補正の提案を持つ単位は触らない
        other = [unit(0, 'かがみ'), unit(3, 'にわ'), unit(5, 'はな')]
        self.assertIs(F.split_wo(other), other)                                    # が・に・は は語の中にもある
        self.assertEqual(F.split_wo([]), [])
        units = [unit(0, 'ずを')]
        self.assertIs(F.split_wo(units, {'CN_F5_WO_SPLIT': '0'}), units)         # 切り替えで前の単位


class WalkSkipsTheSplitParticle(unittest.TestCase):
    def test_next_stop_skips_it(self):
        import app
        units = F.split_wo([unit(0, 'み'), unit(1, 'ずを', pos='助動詞'), unit(3, 'かう')])
        fake = NS(line_results=[{}], _f2_units_for_row=lambda row: None)
        row, idx, got = app.CorrectNoteApp._f2_next_stop(fake, 1, 3, units, -1)     # かう から左へ
        self.assertEqual(got[idx]['text'], 'ず')                                    # 「を」では止まらない


if __name__ == '__main__':
    unittest.main()
