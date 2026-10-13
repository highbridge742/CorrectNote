# -*- coding: utf-8 -*-
# CorrectNote — Copyright (C) 2026 Takahashi Yuu
# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual candidate lists grow to available space and remain reachable."""
import tkinter as tk
import unittest
from unittest.mock import Mock,patch
import app

class DropdownHeightTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.geometry('720x680+100+40')
        self.root.update()
        self.a=app.CorrectNoteApp.__new__(app.CorrectNoteApp)
        self.a.root=self.root;self.a._quick_win=None
        self.a._dropdown_text='資料';self.a._close_dropdown=Mock()
        self.errors=[]
        self.root.report_callback_exception=lambda *args:self.errors.append(args)

    def tearDown(self):
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'a','root')

    def show(self,count,parent=None,area=None):
        parent=parent or self.root
        self.callbacks=[Mock() for _ in range(count)]
        items=[('候補 '+str(i+1),cb) for i,cb in enumerate(self.callbacks)]
        with patch.object(app,'monitor_work_area',return_value=area):
            self.a._make_dropdown(items,parent.winfo_rootx()+30,
                                  parent.winfo_rooty()+60,parent=parent)
        self.root.update()
        dd=self.a._dropdown
        lb=next(c for c in dd.winfo_children() if isinstance(c,tk.Listbox))
        return dd,lb

    def test_all_thirty_candidates_fit_when_window_has_space(self):
        dd,lb=self.show(30)
        self.assertEqual(int(lb.cget('height')),30)
        self.assertIsNotNone(lb.bbox(29))
        self.assertGreater(lb.bbox(29)[1],0)
        self.assertGreaterEqual(dd.winfo_rooty(),self.root.winfo_rooty())
        self.assertLessEqual(dd.winfo_rooty()+dd.winfo_height(),
                            self.root.winfo_rooty()+self.root.winfo_height())
        self.assertFalse(any(isinstance(c,tk.Scrollbar) for c in dd.winfo_children()))
        self.assertEqual(self.errors,[])

    def test_small_window_limits_height_with_scrollbar_and_last_item_can_be_picked(self):
        self.root.geometry('420x260+100+40');self.root.update()
        dd,lb=self.show(80)
        self.assertLess(int(lb.cget('height')),80)
        self.assertLessEqual(dd.winfo_rooty()+dd.winfo_height(),
                            self.root.winfo_rooty()+self.root.winfo_height())
        self.assertTrue(any(isinstance(c,tk.Scrollbar) for c in dd.winfo_children()))
        lb.see(79);lb.selection_clear(0,'end');lb.selection_set(79)
        self.root.update();self.assertIsNotNone(lb.bbox(79))
        # The owned desktop is never activated; deliver through the actual
        # registered Tk binding so the system foreground is irrelevant.
        from tests_tk_keys import deliver_key
        deliver_key(lb,'<Return>','Return',13);self.root.update()
        self.callbacks[79].assert_called_once()
        self.assertEqual(self.errors,[])

    def test_quick_list_uses_monitor_space_beyond_its_small_window(self):
        quick=tk.Toplevel(self.root);quick.geometry('240x100+300+200');self.root.update()
        self.a._quick_win=quick
        dd,lb=self.show(30,quick,(0,0,1200,800))
        self.assertEqual(int(lb.cget('height')),30)
        self.assertGreater(dd.winfo_height(),quick.winfo_height())
        self.assertGreaterEqual(dd.winfo_rooty(),0)
        self.assertLessEqual(dd.winfo_rooty()+dd.winfo_height(),800)
        self.assertIsNotNone(lb.bbox(29))
        self.assertEqual(self.errors,[])

if __name__=='__main__':unittest.main()
