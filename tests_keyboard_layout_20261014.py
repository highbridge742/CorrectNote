"""キーボードの配列と形（項目48-KB・2026-10-14）。

うにさんの指定「オプションにキーボード配列を追加して、QWERTY以外や、
他に配列が変わるもの、左右で分割されたキーボードなどの選択を用意して
ください。これは隣接キーに影響します」。

いちばん大事なのは **既定（QWERTY JIS・標準）で表が1組も変わらない**こと。
2026-10-14 まで corrector・loanword・en_space が書き下していた表を
ここに写して突き合わせる。
"""
import unittest
from types import SimpleNamespace

import keyboard_layout as K
import kana_layout as KL
import corrector as C
import loanword as L
import en_space as E


def _old_corrector_tables():
    rows = ('1234567890-^¥', 'qwertyuiop@[', 'asdfghjkl;:]', 'zxcvbnm,./\\')
    pos = {ch: (r, c) for r, row in enumerate(rows) for c, ch in enumerate(row)}

    def adj(p1, p2):
        return p1[0] == p2[0] and abs(p1[1] - p2[1]) == 1

    def intr(p1, p2):
        if p1 == p2:
            return False
        if p1[0] == p2[0]:
            return abs(p1[1] - p2[1]) == 1
        upper, lower = sorted((p1, p2))
        if lower[0] - upper[0] != 1:
            return False
        return lower[1] == upper[1] or (upper[0] != 1 and lower[1] == upper[1] - 1)
    near = frozenset((a, b) for a, pa in pos.items() for b, pb in pos.items() if adj(pa, pb))
    intrusion = frozenset((a, b) for a, pa in pos.items() for b, pb in pos.items() if intr(pa, pb))
    return pos, near, intrusion


def _old_letter_tables():
    rows = ('qwertyuiop', 'asdfghjkl', 'zxcvbnm')
    pos = {ch: (r, c) for r, row in enumerate(rows) for c, ch in enumerate(row)}
    near = frozenset((a, b) for a, pa in pos.items() for b, pb in pos.items()
                     if a != b and pa[0] == pb[0] and abs(pa[1] - pb[1]) == 1)
    intrusion = frozenset((a, b) for a, pa in pos.items() for b, pb in pos.items()
                          if a != b and abs(pa[0] - pb[0]) <= 1 and abs(pa[1] - pb[1]) <= 1)
    return pos, near, intrusion


def _adjacent_to(key, fn=None):
    fn = fn or C._qwerty_adjacent
    return {x for x in C._QWERTY_POS if fn(key, x)}


