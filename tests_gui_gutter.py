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
        width=float(self.g['width'])
        # 2026-10-15: 幅は桁数と字から（左 12 ＋ 数字 ＋ 右 10）。3 行でも 3 桁分
        self.assertEqual(width,float(self.g.fit_width(3)))
        self.assertEqual(width,float(self.g.fit_width(999)))
        self.assertEqual(self.g.coords(first[0]),[0.0,3.0,width,23.0])
        self.w.mark_set('insert','1.1');self.root.update_idletasks()
        self.assertEqual(self.g.find_withtag('cursor_line'),first)
        self.w.mark_set('insert','2.0');pending=self.g._cursor_after
        self.w.mark_set('insert','3.0');self.assertEqual(self.g._cursor_after,pending)
        self.root.update_idletasks()
        item=self.g.find_withtag('cursor_line')[0]
        self.assertEqual(self.g.coords(item),[0.0,83.0,width,103.0])
        self.assertEqual(len(self.g.find_withtag('mark')),1)
        # 数字は右詰め: 右端から RIGHT_GAP、左は LEFT_PAD 以上
        boxes=[self.g.bbox(i) for i in self.g.find_withtag('num')]
        self.assertTrue(all(b[0]>=self.g.LEFT_PAD-1 for b in boxes),boxes)
        self.assertTrue(all(abs((width-b[2])-self.g.RIGHT_GAP)<=2 for b in boxes),boxes)
        mark=self.g.bbox(self.g.find_withtag('mark')[0])
        self.assertLessEqual(mark[2],self.g.LEFT_PAD)
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
            self.assertEqual(self.g.coords(item),[0.0,3.0,float(self.g['width']),23.0])

    def test_width_follows_digits_and_font_without_clipping(self):
        g=self.g;w=self.w
        import tkinter.font as tkfont
        one=g.fit_width(5);two=g.fit_width(42);three=g.fit_width(999);four=g.fit_width(1200)
        # 1〜999 行は同じ幅（桁が増えても本文が動かない）、4 桁から広がる
        self.assertEqual(one,two);self.assertEqual(two,three);self.assertLess(three,four)
        self.assertEqual(one,g.LEFT_PAD+tkfont.Font(root=self.root,font=g.font).measure('999')+g.RIGHT_GAP)
        # 行が増えると redraw が幅を合わせ、数字はいつも収まる（字も縮めない）
        w.insert('end','\n'+'\n'.join(str(i) for i in range(4,1201)))
        self.geometry={1:(0,3,100,20,15),2:(0,23,100,20,15),3:(0,43,100,20,15)}
        g.redraw()
        self.assertEqual(int(g['width']),four)
        for item in g.find_withtag('num'):
            box=g.bbox(item);self.assertGreaterEqual(box[0],g.LEFT_PAD-1);self.assertLessEqual(box[2],four-g.RIGHT_GAP+1)
        self.assertEqual(tkfont.Font(root=self.root,font=g._number_font(1200,four)).actual('size'),
                         tkfont.Font(root=self.root,font=g.font).actual('size'))
        # 字を大きくしても同じ（_overview_fonts が font を替えて redraw する道）
        big=tkfont.Font(root=self.root,font=g.font);big.configure(size=big.actual('size')*2)
        g.font=big;g.redraw()
        self.assertEqual(int(g['width']),g.fit_width(1200))
        self.assertGreater(int(g['width']),four)
