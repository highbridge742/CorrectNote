# -*- coding: utf-8 -*-
"""Actual child-window coordinates must match Text.bbox, including padding."""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from bulk_insert import BulkInsertDialog

class BulkPreviewPositionTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.root.geometry('760x380+0+0');self.errors=[]
        self.root.report_callback_exception=lambda *exc:self.errors.append(str(exc))
        self.editor=tk.Text(self.root,undo=True,wrap='char',font=('Yu Gothic UI',16),
            padx=14,pady=12,borderwidth=0,highlightthickness=0,exportselection=False)
        self.editor.pack(fill='both',expand=True)
        settings={'bulk_insert_direction':'start','bulk_insert_distance':'2','bulk_insert_text':'【確認】'}
        self.a=SimpleNamespace(root=self.root,editor=self.editor,
            settings=SimpleNamespace(get=settings.get,set=lambda k,v:settings.__setitem__(k,v),save=Mock()),
            _set_window_icons_win32=Mock(),_place_dialog=lambda w,x,y:w.geometry('%dx%d+800+0'%(x,y)),
            _forget_bracket_cycle=Mock(),_after_ime_char_insert=Mock(),_pick_mode=False)
        self.dialog=BulkInsertDialog(self.a,lambda:('#fafafa','#222222','#246175'))
        self.dialog.open();self.root.update()

    def tearDown(self):
        self.dialog.close(focus=False)
        # The pre-existing unit-label trace outlives the dialog; release test-owned variables.
        for variable in (self.dialog.direction,self.dialog.distance):
            for modes,ident in variable.trace_info():variable.trace_remove(modes,ident)
        variable=None
        self.root.destroy();self.assertFalse(self.errors)
        from tests_tk_keys import release_tk_fixture
        release_tk_fixture(self,'dialog','a','editor','root')

    def prepare(self,text='前置き：資料を確認する\n会議の要点をまとめる\nノートを開く：後置き',first='1.4',last='3.6',distance=2,direction='start'):
        self.editor.delete('1.0','end');self.editor.insert('1.0',text);self.editor.edit_reset()
        self.editor.tag_add('sel',first,last);self.dialog.direction.set(direction);self.dialog.distance.set(str(distance))
        self.dialog.text.focus_force();self.dialog.queue_preview();self.root.update()

    def measurements(self):
        self.root.update_idletasks();self.assertTrue(self.dialog._preview_points)
        rows=[]
        for marker,(index,x,y,height) in zip(self.dialog._preview_markers,self.dialog._preview_points):
            box=self.editor.bbox(index);self.assertIsNotNone(box)
            expected=(max(0,box[0]-1),box[1],2,box[3])
            actual=(marker.winfo_rootx()-self.editor.winfo_rootx(),marker.winfo_rooty()-self.editor.winfo_rooty(),marker.winfo_width(),marker.winfo_height())
            self.assertEqual((marker.winfo_x(),marker.winfo_y()),actual[:2])
            rows.append(dict(index=self.editor.index(index),expected=expected,actual=actual,
                delta=(actual[0]-expected[0],actual[1]-expected[1])))
        return rows

    def assert_aligned(self):
        for row in self.measurements():self.assertEqual(row['actual'],row['expected'],row)

    def test_padding_border_and_highlight_do_not_shift_real_marker_windows(self):
        for padx,pady,border,highlight in ((14,12,0,0),(0,0,0,0),(7,3,1,2),(0,0,2,3)):
            with self.subTest(padx=padx,pady=pady,border=border,highlight=highlight):
                self.editor.configure(padx=padx,pady=pady,borderwidth=border,highlightthickness=highlight)
                self.prepare();self.assert_aligned()

    def test_direction_unicode_and_selection_edges_preserve_text_and_undo(self):
        text='😀abc\n\n終😀xyz'
        self.prepare(text,'1.0+1c','3.0+2c',1,'end')
        selection=tuple(map(str,self.editor.tag_ranges('sel')))
        for direction,distance in (('end',1),('start',0),('start',99),('end',99)):
            self.dialog.direction.set(direction);self.dialog.distance.set(str(distance));self.root.update();self.assert_aligned()
        self.assertEqual(self.editor.get('1.0','end-1c'),text)
        self.assertEqual(tuple(map(str,self.editor.tag_ranges('sel'))),selection)
        self.assertEqual(self.editor.dump('1.0','end',window=True),[])
        with self.assertRaises(tk.TclError):self.editor.edit_undo()

    def test_wrapping_scrolling_and_resizing_use_current_bbox(self):
        self.root.geometry('430x300+0+0');self.root.update()
        text='\n'.join('資料の確認をします。'*8 for _ in range(30))
        self.prepare(text,'1.0','end-1c',30);self.assert_aligned()
        self.editor.yview_moveto(.45);self.dialog.queue_preview();self.root.update();self.assert_aligned()
        self.root.geometry('700x350+0+0');self.editor.configure(font=('Yu Gothic UI',20))
        self.dialog.queue_preview();self.root.update();self.assert_aligned()

    def test_real_marker_click_forwards_to_text_and_close_destroys_markers(self):
        self.prepare('ABCDE','1.0','1.end',2);self.assert_aligned();marker=self.dialog._preview_markers[0]
        marker.event_generate('<ButtonPress-1>',x=0,y=2,rootx=marker.winfo_rootx(),rooty=marker.winfo_rooty()+2)
        self.root.update();self.assertIs(self.root.focus_get(),self.editor);self.assertFalse(self.dialog._preview_points)
        self.editor.tag_add('sel','1.0','1.end')
        self.dialog.text.focus_force();self.dialog.queue_preview();self.root.update();self.assert_aligned()
        markers=list(self.dialog._preview_markers);self.dialog.close(focus=False);self.root.update_idletasks()
        self.assertFalse(self.dialog._preview_markers);self.assertTrue(all(not m.winfo_exists() for m in markers))

if __name__=='__main__':unittest.main()