class KeyboardLayoutTest(unittest.TestCase):
    def setUp(self):
        K.apply()

    def tearDown(self):
        K.apply()
        self.assertEqual(K.current(), ('qwerty_jis', 'standard', '', 'jis'))

    def test_default_tables_unchanged(self):
        pos, near, intrusion = _old_corrector_tables()
        self.assertEqual(C._QWERTY_POS, pos)
        self.assertEqual(C._QWERTY_NEAR, near)
        self.assertEqual(C._QWERTY_INTRUSION_NEAR, intrusion)
        lpos, lnear, lintr = _old_letter_tables()
        self.assertEqual(list(L._QWERTY_POS), list(lpos))      # 同じ字・同じ順
        self.assertEqual(L._QWERTY_NEAR, lnear)
        self.assertEqual(L._QWERTY_INTRUSION_NEAR, lintr)
        self.assertEqual(list(E._QWERTY_POS), list(lpos))
        self.assertEqual(E._QWERTY_NEAR, lnear)
        for a in lpos:
            for b in lpos:
                self.assertEqual(L._qwerty_near(a, b), (a, b) in lnear)
                self.assertEqual(L._qwerty_intrusion_near(a, b), (a, b) in lintr)
                self.assertEqual(E._near(a, b), (a, b) in lnear)
        # tests_shift_intrusion の期待値
        self.assertEqual(_adjacent_to('y', C._qwerty_intrusion_adjacent), set('67tuh'))
        self.assertEqual(_adjacent_to('h', C._qwerty_intrusion_adjacent), set('ygjbn'))
        self.assertEqual(_adjacent_to('g'), set('fh'))
        self.assertEqual(KL.ROW_OFFSET, {0: 0.0, 1: 0.5, 2: 0.75, 3: 1.25})

    def test_every_layout_has_each_letter_once(self):
        for name, rows in K.LAYOUT_ROWS.items():
            with self.subTest(layout=name):
                letters = [ch for row in rows for ch in row if 'a' <= ch <= 'z']
                self.assertEqual(sorted(letters), [chr(c) for c in range(97, 123)])
                self.assertEqual(len(rows), 4)
                K.apply(name)
                self.assertEqual(K.current()[0], name)
                self.assertEqual(len(L._QWERTY_POS), 26)
                self.assertEqual(len(E._QWERTY_POS), 26)
                for a, b in C._QWERTY_NEAR:
                    self.assertTrue(C._qwerty_adjacent(a, b))
                    self.assertTrue(C._qwerty_adjacent(b, a))     # 隣は対称

    def test_colemak_dh_is_the_staggered_form(self):
        K.apply('colemak_dh')
        self.assertEqual(K.rows()[3], 'xcdvzkh,./')
        self.assertFalse(C._qwerty_adjacent('v', 'k'))      # 格子形の並びでは v|k が隣になっていた
        self.assertTrue(C._qwerty_adjacent('z', 'k'))
        self.assertTrue(C._qwerty_adjacent('d', 'v'))

    def test_dvorak_changes_neighbours(self):
        K.apply('dvorak')
        self.assertTrue(C._qwerty_adjacent('e', 'u'))      # 中段 a o e u i
        self.assertTrue(C._qwerty_adjacent('h', 't'))
        self.assertFalse(C._qwerty_adjacent('q', 'w'))     # q は下段・w は離れている
        self.assertTrue(C._qwerty_adjacent("'", ','))
        self.assertTrue(L._qwerty_near('c', 'r'))
        self.assertTrue(E._near('g', 'c'))
        self.assertFalse(L._qwerty_near('g', 'h'))
        # 巻き込みは別の表（上下も隣）
        self.assertTrue(C._qwerty_intrusion_adjacent('p', 'u'))  # p の下に u
        self.assertFalse(C._qwerty_intrusion_adjacent('p', 'e'))  # 斜め左下は隣でない（JIS の決まり）
        # 戻せば元の表
        K.apply()
        pos, near, intrusion = _old_corrector_tables()
        self.assertEqual(C._QWERTY_NEAR, near)
        self.assertEqual(C._QWERTY_INTRUSION_NEAR, intrusion)

    def test_split_keyboard_has_no_neighbour_across_the_gap(self):
        K.apply('qwerty_jis', 'split')
        for a, b in (('t', 'y'), ('g', 'h'), ('b', 'n'), ('6', '7')):
            with self.subTest(pair=(a, b)):
                self.assertFalse(C._qwerty_adjacent(a, b))
                self.assertFalse(C._qwerty_adjacent(b, a))
                self.assertFalse(C._qwerty_intrusion_adjacent(a, b))
                self.assertFalse(L._qwerty_intrusion_near(a, b))
        self.assertTrue(C._qwerty_adjacent('5', '6'))        # 段ずれの分割は 6 が左
        self.assertTrue(C._qwerty_adjacent('f', 'g'))
        self.assertTrue(C._qwerty_adjacent('h', 'j'))
        self.assertFalse(C._qwerty_intrusion_adjacent('y', 't'))
        self.assertEqual(_adjacent_to('y', C._qwerty_intrusion_adjacent), set('7uh'))
        self.assertFalse(L._qwerty_near('g', 'h'))
        self.assertFalse(E._near('g', 'h'))
        # かな入力にも効く: か(T) と ん(Y) は別の手の側
        self.assertGreaterEqual(KL.kana_key_distance('か', 'ん'), 50)
        self.assertEqual(KL.kana_key_distance('す', 'か'), 1.0)
        self.assertNotIn('ん', dict(KL.nearby_candidates('か', include_phonetic=False)))
        K.apply()
        self.assertEqual(KL.kana_key_distance('か', 'ん'), 1.0)
        self.assertIn('ん', dict(KL.nearby_candidates('か', include_phonetic=False)))

    def test_split_ortho_splits_the_number_row_between_5_and_6(self):
        K.apply('qwerty_jis', 'split_ortho')
        self.assertFalse(C._qwerty_adjacent('5', '6'))
        self.assertTrue(C._qwerty_adjacent('6', '7'))
        self.assertFalse(C._qwerty_intrusion_adjacent('6', 't'))

    def test_ortho_has_no_diagonal_neighbours(self):
        K.apply('qwerty_jis', 'ortho')
        self.assertEqual(KL.ROW_OFFSET, {0: 0.0, 1: 0.0, 2: 0.0, 3: 0.0})
        self.assertEqual(_adjacent_to('y', C._qwerty_intrusion_adjacent), set('6tuh'))
        self.assertEqual(_adjacent_to('h', C._qwerty_intrusion_adjacent), set('ygjn'))
        self.assertTrue(C._qwerty_adjacent('g', 'h'))        # 左右はそのまま
        self.assertTrue(L._qwerty_intrusion_near('y', 'h'))
        self.assertFalse(L._qwerty_intrusion_near('y', 'g'))   # 斜めは隣でない
        self.assertFalse(L._qwerty_intrusion_near('y', 'j'))
        # かな: く(H) の巻き込みの隣は ん(Y)・み(N)・き(G)・ま(J)。こ(B) は斜め
        self.assertEqual(KL.kana_key_distance('く', 'ん', intrusion=True), 1.0)
        self.assertGreater(KL.kana_key_distance('く', 'こ', intrusion=True), 1.0)
        K.apply()
        self.assertEqual(KL.kana_key_distance('く', 'こ', intrusion=True), 1.0)

    def test_custom_rows(self):
        rows = K.parse_rows('qwertyuiop|asdfghjkl|zxcvbnm')
        self.assertEqual(rows, ('1234567890-^¥', 'qwertyuiop', 'asdfghjkl', 'zxcvbnm'))
        self.assertEqual(K.parse_rows('q w e r t y u i o p\nasdfghjkl\nzxcvbnm'), rows)
        self.assertIsNone(K.parse_rows('abc|def|ghi'))
        self.assertIsNone(K.parse_rows(''))
        self.assertIsNone(K.parse_rows(None))
        # 段に使った字は数字段から外すが、位置は詰めない（0 と ^ が隣にならない）
        rows2 = K.parse_rows("qwertyuiop-|asdfghjkl|zxcvbnm")
        self.assertEqual(rows2[0], '1234567890 ^¥')
        K.apply('custom', 'standard', "qwertyuiop-|asdfghjkl|zxcvbnm")
        self.assertFalse(C._qwerty_adjacent('0', '^'))
        self.assertEqual(C._QWERTY_POS['^'], (0, 11))
        self.assertNotIn(' ', C._QWERTY_POS)
        # Hunspell の man にある KEY の例（字だけ・段は | 区切り）
        K.apply('custom', 'standard', 'pyfgcrl|aeouidhtns|qjkxbmwvz')
        self.assertEqual(K.current(), ('custom', 'standard', 'pyfgcrl|aeouidhtns|qjkxbmwvz', 'jis'))
        self.assertTrue(C._qwerty_adjacent('e', 'o'))
        self.assertTrue(C._qwerty_adjacent('o', 'u'))
        self.assertFalse(C._qwerty_adjacent('e', 'u'))
        self.assertFalse(C._qwerty_adjacent('e', 'r'))
        self.assertTrue(L._qwerty_near('h', 't'))
        # 読めない段は既定に落ちる（補正を止めない）
        K.apply('custom', 'standard', 'abc')
        self.assertEqual(K.current(), ('qwerty_jis', 'standard', '', 'jis'))

    def test_unknown_names_fall_back_to_default(self):
        self.assertFalse(K.apply('qwerty_jis', 'standard'))
        self.assertFalse(K.apply('nonsense', 'weird', None, 'nonsense'))
        self.assertEqual(K.current(), ('qwerty_jis', 'standard', '', 'jis'))
        self.assertFalse(K.apply_spec(None))
        self.assertTrue(K.apply_spec(('dvorak', 'split', '')))      # 3つの古い組も読める
        self.assertTrue(K.apply_spec(['qwerty_jis', 'standard']))   # JSON を往復しても読める
        self.assertFalse(K.apply_spec(42))                           # 組でない値は既定
        self.assertEqual(K.spec_text(42), 'qwerty_jis/standard/jis')
        self.assertEqual(K.current(), ('qwerty_jis', 'standard', '', 'jis'))

    def test_spec_from_settings(self):
        self.assertEqual(K.spec({}), ('qwerty_jis', 'standard', '', 'jis'))
        self.assertEqual(K.spec(None), ('qwerty_jis', 'standard', '', 'jis'))
        self.assertEqual(K.spec({'keyboard_layout': 'colemak', 'keyboard_shape': 'ortho'}),
                         ('colemak', 'ortho', '', 'jis'))
        self.assertEqual(K.spec({'keyboard_layout': 'custom', 'keyboard_custom_rows': 'x|y|z'}),
                         ('custom', 'standard', 'x|y|z', 'jis'))
        # custom でないときは段の文字列を持ち歩かない
        self.assertEqual(K.spec({'keyboard_layout': 'dvorak', 'keyboard_custom_rows': 'x'}),
                         ('dvorak', 'standard', '', 'jis'))
        self.assertEqual(K.spec({'kana_layout': 'nicola'}), ('qwerty_jis', 'standard', '', 'nicola'))
        self.assertEqual(K.spec({'kana_layout': 'bogus'}), ('qwerty_jis', 'standard', '', 'jis'))
        # かな配列はかな入力のときだけ。ローマ字入力では JIS のまま（指紋も jis）
        self.assertEqual(K.spec({'kana_layout': 'nicola', 'input_method': 'romaji'}),
                         ('qwerty_jis', 'standard', '', 'jis'))
        self.assertEqual(K.spec({'kana_layout': 'shin_jis', 'input_method': 'kana'}),
                         ('qwerty_jis', 'standard', '', 'shin_jis'))
        self.assertEqual(K.spec({'kana_layout': 'nicola', 'input_method': 'kana',
                                 'keyboard_layout': 'dvorak'}),
                         ('dvorak', 'standard', '', 'nicola'))
        self.assertEqual(K.spec_text(('dvorak', 'split', '')), 'dvorak/split/jis')
        self.assertEqual(K.spec_text(None), 'qwerty_jis/standard/jis')
        self.assertEqual(K.spec_text(('custom', 'ortho', 'a|b|c', 'shin_jis')), 'custom/ortho/shin_jis/a|b|c')
        self.assertEqual(K.describe(('dvorak', 'split', '')), 'Dvorak・左右分割')
        self.assertEqual(K.describe(('dvorak', 'split', '', 'nicola')), 'Dvorak・左右分割・親指シフト')

    def test_settings_accept_the_new_keys(self):
        import settings as S
        self.assertEqual(S.DEFAULTS['keyboard_layout'], 'qwerty_jis')
        self.assertEqual(S.DEFAULTS['keyboard_shape'], 'standard')
        self.assertEqual(tuple(S.KEYBOARD_LAYOUT_LABELS), K.LAYOUTS)
        self.assertEqual(tuple(S.KEYBOARD_SHAPE_LABELS), K.SHAPES)
        self.assertEqual(S.DEFAULTS['kana_layout'], 'jis')
        self.assertEqual(tuple(S.KANA_LAYOUT_LABELS), K.KANA_LAYOUTS)

    def test_worker_state_and_fingerprint_follow_the_keyboard(self):
        import analysis_worker as W
        import analysis_cache as AC
        a = SimpleNamespace(settings={'input_method': 'kana'})
        b = SimpleNamespace(settings={'input_method': 'kana', 'keyboard_layout': 'dvorak'})
        ka, kb = W.state_key(a), W.state_key(b)
        self.assertEqual(len(ka), 10)
        self.assertNotEqual(ka, kb)
        self.assertFalse(W.same_model_state(ka, kb))      # 配列が変われば全部やり直す
        self.assertTrue(W.same_model_state(ka, W.state_key(a)))
        fa = AC.build_fingerprint('.', '1.0', 'kana', ())
        fb = AC.build_fingerprint('.', '1.0', 'kana', (), keyboard=('dvorak', 'split', ''))
        self.assertEqual(fa['keyboard'], 'qwerty_jis/standard/jis')
        self.assertEqual(fb['keyboard'], 'dvorak/split/jis')
        c = SimpleNamespace(settings={'input_method': 'kana', 'kana_layout': 'nicola'})
        self.assertFalse(W.same_model_state(ka, W.state_key(c)))   # かな配列が変われば全部やり直す
        fc = AC.build_fingerprint('.', '1.0', 'kana', (), keyboard=K.spec(c.settings))
        self.assertEqual(fc['keyboard'], 'qwerty_jis/standard/nicola')

    def test_romaji_slip_follows_the_layout(self):
        # ローマ字入力: ほ→ご は h/g が隣（QWERTY）。Dvorak では h の隣は d と t
        self.assertTrue(C.adjacent_slip('ほ', 'ご', 'romaji'))
        K.apply('dvorak')
        self.assertFalse(C.adjacent_slip('ほ', 'ご', 'romaji'))
        self.assertTrue(C.adjacent_slip('ほ', 'と', 'romaji'))       # ho / to（h と t が隣）
        self.assertIn('と', dict(KL.nearby_candidates('ほ', include_phonetic=False,
                                                     input_method='romaji')))
        K.apply()
        self.assertTrue(C.adjacent_slip('ほ', 'ご', 'romaji'))
        self.assertNotIn('と', dict(KL.nearby_candidates('ほ', include_phonetic=False,
                                                        input_method='romaji')))


if __name__ == '__main__':
    unittest.main()
