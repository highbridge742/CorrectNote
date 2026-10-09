# -*- coding: utf-8 -*-
"""Run only on the test's nonactivated owned desktop; all openers are mocks."""
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from analysis_work import observe_text
from text_links import TextLinks


class TextLinksGuiTests(unittest.TestCase):
    def setUp(self):
        self.root=tk.Tk();self.errors=[]
        self.root.report_callback_exception=lambda *error:self.errors.append(error)
        self.root.geometry('820x220')
        self.text=tk.Text(self.root,undo=True,wrap='none',font=('Consolas',12));self.text.pack(fill='both',expand=True)
        self.edits=Mock();self.cursor=Mock();self.blocked=False;self.scope=1;self.opens=Mock()
        observe_text(self.text,on_edit=self.edits,on_cursor=self.cursor)
        self.links=TextLinks(self.text,blocked=lambda:self.blocked,scope=lambda:self.scope,opener=self.opens)
        self.text.insert('1.0','😀  https://example.test/資料  後ろ\n'+r'"C:\Program Files\Note\a.txt"'+'\n'+'ordinary\n'*30)
        self.text.edit_reset();self.text.edit_modified(False);self.pump()

    def tearDown(self):
        self.root.destroy();self.assertEqual(self.errors,[])

    def pump(self):self.root.update()

    def point(self,index):
        box=self.text.bbox(index);self.assertIsNotNone(box,index)
        return box[0]+max(1,box[2]//2),box[1]+box[3]//2

    def event(self,sequence,index='1.0+6c',state=0):
        x,y=self.point(index)
        self.text.event_generate(sequence,x=x,y=y,state=state)
        self.pump()

    def test_click_opens_only_at_release_and_does_not_edit_or_record_undo(self):
        source=self.text.get('1.0','end-1c');edits=self.edits.call_count
        ranges=self.text.tag_ranges(TextLinks.TAG)
        self.assertEqual(len(ranges),4)
        # Native Tk 8.6 indices count the supplementary character twice. Do
        # not feed returned numeric indices back as Python-character offsets.
        self.assertEqual(str(ranges[0]),self.text.index('1.0+3c'))
        self.assertEqual(str(ranges[1]),self.text.index('1.0+'+str(3+len('https://example.test/資料'))+'c'))
        self.assertIn(TextLinks.TAG,self.text.tag_names('1.0+3c'))
        self.assertNotIn(TextLinks.TAG,self.text.tag_names('1.0+2c'))
        self.event('<ButtonPress-1>');self.opens.assert_not_called()
        self.event('<ButtonRelease-1>');self.opens.assert_called_once()
        self.assertEqual(self.opens.call_args[0][0].target,'https://example.test/資料')
        self.assertEqual(self.text.get('1.0','end-1c'),source)
        self.assertEqual(self.edits.call_count,edits)
        self.assertFalse(self.text.edit_modified())
        with self.assertRaises(tk.TclError):self.text.edit_undo()
        self.event('<ButtonPress-1>','2.0+4c');self.event('<ButtonRelease-1>','2.0+4c')
        self.assertEqual(self.opens.call_args[0][0].target,r'C:\Program Files\Note\a.txt')

    def test_noop_scroll_sync_and_small_pointer_jitter_keep_click(self):
        self.event('<ButtonPress-1>')
        self.text.yview_moveto(self.text.yview()[0]);self.pump()
        x,y=self.point('1.0+6c')
        self.text.event_generate('<B1-Motion>',x=x+1,y=y,state=0x100)
        self.pump()
        self.text.event_generate('<ButtonRelease-1>',x=x+1,y=y)
        self.pump();self.opens.assert_called_once()

    def test_drag_selects_and_never_opens(self):
        self.event('<ButtonPress-1>')
        self.event('<B1-Motion>','1.0+20c',state=0x100)
        self.event('<ButtonRelease-1>','1.0+20c')
        self.opens.assert_not_called();self.assertTrue(self.text.tag_ranges('sel'))
        self.assertTrue(self.text.get('sel.first','sel.last'))

    def test_existing_pick_modes_and_modified_selection_take_priority(self):
        releases=Mock();self.text.bind('<ButtonRelease-1>',lambda event:releases())
        self.blocked=True
        self.event('<ButtonPress-1>');self.event('<ButtonRelease-1>')
        releases.assert_called_once();self.opens.assert_not_called()
        self.blocked=False
        modifiers=(1,4,0x20000) if self.root.tk.call('tk','windowingsystem')=='win32' else (1,4,8,0x80,0x20000)
        for state in modifiers:
            self.event('<ButtonPress-1>',state=state)
            self.event('<ButtonRelease-1>',state=state)
        self.opens.assert_not_called()

    def test_edit_projection_undo_and_scope_invalidate_old_targets(self):
        self.event('<ButtonPress-1>')
        # Like a tab or corrected display rebuild: no canonical edit callback.
        edits=self.edits.call_count;self.text._correctnote_display_depth=1
        self.text.replace('1.0','1.end','https://new.example.test/')
        self.assertNotIn(TextLinks.TAG,self.text.tag_names('1.0+6c'))
        self.assertIn(TextLinks.TAG,self.text.tag_names('2.0+3c'))
        self.text._correctnote_display_depth=0;self.pump()
        self.assertEqual(self.edits.call_count,edits)
        self.event('<ButtonRelease-1>');self.opens.assert_not_called()
        self.event('<ButtonPress-1>');self.scope=2;self.event('<ButtonRelease-1>')
        self.opens.assert_not_called()
        self.text.edit_undo();self.pump()
        self.assertIn('https://example.test/資料',self.text.get('1.0','end-1c'))
        self.assertTrue(self.text.tag_ranges(TextLinks.TAG))

    def test_scroll_and_line_break_make_press_stale(self):
        # Scrollbar/programmatic scroll out and back must not revive a click,
        # even if the final viewport happens to equal the pressed viewport.
        self.event('<ButtonPress-1>')
        self.text.yview_scroll(1,'units');self.text.yview_moveto(0);self.pump()
        self.event('<ButtonRelease-1>');self.opens.assert_not_called()
        self.event('<ButtonPress-1>');self.text.yview_scroll(1,'units');self.pump()
        # Same coordinates now point at a different line.
        x,y=self.point('2.0+4c')
        self.links.release(SimpleNamespace(x=x,y=y,state=0));self.opens.assert_not_called()
        self.text.yview_moveto(0);self.pump();self.event('<ButtonPress-1>')
        self.text.insert('1.0','\n');self.pump();self.event('<ButtonRelease-1>','2.0+6c')
        self.opens.assert_not_called()
        ranges=self.text.tag_ranges(TextLinks.TAG)
        self.assertTrue(str(ranges[0]).startswith('2.'))

    def test_theme_destroy_and_error_are_local(self):
        self.links.set_dark(True);self.assertEqual(self.text.tag_cget(TextLinks.TAG,'foreground'),'#78b9ff')
        self.links.set_dark(False);self.assertEqual(self.text.tag_cget(TextLinks.TAG,'foreground'),'#065dcc')
        error=Mock();self.links.on_error=error;self.links.opener=Mock(side_effect=OSError('missing'))
        self.event('<ButtonPress-1>');self.event('<ButtonRelease-1>');error.assert_called_once()
        self.text.insert('end','x');self.text.destroy();self.pump()
        self.assertTrue(self.links._destroyed);self.assertIsNone(self.links._pending)

    def test_local_edit_keeps_other_rows_and_bounds_rescan_work(self):
        import text_links
        # Preserve a second-row path while edits change URL length in row 1.
        old=self.links._rows[2][0][2].target
        with patch.object(text_links,'find_links',wraps=text_links.find_links) as detector:
            self.text.insert('1.0','一');self.pump()
            self.assertEqual(detector.call_count,1)
            self.assertNotIn('\n',detector.call_args[0][0])
            self.assertEqual(self.links._rows[2][0][2].target,old)
            self.assertIn(TextLinks.TAG,self.text.tag_names('2.0+3c'))
            self.text.delete('1.0','1.0+1c');self.pump()
            self.assertNotIn('\n',detector.call_args[0][0])
            self.text.replace('1.0+3c','1.0+8c','https');self.pump()
            self.assertNotIn('\n',detector.call_args[0][0])
            # A multi-line replace can preserve total line count but still
            # changes several rows; it must not take the single-row shortcut.
            self.text.replace('1.0','2.end','first\nhttps://replacement.test/');self.pump()
            self.assertIn('\n',detector.call_args[0][0])
            self.assertNotIn(1,self.links._rows)
            self.assertEqual(self.links._rows[2][0][2].target,'https://replacement.test/')

    def test_end_append_and_consumed_selection_aliases_have_current_ranges(self):
        self.text.insert('end','https://append.test/path');self.pump()
        row=int(self.text.index('end-1c').split('.')[0])
        self.assertEqual(self.links._rows[row][0][2].target,'https://append.test/path')
        self.text.tag_add('sel',f'{row}.0+8c',f'{row}.0+10c')
        self.text.delete('sel.first','sel.last');self.pump()
        self.assertEqual(self.links._rows[row][0][2].target,self.text.get(f'{row}.0',f'{row}.end'))
        self.text.tag_add('sel',f'{row}.0+8c',f'{row}.0+10c')
        self.text.replace('sel.first','sel.last','new');self.pump()
        self.assertEqual(self.links._rows[row][0][2].target,self.text.get(f'{row}.0',f'{row}.end'))



class TextLinksLifecycleTests(unittest.TestCase):
    def test_bind_class_cleanup_across_tkinter_ownership_versions(self):
        # CPython 3.9 did not track class commands; 3.11 tracks them on root.
        # Exercise both registration contracts with real Tcl commands and
        # destruction, including the links=False long-line display lifecycle.
        for tracked in (False,True):
            with self.subTest(root_tracks_class_commands=tracked):
                def bind_class(widget,tag,sequence=None,func=None,add=None):
                    owner=widget._root() if tracked else widget
                    return owner._bind(('bind',tag),sequence,func,add,tracked)
                root=tk.Tk();root.withdraw();errors=[]
                root.report_callback_exception=lambda *exc:errors.append(exc)
                try:
                    with patch.object(tk.Misc,'bind_class',bind_class):
                        survivor=tk.Text(root);survivor.pack();root.deiconify();survived=Mock()
                        survivor.bind('<<StillAlive>>',lambda event:survived())
                        root.update()
                        for enabled in (True,False,True):
                            top=tk.Toplevel(root);text=tk.Text(top)
                            controller=TextLinks(text,links=enabled,opener=Mock())
                            commands=tuple(controller._bindings.values())
                            text.insert('1.0','https://example.test/')
                            top.destroy()
                            controller.destroy(SimpleNamespace(widget=text))
                            self.assertTrue(controller._destroyed)
                            for command in commands:
                                self.assertFalse(root.tk.call('info','commands',command))
                                self.assertNotIn(command,root._tclCommands or ())
                        survivor.event_generate('<<StillAlive>>')
                        self.assertEqual(survived.call_count,1)
                        self.assertEqual(errors,[])
                finally:
                    root.destroy()


if __name__=='__main__':unittest.main()
