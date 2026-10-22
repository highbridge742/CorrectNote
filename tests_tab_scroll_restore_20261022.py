# -*- coding: utf-8 -*-
"""The tab's saved view is not put back once the user has moved (2026-10-22).

うにさん「タブ移動して、途中の行にいたので、1行目ボタンで先頭に移動した後、解析が済むと
タブ移動した行に戻りました」. After a tab opens, its saved view is applied again when the
layout settles and when the first analysis ends (_restore_pending_scroll). The user moving
the view counted only away from the top, so a jump to line 1 looked untouched. Now a cursor
on another row than the one the tab opened with, the scrollbar, the wheel and the line jumps
(1行目／最終行・Ctrl+Home・a click) drop it. Withdrawn root."""
import inspect
import unittest
from unittest.mock import Mock
import tkinter as tk

import app


class TabScrollRestoreTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk(); self.root.withdraw()
        a = self.a = app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        a.root = self.root
        a.editor = tk.Text(self.root, height=10); a.result_view = tk.Text(self.root, height=10)
        a.editor.pack(); a.result_view.pack()
        a.editor_gutter = Mock(); a.result_gutter = Mock()
        body = '\n'.join('%d 行目' % i for i in range(1, 401))
        for w in (a.editor, a.result_view): w.insert('1.0', body)
        self.root.update_idletasks()

    def tearDown(self):
        self.root.destroy()

    def opened_at(self, row):
        """What _load_active_tab leaves: the cursor and the saved top row."""
        a = self.a
        a.editor.mark_set('insert', '%d.2' % row)
        a._pending_scroll = 0.5; a._pending_scroll_top = row
        a._pending_scroll_cursor = a.editor.index('insert')
        a._pending_scroll_applied = a.editor.yview()[0]

    def top_row(self):
        return int(self.a.editor.index('@0,0').split('.')[0])

    def test_untouched_tab_still_gets_its_saved_view(self):
        self.opened_at(200)
        self.a.editor.yview_moveto(0)                    # the layout pulls it back to the top
        self.a._restore_pending_scroll(final=True)
        self.assertEqual(self.top_row(), 200)

    def test_jump_to_line_one_is_kept_after_analysis(self):
        self.opened_at(200)
        self.a.editor.mark_set('insert', '1.0'); self.a.editor.yview_moveto(0)   # 1行目・Ctrl+Home・a click
        self.a._restore_pending_scroll(final=True)
        self.assertEqual(self.top_row(), 1)
        self.assertEqual((self.a._pending_scroll, self.a._pending_scroll_top), (0.0, None))
        self.a._restore_pending_scroll(final=True)        # nothing is left to put back
        self.assertEqual(self.top_row(), 1)

    def test_autofix_moving_the_column_on_the_same_row_is_not_a_user_move(self):
        self.opened_at(200)
        self.a.editor.mark_set('insert', '200.5'); self.a.editor.yview_moveto(0)
        self.a._restore_pending_scroll(final=True)
        self.assertEqual(self.top_row(), 200)

    def test_wheel_scrollbar_and_line_jumps_drop_the_saved_view(self):
        a = self.a
        self.opened_at(200)
        a._tab_wheel = Mock(return_value=None); a._wheel_scroll = Mock()
        a._on_wheel(type('E', (), {'delta': 120})())
        self.assertEqual((a._pending_scroll, a._pending_scroll_top), (0.0, None))
        for name in ('_on_scrollbar', '_goto_line'):
            body = inspect.getsource(getattr(app.CorrectNoteApp, name))
            self.assertIn('self._drop_pending_scroll()', body, name)
        loader = inspect.getsource(app.CorrectNoteApp._load_active_tab)
        self.assertIn("self._pending_scroll_cursor = self.editor.index('insert')", loader)


if __name__ == '__main__':
    unittest.main()
