# -*- coding: utf-8 -*-
"""The hotkey box is looked at twice a second and the drop box once a second (2026-11-07 うにさん「ホットキーは1秒に2回、
ドロップは1秒に1回でよい」). Nothing put in a box is missed: it is taken at the next look. IME text the window keeps
for Tk (emoji) does not wait for the drop look: the IME look takes it too."""
import queue
import time
import tkinter as tk
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

import app


class SlowPolls(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()

    def tearDown(self):
        for identifier in self.root.tk.splitlist(self.root.tk.call('after', 'info')):
            self.root.tk.call('after', 'cancel', identifier)
        self.root.destroy()

    def pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.root.update(); time.sleep(0.005)

    def test_intervals(self):
        self.assertEqual(app.CorrectNoteApp.HOTKEY_POLL_MS, 500)
        self.assertEqual(app.CorrectNoteApp.DROP_POLL_MS, 1000)

    def test_every_hotkey_press_is_taken_at_the_next_look(self):
        opened = []
        a = SimpleNamespace(root=self.root, HOTKEY_POLL_MS=app.CorrectNoteApp.HOTKEY_POLL_MS, _hotkey_queue=queue.Queue(),
                            _open_quick_capture=lambda name: opened.append(name), _toggle_word_book_from_hotkey=Mock())
        a._poll_hotkey_queue = lambda: app.CorrectNoteApp._poll_hotkey_queue(a)
        a._poll_hotkey_queue()
        for name in ('quick', 'quick', 'quick'):
            a._hotkey_queue.put_nowait(name)
        self.pump(0.65)
        self.assertEqual(opened, ['quick', 'quick', 'quick'])

    def test_every_drop_is_taken_at_the_next_look(self):
        dropped = []
        a = SimpleNamespace(root=self.root, DROP_POLL_MS=app.CorrectNoteApp.DROP_POLL_MS, _drop_icon_pending=False,
                            _drop_queue=[], _ime_text_queue=[], _on_files_dropped=lambda paths: dropped.append(paths),
                            _insert_ime_text=Mock(), _queue_window_icons=Mock())
        a._drain_drop_queue = lambda: app.CorrectNoteApp._drain_drop_queue(a)
        a._drain_drop_queue()
        a._drop_queue.extend([['a.txt'], ['b.txt']])
        self.pump(1.2)
        self.assertEqual(dropped, [['a.txt'], ['b.txt']])


if __name__ == '__main__':
    unittest.main()
