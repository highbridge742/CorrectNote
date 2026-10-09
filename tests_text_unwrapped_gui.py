# -*- coding: utf-8 -*-
"""Synthetic text only; run on a nonactivated owned desktop, with fake openers."""
import time
import tkinter as tk
import unittest
from unittest.mock import Mock,patch
from analysis_work import observe_text
from text_links import TextLinks


class UnwrappedTextGuiTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.errors=[];self.root.geometry('840x300')
        self.root.report_callback_exception=lambda *error:self.errors.append(error)
        self.text=tk.Text(self.root,undo=True,wrap='char',font=('Consolas',12))
        self.text.pack(fill='both',expand=True);self.opens=Mock();self.edits=Mock()
        observe_text(self.text,on_edit=self.edits)
        self.links=TextLinks(self.text,opener=self.opens);self.root.update()

    def tearDown(self):
        self.root.destroy();self.assertEqual(self.errors,[]);self.opens.assert_not_called()

    def tagged(self,row):
        return TextLinks.UNWRAPPED_TAG in self.text.tag_names(str(row)+'.0')

    def set_text(self,text):
        self.text.delete('1.0','end');self.text.insert('1.0',text)
        self.text.edit_reset();self.text.edit_modified(False);self.root.update()

    def test_data_only_is_synchronous_and_other_wrapping_links_selection_stay_native(self):
        source='  "data:image/png;base64,'+'A'*900+'"  '
        self.text.insert('1.0',source+'\nhttps://example.test/'+('path/'*80)+'\n'+r'C:\folder\note.txt'+'\nordinary words '*40)
        self.assertTrue(self.tagged(1))  # Before any idle redraw.
        self.assertFalse(self.tagged(2));self.assertFalse(self.tagged(3));self.assertFalse(self.tagged(4))
        self.assertEqual(self.text.cget('wrap'),'char')
        self.root.update()
        self.assertIn(TextLinks.TAG,self.text.tag_names('2.0'))
        self.assertIn(TextLinks.TAG,self.text.tag_names('3.0'))
        self.text.tag_add('sel','1.2','1.12');selection=self.text.get('sel.first','sel.last')
        body=self.text.get('1.0','end-1c');self.text.edit_reset();self.text.edit_modified(False);edits=self.edits.call_count
        self.links.changed();self.root.update()
        self.assertEqual(self.text.get('1.0','end-1c'),body)
        self.assertEqual(self.text.get('sel.first','sel.last'),selection)
        self.assertFalse(self.text.edit_modified());self.assertEqual(self.edits.call_count,edits)
        with self.assertRaises(tk.TclError):self.text.edit_undo()

    def test_mixed_short_prose_removes_data_tag_and_plain_length_boundary(self):
        self.set_text('data:,abc')
        self.text.insert('end',' 説明');self.assertFalse(self.tagged(1))
        self.text.delete('1.9','1.end');self.assertTrue(self.tagged(1))
        self.set_text('字'*4000);self.assertFalse(self.tagged(1))
        self.text.insert('end','字');self.assertTrue(self.tagged(1))
        self.text.delete('1.end-1c','1.end');self.assertFalse(self.tagged(1))
        self.assertEqual(self.text.get('1.0','end-1c'),'字'*4000)

    def test_line_split_delete_undo_redo_restore_presentation_before_see(self):
        import text_edit
        self.set_text('x'*4001);self.assertTrue(self.tagged(1))
        self.text.insert('1.2000','\n');self.text.edit_separator()
        self.assertFalse(self.tagged(1));self.assertFalse(self.tagged(2))
        original=text_edit.UnicodeUndoCommand._invoke;seen=[]
        def invoke(command,args):
            if args and args[0]=='see' and command.widget is self.text:
                value=self.text.get('1.0','1.end')
                self.assertEqual(self.tagged(1),len(value)>4000)
                seen.append(args)
            return original(command,args)
        with patch.object(text_edit.UnicodeUndoCommand,'_invoke',invoke):
            self.text.edit_undo();self.assertEqual(self.text.get('1.0','end-1c'),'x'*4001);self.assertTrue(self.tagged(1))
            self.text.edit_redo();self.assertFalse(self.tagged(1));self.assertFalse(self.tagged(2))
        self.assertTrue(seen,'native Undo/Redo must reach see for this boundary')
        self.text.delete('1.0','end');self.assertEqual(self.text.tag_ranges(TextLinks.UNWRAPPED_TAG),())
        self.text.edit_undo();self.assertFalse(self.tagged(1));self.assertFalse(self.tagged(2))

    def test_line_moves_and_projection_rebuild_remove_stale_tags(self):
        self.set_text('data:,abc\nplain\ndata:,def')
        self.text.insert('1.0','heading\n');self.assertFalse(self.tagged(1));self.assertTrue(self.tagged(2));self.assertTrue(self.tagged(4))
        self.text.delete('1.0','3.0');self.assertFalse(self.tagged(1));self.assertTrue(self.tagged(2))
        self.text._correctnote_display_depth=1;edits=self.edits.call_count
        self.text.replace('1.0','end','plain\nhttps://example.test/')
        self.text._correctnote_display_depth=0
        self.assertEqual(self.text.tag_ranges(TextLinks.UNWRAPPED_TAG),());self.assertEqual(self.edits.call_count,edits)
        self.root.update();self.assertIn(TextLinks.TAG,self.text.tag_names('2.0'))

    def test_coalesced_link_refresh_reuses_read_text_and_one_observer(self):
        import text_links
        self.set_text('data:,abc\nhttps://example.test/')
        callbacks=self.text._correctnote_observers;self.assertEqual(callbacks['changed'].count(self.links.changed),1)
        with patch.object(self.text,'get',wraps=self.text.get) as get,patch.object(text_links,'find_links',wraps=text_links.find_links) as find:
            for value in ('x','y','z'):self.text.insert('2.end',value)
            self.assertEqual(get.call_count,3)
            self.root.update();self.assertEqual(get.call_count,3);self.assertEqual(find.call_count,1)
            self.assertEqual(self.links._rows[2][0][2].target,'https://example.test/xyz')
        # Full scan still pending, then local edit: the saved full snapshot must update.
        self.text.insert('1.0','head\n');self.text.insert('3.end','a');self.root.update()
        self.assertEqual(self.links._rows[3][0][2].target,'https://example.test/xyza')
        self.text.destroy();self.assertNotIn(self.links.changed,callbacks['changed'])

    def test_two_panes_36k_resize_to_420_keeps_one_display_line_and_native_drag(self):
        self.text.pack_forget()
        self.root.columnconfigure((0,1),weight=1,uniform='panes');self.root.rowconfigure(0,weight=1)
        self.text.grid(row=0,column=0,sticky='nsew')
        other=tk.Text(self.root,undo=True,wrap='char',font=('Consolas',12));other.grid(row=0,column=1,sticky='nsew')
        links=TextLinks(other,opener=self.opens)
        source='data:image/png;base64,'+'A'*36000
        self.text.insert('1.0',source+'\nnext');other.insert('1.0','文'*36000+'\nnext')
        self.root.update()
        started=time.perf_counter();self.root.geometry('420x300');self.root.update();elapsed=time.perf_counter()-started
        self.assertLess(elapsed,2.0)
        for widget in (self.text,other):
            self.assertTrue(widget.winfo_ismapped());self.assertGreaterEqual(widget.winfo_width(),200)
            self.assertLessEqual(widget.winfo_width(),220)
            self.assertEqual(int(widget.tk.call(widget._w,'count','-displaylines','1.0','2.0')),1)
            self.assertEqual(widget.cget('wrap'),'char')
        self.assertEqual(self.text.get('1.0','1.end'),source)
        self.assertEqual(other.get('1.0','1.end'),'文'*36000)
        a=self.text.bbox('1.2');b=self.text.bbox('1.10');self.assertIsNotNone(a);self.assertIsNotNone(b)
        self.text.event_generate('<ButtonPress-1>',x=a[0]+1,y=a[1]+a[3]//2)
        self.text.event_generate('<B1-Motion>',x=b[0]+1,y=b[1]+b[3]//2,state=0x100)
        self.text.event_generate('<ButtonRelease-1>',x=b[0]+1,y=b[1]+b[3]//2);self.root.update()
        self.assertTrue(self.text.get('sel.first','sel.last'))
        print('36K two-pane resize 840->420 seconds:',round(elapsed,6),flush=True)


if __name__=='__main__':unittest.main()
