# -*- coding: utf-8 -*-
"""再変換・再入力変換のキー操作の間、欄の上のマウスカーソルを隠す（作った例・本当のマウスは動かさない）。"""
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest.mock import patch

import reinput
from reinput import CursorHider, ListKeys, ReInput


class Base(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.addCleanup(self.root.destroy)
        self.root.withdraw()
        self.text = tk.Text(self.root, cursor='xterm', undo=True)
        self.text.insert('1.0', '資料を作る')
        self.other = tk.Text(self.root, cursor='arrow')
        self.app = NS(editor=self.text, result_view=self.other, _dropdown=None, _f2_focus_target=None, _composing=lambda w: False,
                      status=NS(config=lambda **k: None), settings={},
                      _text_edge_column=lambda w, row, text, at, d: len(text) if d > 0 else 0)
        self.h = self.app._cursor_hider = CursorHider(self.app)
        self.r = self.app._reinput = ReInput(self.app, self.text)
        patch.object(ReInput, 'reading_of', lambda s, row, col, surface: 'しりょう').start()
        patch.object(ReInput, 'choices_for', lambda s, reading: ['試料']).start()
        patch.object(ReInput, '_owner', lambda s: 'tab').start()
        patch.object(ReInput, '_char_readings', lambda s, ch: []).start()
        self.addCleanup(patch.stopall)

    def cursors(self):
        return self.text.cget('cursor'), self.other.cget('cursor')

    def key(self, name):
        return self.r.on_press(NS(keysym=name))

    def idle(self):
        self.root.update()


class Hider(Base):
    def test_hide_and_restore_the_names(self):
        self.h.hide()
        self.assertEqual(self.cursors(), ('none', 'none'))
        self.h.restore()
        self.assertEqual(self.cursors(), ('xterm', 'arrow'))

    def test_hiding_twice_keeps_the_first_name(self):
        self.h.hide(); self.h.hide(); self.h.restore()
        self.assertEqual(self.cursors(), ('xterm', 'arrow'))

    def test_moving_the_mouse_restores(self):
        self.h.hide()
        self.h.at = (100, 100)
        self.h.on_motion(NS(x_root=100, y_root=100))
        self.assertEqual(self.text.cget('cursor'), 'none')       # 動いていない Motion
        self.h.on_motion(NS(x_root=100, y_root=101))             # 動いたら距離によらず
        self.assertEqual(self.text.cget('cursor'), 'xterm')

    def test_motion_with_nothing_hidden_does_nothing(self):
        self.h.on_motion(NS(x_root=1, y_root=1))
        self.assertEqual(self.text.cget('cursor'), 'xterm')

    def test_a_list_opened_while_hidden_is_hidden(self):
        box = tk.Listbox(self.root, cursor='arrow')
        self.h.hide(); self.h.add(box)
        self.assertEqual(box.cget('cursor'), 'none')
        self.h.restore()
        self.assertEqual(box.cget('cursor'), 'arrow')

    def test_a_list_opened_while_shown_stays(self):
        box = tk.Listbox(self.root, cursor='arrow')
        self.h.add(box)
        self.assertEqual(box.cget('cursor'), 'arrow')

    def test_a_widget_gone_is_no_trouble(self):
        box = tk.Listbox(self.root)
        self.h.hide(box)
        box.destroy()
        self.h.restore()
        self.assertEqual(self.text.cget('cursor'), 'xterm')

    def test_the_mode_still_on_is_not_restored(self):
        self.h.hide()
        self.app._f2_focus_target = dict(widget=self.text)
        self.h.check()
        self.assertEqual(self.text.cget('cursor'), 'none')
        self.app._f2_focus_target = None
        self.h.check()
        self.assertEqual(self.text.cget('cursor'), 'xterm')


class ReInputKeys(Base):
    def begin(self):
        self.text.mark_set('insert', '1.1')
        self.assertTrue(self.r.start())

    def test_opening_hides(self):
        self.begin()
        self.assertEqual(self.text.cget('cursor'), 'none')

    def test_moving_the_mouse_shows_it_while_open_and_a_key_hides_it_again(self):
        self.begin()
        self.h.at = (0, 0)
        self.h.on_motion(NS(x_root=50, y_root=50))
        self.assertEqual(self.text.cget('cursor'), 'xterm')
        self.assertIsNotNone(self.r.state)
        self.key('a')
        self.assertEqual(self.text.cget('cursor'), 'none')

    def test_a_key_in_the_range_hides(self):
        self.begin()
        self.key('a')
        self.assertEqual(self.text.cget('cursor'), 'none')

    def test_control_alone_does_not_hide(self):
        self.begin()
        self.h.restore()
        self.key('Control_L')
        self.assertEqual(self.text.cget('cursor'), 'xterm')

    def test_ending_restores(self):
        for end in ('Return', 'Escape'):
            self.begin()
            self.key('space')
            self.assertEqual(self.text.cget('cursor'), 'none')
            self.key(end); self.idle()
            self.assertEqual(self.text.cget('cursor'), 'xterm')

    def test_leaving_restores(self):
        self.begin(); self.key('a')
        self.text.mark_set('insert', '1.end')
        self.r.leave(); self.idle()
        self.assertEqual(self.text.cget('cursor'), 'xterm')

    def test_outside_any_mode_keys_do_not_hide(self):
        self.key('a')
        self.assertEqual(self.text.cget('cursor'), 'xterm')

    def test_the_reconvert_range_with_no_list(self):
        self.app._f2_focus_target = dict(widget=self.text, row=1, start=0, end=2, text='資料')
        self.key('Left')
        self.assertEqual(self.text.cget('cursor'), 'none')


class ListSide(Base):
    def setUp(self):
        super().setUp()
        self.box = tk.Listbox(self.root, cursor='arrow')
        self.box.insert('end', 'a', 'b'); self.box.selection_set(0)
        self.app._f2_focus_target = dict(widget=self.text, row=1, start=0, end=2, text='資料')
        self.app._dropdown = object()
        self.app._dropdown_pick = lambda: None
        self.keys = ListKeys(self.app, self.box)
        self.keys.remember_first()

    def test_up_down_on_the_list_hides(self):
        self.keys.press(NS(keysym='Down', char=''))
        self.assertEqual((self.text.cget('cursor'), self.box.cget('cursor')), ('none', 'none'))

    def test_left_right_too(self):
        self.keys.press(NS(keysym='Right', char=''))
        self.assertEqual(self.text.cget('cursor'), 'none')

    def test_control_alone_does_not_hide(self):
        self.keys.press(NS(keysym='Control_L', char=''))
        self.assertEqual(self.text.cget('cursor'), 'xterm')

    def test_another_boxs_list_does_not_hide(self):
        self.app._f2_focus_target = dict(widget=object())
        self.keys.press(NS(keysym='Down', char=''))
        self.assertEqual(self.text.cget('cursor'), 'xterm')

    def test_the_mode_ended_restores(self):
        self.keys.press(NS(keysym='Down', char=''))
        self.app._dropdown = None; self.app._f2_focus_target = None
        reinput.check_cursor(self.app); self.root.update()
        self.assertEqual(self.text.cget('cursor'), 'xterm')


class Reconvert(Base):
    def test_opening_a_list_hides_with_the_list(self):
        box = tk.Listbox(self.root, cursor='arrow')
        self.app._dropdown = object(); self.app._dropdown_parts = dict(lb=box)
        reinput.hide_cursor_for_reconvert(self.app)
        self.assertEqual((self.text.cget('cursor'), box.cget('cursor')), ('none', 'none'))

    def test_a_range_with_no_list_hides(self):
        self.app._f2_focus_target = dict(widget=self.text)
        reinput.hide_cursor_for_reconvert(self.app)
        self.assertEqual(self.text.cget('cursor'), 'none')

    def test_nothing_opened_does_not_hide(self):
        reinput.hide_cursor_for_reconvert(self.app)
        self.assertEqual(self.text.cget('cursor'), 'xterm')


class NeverStuck(Base):
    def test_the_watch_restores_when_no_mode_is_open(self):
        self.h.hide()
        self.h.at = None
        self.h._watching()
        self.assertEqual(self.text.cget('cursor'), 'xterm')

    def test_the_watch_restores_when_the_mouse_moved_elsewhere(self):
        self.app._f2_focus_target = dict(widget=self.text)
        self.h.hide()
        self.h.at = (-5, -5)
        self.h._watching()
        self.assertEqual(self.text.cget('cursor'), 'xterm')

    def test_the_watch_keeps_it_while_the_mode_is_on_and_the_mouse_still(self):
        self.app._f2_focus_target = dict(widget=self.text)
        self.h.hide()
        self.h._watching()
        self.assertEqual(self.text.cget('cursor'), 'none')
        self.assertIsNotNone(self.h._watch)
        self.h.restore()
        self.assertIsNone(self.h._watch)

    def test_entering_a_box_with_no_mode_restores(self):
        self.h.hide()
        self.h.on_enter()
        self.assertEqual(self.text.cget('cursor'), 'xterm')

    def test_entering_with_the_mode_on_stays(self):
        self.app._f2_focus_target = dict(widget=self.text)
        self.h.hide()
        self.h.on_enter()
        self.assertEqual(self.text.cget('cursor'), 'none')

    def test_the_result_pane_watches_the_mouse(self):
        app = NS(result_view=tk.Text(self.root))
        reinput.install(app, tk.Text(self.root))
        self.assertEqual(app.result_view.bindtags()[0], reinput.BIND_TAG + 'Pane')

    def test_a_list_gone_while_hidden_is_no_trouble(self):
        box = tk.Listbox(self.root)
        self.h.hide(box)
        box.destroy()
        self.h.at = None
        self.h._watching()
        self.assertEqual(self.text.cget('cursor'), 'xterm')


class App(Base):
    def test_restore_is_safe_with_no_hider(self):
        reinput.restore_cursor(NS()); reinput.check_cursor(NS())

    def test_install_makes_one_hider(self):
        app = NS()
        box = tk.Text(self.root)
        reinput.install(app, box)
        first = app._cursor_hider
        reinput.install(app, tk.Text(self.root), quick=True)
        self.assertIs(app._cursor_hider, first)


if __name__ == '__main__':
    unittest.main()
