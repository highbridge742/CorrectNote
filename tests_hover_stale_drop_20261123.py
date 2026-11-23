# -*- coding: utf-8 -*-
"""遅れて届いたオンマウスの答えを、出す前に「今も出してよいか」確かめる（2026-11-23 うにさん 14:37Z「縮小中に予測候補が
出ました。縮小になる直前にオンマウスしたものが遅れたのだと思います」）。
・頼んだ（止まった）後に、縮小（俯瞰・速い形も）に入った・タブを替えた・スクロールした・打った・クリックした・焦点が
  外れた時は、届いた答えを出さない。待っている頼みと見直しの予約も取り消す
・マウスがその語から離れた時も出さない（前から）
・何も起きなければ今までどおり出す
CN_HOVER_STALE_DROP=0 で前の形。Tk の窓は作らない（作り物のアプリと欄）。"""
import os
import time
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import auto_candidates as AC

KEY = ('editor', 3, 2, 4)


class FakeRoot:
    def __init__(self):
        self.jobs = {}
        self.n = 0

    def after(self, ms, fn):
        self.n += 1
        self.jobs[self.n] = fn
        return self.n

    def after_cancel(self, job):
        self.jobs.pop(job, None)

    def focus_get(self):
        return 'editor'


class FakeText:
    def __init__(self):
        self.top = '1.0'

    def index(self, what):
        return self.top if what == '@0,0' else '1.0'

    def winfo_pointerxy(self):
        return (110, 120)

    def winfo_rootx(self):
        return 100

    def winfo_rooty(self):
        return 100

    def winfo_width(self):
        return 500

    def winfo_height(self):
        return 400

    def tag_ranges(self, name):
        return ()


def make_app():
    app = NS(root=FakeRoot(), _dropdown=None, _dropdown_parts=None, _overview=None, status=None)
    app.editor = FakeText()
    app.opened = 0

    def open_dd(event, row, unit):
        app.opened += 1
        app._dropdown = object()
        app._dropdown_parts = dict(passive=app._dropdown_passive)
    app._open_editor_dropdown = open_dd
    app._close_dropdown = lambda: (setattr(app, '_dropdown', None), setattr(app, '_dropdown_parts', None))
    return app


class StaleDrop(unittest.TestCase):
    def setUp(self):
        for name, value in (('hover_on', lambda app, environ=None: True),
                            ('hover_typed_recently', lambda app, now=None: False),
                            ('_async_ask_on', lambda: False),
                            ('analysis_busy', lambda app: False),
                            ('_hit', lambda app, w, e: ('editor', 3, dict(start=2, end=4))),
                            ('_key', lambda hit: KEY)):
            p = mock.patch.object(AC, name, value)
            p.start()
            self.addCleanup(p.stop)
        self.app = make_app()
        self.w = self.app.editor

    def asked(self):
        """語の上で止まった（頼んだ）時の控え。"""
        return AC._stamp(self.app, self.w, dict(x=10, y=20, x_root=110, y_root=120))

    def show(self, snap):
        return AC.hover_show(self.app, self.w, KEY, snap)

    def test_shown_when_nothing_happened(self):
        self.assertTrue(self.show(self.asked()))
        self.assertEqual(self.app.opened, 1)

    def test_not_shown_after_entering_the_overview(self):
        snap = self.asked()
        self.app._overview = {'widget': self.w}
        self.assertFalse(self.show(snap))
        self.app._overview = None
        snap = self.asked()
        import overview_fast
        with mock.patch.object(overview_fast, 'active', lambda app: object()):     # 速い形の俯瞰
            self.assertFalse(self.show(snap))
            self.assertTrue(AC.busy(self.app, self.w))                            # 俯瞰の最中は新しく出さない
        self.assertEqual(self.app.opened, 0)

    def test_press_to_enter_the_overview_drops_the_waiting_ask(self):
        snap = self.asked()
        self.app._hover_asks = dict(key=KEY, pending={'k': 11}, got={}, done={}, since=time.monotonic())
        self.app._hover_ask_job = self.app.root.after(30, lambda: None)
        self.app._hover_waiting = (self.w, KEY, snap)
        AC.on_press(self.app, NS(num=3))                                          # 右ダブルクリック（縮小）の押し下げ
        self.assertIsNone(self.app._hover_asks)
        self.assertIsNone(self.app._hover_ask_job)
        self.assertIsNone(self.app._hover_waiting)
        self.assertFalse(self.show(snap))                                         # 遅れて組み立てに来ても出さない

    def test_not_shown_after_a_tab_switch(self):
        snap = self.asked()
        AC.settle(self.app)
        self.assertFalse(self.show(snap))

    def test_not_shown_after_a_scroll(self):
        snap = self.asked()
        AC.scrolled(self.app)
        self.assertFalse(self.show(snap))
        snap = self.asked()
        self.w.top = '40.0'                                                       # スクロールバー・キーで見える所が動いた
        self.assertFalse(self.show(snap))

    def test_not_shown_after_typing_or_a_click_or_focus_loss(self):
        snap = self.asked()
        AC.on_key(self.app, NS(keysym='a', char='a'))
        self.assertFalse(self.show(snap))
        snap = self.asked()
        AC.on_press(self.app, NS(num=1))
        self.assertFalse(self.show(snap))
        snap = self.asked()
        AC.bump(self.app, 'focus')
        self.assertFalse(self.show(snap))
        snap = self.asked()
        AC.on_key(self.app, NS(keysym='Shift_L', char=''))                         # 修飾キーだけは打鍵ではない
        self.assertTrue(self.show(snap))

    def test_not_shown_when_the_mouse_left_the_word(self):
        snap = self.asked()
        with mock.patch.object(AC, '_key', lambda hit: ('editor', 3, 6, 9)):
            self.assertFalse(self.show(snap))

    def test_late_async_answer_is_dropped(self):
        snap = self.asked()
        self.app._hover_asks = dict(key=KEY, pending={}, got={}, done={}, since=time.monotonic())
        AC.settle(self.app)                                                       # 待っている間にタブを替えた
        AC._poll_asks(self.app, self.w, KEY, snap)                                # 答えがそろった時の続き
        self.assertEqual(self.app.opened, 0)

    def test_switch_back(self):
        with mock.patch.dict(os.environ, {'CN_HOVER_STALE_DROP': '0'}):
            snap = self.asked()
            AC.settle(self.app)
            self.w.top = '40.0'
            self.assertTrue(self.show(snap))                                      # 前の形: 届けば出す


if __name__ == '__main__':
    unittest.main()
