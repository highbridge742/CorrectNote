# -*- coding: utf-8 -*-
"""手の位置のずれ（片手が横に1キーずれて続けて打ち違う）の戻しを、1打の戻しと同じ場で比べる（うに 2026-11-10 08:09Z）。
例は作った文。"""
import os
import unittest

import odd_respell as O


def _res(line, odd):
    return {'original': line, 'corrected': line, 'changed': False, 'details': [],
            'odd_spans': [list(odd) + ['odd']], 'odd_reasons': [list(odd) + ['x']]}


class ShiftExplained(unittest.TestCase):
    def _ops(self, x, y):
        import difflib
        return [o for o in difflib.SequenceMatcher(None, x, y, autojunk=False).get_opcodes() if o[0] != 'equal']

    def test_shift(self):
        # ね→も・り→の は右手の揃った1列のずれ
        x, y = 'ねりさしで長さ', 'ものさしで長さ'
        self.assertTrue(O._shift_explained(x, y, self._ops(x, y)))

    def test_not_shift(self):
        x, y = 'ほしがるだけ', 'しかけるだけ'
        self.assertFalse(O._shift_explained(x, y, self._ops(x, y)))

    def test_verb_guard_passes_shift(self):
        line = 'ねりさしで長さを測る'
        res = _res(line, (0, 5))
        out = dict(res, corrected='ものさしで長さを測る', changed=True)
        self.assertIs(O._kana_verb_guard(res, out, line), out)
        os.environ['CN_SHIFT_PASS_VERB_GUARD'] = '0'
        try:
            self.assertEqual(O._kana_verb_guard(res, out, line)['corrected'], line)
        finally:
            del os.environ['CN_SHIFT_PASS_VERB_GUARD']


class EverydayNoun(unittest.TestCase):
    def test_everyday_not_rare_in_shift(self):
        # 身近な名詞を稀な語としないのは、手のずれの戻しを比べている間だけ（1打の戻しの 無柄化→無縁 は前のまま）
        self.assertTrue(O._rare_new_noun('ねりさしで長さを測る', '物差しで長さを測る'))
        O._IN_SHIFT[0] = True
        try:
            self.assertFalse(O._rare_new_noun('ねりさしで長さを測る', '物差しで長さを測る'))
            os.environ['CN_RARE_EVERYDAY'] = '0'
            try:
                self.assertTrue(O._rare_new_noun('ねりさしで長さを測る', '物差しで長さを測る'))
            finally:
                del os.environ['CN_RARE_EVERYDAY']
        finally:
            O._IN_SHIFT[0] = False


class ShiftRivals(unittest.TestCase):
    def test_same_shift_is_one(self):
        k = ((0, 2, 'てが'),)
        seen = {'手紙を出した': (100, True), '手紙をでした': (90, True)}
        came = {'手紙を出した': {k}, '手紙をでした': {k}}
        self.assertEqual(O._shift_rivals(seen, came, 10000, 0), 1)

    def test_two_shifts(self):
        seen = {'甲': (100, True), '乙': (90, True)}
        came = {'甲': {((0, 2, 'あい'),)}, '乙': {((0, 2, 'かき'),)}}
        self.assertEqual(O._shift_rivals(seen, came, 10000, 0), 2)


class TypedWindow(unittest.TestCase):
    def setUp(self):
        import kanji_guess
        self.kg = kanji_guess
        self.old = kanji_guess._IME_READINGS_PROVIDER
        rec = {'襟数': ['えりすう']}
        kanji_guess._IME_READINGS_PROVIDER = lambda s: rec.get(s, [])

    def tearDown(self):
        self.kg._IME_READINGS_PROVIDER = self.old

    def test_window(self):
        # 漢字の語は打った読み、前後の平仮名は字のまま（近い3字まで）
        got = O._typed_window('お手数ですが襟数とお電話ください', 6, 8)
        self.assertEqual(got, (3, 10, ['ですがえりすうとお'], 3, 10))

    def test_whole_word_left(self):
        # 前の平仮名が漢字の語の送り仮名なら、語ごと打った読みで入れる（燃え｜髪は → もえかみは）
        self.kg._IME_READINGS_PROVIDER = lambda s: {'燃え': ['もえ'], '髪': ['かみ']}.get(s, [])
        self.assertEqual(O._typed_window('燃え髪はで終わる', 2, 3)[:3], (0, 5, ['もえかみはで']))
        self.assertEqual(O._typed_window('燃え髪はで終わる', 2, 3, whole_word=False)[:3], (1, 5, ['えかみはで']))

    def test_no_record(self):
        self.assertIsNone(O._typed_window('お手数ですが襟巻とお電話ください', 6, 8))

    def test_switch(self):
        called = []
        tw = O._typed_window
        O._typed_window = lambda *a, **k: called.append(a) or tw(*a, **k)
        os.environ['CN_SHIFT_TYPED_WINDOW'] = '0'
        try:
            O._shift_span('お手数ですが襟数とお電話ください', 6, 8, ['えりすう'], 6, 8, None)
            self.assertEqual(called, [])
        finally:
            del os.environ['CN_SHIFT_TYPED_WINDOW']
            O._typed_window = tw
        O._shift_span('お手数ですが襟数とお電話ください', 6, 8, ['えりすう'], 6, 8, None)


class BreaksKanaVerb(unittest.TestCase):
    def test_breaks(self):
        # 1打の戻しが かなの用言 ねり を 寝る に替える形（後ろの守りで採られない）
        self.assertTrue(O._breaks_kana_verb('ねりさしで長さを測る', '寝るさしで長さを測る'))
        self.assertFalse(O._breaks_kana_verb('ねりさしで長さを測る', 'ものさしで長さを測る', shift_ok=True))
        self.assertFalse(O._breaks_kana_verb('本をかっつた', '本を買った'))


if __name__ == '__main__':
    unittest.main()
