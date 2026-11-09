# -*- coding: utf-8 -*-
"""Enter presses that piled up while the window was busy go in together (enter_batch, 2026-11-07 うにさん「処理が遅れたあと、
2回以上分の入力が来ていたなら、改行をまとめて複数個入れてはどうか」). The text, the cursor and the undo steps are the
same as pressing Enter that many times one by one; Shift/Ctrl/Alt or a conversion in progress take nothing more."""
from types import SimpleNamespace
import tkinter as tk
import unittest
from unittest.mock import patch

import enter_batch


def press_once(widget):
    """Tk's own <Return> of the Text class."""
    widget.tk.call('tk::TextInsert', widget._w, '\n')
    if int(widget.cget('autoseparators')):
        widget.edit_separator()


def undo_steps(widget, rows):
    steps = 0
    while int(widget.index('end-1c').split('.')[0]) > rows and steps < 100:
        widget.edit_undo(); steps += 1
    return steps


class EnterBatch(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def make(self):
        w = tk.Text(self.root, undo=True, autoseparators=True)
        w.insert('1.0', '一行目\n二行目の途中で改行する\n三行目')
        w.edit_reset()
        w.mark_set('insert', '2.4')
        return w

    def batched(self, own, queued, state=0, composing=False):
        w = self.make()
        app = SimpleNamespace(_enter_batch=dict(presses=0, batched=0, batches=0, largest=0), _enter_own=own)
        press_once(w)                              # the Text class binding ran first
        queue = list(queued) + [0]
        with patch.object(enter_batch, '_queued_return', side_effect=lambda *a: queue.pop(0)), \
                patch.object(enter_batch, '_user32', return_value=(SimpleNamespace(GetKeyState=lambda vk: 0), None, None)), \
                patch('ime_watch.composition_live', return_value=composing):
            w.focus_get = lambda: w
            enter_batch.on_return(app, SimpleNamespace(widget=w, state=state))
        return w, app

    def test_piled_up_presses_are_the_same_as_one_by_one(self):
        w, app = self.batched(own=2, queued=[3, 2])          # this message held 2, then 3 and 2 more waited
        ref = self.make()
        for _ in range(1 + 1 + 3 + 2):
            press_once(ref)
        self.assertEqual(w.get('1.0', 'end-1c'), ref.get('1.0', 'end-1c'))
        self.assertEqual(w.index('insert'), ref.index('insert'))
        self.assertEqual(undo_steps(w, 3), undo_steps(ref, 3))      # one undo step per newline, as before
        self.assertEqual(w.get('1.0', 'end-1c'), ref.get('1.0', 'end-1c'))
        self.assertEqual(app._enter_batch['batched'], 6)

    def test_a_single_press_adds_nothing(self):
        w, app = self.batched(own=1, queued=[])
        self.assertEqual(w.get('1.0', 'end-1c').count('\n'), 3)
        self.assertEqual(app._enter_batch['batched'], 0)

    def test_modifiers_or_a_conversion_take_nothing_more(self):
        for kwargs in (dict(state=0x0001), dict(state=0x0004), dict(state=0x20000), dict(composing=True)):
            w, app = self.batched(own=3, queued=[2], **kwargs)
            self.assertEqual(w.get('1.0', 'end-1c').count('\n'), 3, kwargs)
            self.assertEqual(app._enter_batch['batched'], 0, kwargs)


if __name__ == '__main__':
    unittest.main()
