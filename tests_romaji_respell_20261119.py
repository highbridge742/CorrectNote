"""2026-11-19: ローマ字入力の読み直しを後の段で戻さない・文の形の紫も読み直す（作った例）。"""
import os
import unittest

import dict_word_keep as K
import fixed_still_odd as F


class RomajiOddKept(unittest.TestCase):
    line = '週末の買い物の予定を書く。'
    new = '週末の会い物の予定を書く。'

    def _res(self):
        return {'corrected': self.new, 'changed': True, 'details': [('買い物', '会い物', '紫の所の打ち違い')]}

    def test_romaji_keeps(self):
        self.assertEqual(K.keep(self.line, self._res(), input_method='romaji')['corrected'], self.new)

    def test_switch_off_same_as_kana(self):
        kana = K.keep(self.line, self._res(), input_method='kana')['corrected']
        os.environ['CN_DICT_WORD_KEEP_ROMAJI_ODD'] = '0'
        try:
            self.assertEqual(K.keep(self.line, self._res(), input_method='romaji')['corrected'], kana)
        finally:
            del os.environ['CN_DICT_WORD_KEEP_ROMAJI_ODD']


class RespellBackTouch(unittest.TestCase):
    line = '青空の歩道橋'
    res = {'corrected': '青空の補導局', 'details': [('歩道橋', '補導局', '紫の所の打ち違い')]}

    def _back(self, im, span):
        F._IM[0] = im
        try:
            return F._guess_only_back(self.line, dict(self.res), span)
        finally:
            F._IM[0] = None

    def test_kana_adjacent_goes_back(self):
        self.assertIsNotNone(self._back('kana', (1, 3)))

    def test_romaji_adjacent_kept(self):
        self.assertIsNone(self._back('romaji', (1, 3)))

    def test_romaji_overlap_goes_back(self):
        self.assertIsNotNone(self._back('romaji', (3, 6)))

    def test_switch_off(self):
        os.environ['CN_FSO_RESPELL_BACK_ROMAJI_TOUCH'] = '0'
        try:
            self.assertIsNotNone(self._back('romaji', (1, 3)))
        finally:
            del os.environ['CN_FSO_RESPELL_BACK_ROMAJI_TOUCH']


class ShapeRespellGate(unittest.TestCase):
    def test_kana_untouched(self):
        import correction_entry as ce
        r = {'corrected': 'あ', 'odd_spans': [(0, 1)]}
        self.assertIs(ce._shape_respell('あ', {'odd_spans': []}, r, None, None, None, None, None, 'kana'), r)

    def test_no_new_span_untouched(self):
        import correction_entry as ce
        r = {'corrected': 'あ', 'odd_spans': [(0, 1)]}
        self.assertIs(ce._shape_respell('あ', {'odd_spans': [(0, 1)]}, r, None, None, None, None, None, 'romaji'), r)


class ShoTail(unittest.TestCase):
    def test_marks_sho_followed_by_word(self):
        import broken_shape as B
        self.assertTrue(any(r == '丁寧の形の後ろが続きません' for a, b, r in B.spans('どうでしょいか')))

    def test_plain_endings_not_marked(self):
        import broken_shape as B
        for t in ('どうでしょうか', 'そうでしょ。', 'いいでしょね', '行きましょう'):
            self.assertFalse([x for x in B.spans(t) if x[2] == '丁寧の形の後ろが続きません'], t)

    def test_switch_off(self):
        import broken_shape as B
        os.environ['CN_BROKEN_SHO_TAIL'] = '0'
        try:
            self.assertFalse([x for x in B.spans('どうでしょいか') if x[2] == '丁寧の形の後ろが続きません'])
        finally:
            del os.environ['CN_BROKEN_SHO_TAIL']


