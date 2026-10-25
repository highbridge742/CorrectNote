"""かな配列の選択（項目48-KB・かな配列・2026-10-14）。

うにさんがカードで「用意する」と答えた、かな入力の配列の選択
（JIS かな・親指シフト＝NICOLA・新JIS）。

いちばん大事なのは **既定（JIS）で表が1字も動かない**こと。2026-10-14
までの `kana_layout` の書き下しをここに写して突き合わせる。
"""
import unittest

import keyboard_layout as K
import kana_layout as KL
import halfwidth as H
import contextual_repair as CR
import corrector as C


# 2026-10-14 までの kana_layout の表（既定が変わっていないことの物差し）
_OLD_POSITIONS = {
    'ぬ': (0, 0), 'ふ': (0, 1), 'あ': (0, 2), 'う': (0, 3), 'え': (0, 4),
    'お': (0, 5), 'や': (0, 6), 'ゆ': (0, 7), 'よ': (0, 8), 'わ': (0, 9),
    'ほ': (0, 10), 'へ': (0, 11),
    'た': (1, 0), 'て': (1, 1), 'い': (1, 2), 'す': (1, 3), 'か': (1, 4),
    'ん': (1, 5), 'な': (1, 6), 'に': (1, 7), 'ら': (1, 8), 'せ': (1, 9),
    'ち': (2, 0), 'と': (2, 1), 'し': (2, 2), 'は': (2, 3), 'き': (2, 4),
    'く': (2, 5), 'ま': (2, 6), 'の': (2, 7), 'り': (2, 8), 'れ': (2, 9),
    'け': (2, 10), 'む': (2, 11),
    'つ': (3, 0), 'さ': (3, 1), 'そ': (3, 2), 'ひ': (3, 3), 'こ': (3, 4),
    'み': (3, 5), 'も': (3, 6), 'ね': (3, 7), 'る': (3, 8), 'め': (3, 9),
    'ろ': (3, 10),
    'ー': (0, 12), 'を': (0, 9),
    'ぁ': (0, 2), 'ぅ': (0, 3), 'ぇ': (0, 4), 'ぉ': (0, 5),
    'ゃ': (0, 6), 'ゅ': (0, 7), 'ょ': (0, 8),
    'ぃ': (1, 2), 'っ': (3, 0),
    '゛': (1, 10), '゜': (1, 11),
}
_OLD_SHIFT_KANA = frozenset('ぁぃぅぇぉっゃゅょを')
_OLD_MARK_OF = dict({c: '゛' for c in 'がぎぐげござじずぜぞだぢづでどばびぶべぼゔ'},
                    **{c: '゜' for c in 'ぱぴぷぺぽ'})
_ALL = 'あいうえおかきくけこさしすせそたちつてとなにぬねのはひふへほまみむめもやゆよらりるれろわをん' \
       'がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽぁぃぅぇぉゃゅょっー'


