# -*- coding: utf-8 -*-
"""単語帳の数字キー: IME を掛けない窓・押したらキーを受ける（作った単語帳・本物の前面切り替えはしない）。"""
import json
import os
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import word_book
from word_book import WordBook


class Book(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        path = Path(self.tmp.name) / 'word_book.json'
        path.write_text(json.dumps({'version': 2, 'sets': [['一'], ['二'], ['三'], ['四']], 'active_set': 0, 'visible': False, 'width': 220}, ensure_ascii=False), encoding='utf-8')
        self.root = tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)
        app = NS(root=self.root, status=Mock(), word_book_btn=Mock(), _editor_font=lambda: ('Yu Gothic UI', 10),
                 _start_word_book_add=lambda: None, _pick_mode=None, _set_window_icons_win32=lambda win: None)
        for name, value in (('_place', lambda book, near_pointer=False: None), ('_give_back_after_open', lambda book: None)):
            p = patch.object(WordBook, name, value); p.start(); self.addCleanup(p.stop)
        self.book = WordBook(app, path, lambda: ('#ffffff', '#000000', '#3366cc'), lambda: 220)
        self.book.open()
        self.book.window.geometry('+10000+100')
        self.root.update()
        self.addCleanup(self.close)

    def close(self):
        try:
            self.book.close()
        except Exception:
            pass

    def fake(self, took=True):
        real = self.book._native      # 窓の subclass の手続きを持っているので、閉じるまで手放さない
        self.addCleanup(setattr, self.book, '_native', real)
        self.book._native = NS(take_keys=Mock(return_value=took), no_ime=Mock(), detach=lambda: None, hwnd=None)
        self.book.window.focus_force = Mock()
        return self.book._native


class Press(Book):
    def test_pressing_the_window_takes_the_keys(self):
        native = self.fake()
        self.book._press_on_window(NS(widget=self.book.canvas))
        native.take_keys.assert_called_once()
        self.book.window.focus_force.assert_called_once()

    def test_pressing_a_word_does_not(self):
        native = self.fake()
        button = tk.Button(self.book.window)
        self.book._press_on_window(NS(widget=button))
        native.take_keys.assert_not_called()

    def test_with_our_own_app_in_front_it_stays_as_it_was(self):
        self.fake(took=False)
        self.book._press_on_window(NS(widget=self.book.canvas))
        self.book.window.focus_force.assert_not_called()

    def test_a_digit_switches_the_set(self):
        self.book._set_key(2)
        self.assertEqual(self.book.active_set, 2)

    def test_rendering_again_keeps_the_ime_off(self):
        native = self.fake()
        self.book.render()
        native.no_ime.assert_called()


