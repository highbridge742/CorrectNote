# -*- coding: utf-8 -*-
"""Menu checkbuttons toggle and the menu opens again (2026-10-22 うにさん「メニューのチェックボックス
項目は、クリックしたらチェックを切り替えて、メニューを閉じないようにする」).

A Windows menu always closes when an item is chosen, so every checkbutton under a menubar
button gets its original command plus a request to open the same menu again. The menus are
built in a withdrawn root here; posting is replaced, nothing native is shown. Also: the hotkey
status item moved from the View menu to the Edit menu."""
import inspect
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
import tkinter as tk

import app


class MenuKeepOpenTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        bar = tk.Frame(self.root)
        self.button = tk.Menubutton(bar, text='表示')
        self.menu = tk.Menu(self.button, tearoff=0); self.button.configure(menu=self.menu)
        self.sub = tk.Menu(self.menu, tearoff=0)
        a._menu_buttons = [self.button]
        self.calls = []
        self.var = tk.BooleanVar(value=False); self.subvar = tk.BooleanVar(value=False)
        self.menu.add_command(label='コマンド', command=lambda: self.calls.append('command'))
        self.menu.add_checkbutton(label='チェック', variable=self.var, command=lambda: self.calls.append('check'))
        self.menu.add_checkbutton(label='命令なし', variable=tk.BooleanVar(value=False))
        self.menu.add_cascade(label='下', menu=self.sub)
        self.sub.add_checkbutton(label='下のチェック', variable=self.subvar)
        self.posted = []
        a._post_menu_bar = lambda event: self.posted.append(str(event.widget))

    def tearDown(self):
        self.root.destroy()

    def run_after(self):
        for _ in range(5): self.root.update(); self.root.after(5); self.root.update()

    def test_checkbutton_toggles_runs_its_command_and_reopens_its_menu(self):
        self.a._keep_menu_open_entries(self.button)
        self.a._native_menu_active = False
        self.menu.invoke(1)
        self.assertTrue(self.var.get()); self.assertEqual(self.calls, ['check'])
        self.run_after()
        self.assertEqual(self.posted, [str(self.button)])
        self.menu.invoke(1)
        self.assertFalse(self.var.get()); self.run_after()
        self.assertEqual(self.posted, [str(self.button)] * 2)

    def test_plain_commands_still_close(self):
        self.a._keep_menu_open_entries(self.button)
        self.menu.invoke(0); self.run_after()
        self.assertEqual(self.calls, ['command']); self.assertEqual(self.posted, [])

    def test_entry_without_command_and_cascade_entries_also_reopen(self):
        self.a._keep_menu_open_entries(self.button)
        self.a._native_menu_active = False
        self.menu.invoke(2); self.run_after()
        self.sub.invoke(0); self.run_after()
        self.assertTrue(self.subvar.get())
        self.assertEqual(self.posted, [str(self.button)] * 2)

    def test_wrapping_is_idempotent_and_survives_rebuilt_menus(self):
        for _ in range(3): self.a._keep_menu_open_entries(self.button)
        self.assertEqual(str(self.menu.entrycget(1, 'command')).count(self.a._KEEP_MENU_OPEN), 1)
        self.menu.delete(0, 'end')                    # a menu rebuilt later (like ボタン)
        self.menu.add_checkbutton(label='作り直し', variable=self.var)
        self.a._keep_menu_open_entries(self.button)   # done again before each post
        self.assertIn(self.a._KEEP_MENU_OPEN, str(self.menu.entrycget(0, 'command')))

    def test_inside_the_menu_loop_only_a_flag_is_left(self):
        self.a._keep_menu_open_entries(self.button)
        self.a._native_menu_active = True             # the loop itself opens it again
        self.menu.invoke(1); self.run_after()
        self.assertEqual(self.posted, [])
        self.assertEqual(self.a._menu_reopen, str(self.button))

    def test_hotkey_status_is_in_the_edit_menu(self):
        source = inspect.getsource(app.CorrectNoteApp._build_menubar)
        self.assertIn("m_edit.add_command(label='ホットキーの状態を確認…'", source)
        self.assertNotIn("m_view.add_command(label='ホットキーの状態を確認…'", source)
        quick = source.index("m_edit.add_command(label='簡易入力ウィンドウを開く'")
        status = source.index("m_edit.add_command(label='ホットキーの状態を確認…'")
        book = source.index("m_edit.add_command(label='単語帳を開く／閉じる'")
        self.assertLess(quick, status); self.assertLess(status, book)
        # 2026-10-22: the six View items below 「ダークモード」 are in the Edit menu now
        view = source[source.index("_make_menubutton('表示')"):source.index("_make_menubutton('ボタン')")]
        for label in ('簡易入力ホットキー有効化（Insert）', '簡易入力ホットキー有効化（-）', '単語帳ホットキー有効化',
                      '簡易入力の説明を表示', '簡易入力を閉じたら、元の入力欄へ貼り付ける',
                      '簡易入力を閉じたら、クリップボードに入れる'):
            self.assertNotIn(label, view)
            self.assertIn("label='%s'" % label, source)


if __name__ == '__main__':
    unittest.main()