class KanaLayoutTest(unittest.TestCase):
    def setUp(self):
        K.apply()

    def tearDown(self):
        K.apply()
        self.assertEqual(KL.current_kana_layout(), 'jis')

    def test_default_tables_unchanged(self):
        self.assertEqual(KL.KANA_POSITIONS, _OLD_POSITIONS)
        self.assertEqual(list(KL.KANA_POSITIONS), list(_OLD_POSITIONS))     # 並びも同じ
        self.assertEqual(KL._SHIFT_KANA, _OLD_SHIFT_KANA)
        self.assertEqual(KL.MARK_OF, _OLD_MARK_OF)
        self.assertEqual(KL.SHIFT_KANA_PAIR, dict(KL.SMALL_KANA_PAIR, **{'わ': 'を', 'を': 'わ'}))
        self.assertEqual(KL._SHIFT_NEIGHBORS, {'left': frozenset('つ'), 'right': frozenset('ろ')})
        self.assertEqual(KL.ALL_KANA, list(dict.fromkeys(list(_OLD_POSITIONS) + list(KL.DAKUTEN_BASE))))
        self.assertTrue(KL.marks_are_keys())
        self.assertEqual(KL.keystrokes('が'), ('か', '゛'))
        self.assertEqual(KL.keystrokes('ぱ'), ('は', '゜'))
        self.assertEqual(KL.keystrokes('ゃ'), ('ゃ',))
        self.assertEqual(KL.kana_key_distance('か', 'が'), 0.4)
        self.assertEqual(KL.kana_key_distance('ざ', 'は'), KL.FAR)      # 2打鍵の違い（48-FX）
        self.assertEqual(KL.kana_key_distance('ゅ', 'よ'), KL.FAR)      # Shift と別キー
        self.assertEqual(KL.mark_key_neighbors('゛'), ('け', 'せ', 'へ', 'ほ'))  # 2026-10-24 keytend: 同じ指の1段上下も隣
        self.assertEqual(KL.mark_key_neighbors('゜'), ('へ', 'む', 'ー'))  # 2026-10-24 keytend: 同じ指の1段上下も隣
        self.assertEqual(KL.same_key_kana_alternatives('あ'), ('ぁ',))
        self.assertEqual(KL.same_key_kana_alternatives('わ'), ('を',))
        self.assertEqual(KL.same_key_kana_alternatives('゛'), ())
        self.assertEqual(KL.same_key_characters('（'), ['ゆ', 'ゅ', '8', '８', '('])
        self.assertEqual(H.HALFWIDTH_TO_KANA['f'], 'は')
        self.assertEqual(H.SHIFT_TO_KANA['#'], 'ぁ')
        self.assertEqual(H.KANA_TO_HALFWIDTH['ろ'], '\\')

    def test_every_layout_covers_the_kana(self):
        for name in KL.KANA_LAYOUTS:
            with self.subTest(layout=name):
                K.apply(kana=name)
                self.assertEqual(KL.current_kana_layout(), name)
                missing = [c for c in _ALL if c not in KL.KANA_POSITIONS and c not in KL.DAKUTEN_BASE]
                self.assertEqual(missing, [])
                for c in _ALL:
                    strokes = KL.keystrokes(c)
                    self.assertTrue(all(k in KL.KANA_POSITIONS for k in strokes), (c, strokes))
                    self.assertEqual(KL.kana_key_distance(c, c), 0.0)
                # 同じキーの別の面は、位置が同じで面が違う
                for c, others in KL._SAME_KEY_ALTS.items():
                    for o in others:
                        self.assertEqual(KL.KANA_POSITIONS[c], KL.KANA_POSITIONS[o])
                        self.assertNotEqual(KL.kana_layer(c), KL.kana_layer(o))

    def test_nicola_voiced_kana_are_one_chord(self):
        K.apply(kana='nicola')
        self.assertFalse(KL.marks_are_keys())
        self.assertEqual(KL.MARK_OF, {})
        self.assertEqual(KL.keystrokes('が'), ('が',))
        self.assertEqual(KL.keystrokes('ぱ'), ('ぱ',))
        # 位置: 濁音は清音と同じキー（か＝W、が＝W＋右親指）。ぽ は い（L）のキー
        self.assertEqual(KL.KANA_POSITIONS['が'], KL.KANA_POSITIONS['か'])
        self.assertEqual(KL.KANA_POSITIONS['ぽ'], KL.KANA_POSITIONS['い'])
        self.assertEqual(KL.KANA_POSITIONS['ゔ'], KL.KANA_POSITIONS['う'])
        self.assertEqual(KL.KANA_POSITIONS['ー'], (3, 1))                  # X＋左親指
        self.assertEqual(KL.KANA_POSITIONS['を'], (2, 0))                  # A＋左親指
        self.assertEqual((KL.kana_layer('か'), KL.kana_layer('え'), KL.kana_layer('が')), ('', 'L', 'R'))
        self.assertEqual((KL.kana_layer('は'), KL.kana_layer('み'), KL.kana_layer('ば')), ('', 'R', 'L'))
        # 距離: 同じキーの別の面は親指の押し違い。同じ親指の隣は 1.0。親指も違えば FAR
        self.assertEqual(KL.kana_key_distance('か', 'が'), 0.3)
        self.assertEqual(KL.kana_key_distance('か', 'え'), 0.3)
        self.assertEqual(KL.kana_key_distance('が', 'だ'), 1.0)
        self.assertEqual(KL.kana_key_distance('ぽ', 'ぎ'), 1.0)            # L と K、どちらも左親指
        self.assertEqual(KL.kana_key_distance('が', 'ぱ'), KL.FAR)         # 右親指 と 左親指
        self.assertEqual(KL.kana_key_distance('が', 'さ'), KL.FAR)         # 面もキーも違う
        self.assertEqual(KL.kana_key_distance('ざ', 'は'), KL.FAR)
        near = dict(KL.nearby_candidates('か', include_phonetic=False))
        self.assertEqual(set(near), {'か', 'え', 'が', 'た', 'し'})  # 2026-10-24 keytend: 同じ指の1段上下も隣
        # 印のキーで打たないので、印の隣の誤りは出ない
        self.assertEqual(KL.mark_key_neighbors('゛'), ())
        self.assertEqual(KL.mark_slip_candidates('か', 'た'), ())
        self.assertEqual(KL.same_key_kana_alternatives('か'), ('え', 'が'))
        self.assertEqual(KL.same_key_kana_alternatives('ぁ'), ())        # Q の右親指は ゜（字ではない）
        self.assertEqual(KL.same_key_characters('w'), ['か', 'え', 'が', 'W'])
        self.assertEqual(KL.same_key_characters('か'), ['え', 'が', 'w', 'W'])
        # 半角のまま打った表: 親指の面は出ない
        self.assertEqual(H.HALFWIDTH_TO_KANA['w'], 'か')
        self.assertEqual(H.HALFWIDTH_TO_KANA['f'], 'け')
        self.assertEqual(H.SHIFT_TO_KANA, {})
        # 打鍵の一手: か → が は Shift（親指）の押し違い 0.4
        rows = {(r.reading, r.operation): r.cost for r in CR.key_repairs('かき')}
        self.assertEqual(rows.get(('がき', 'shift')), 0.4)
        self.assertEqual(rows.get(('えき', 'shift')), 0.4)
        self.assertNotIn(('がき', 'omission'), rows)
        self.assertEqual(KL.single_key_drop_adjacency('がだ', 'が'), True)   # だ（E・右親指）は が の隣
        self.assertTrue(C.adjacent_slip('が', 'だ', 'kana'))
        self.assertFalse(C.adjacent_slip('が', 'ぱ', 'kana'))

    def test_shin_jis_marks_are_keys(self):
        K.apply(kana='shin_jis')
        self.assertTrue(KL.marks_are_keys())
        self.assertEqual(KL.keystrokes('が'), ('か', '゛'))
        self.assertEqual(KL.keystrokes('ぱ'), ('は', '゜'))
        self.assertEqual(KL.KANA_POSITIONS['゛'], (2, 8))                 # 中段の L
        self.assertEqual(KL.KANA_POSITIONS['゜'], (1, 1))                 # Shift＋W
        self.assertEqual(KL.kana_layer('゜'), 'S')
        self.assertEqual(KL.KANA_POSITIONS['ー'], (3, 8))                 # Shift＋．
        self.assertEqual(KL.KANA_POSITIONS['を'], (1, 8))
        self.assertEqual(KL.KANA_POSITIONS['っ'], (3, 5))
        self.assertEqual(KL.kana_key_distance('そ', 'ぁ'), 0.3)           # 同じキー・Shift
        self.assertEqual(KL.kana_key_distance('あ', 'ぁ'), KL.FAR)        # 別キー・Shift
        self.assertEqual(KL.kana_key_distance('そ', 'け'), 1.0)
        self.assertEqual(KL.kana_key_distance('か', 'が'), 0.4)
        self.assertEqual(KL.kana_key_distance('が', 'ざ'), KL.FAR)
        self.assertEqual(KL.kana_key_distance('い', 'き'), 2.0)           # 間に ゛
        # ゛（L）を狙って隣を叩く: い（K）・き（;）。Shift の字（も・ゆ）と同じキーの わ は入らない
        self.assertEqual(KL.mark_key_neighbors('゛'), ('い', 'き', 'を'))  # 2026-10-24 keytend: 同じ指の1段上下も隣
        self.assertEqual(KL.mark_key_neighbors('゜'), ('ぁ', 'へ', 'ほ'))  # 2026-10-24 keytend: 同じ指の1段上下も隣
        self.assertEqual(KL.SHIFT_KANA_PAIR['ぁ'], 'そ')
        self.assertEqual(KL.SHIFT_KANA_PAIR['や'], 'を')
        self.assertEqual(KL._SHIFT_NEIGHBORS, {'left': frozenset('す'), 'right': frozenset('れ')})
        self.assertEqual(H.HALFWIDTH_TO_KANA['q'], 'そ')
        self.assertEqual(H.SHIFT_TO_KANA['Q'], 'ぁ')
        self.assertEqual(H.SHIFT_TO_KANA['>'], 'ー')
        self.assertEqual(H.KANA_TO_HALFWIDTH['そ'], 'q')
        rows = {(r.reading, r.operation): r.cost for r in CR.key_repairs('かき')}
        self.assertEqual(rows.get(('がき', 'omission')), KL.MISSING_KEY_COST)
        self.assertEqual(rows.get(('へき', 'shift')), 0.4)

    def test_switching_back_restores_jis_exactly(self):
        before = (dict(KL.KANA_POSITIONS), list(KL.ALL_KANA), dict(KL.MARK_OF),
                  dict(KL.SHIFT_KANA_PAIR), KL._SHIFT_KANA, dict(KL._KEY_OF_CHAR),
                  dict(H.HALFWIDTH_TO_KANA), dict(H.SHIFT_TO_KANA), dict(H.KANA_TO_HALFWIDTH))
        near_before = {c: KL.nearby_candidates(c) for c in _ALL}
        self.assertTrue(K.apply(kana='nicola'))
        self.assertNotEqual(dict(KL.KANA_POSITIONS), before[0])
        self.assertTrue(K.apply(kana='shin_jis'))
        self.assertTrue(K.apply())
        after = (dict(KL.KANA_POSITIONS), list(KL.ALL_KANA), dict(KL.MARK_OF),
                 dict(KL.SHIFT_KANA_PAIR), KL._SHIFT_KANA, dict(KL._KEY_OF_CHAR),
                 dict(H.HALFWIDTH_TO_KANA), dict(H.SHIFT_TO_KANA), dict(H.KANA_TO_HALFWIDTH))
        self.assertEqual(after, before)
        self.assertEqual({c: KL.nearby_candidates(c) for c in _ALL}, near_before)
        self.assertFalse(K.apply(kana='jis'))
        self.assertFalse(K.apply(kana='bogus'))          # 知らない名前は JIS のまま

    def test_foreign_caches_are_cleared_on_switch(self):
        import vocabulary as V
        self.assertEqual(CR._key_neighbors('か'), (('え', 1.05), ('す', 1.0), ('ん', 1.0), ('き', 1.05)))   # JIS: す か ん、上 え・下 き（keytend）
        self.assertEqual(V._sub_cost('か', 'ん'), 1.0)
        K.apply(kana='nicola')
        self.assertEqual(CR._key_neighbors('か'), (('た', 1.0), ('し', 1.05)))   # NICOLA: 。か た、下 し（keytend）
        self.assertGreater(V._sub_cost('か', 'ん'), 1.0)
        K.apply()
        self.assertEqual(CR._key_neighbors('か'), (('え', 1.05), ('す', 1.0), ('ん', 1.0), ('き', 1.05)))
        self.assertEqual(V._sub_cost('か', 'ん'), 1.0)

    def test_spec_carries_the_kana_layout(self):
        self.assertEqual(K.spec({'kana_layout': 'shin_jis'}), ('qwerty_jis', 'standard', '', 'shin_jis'))
        self.assertTrue(K.apply_spec(('qwerty_jis', 'standard', '', 'nicola')))
        self.assertEqual(KL.current_kana_layout(), 'nicola')
        self.assertEqual(K.spec_text(K.current()), 'qwerty_jis/standard/nicola')
        self.assertEqual(K.describe(), 'QWERTY(JIS)・標準・親指シフト')
        self.assertTrue(K.apply_spec(('qwerty_jis', 'standard', '')))   # 古い3つの組 → JIS かな
        self.assertEqual(KL.current_kana_layout(), 'jis')


if __name__ == '__main__':
    unittest.main()
