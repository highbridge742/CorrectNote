# -*- coding: utf-8 -*-
"""Owned Tk only; synthetic clipboard replacement, no real clipboard or browser."""
from pathlib import Path
import subprocess,sys,tempfile,time,unittest


def redo_tail_child():
    import tkinter as tk
    from text_links import TextLinks
    root=tk.Tk();root.geometry('420x240');errors=[]
    root.report_callback_exception=lambda *e:errors.append(e)
    try:
        for enabled in (False,True):
            for source in ('data:image/png;base64,'+'A'*36000+'==','長'*36000):
                text=tk.Text(root,undo=True,wrap='char',font=('Consolas',12));text.pack(fill='both',expand=True)
                display=TextLinks(text,links=enabled);root.update();text.edit_reset()
                text.insert('1.0',source);text.edit_separator();root.update()
                assert text.tag_ranges(display.ELIDED_TAG)
                started=time.perf_counter();text.edit_undo();root.update();text.edit_redo()
                text.tag_configure('synthetic_underline',underline=True,foreground='#bb6600')
                text.tag_add('synthetic_underline','1.0','end-1c')
                text.mark_set('insert','end-1c');text.see('insert');root.update()
                assert time.perf_counter()-started<2.0
                assert text.get('1.0','end-1c')==source
                assert display.ELIDED_TAG in text.tag_names('1.0+35000c')
                assert text.dlineinfo('1.0')[2]<=display._clip_signature[0]+2
                print('REDO_TAIL_OK',enabled,len(source),text.xview(),round(time.perf_counter()-started,6),flush=True)
                text.destroy();root.update()
    finally:root.destroy()
    assert not errors,errors