@unittest.skipUnless(os.name == 'nt', 'windows')
class Native(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.addCleanup(self.root.destroy)
        self.root.withdraw()
        self.win = tk.Toplevel(self.root)
        self.win.geometry('+10000+100')
        self.button = tk.Button(self.win, text='x'); self.button.pack()
        self.root.update()

    def native(self):
        native = word_book._WordBookNative.__new__(word_book._WordBookNative)
        import ctypes as c
        native.c = c
        native.user = NS(GetForegroundWindow=lambda: 1, GetWindowThreadProcessId=Mock(), SetForegroundWindow=Mock(return_value=1))
        native.hwnd = c.WinDLL('user32').GetAncestor(self.win.winfo_id(), 2)
        return native

    def test_no_ime_only_on_this_window(self):
        import ctypes as c
        from ctypes import wintypes as W
        imm = c.WinDLL('imm32')
        imm.ImmGetContext.argtypes = [W.HWND]; imm.ImmGetContext.restype = W.HANDLE
        imm.ImmReleaseContext.argtypes = [W.HWND, W.HANDLE]
        other = tk.Toplevel(self.root); other.geometry('+10000+300'); self.root.update()
        before = imm.ImmGetContext(other.winfo_id())
        if before:
            imm.ImmReleaseContext(other.winfo_id(), before)
        self.assertTrue(self.native().no_ime(self.win))
        for widget in (self.win, self.button):
            self.assertFalse(imm.ImmGetContext(widget.winfo_id()))
        after = imm.ImmGetContext(other.winfo_id())
        self.assertEqual(bool(after), bool(before))
        if after:
            imm.ImmReleaseContext(other.winfo_id(), after)


@unittest.skipUnless(os.name == 'nt', 'windows')
class SendAfterComingForward(unittest.TestCase):
    """見出しで前に出したあと語を押す: 送り先は、前に出す直前に前にあったアプリ（前面の切り替えは偽物）。"""
    BOOK, OTHER, THIRD = 100, 200, 300

    def native(self):
        native = word_book._WordBookNative.__new__(word_book._WordBookNative)
        import ctypes as c
        self.front = self.OTHER
        self.sets = []
        def set_front(hwnd):
            self.sets.append(hwnd); self.front = hwnd; return 1
        def pid_of(hwnd, out=None):
            if out is not None:
                out._obj.value = 7
            return 1
        native.c = c
        native.user = NS(GetForegroundWindow=lambda: self.front, SetForegroundWindow=set_front, IsWindow=lambda h: True, IsWindowVisible=lambda h: True,
                         IsIconic=lambda h: False, GetAncestor=lambda h, f: h, GetWindowThreadProcessId=pid_of)
        native.hwnd = self.BOOK
        native.previous = None; native.focus = None; native.return_focus = None
        native.event_hook = native.focus_hook = None
        return native

    def test_the_app_that_was_in_front_gets_it(self):
        native = self.native()
        native._remember(self.OTHER)              # 別のアプリが前
        with patch.object(word_book._WordBookNative, 'own_app_in_front', lambda s: False):
            self.assertTrue(native.take_keys())   # 見出しを押した
        self.assertEqual(self.front, self.BOOK)
        native._remember(self.BOOK)               # 前面の変化の知らせは自分の窓: 覚え直さない
        self.assertEqual(native.previous[0], self.OTHER)
        self.assertTrue(native.restore_previous())
        self.assertEqual(self.front, self.OTHER)

    def test_a_third_app_afterwards_takes_over(self):
        native = self.native()
        native._remember(self.OTHER)
        with patch.object(word_book._WordBookNative, 'own_app_in_front', lambda s: False):
            native.take_keys()
        self.front = self.THIRD
        native._remember(self.THIRD)
        self.assertEqual(native.previous[0], self.THIRD)


@unittest.skipUnless(os.name == 'nt', 'windows')
class FrontWork(unittest.TestCase):
    """前面の切り替えは全部偽物。"""
    BOOK, OTHER, SWITCHER, THIRD = 100, 200, 400, 300

    def native(self, refuse=0):
        native = word_book._WordBookNative.__new__(word_book._WordBookNative)
        import ctypes as c
        self.front = self.OTHER
        self.refuse = [refuse]
        self.styles = []
        self.attached = []
        def set_front(hwnd):
            if self.refuse[0] > 0:
                self.refuse[0] -= 1
                return 0
            self.front = hwnd
            return 1
        def pid_of(hwnd, out=None):
            if out is not None:
                out._obj.value = 7
            return 1
        native.c = c
        native.user = NS(GetForegroundWindow=lambda: self.front, SetForegroundWindow=set_front, IsWindow=lambda h: True, IsWindowVisible=lambda h: True,
                         IsIconic=lambda h: False, GetAncestor=lambda h, f: h, GetWindowThreadProcessId=pid_of, BringWindowToTop=lambda h: 1,
                         AttachThreadInput=lambda a, b, on: self.attached.append(on) or 1,
                         GetClassNameW=self.class_name)
        native.hwnd = self.BOOK
        native.previous = None; native.focus = None; native.return_focus = None
        native.event_hook = native.focus_hook = None
        native._set_noactivate = lambda on: self.styles.append(on)
        for p in (patch.object(word_book._WordBookNative, 'own_app_in_front', lambda s: False),):
            p.start(); self.addCleanup(p.stop)
        return native

    def class_name(self, hwnd, buf, size):
        buf.value = 'XamlExplorerHostIslandWindow' if hwnd == self.SWITCHER else 'App'
        return 1

    def test_press_lifts_the_no_activate_and_comes_forward(self):
        native = self.native()
        self.assertTrue(native.take_keys())
        self.assertEqual(self.front, self.BOOK)
        self.assertEqual(self.styles, [False])
        self.assertTrue(native.took)
        self.assertEqual(native.previous[0], self.OTHER)

    def test_our_own_app_in_front_changes_nothing(self):
        native = self.native()
        with patch.object(word_book._WordBookNative, 'own_app_in_front', lambda s: True):
            self.assertFalse(native.take_keys())
        self.assertEqual((self.front, self.styles), (self.OTHER, []))

    def test_refused_tries_attached_input(self):
        native = self.native(refuse=1)
        self.assertTrue(native.take_keys())
        self.assertEqual(self.attached, [True, False])

    def test_refused_twice_gives_up_and_stays_no_activate(self):
        native = self.native(refuse=2)
        self.assertFalse(native.take_keys())
        self.assertEqual(self.styles, [False, True])
        self.assertFalse(native.took)

    def test_a_digit_gives_the_front_back(self):
        native = self.native()
        native.take_keys()
        self.assertTrue(native.give_back())
        self.assertEqual(self.front, self.OTHER)
        self.assertFalse(native.took)
        self.assertEqual(self.styles, [False, True])

    def test_no_give_back_if_the_user_went_elsewhere(self):
        native = self.native()
        native.take_keys()
        self.front = self.THIRD
        self.assertFalse(native.give_back())
        self.assertEqual(self.front, self.THIRD)

    def test_pressing_the_title_bar_comes_forward(self):
        native = self.native()
        native._on_nc_press(2)
        self.assertEqual(self.front, self.BOOK)
        self.assertEqual(native.previous[0], self.OTHER)

    def test_title_bar_buttons_do_not(self):
        native = self.native()
        for hit in (8, 9, 20):
            native._on_nc_press(hit)
        self.assertEqual(self.front, self.OTHER)

    def test_moving_by_the_title_bar_gives_the_front_back(self):
        native = self.native()
        native._on_nc_press(2)
        native.moved = True
        native.refocus_previous = lambda: None
        native._after_move()
        self.assertEqual(self.front, self.OTHER)
        self.assertFalse(native.took)

    def test_pressing_without_moving_stays_for_the_digit(self):
        native = self.native()
        native._on_nc_press(2)
        native._after_move()
        self.assertEqual(self.front, self.BOOK)
        self.assertTrue(native.took)

    def test_an_untitled_xaml_window_is_the_switcher_but_a_titled_one_is_an_app(self):
        native = self.native()
        native.user.GetClassNameW = lambda h, b, n: setattr(b, 'value', 'XamlWindow')
        native.user.GetWindowTextLengthW = lambda h: 0
        self.assertTrue(native._is_switcher(1))
        native.user.GetWindowTextLengthW = lambda h: 5
        self.assertFalse(native._is_switcher(1))

    def test_alt_tab_list_is_not_the_target(self):
        native = self.native()
        native._remember(self.OTHER)
        native._remember(self.SWITCHER)     # Alt+Tab の一覧
        native._remember(self.BOOK)         # 単語帳が前に
        self.assertEqual(native.previous[0], self.OTHER)
        self.front = self.BOOK
        self.assertTrue(native.restore_previous())
        self.assertEqual(self.front, self.OTHER)

    def test_alt_tab_list_is_not_the_remembered_control(self):
        native = self.native()
        native._remember_focus(self.OTHER)
        native._remember_focus(self.SWITCHER)
        self.assertEqual(native.focus[0], self.OTHER)


class SetKey(Book):
    def test_the_digit_keeps_the_focus_here(self):
        native = self.fake()
        native.took = True
        native.give_back = Mock()
        self.book._set_key(1)
        self.book._set_key(2)
        native.give_back.assert_not_called()
        self.assertEqual(self.book.active_set, 2)

    def test_the_add_button_says_the_set(self):
        self.assertIn('セット1', self.book.add_button.cget('text'))
        self.book._set_key(2)
        self.assertIn('セット3', self.book.add_button.cget('text'))

    def test_the_strip_under_the_title_comes_forward_too(self):
        native = self.fake()
        native.start_move = lambda: True
        self.book._start_drag(NS(widget=self.book.header, x_root=0, y_root=0))
        native.take_keys.assert_called_once()

    def test_english(self):
        import ui_lang_en
        table = next(v for v in vars(ui_lang_en).values() if isinstance(v, dict) and '改行' in v)
        self.assertEqual(table['追加（セット{0}）'], 'Add (Set {0})')


if __name__ == '__main__':
    unittest.main()
