# -*- coding: utf-8 -*-
"""Cursor line number follows native Text marks without polling or editing."""
import tkinter as tk
import unittest
from unittest.mock import patch
import app

class GutterTkTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.withdraw()
        self.w=tk.Text(self.root,width=10,height=8,wrap='char',undo=True)
        self.g=app.LineNumberGutter(self.root,self.w,bookmarks={2})
        self.w.insert('1.0','先頭\n長い😀本文を折り返して表示する行\n最後')
        self.geometry={1:(0,3,100,20,15),2:(0,23,100,20,15),3:(0,83,100,20,15)}
        # A hidden real Tk widget has no display metrics. Supply just geometry;
        # Text marks/observer, Canvas items and after-idle are real Tcl objects.
        self.patches=[patch.object(self.w,'dlineinfo',side_effect=self.line_info),
                      patch.object(self.w,'winfo_height',return_value=110),
                      patch.object(self.w,'index',side_effect=self.text_index)]
        self.original_index=self.w.index
        for p in self.patches:p.start()
    def text_index(self,value):
        if value=='@0,0':return '1.0'
        if value=='@0,109':return '3.0'
        return self.original_index(value)
    def line_info(self,index):
        return self.geometry.get(int(self.w.index(index).split('.')[0]))
    def tearDown(self):
        for p in self.patches:p.stop()
        del p
        self.patches=[]
        self.root.destroy()
        from tests_tk_keys import release_tk_fixture
        self.original_index=None
        release_tk_fixture(self,'w','g','root')
    def test_cursor_moves_coalesce_and_same_row_does_not_repaint(self):
        self.w.mark_set('insert','1.0');self.root.update_idletasks()
        first=self.g.find_withtag('cursor_line')
        self.assertEqual(len(first),1)
        self.assertEqual(self.g.coords(first[0]),[0.0,3.0,48.0,23.0])
        self.w.mark_set('insert','1.1');self.root.update_idletasks()
        self.assertEqual(self.g.find_withtag('cursor_line'),first)
        self.w.mark_set('insert','2.0');pending=self.g._cursor_after
        self.w.mark_set('insert','3.0');self.assertEqual(self.g._cursor_after,pending)
        self.root.update_idletasks()
        item=self.g.find_withtag('cursor_line')[0]
        self.assertEqual(self.g.coords(item),[0.0,83.0,48.0,103.0])
        self.assertEqual(len(self.g.find_withtag('mark')),1)
    def test_palette_readonly_and_pending_destroy(self):
        self.w.configure(state='disabled')
        self.w.mark_set('insert','2.0');self.root.update_idletasks()
        for palette in (app.LIGHT_PALETTE,app.DARK_PALETTE):
            with patch.object(app,'LINE_NUM_ACTIVE_BG',palette['LINE_NUM_ACTIVE_BG']):
                self.g.redraw()
                item=self.g.find_withtag('cursor_line')[0]
                self.assertEqual(self.g.itemcget(item,'fill'),palette['LINE_NUM_ACTIVE_BG'])
                self.assertTrue(all(int(palette['LINE_NUM_ACTIVE_BG'][i:i+2],16)>
                                    int(palette['LINE_NUM_BG'][i:i+2],16) for i in (1,3,5)))
        self.w.mark_set('insert','3.0')
        self.assertIsNotNone(self.g._cursor_after)
        self.g.destroy();self.root.update_idletasks()
        self.w.mark_set('insert','1.0');self.root.update_idletasks()

    def test_wrapped_line_head_above_view_keeps_visible_number(self):
        self.w.mark_set('insert','2.0')
        with patch.object(self.w,'index',side_effect=lambda value: '2.8' if value=='@0,0'
                          else '3.0' if value=='@0,109' else self.original_index(value)), \
             patch.object(self.w,'dlineinfo',side_effect=lambda index:
                          (0,3,100,20,15) if index=='@0,0' else None if index=='2.0'
                          else (0,83,100,20,15)):
            self.g.redraw()
            self.assertEqual([self.g.itemcget(item,'text') for item in self.g.find_withtag('num')],['2','3'])
            item=self.g.find_withtag('cursor_line')[0]
            self.assertEqual(self.g.coords(item),[0.0,3.0,48.0,23.0])