class ElidedRowsGuiTests(unittest.TestCase):
    def setUp(self):
        import tkinter as tk
        from text_links import TextLinks
        self.tk=tk;self.root=tk.Tk();self.root.geometry('420x240');self.errors=[]
        self.root.report_callback_exception=lambda *e:self.errors.append(e)
        self.text=tk.Text(self.root,undo=True,wrap='char',font=('Consolas',12),padx=4,pady=4)
        self.text.pack(fill='both',expand=True);self.display=TextLinks(self.text);self.root.update()

    def tearDown(self):self.root.destroy();self.assertEqual(self.errors,[])

    def visible_length(self):
        first=self.text.tag_ranges(self.display.ELIDED_TAG)[0]
        return len(self.text.get('1.0',first))

    def test_native_redo_36k_tail_redraw_finishes_in_bounded_child(self):
        result=subprocess.run([sys.executable,'-B','-X','utf8',str(Path(__file__).resolve()),'--redo-tail'],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',timeout=15)
        print(result.stdout,flush=True);self.assertEqual(result.returncode,0,result.stdout);self.assertEqual(result.stdout.count('REDO_TAIL_OK'),4)

    def test_get_native_copy_and_save_keep_full_emoji_payload_and_selection(self):
        source='😀漢\t'+'abcdefghijklmnopqrstuvwxyz'*1500+'終端'
        self.text.insert('1.0',source);self.root.update();self.text.edit_reset();self.text.edit_modified(False)
        self.assertEqual(self.text.get('1.0','end-1c'),source)
        self.assertIn(self.display.ELIDED_TAG,self.text.tag_names('1.0+30000c'))
        self.text.tag_add('sel','1.0','end-1c')
        self.root.tk.eval('rename clipboard original_clipboard; set fake_copy {}; proc clipboard {args} {if {[lindex $args 0] eq "clear"} {set ::fake_copy {}}; if {[lindex $args 0] eq "append"} {append ::fake_copy [lindex $args end]}}')
        self.root.tk.call('tk_textCopy',self.text._w)
        self.assertEqual(self.root.tk.getvar('fake_copy'),source)
        with tempfile.TemporaryDirectory(prefix='correctnote-elide-save-') as folder:
            f=Path(folder)/'synthetic.txt';f.write_text(self.text.get('1.0','end-1c'),encoding='utf8');self.assertEqual(f.read_text(encoding='utf8'),source)
        self.display.refresh_display();self.assertEqual(self.text.get('sel.first','sel.last'),source)
        self.assertFalse(self.text.edit_modified())
        with self.assertRaises(self.tk.TclError):self.text.edit_undo()

    def test_width_font_tabs_and_emoji_have_bounded_visible_pixels(self):
        self.text.insert('1.0','A'*36000);self.root.update();small=self.visible_length()
        self.text.configure(font=('Consolas',96));self.display.refresh_display();self.root.update();large=self.visible_length()
        self.assertLess(large,small);self.assertLessEqual(self.text.dlineinfo('1.0')[2],self.display._clip_signature[0]+2)
        self.text.configure(font=('Consolas',12));self.display.refresh_display();self.root.update();self.assertEqual(self.visible_length(),small)
        self.root.geometry('220x240');self.root.update();narrow=self.visible_length();self.assertLess(narrow,small)
        self.root.geometry('820x240');self.root.update();self.assertGreater(self.visible_length(),small)
        for tabs in ((),(80,),('100000p',),('120','right')):
            self.text.replace('1.0','end','😀\t'+'漢'*36000);self.text.configure(tabs=tabs);self.display.refresh_display();self.root.update()
            self.assertLessEqual(self.text.dlineinfo('1.0')[2],self.display._clip_signature[0]+2)
            self.assertEqual(self.text.get('1.0','end-1c'),'😀\t'+'漢'*36000)

    def test_shortening_split_and_undo_remove_or_restore_only_presentation(self):
        self.text.insert('1.0','x'*4001);self.root.update();self.text.edit_reset()
        self.text.insert('1.2000','\n');self.text.edit_separator()
        self.assertFalse(self.text.tag_ranges(self.display.ELIDED_TAG));self.assertFalse(self.text.tag_ranges(self.display.UNWRAPPED_TAG))
        self.text.edit_undo();self.assertTrue(self.text.tag_ranges(self.display.ELIDED_TAG));self.root.update()
        self.text.edit_redo();self.assertFalse(self.text.tag_ranges(self.display.ELIDED_TAG));self.root.update()
        self.text.replace('1.0','end','短い通常文\nhttps://example.test/');self.root.update()
        self.assertFalse(self.text.tag_ranges(self.display.ELIDED_TAG));self.assertIn(self.display.TAG,self.text.tag_names('2.0'))

    def test_hidden_rows_skip_link_detection_without_shifting_following_links(self):
        from unittest.mock import patch
        import text_links
        huge='https://large.example.test/'+'a'*20000
        with patch.object(text_links,'find_links',wraps=text_links.find_links) as find:
            self.text.insert('1.0',huge+'\nhttps://normal.example.test/\n'+'長'*6000+'\nC:\\Synthetic\\a.txt');self.root.update()
            self.assertTrue(find.called);self.assertTrue(all(huge not in c.args[0] and '長'*6000 not in c.args[0] for c in find.call_args_list))
            self.assertNotIn(self.display.TAG,self.text.tag_names('1.0'));self.assertIn(self.display.TAG,self.text.tag_names('2.0'));self.assertIn(self.display.TAG,self.text.tag_names('4.0'))
            find.reset_mock();self.text.insert('1.end','x');self.root.update();find.assert_not_called()
            self.text.insert('1.0','heading\n');self.root.update();self.assertEqual(self.display._rows[3][0][2].target,'https://normal.example.test/')
            self.assertEqual(self.display._rows[5][0][2].target,'C:\\Synthetic\\a.txt')

    def test_tail_tag_priority_and_lifecycle_have_no_duplicate_observer(self):
        self.text.insert('1.0','長'*9000);self.root.update()
        self.text.tag_configure('synthetic_visible',elide=False,foreground='red');self.text.tag_add('synthetic_visible','1.0','end')
        self.display.refresh_display()
        self.assertEqual(self.text.tag_names('1.0+8000c')[-1],self.display.ELIDED_TAG)
        self.assertIs(self.text._correctnote_literal_display,self.display)
        callbacks=self.text._correctnote_observers
        self.assertEqual(callbacks['changed'].count(self.display.changed),1)
        self.text.destroy();self.assertNotIn(self.display.changed,callbacks['changed']);self.assertFalse(hasattr(self.text,'_correctnote_literal_display'))


if __name__=='__main__':redo_tail_child() if '--redo-tail' in sys.argv else unittest.main()
