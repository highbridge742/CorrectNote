# -*- coding: utf-8 -*-
"""F5 予測の文末（全角あり）の既定の並び（2026-11-21 14:26Z うにさん「文末のデフォルトを、画像の並びにする」・最後は
「半角が前後にある」矢印・14:30Z 半角だけも「半角はこう。ピリオドの下はカンマ」）。CN_F5_TAIL_DEFAULT2=0 で前の既定。自分で並べた一覧（設定）は上書きしない。"""
import os
import unittest
from unittest import mock

import f5_predict as F
import f5_predict_window as W

WANT = ['？', '！', '…', '～', '!?', '、', '。', '→', '⇒', ' ⇒ ']


class FakeSettings:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.saved = 0

    def get(self, key, default=None):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value

    def save(self):
        self.saved += 1


class FakeApp:
    def __init__(self, lists=None):
        self.settings = FakeSettings({'f5_predict_lists': lists} if lists is not None else {})


class TailDefault(unittest.TestCase):
    def test_new_default_order(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop('CN_F5_TAIL_DEFAULT2', None)
            os.environ.pop('CN_F5_END_ORDER', None)
            got = F.default_list('end_wide')
        self.assertEqual(got, WANT)
        self.assertEqual([hex(ord(c)) for c in got[-1]], ['0x20', '0x21d2', '0x20'])     # 半角空白＋⇒＋半角空白
        self.assertEqual([hex(ord(c)) for c in got[3]], ['0xff5e'])                       # 全角のチルダ

    def test_switch_back_and_narrow_unchanged(self):
        with mock.patch.dict(os.environ, {'CN_F5_TAIL_DEFAULT2': '0'}):
            self.assertEqual(F.default_list('end_wide'), list(F.END_WIDE))
            narrow_old = F.default_list('end_narrow')
        self.assertEqual(narrow_old, list(F.END_NARROW))

    def test_new_narrow_order(self):
        os.environ.pop('CN_F5_TAIL_DEFAULT2', None)
        for fixed in ('1', '0'):                                                          # 手間の順に並べ替えない
            with mock.patch.dict(os.environ, {'CN_F5_FIXED_ORDER': fixed}):
                self.assertEqual(F.default_list('end_narrow'), ['?', '!', '!?', '...', '.', ',', '&', '//'])
        self.assertIn('...', F.END_NARROW)                                                # 三点は前の既定と同じ字

    def test_own_list_is_kept(self):
        mine = ['。', '！', 'w']
        app = FakeApp({'end_wide': mine})
        self.assertEqual(W.current(app, 'end_wide'), mine)                                # 自分で並べた一覧はそのまま
        self.assertEqual(app.settings.saved, 0)                                           # 開いただけでは書かない

    def test_no_saved_list_uses_new_default_and_reset_clears(self):
        app = FakeApp()
        self.assertEqual(W.current(app, 'end_wide'), WANT)                                # 保存が無い時は新しい既定
        W.store(app, 'end_wide', ['。', '！'])
        self.assertEqual(W.current(app, 'end_wide'), ['。', '！'])
        W.store(app, 'end_wide', F.default_list('end_wide'))                              # 「戻す」
        self.assertNotIn('end_wide', app.settings.get('f5_predict_lists'))                # 既定は設定に残さない
        self.assertEqual(W.current(app, 'end_wide'), WANT)


if __name__ == '__main__':
    unittest.main()
