# -*- coding: utf-8 -*-
"""打鍵の記録に、字でないキーの種類（BackSpace・変換の Space・矢印など）を残す（2026-11-22 うにさん「再入力変換は、実際に
どのキーを押したかという情報から、平仮名にしてください」・前は Space と BackSpace が同じ空の字で見分けられなかった）。
記録の字は前と同じ空の字のまま（'' と等しく偽）なので、記録を読む所（打鍵の巻き込み・シフトの抜け・子のプロセス）の答えは
変わらない。種類を読むのは typed_kana（再入力変換）だけ。CN_STROKE_KEY_KINDS=0・CN_TYPED_KANA_KINDS=0 で前の形。
作った打鍵だけ（本物の IME・うにさんの記録は使わない）。"""
import os
import pickle
import unittest
from unittest import mock

import keystroke_doubt
import shift_slip
import stroke_keys as S
import typed_kana as T


class Ev:
    def __init__(self, keycode):
        self.keycode = keycode


def typed(*keycodes, env=None):
    """IME が入っている時の打鍵（押しは 229、離しで本当のキー）を Strokes に通して、確定1つぶんの記録を返す。"""
    with mock.patch.dict(os.environ, env or {}):
        st = S.Strokes()
        for code in keycodes:
            st.clock.press(229)
            st._release(Ev(code))
        return st.for_commits(1)[0]


E, A, T_, H, BS, SP, LEFT, ESC, RET = 0x45, 0x41, 0x54, 0x48, 8, 32, 37, 27, 13      # い ち か く・字でないキー


class Record(unittest.TestCase):
    def test_kinds_are_kept_and_the_value_is_unchanged(self):
        keys = typed(E, A, BS, SP, RET)
        self.assertEqual([k for k, _t in keys], ['e', 'a', '', '', ''])          # 値は前と同じ
        self.assertEqual([getattr(k, 'name', None) for k, _t in keys], [None, None, 'BackSpace', 'space', 'Return'])
        self.assertTrue(all(not k for k, _t in keys[2:]))
        self.assertEqual(S.kind_of_keycode(0x99), 'other')

    def test_the_real_release_handler(self):
        st = S.Strokes()
        for code in (E, BS):
            st.clock.press(229)
            st._release(Ev(code))
        keys = st.for_commits(1)[0]
        self.assertEqual(keys[1][0], '')
        self.assertEqual(keys[1][0].name, 'BackSpace')

    def test_switch_back(self):
        keys = typed(E, BS, env={'CN_STROKE_KEY_KINDS': '0'})
        self.assertIsNone(getattr(keys[1][0], 'name', None))

    def test_child_process_gets_plain_empty(self):
        got = pickle.loads(pickle.dumps(typed(E, BS)))
        self.assertIs(type(got[1][0]), str)
        self.assertEqual(got[1][0], '')


class OtherReaders(unittest.TestCase):
    """記録を読むほかの所は、種類があっても前と同じ答え。"""

    def plain(self, keys):
        return tuple((str(k) if k else '', t) for k, t in keys)

    def test_keystroke_doubt(self):
        keys = typed(E, A, BS, A, SP)
        positions = {'e': (1, 2), 'a': (2, 1)}
        same = lambda p, q: True
        self.assertEqual(keystroke_doubt.doubt_pairs(keys, positions, same, 1000),
                         keystroke_doubt.doubt_pairs(self.plain(keys), positions, same, 1000))

    def test_shift_slip(self):
        keys = typed(E, A, SP)
        shifts = [(keys[-1][1] + 1.0, keys[-1][1] + 2.0)]
        self.assertEqual(shift_slip.empty_shifts(keys, shifts), shift_slip.empty_shifts(self.plain(keys), shifts))
        self.assertEqual(shift_slip._char_index(keys, 'いち'), shift_slip._char_index(self.plain(keys), 'いち'))
        keys = typed(E, BS, A)
        self.assertIsNone(shift_slip._char_index(keys, 'ち'))                       # BS を含む記録は前と同じく合わせない


class TypedKana(unittest.TestCase):
    def test_backspace_drops_the_typed_kana(self):
        self.assertEqual(T.from_keys(typed(E, A, A, BS, T_, SP, RET)), 'いちか')       # い ち ち BS か → いちか
        self.assertEqual(T.from_keys(typed(T_, 0xC0, BS, H)), 'く')                  # が（か＋゛）を BS で1字消す

    def test_old_records_are_read_as_before(self):
        old = tuple((str(k) if k else '', t) for k, t in typed(E, A, A, BS, T_))
        self.assertEqual(T.from_keys(old), 'いちちか')                               # 種類が無い: 前と同じ（呼ぶ側が字数で弾く）
        with mock.patch.dict(os.environ, {'CN_TYPED_KANA_KINDS': '0'}):
            self.assertEqual(T.from_keys(typed(E, A, A, BS, T_)), 'いちちか')

    def test_unclear_keys_give_none(self):
        self.assertIsNone(T.from_keys(typed(E, A, LEFT, T_)))                         # 字の位置を動かした
        self.assertIsNone(T.from_keys(typed(E, ESC, A)))
        self.assertIsNone(T.from_keys(typed(E, SP, BS, A)))                          # 変換の後の BS
        self.assertIsNone(T.from_keys(typed(BS, E)))                                 # 確定の外の字を消した

    def test_romaji(self):
        K, I, N, A_ = 0x4B, 0x49, 0x4E, 0x41
        self.assertEqual(T.from_keys(typed(K, I, K, BS, N, A_), method='romaji'), 'きな')   # まだかなでない k を消す
        self.assertEqual(T.from_keys(typed(K, A_, N, BS, K, I), method='romaji'), 'かき')   # かなの ん を消す
        self.assertEqual(T.from_keys(typed(K, A_, BS, K, I), method='romaji'), 'き')        # か を消す


if __name__ == '__main__':
    unittest.main()
