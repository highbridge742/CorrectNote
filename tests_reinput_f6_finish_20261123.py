# -*- coding: utf-8 -*-
"""再入力変換の途中に F6: 範囲をひらがな（開いた時の読み＝打ったキーのかなが先）にして終える（2026-11-23 03:32 うにさん
「再入力変換の変換中に、F6を押したらひらがなで決定する」）。IME の変換中（未確定）は IME に任せる。
CN_REINPUT_F6_FINISH=0 で前の形。本物の IME・本物の打鍵は使わない（作り物の再入力変換と作った字）。"""
import os
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import app


class FakeReInput:
    def __init__(self, state, composing=False):
        self.state = state
        self._composing = composing
        self.log = []

    def composing(self):
        return self._composing

    def _write(self, text, keep_cursor=False):
        self.log.append(('write', text))

    def finish(self):
        self.log.append(('finish',))
        self.state = None


def fake_app(owner):
    a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
    a.editor = object()
    a._reinput = owner
    a._quick_text = None
    return a


class F6Finish(unittest.TestCase):
    def test_f6_writes_hiragana_and_finishes(self):
        owner = FakeReInput(dict(typed_reading='いちがうごく', reading='いつがうごく', shown='一が動く'))
        a = fake_app(owner)
        self.assertTrue(a._reinput_f6_finish(a.editor, 'F6'))
        self.assertEqual(owner.log, [('write', 'いちがうごく'), ('finish',)])   # 開いた時の読み（打ったキーのかな）

    def test_reading_from_conversion_when_no_typed(self):
        owner = FakeReInput(dict(typed_reading=None, reading='カイギ'))
        a = fake_app(owner)
        self.assertTrue(a._reinput_f6_finish(a.editor, 'F6'))
        self.assertEqual(owner.log[0], ('write', 'かいぎ'))

    def test_not_while_ime_composes_or_closed(self):
        a = fake_app(FakeReInput(dict(typed_reading='かいぎ'), composing=True))
        self.assertFalse(a._reinput_f6_finish(a.editor, 'F6'))                 # IME の変換中は IME に任せる
        a = fake_app(FakeReInput(None))
        self.assertFalse(a._reinput_f6_finish(a.editor, 'F6'))                 # 再入力変換をしていない
        a = fake_app(FakeReInput(dict(typed_reading='かいぎ')))
        self.assertFalse(a._reinput_f6_finish(a.editor, 'F7'))                 # F6 だけ

    def test_switch_back(self):
        owner = FakeReInput(dict(typed_reading='かいぎ'))
        a = fake_app(owner)
        with mock.patch.dict(os.environ, {'CN_REINPUT_F6_FINISH': '0'}):
            self.assertFalse(a._reinput_f6_finish(a.editor, 'F6'))
        self.assertEqual(owner.log, [])


class F6DuringImeComposition(unittest.TestCase):
    """IME の変換中（未確定）の F6 は IME が受け、Tk には keycode 229 で届く。元のキーが F6 なら、IME に確定を頼み、
    確定が届いたら再入力変換も終える（CN_REINPUT_F6_IME）。本物の IME は使わない（模擬）。"""

    def setUp(self):
        import tkinter as tk
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        self.w = tk.Text(self.root)
        self.owner = FakeReInput(dict(typed_reading='かいぎ'))
        self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.a.root = self.root
        self.a.editor = self.w
        self.a._reinput = self.owner
        self.a._quick_text = None

    def run_with(self, vk, keycode=229, env=None):
        import time
        import ime_watch
        composing = [True, True, False]
        completed = []
        with mock.patch.object(ime_watch, 'virtual_key', lambda hwnd: vk), \
                mock.patch.object(ime_watch, 'composition_active', lambda hwnd: composing.pop(0) if composing else False), \
                mock.patch.object(ime_watch, 'complete_composition', lambda hwnd: completed.append(hwnd) or True), \
                mock.patch.dict(os.environ, env or {}):
            self.a._reinput_f6_ime(NS(widget=self.w, keycode=keycode, keysym='??'))
            end = time.monotonic() + 1.5
            while time.monotonic() < end and self.owner.state is not None:
                self.root.update()
                time.sleep(0.005)
            self.root.update()
        return completed

    def test_f6_in_ime_commits_and_finishes(self):
        completed = self.run_with(0x75)
        self.assertEqual(len(completed), 1)                       # IME に確定を1回だけ頼んだ（キーは送らない）
        self.assertEqual(self.owner.log, [('finish',)])           # 確定が届いてから再入力変換を終えた

    def test_other_keys_do_nothing(self):
        self.assertEqual(self.run_with(0x76), [])                 # F7
        self.assertEqual(self.run_with(0x75, keycode=65), [])     # IME を通らないキー
        self.assertEqual(self.owner.log, [])

    def test_switch_back(self):
        self.assertEqual(self.run_with(0x75, env={'CN_REINPUT_F6_IME': '0'}), [])
        self.assertEqual(self.owner.log, [])


if __name__ == '__main__':
    unittest.main()
