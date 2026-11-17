# -*- coding: utf-8 -*-
"""2026-11-15 うにさんの追加の直し（自分の Tk の窓だけ・作った例文）:
- タブを替えると、前のタブで目次から下のほうへ飛んだ時の「真ん中に寄せる余白」（navigation_head／tail）が補正欄の
  1行目に残り、左右の行の高さをそろえる所が本文の1行目にも同じ空きを足していた → タブを読み込む時に外す
- 目次の行をクリックして飛んだ後、ボタンを離すまでの動きで選択を広げない"""
import os
import tkinter as tk
import unittest
from types import SimpleNamespace as NS
from unittest import mock

import title_inline as TI


class _Stop(Exception):
    pass


class TabLoadClearsJumpMargins(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError:
            self.skipTest('no display')
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def run_load(self, environ):
        import app
        panes = [tk.Text(self.root) for _ in range(2)]
        for pane in panes:
            pane.insert('1.0', '前のタブの1行目\n2行目')
            pane.tag_add('navigation_head', '1.0', '1.0+1c')
            pane.tag_add('navigation_tail', 'end-2c linestart', 'end')
        fake = NS(editor=panes[0], result_view=panes[1], _navigation_padding_active=False,
                  _cancel_autoscan=lambda: None, _unmask_navigation_margins=lambda w: None)
        fake._clear_navigation_padding = lambda: app.CorrectNoteApp._clear_navigation_padding(fake)

        def stop():
            raise _Stop()
        fake._clear_copy_emphasis = stop
        with mock.patch.dict(os.environ, environ, clear=False):
            with self.assertRaises(_Stop):
                app.CorrectNoteApp._load_active_tab_core(fake)
        return [(p.tag_ranges('navigation_head'), p.tag_ranges('navigation_tail')) for p in panes]

    def test_margins_go_even_when_the_flag_was_already_off(self):
        # 補正欄は変わった所だけ書き直すので、1行目の頭の字の余白が残った（左右の行をそろえる所が本文にも空きを足した）
        self.assertEqual(self.run_load({'CN_TAB_NAV_CLEAR': '1'}), [((), ()), ((), ())])

    def test_switch_back_to_the_old_behaviour(self):
        got = self.run_load({'CN_TAB_NAV_CLEAR': '0'})
        self.assertTrue(all(head and tail for head, tail in got))


class TocPressHoldsTheDrag(unittest.TestCase):
    def test_motion_after_a_toc_press_does_not_select(self):
        toc = TI.InlineTitleToc.__new__(TI.InlineTitleToc)
        toc._active = False
        toc._drag = False
        toc._head_press = True
        self.assertEqual(toc._b1_motion(NS(x=10, y=10)), 'break')
        self.assertEqual(toc._release(NS(x=10, y=10)), 'break')
        self.assertFalse(toc._head_press)
        self.assertIsNone(toc._b1_motion(NS(x=10, y=10)))      # 次の押しからはふつう（本文の選択）


if __name__ == '__main__':
    unittest.main()
