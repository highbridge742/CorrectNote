# -*- coding: utf-8 -*-
"""簡易入力を閉じる時、確定の字を覚える見張り（ime_burst.Watch）を窓から外してから手放す（2026-11-23）。外さずに手放すと、
窓を壊す時の知らせで解放済みの呼び先が呼ばれ、時々 0xC000041D で落ちていた（tests_quick_focus_return の子が簡易入力の窓の
destroy の中で消えた・10回中約5回 → 直して10回中0回）。外せなかった時は呼び先を生かしておく。
CN_IME_BURST_CLOSE_WATCH=0 で前の形。"""
import os
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import ime_burst


class FakeWatch:
    def __init__(self, removed=True):
        self.hwnd = 123
        self.closed = 0
        self.removed = removed

    def close(self):
        self.closed += 1
        if self.removed:
            self.hwnd = 0


class CloseWatch(unittest.TestCase):
    def setUp(self):
        self.addCleanup(ime_burst._KEEP_ALIVE.clear)

    def app(self, watch):
        return NS(_quick_burst_watch=watch, _quick_burst_job=None, _quick_burst_event=None, root=None)

    def test_watch_is_removed_before_it_is_dropped(self):
        w = FakeWatch()
        a = self.app(w)
        ime_burst.close_quick(a)
        self.assertEqual(w.closed, 1)
        self.assertIsNone(a._quick_burst_watch)
        self.assertNotIn(w, ime_burst._KEEP_ALIVE)

    def test_watch_that_could_not_be_removed_is_kept_alive(self):
        w = FakeWatch(removed=False)
        ime_burst.close_quick(self.app(w))
        self.assertIn(w, ime_burst._KEEP_ALIVE)

    def test_switch_back(self):
        w = FakeWatch()
        with mock.patch.dict(os.environ, {'CN_IME_BURST_CLOSE_WATCH': '0'}):
            ime_burst.close_quick(self.app(w))
        self.assertEqual(w.closed, 0)                       # 前の形: 外さずに手放した


if __name__ == '__main__':
    unittest.main()