class ImeLineSlice(unittest.TestCase):
    def setUp(self):
        import odd_respell as O
        self.O = O
        O._IME_LINE.clear()

    def tearDown(self):
        self.O._IME_LINE.clear()

    def test_slice_on_word_bounds(self):
        # 作った例: 打った読み（IME の読み）と解析の読みが違う漢字の語
        self.O._IME_LINE['甲乙丙の話'] = ('こうおつへいのはなし', ((0, 3, 0, 6, 100, 3), (3, 4, 6, 7, 0, 2), (4, 5, 7, 10, 100, 3)))
        self.assertEqual(self.O._ime_line_slice('甲乙丙の話', 0, 3), 'こうおつへい')
        self.assertIsNone(self.O._ime_line_slice('甲乙丙の話', 0, 2))

    def test_untyped_dictionary_ignored(self):
        self.O._IME_LINE['甲乙丙の話'] = ('こうおつへいのはなし', ((0, 3, 0, 6, 0, 0), (3, 4, 6, 7, 0, 0), (4, 5, 7, 10, 0, 0)))
        self.assertIsNone(self.O._ime_line_slice('甲乙丙の話', 0, 3))

    def test_switch_off(self):
        self.O._IME_LINE['甲乙丙の話'] = ('こうおつへいのはなし', ((0, 3, 0, 6, 100, 3), (3, 4, 6, 7, 0, 2), (4, 5, 7, 10, 100, 3)))
        os.environ['CN_ROMAJI_IME_READING'] = '0'
        try:
            self.assertIsNone(self.O._ime_line_slice('甲乙丙の話', 0, 3))
        finally:
            del os.environ['CN_ROMAJI_IME_READING']


class OneKeyElsewhere(unittest.TestCase):
    def test_one_key_word_outside(self):
        import odd_respell as O
        # 作った例: 戻した所 [0,1) の外の1語が ローマ字1打（me → ne）
        self.assertTrue(O._romaji_one_key_elsewhere('雨の目', '雨の目', '雨の根', 0, 1))

    def test_inside_change_not_counted(self):
        import odd_respell as O
        self.assertFalse(O._romaji_one_key_elsewhere('雨の時刻', '雨の時刻', '飴の時刻', 0, 1))

    def test_far_change_not_counted(self):
        import odd_respell as O
        self.assertFalse(O._romaji_one_key_elsewhere('雨の時刻', '雨の時刻', '雨の未来', 0, 1))


class FsoRomajiRespellGate(unittest.TestCase):
    def test_kana_untouched(self):
        out = {'corrected': '雨の日', 'odd_spans': [(2, 3)]}
        self.assertIs(F._romaji_respell_mark('雨の目', {'odd_spans': []}, out, (None, None, None, 'kana'), {}), out)

    def test_purple_on_fix_untouched(self):
        out = {'corrected': '雨の日', 'odd_spans': [(2, 3)]}
        self.assertIs(F._romaji_respell_mark('雨の目', {'odd_spans': []}, out, (None, None, None, 'romaji'), {}), out)

    def test_switch_off(self):
        out = {'corrected': '飴の目', 'odd_spans': [(2, 3)]}
        os.environ['CN_FSO_ROMAJI_RESPELL'] = '0'
        try:
            self.assertIs(F._romaji_respell_mark('雨の目', {'odd_spans': []}, out, (None, None, None, 'romaji'), {}), out)
        finally:
            del os.environ['CN_FSO_ROMAJI_RESPELL']


class TwoKey(unittest.TestCase):
    def test_two_key_reading(self):
        import odd_respell as O
        # 作った例: sakura を sakrtua と打った（入れ替え＋隣のキーの1打）
        self.assertIn('さくら', O._romaji_two_key_repairs('さkrつあ'))

    def test_switch_off(self):
        import odd_respell as O
        os.environ['CN_ROMAJI_TWO_KEY'] = '0'
        try:
            self.assertEqual(O._romaji_two_key_repairs('さkrつあ'), [])
        finally:
            del os.environ['CN_ROMAJI_TWO_KEY']


if __name__ == '__main__':
    unittest.main()
