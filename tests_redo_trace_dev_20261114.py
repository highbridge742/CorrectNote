# -*- coding: utf-8 -*-
"""大きな解き直しの記録（_note_big_redo）と「解析の記録…」ボタンを、開発版で戻す（2026-11-14 うにさん「全体に再解析が入る
チェックを開発側に適用して」）。frozen でない（.py で動かす）時は既定で取る・出す。frozen（EXE・Store 版）では既定で取らない・
出さない。CN_REDO_TRACE=0 なら取らない、CN_REDO_TRACE=1 なら EXE でも取る。作った値だけを使い、個人ファイルは使わない。"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest import mock

import app


class RedoTraceOn(unittest.TestCase):
    def test_default_follows_frozen(self):
        self.assertTrue(app.redo_trace_on({}, frozen=False))           # 開発版: 既定で取る
        self.assertFalse(app.redo_trace_on({}, frozen=True))           # EXE・Store 版: 既定で取らない

    def test_switches(self):
        self.assertFalse(app.redo_trace_on({'CN_REDO_TRACE': '0'}, frozen=False))
        self.assertTrue(app.redo_trace_on({'CN_REDO_TRACE': '1'}, frozen=True))
        self.assertTrue(app.redo_trace_on({'CN_DEBUG_TOOLS': '1'}, frozen=True))
        self.assertFalse(app.redo_trace_on({'CN_REDO_TRACE': '0', 'CN_DEBUG_TOOLS': '1'}, frozen=False))

    def test_note_big_redo_writes_only_when_on(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            fake = SimpleNamespace(_scroll_trace_dir=d, REDO_TRACE_MIN_ROWS=30, _STATE_NAMES=app.CorrectNoteApp._STATE_NAMES,
                                   session=SimpleNamespace(active=0))
            with mock.patch.object(app.analysis_async, 'state_key', lambda a: ('s',)):
                with mock.patch.object(app, 'redo_trace_on', lambda: False):
                    app.CorrectNoteApp._note_big_redo(fake, 'test', 100, 90, 'shape')
                self.assertFalse(os.path.exists(os.path.join(d, 'analysis_redo.log')))
                with mock.patch.object(app, 'redo_trace_on', lambda: True), mock.patch.dict(os.environ, {}, clear=False):
                    os.environ.pop('CN_REDO_TRACE', None)
                    app.CorrectNoteApp._note_big_redo(fake, 'test', 100, 90, 'shape')
                self.assertTrue(os.path.exists(os.path.join(d, 'analysis_redo.log')))


class TraceButton(unittest.TestCase):
    def _texts(self, frozen):
        import tkinter as tk
        import debug_menu

        class _Settings(dict):
            def get(self, k, d=None):
                return dict.get(self, k, d)

            def set(self, k, v):
                self[k] = v

            def save(self):
                pass
        root = tk.Tk()
        root.withdraw()
        try:
            fake = app.CorrectNoteApp.__new__(app.CorrectNoteApp)      # 既定の値（クラスの属性）だけ持つ、起動しない app
            fake.root, fake.settings = root, _Settings(debug_timings={})
            env = {k: v for k, v in os.environ.items() if k not in ('CN_DEBUG_TOOLS', 'CN_REDO_TRACE')}
            with mock.patch.object(sys, 'frozen', frozen, create=True), mock.patch.dict(os.environ, env, clear=True):
                dlg = debug_menu.open_window(fake)
            texts = []

            def walk(w):
                try:
                    texts.append(str(w.cget('text')))
                except Exception:
                    pass
                for c in w.winfo_children():
                    walk(c)
            walk(dlg)
            dlg.destroy()
            return texts
        finally:
            root.destroy()

    def test_button_in_dev_not_in_frozen(self):
        self.assertTrue(any('解析の記録' in t for t in self._texts(False)))
        self.assertFalse(any('解析の記録' in t for t in self._texts(True)))


if __name__ == '__main__':
    unittest.main()
