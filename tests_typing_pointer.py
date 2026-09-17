# -*- coding: utf-8 -*-
"""Typing, mouse activity and IME changes share one pointer lifecycle."""
import tkinter as tk
import types
import unittest
from unittest.mock import patch
import app
from tests_tk_keys import deliver_key, release_tk_fixture


class TypingPointerTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.editor = tk.Text(self.root, cursor='xterm')
        a.result_view = tk.Text(self.root, cursor='arrow')
        a._quick_text = tk.Text(self.root, cursor='xterm')
        a._pick_mode = None; a._scroll_cursor = None
        a._scroll_panes = lambda: [a.root, a.editor, a.result_view]
        self.entry = tk.Entry(self.root, cursor='xterm')
        for widget in (a.editor, a.result_view, a._quick_text, self.entry):
            a._bind_typing_pointer(widget)
            widget.winfo_id()
        self.pointer = a._typing_pointer

    def tearDown(self):
        self.root.destroy()
        release_tk_fixture(self, 'a', 'pointer', 'entry', 'root')

    def activity(self, widget, sequence):
        tag = self.pointer.tag
        script = widget.tk.call('bind', tag, sequence)
        self.assertTrue(script)
        widget.tk.call('bind', tag, '<<PointerActivityTest>>', script)
        widget.event_generate('<<PointerActivityTest>>')

    def test_typing_hides_and_drag_or_focus_loss_restores_then_typing_hides_again(self):
        a = self.a; w = a.editor
        self.assertEqual(w.bindtags()[0], self.pointer.tag)
        deliver_key(w, '<KeyPress>', 'a', 65, char='a')
        self.assertEqual(w.get('1.0', 'end-1c'), 'a')
        self.assertEqual(w.cget('cursor'), 'none')
        self.activity(w, '<Motion>')
        self.assertEqual(w.cget('cursor'), 'xterm')
        deliver_key(w, '<KeyPress>', 'b', 66, char='b')
        self.assertEqual(w.cget('cursor'), 'none')
        self.activity(w, '<FocusOut>')
        self.assertEqual(w.cget('cursor'), 'xterm')
        deliver_key(w, '<KeyPress>', 'c', 67, char='c')
        self.assertEqual(w.cget('cursor'), 'none')
        self.activity(w, '<ButtonPress>')
        self.assertFalse(self.pointer.saved)
        self.assertEqual(a.result_view.cget('cursor'), 'arrow')

    def test_quick_and_search_fields_use_the_same_typing_tag(self):
        for widget in (self.a._quick_text, self.entry):
            deliver_key(widget, '<KeyPress>', 'x', 88, char='字')
            self.assertEqual(widget.cget('cursor'), 'none')
            self.activity(widget, '<MouseWheel>')
            self.assertEqual(widget.cget('cursor'), 'xterm')

    def test_shortcuts_selection_drag_readonly_and_quote_enter_do_not_hide(self):
        a = self.a
        for key, char, state in (('Left', '', 0), ('Shift_L', '', 1),
                                 ('c', 'c', 4), ('x', 'x', 0x20000),
                                 ('a', 'a', 0x100), ('BackSpace', '\b', 0)):
            event = types.SimpleNamespace(widget=a.editor, keysym=key, char=char, state=state)
            self.assertFalse(a._typing_pointer_is_input(event), key)
        a._pick_mode = 'f1'
        self.assertFalse(a._typing_pointer_is_input(types.SimpleNamespace(
            widget=a.editor, keysym='Return', char='\r', state=0)))
        a.result_view.config(state='disabled')
        self.assertFalse(a._typing_pointer_is_input(types.SimpleNamespace(
            widget=a.result_view, keysym='a', char='a', state=0)))
        self.assertTrue(a._typing_pointer_is_input(types.SimpleNamespace(
            widget=a.editor, keysym='F1', keycode=112, char='p', state=8)))

    def test_hover_mode_changes_and_scroll_never_restore_an_old_hidden_cursor(self):
        a = self.a; w = a.editor
        self.pointer.hide(w)
        a._pick_mode = 'f1'
        a._set_pane_cursor(a.result_view, 'hand2')
        self.assertEqual(a.result_view.cget('cursor'), 'none')
        self.pointer.restore()
        self.assertEqual(a.result_view.cget('cursor'), 'xterm')
        a._pick_mode = None
        a._set_pane_cursor(a.result_view, 'arrow')
        self.pointer.hide(w)
        a._scroll_cursor_hide(w)
        self.assertFalse(self.pointer.saved)
        self.assertTrue(a._scroll_cursor)
        self.pointer.hide(w)
        self.assertFalse(self.pointer.saved)
        a._scroll_cursor_restore()
        self.assertEqual(w.cget('cursor'), 'xterm')
        self.assertEqual(a.result_view.cget('cursor'), 'arrow')

    def test_mouse_restore_captures_ime_change_before_the_next_timer_tick(self):
        pointer=self.pointer;w=self.a.editor
        pointer.hide(w)
        with patch.object(self.root,'focus_get',return_value=w), \
                patch('ime_watch.composition_active',return_value=True), \
                patch('ime_watch.read_composition',return_value={'comp':'入力'}):
            self.activity(w,'<Motion>')
            pointer.poll_composition()
            self.assertEqual(w.cget('cursor'),'xterm')

    def test_unchanged_ime_does_not_rehide_after_mouse_use_but_new_input_does(self):
        pointer = self.pointer; w = self.a._quick_text
        composition = {'comp': 'に'}
        with patch.object(self.root, 'focus_get', return_value=w), \
                patch('ime_watch.composition_active', return_value=True), \
                patch('ime_watch.read_composition', side_effect=lambda _: composition):
            pointer.poll_composition()
            self.assertEqual(w.cget('cursor'), 'none')
            self.activity(w, '<Motion>')
            pointer.poll_composition()
            self.assertEqual(w.cget('cursor'), 'xterm')
            composition['comp'] = 'にほ'
            pointer.poll_composition()
            self.assertEqual(w.cget('cursor'), 'none')
            self.activity(w, '<FocusOut>')
            with patch.object(self.root, 'focus_get', return_value=None):
                pointer.poll_composition()
            self.assertEqual(w.cget('cursor'), 'xterm')


if __name__ == '__main__': unittest.main()
